# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Tests for the enqueue/worker glue and the IssueViewSet capture hook (plan U3).

Only the ``before`` side exists: ``IssueViewSet.perform_create`` schedules a
``before`` snapshot on issue creation (the ephemeral problematic state). The good
state is durable and read live at export, so nothing is captured at resolve, save,
or job completion. Plus the worker entry + enqueue helpers — queue targeting and
failure isolation (plan R8).
"""

from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from cvat.apps.engine import models
from cvat.apps.engine.issue_snapshots import enqueue_issue_snapshot, run_issue_snapshot_capture
from cvat.apps.engine.models import IssueAnnotationSnapshot, IssueSnapshotTrigger
from cvat.apps.engine.serializers import IssueWriteSerializer
from cvat.apps.engine.tests.test_issue_snapshots_capture import _make_job
from cvat.apps.engine.views import IssueViewSet

_ENQUEUE = "cvat.apps.engine.issue_snapshots.enqueue_issue_snapshot"
_GET_QUEUE = "cvat.apps.engine.issue_snapshots.django_rq.get_queue"


class IssueSnapshotWorkerTest(TestCase):
    def test_run_capture_invokes_capture(self):
        with mock.patch("cvat.apps.engine.issue_snapshots.capture_issue_snapshot") as capture:
            run_issue_snapshot_capture(42, IssueSnapshotTrigger.BEFORE)
        capture.assert_called_once_with(42, IssueSnapshotTrigger.BEFORE)

    def test_run_capture_isolates_exceptions(self):
        with mock.patch(
            "cvat.apps.engine.issue_snapshots.capture_issue_snapshot",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise — a capture failure cannot escalate to the worker.
            self.assertIsNone(run_issue_snapshot_capture(42, IssueSnapshotTrigger.BEFORE))

    def test_enqueue_before_targets_notifications_queue(self):
        with mock.patch(_GET_QUEUE) as get_queue:
            queue = get_queue.return_value
            enqueue_issue_snapshot(7, IssueSnapshotTrigger.BEFORE)
        get_queue.assert_called_once_with("notifications")
        queue.enqueue.assert_called_once_with(
            run_issue_snapshot_capture, 7, IssueSnapshotTrigger.BEFORE
        )

    def test_enqueue_before_isolates_failure(self):
        with mock.patch(_GET_QUEUE, side_effect=ConnectionError("no redis")):
            # Enqueue failure must not break issue creation.
            self.assertIsNone(enqueue_issue_snapshot(7, IssueSnapshotTrigger.BEFORE))


class IssueSnapshotHookTest(TestCase):
    """A `before` is scheduled on issue creation and on every reopen (resolved
    true -> false), and on nothing else — resolves and no-op updates schedule
    nothing (the good state is durable, read live at export)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.User.objects.create_user(username="rev", password="x")
        cls.task = models.Task.objects.create(name="hook-test", mode="annotation")
        cls.segment = models.Segment.objects.create(task=cls.task, start_frame=0, stop_frame=5)
        cls.job = models.Job.objects.create(segment=cls.segment, type=models.JobType.ANNOTATION)

    def _view(self):
        view = IssueViewSet()
        view.request = SimpleNamespace(user=self.user)
        return view

    def _issue(self, resolved):
        return models.Issue.objects.create(
            job=self.job, frame=0, position=[0.0, 0.0, 1.0, 1.0], resolved=resolved
        )

    def _perform_update(self, issue, resolved):
        serializer = IssueWriteSerializer(instance=issue, data={"resolved": resolved}, partial=True)
        serializer.is_valid(raise_exception=True)
        with mock.patch(_ENQUEUE) as enq:
            with self.captureOnCommitCallbacks(execute=True):
                self._view().perform_update(serializer)
        return enq

    def test_create_schedules_before(self):
        serializer = IssueWriteSerializer(
            data={
                "job": self.job.id,
                "frame": 0,
                "position": [0.0, 0.0, 1.0, 1.0],
                "message": "bad keypoints",
            }
        )
        serializer.is_valid(raise_exception=True)
        with mock.patch(_ENQUEUE) as enq:
            with self.captureOnCommitCallbacks(execute=True):
                self._view().perform_create(serializer)
        enq.assert_called_once_with(serializer.instance.id, IssueSnapshotTrigger.BEFORE)

    def test_reopen_schedules_before(self):
        issue = self._issue(resolved=True)
        self._perform_update(issue, resolved=False).assert_called_once_with(
            issue.id, IssueSnapshotTrigger.BEFORE
        )

    def test_resolve_does_not_schedule(self):
        issue = self._issue(resolved=False)
        self._perform_update(issue, resolved=True).assert_not_called()

    def test_stay_resolved_does_not_schedule(self):
        issue = self._issue(resolved=True)
        self._perform_update(issue, resolved=True).assert_not_called()

    def test_each_reopen_captures_again(self):
        # resolve -> reopen -> re-resolve -> reopen: a `before` on each reopen only.
        issue = self._issue(resolved=True)
        self._perform_update(issue, resolved=False).assert_called_once_with(
            issue.id, IssueSnapshotTrigger.BEFORE
        )  # reopen 1
        issue.refresh_from_db()
        self._perform_update(issue, resolved=True).assert_not_called()  # re-resolve
        issue.refresh_from_db()
        self._perform_update(issue, resolved=False).assert_called_once_with(
            issue.id, IssueSnapshotTrigger.BEFORE
        )  # reopen 2


class _SyncQueue:
    """Stand-in for the RQ queue that runs the job inline, so a test drives the
    real enqueue -> worker -> capture chain without a live Redis/worker."""

    def enqueue(self, func, *args, **kwargs):
        return func(*args)


class IssueSnapshotEndToEndTest(TestCase):
    """Unmocked wiring: perform_create / perform_update -> on_commit -> enqueue ->
    (inline) run_issue_snapshot_capture -> a persisted ``before`` snapshot row.
    Only the queue transport is stubbed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.User.objects.create_user(username="e2e", password="x")

    def _view(self):
        view = IssueViewSet()
        view.request = SimpleNamespace(user=self.user)
        return view

    def _run_inline(self, perform):
        with mock.patch(_GET_QUEUE, return_value=_SyncQueue()):
            with self.captureOnCommitCallbacks(execute=True):
                perform()

    def test_create_persists_before_snapshot(self):
        _, job, _ = _make_job()
        serializer = IssueWriteSerializer(
            data={
                "job": job.id,
                "frame": 1,
                "position": [0.0, 0.0, 1.0, 1.0],
                "message": "bad keypoints",
            }
        )
        serializer.is_valid(raise_exception=True)
        view = self._view()
        self._run_inline(lambda: view.perform_create(serializer))
        self.assertEqual(
            IssueAnnotationSnapshot.objects.filter(
                issue=serializer.instance, trigger=IssueSnapshotTrigger.BEFORE
            ).count(),
            1,
        )

    def test_reopen_persists_another_before_snapshot(self):
        _, job, _ = _make_job()
        issue = models.Issue.objects.create(
            job=job, frame=1, position=[0.0, 0.0, 1.0, 1.0], resolved=True
        )
        serializer = IssueWriteSerializer(instance=issue, data={"resolved": False}, partial=True)
        serializer.is_valid(raise_exception=True)
        view = self._view()
        self._run_inline(lambda: view.perform_update(serializer))
        self.assertEqual(
            IssueAnnotationSnapshot.objects.filter(
                issue=issue, trigger=IssueSnapshotTrigger.BEFORE
            ).count(),
            1,
        )
