# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Tests for the enqueue/worker glue and IssueViewSet capture hooks (plan U3).

Two layers:
  * the worker entry + enqueue helpers, verified with mocks — correct queue
    targeting, argument passing, and failure isolation (plan R8); and
  * the IssueViewSet ``perform_create`` / ``perform_update`` transition logic,
    driven through the real viewset + serializer with the enqueue mocked, so we
    assert exactly when a snapshot is scheduled: on create (``before``) and on
    each ``resolved`` false->true transition (``after``), and never otherwise.
"""

from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from cvat.apps.engine import models
from cvat.apps.engine.issue_snapshots import (
    capture_issue_snapshot,
    enqueue_issue_snapshot,
    enqueue_job_after_snapshots,
    run_issue_snapshot_capture,
    run_job_after_snapshots,
    schedule_job_after_snapshots,
)
from cvat.apps.engine.models import IssueAnnotationSnapshot, IssueSnapshotTrigger
from cvat.apps.engine.serializers import IssueWriteSerializer
from cvat.apps.engine.tests.test_issue_snapshots_capture import _make_job
from cvat.apps.engine.views import IssueViewSet

_ENQUEUE = "cvat.apps.engine.issue_snapshots.enqueue_issue_snapshot"


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
            self.assertIsNone(run_issue_snapshot_capture(42, IssueSnapshotTrigger.AFTER))

    def test_enqueue_targets_notifications_queue(self):
        with mock.patch("cvat.apps.engine.issue_snapshots.django_rq.get_queue") as get_queue:
            queue = get_queue.return_value
            enqueue_issue_snapshot(7, IssueSnapshotTrigger.BEFORE)
        get_queue.assert_called_once_with("notifications")
        queue.enqueue.assert_called_once_with(
            run_issue_snapshot_capture, 7, IssueSnapshotTrigger.BEFORE
        )

    def test_enqueue_isolates_failure(self):
        with mock.patch(
            "cvat.apps.engine.issue_snapshots.django_rq.get_queue",
            side_effect=ConnectionError("no redis"),
        ):
            # Enqueue failure must not break issue create/resolve.
            self.assertIsNone(enqueue_issue_snapshot(7, IssueSnapshotTrigger.AFTER))

    def test_enqueue_job_after_targets_notifications_queue(self):
        with mock.patch("cvat.apps.engine.issue_snapshots.django_rq.get_queue") as get_queue:
            queue = get_queue.return_value
            enqueue_job_after_snapshots(11)
        get_queue.assert_called_once_with("notifications")
        queue.enqueue.assert_called_once_with(run_job_after_snapshots, 11)

    def test_enqueue_job_after_isolates_failure(self):
        with mock.patch(
            "cvat.apps.engine.issue_snapshots.django_rq.get_queue",
            side_effect=ConnectionError("no redis"),
        ):
            # A save must not fail because snapshot enqueue is down.
            self.assertIsNone(enqueue_job_after_snapshots(11))


class IssueViewSetSnapshotHookTest(TestCase):
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

    def _issue(self, resolved=False):
        return models.Issue.objects.create(
            job=self.job, frame=0, position=[0.0, 0.0, 1.0, 1.0], resolved=resolved
        )

    def _perform_update(self, issue, resolved):
        """Run perform_update with the enqueue mocked; return the mock."""
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

    def test_resolve_schedules_after(self):
        issue = self._issue(resolved=False)
        enq = self._perform_update(issue, resolved=True)
        enq.assert_called_once_with(issue.id, IssueSnapshotTrigger.AFTER)

    def test_non_transition_update_does_not_schedule(self):
        issue = self._issue(resolved=False)
        enq = self._perform_update(issue, resolved=False)  # stays open
        enq.assert_not_called()

    def test_already_resolved_update_does_not_schedule(self):
        issue = self._issue(resolved=True)
        enq = self._perform_update(issue, resolved=True)  # true -> true
        enq.assert_not_called()

    def test_reopen_then_reresolve_schedules_after_each_time(self):
        # AE3: resolve -> reopen -> re-resolve captures an `after` on each resolve.
        issue = self._issue(resolved=False)

        self._perform_update(issue, resolved=True).assert_called_once_with(
            issue.id, IssueSnapshotTrigger.AFTER
        )
        issue.refresh_from_db()

        self._perform_update(issue, resolved=False).assert_not_called()  # reopen
        issue.refresh_from_db()

        self._perform_update(issue, resolved=True).assert_called_once_with(
            issue.id, IssueSnapshotTrigger.AFTER
        )


class _SyncQueue:
    """Stand-in for the RQ queue that runs the job inline, so the test drives the
    real enqueue_issue_snapshot -> run_issue_snapshot_capture -> capture chain
    without a live Redis/worker (the RQ transport itself is out of scope here)."""

    def enqueue(self, func, *args, **kwargs):
        return func(*args)


class IssueSnapshotEndToEndTest(TestCase):
    """Unmocked wiring: perform_create/update -> transaction.on_commit ->
    enqueue_issue_snapshot -> (inline) run_issue_snapshot_capture -> capture ->
    a persisted IssueAnnotationSnapshot row. Uses a data-backed job so capture
    actually reaches build_snapshot_data; only the queue transport is stubbed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.User.objects.create_user(username="e2e", password="x")

    def _view(self):
        view = IssueViewSet()
        view.request = SimpleNamespace(user=self.user)
        return view

    def _run_inline(self, perform):
        with mock.patch(
            "cvat.apps.engine.issue_snapshots.django_rq.get_queue",
            return_value=_SyncQueue(),
        ):
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

    def test_resolve_persists_after_snapshot(self):
        _, job, _ = _make_job()
        issue = models.Issue.objects.create(
            job=job, frame=1, position=[0.0, 0.0, 1.0, 1.0], resolved=False
        )
        serializer = IssueWriteSerializer(instance=issue, data={"resolved": True}, partial=True)
        serializer.is_valid(raise_exception=True)
        view = self._view()
        self._run_inline(lambda: view.perform_update(serializer))
        self.assertEqual(
            IssueAnnotationSnapshot.objects.filter(
                issue=issue, trigger=IssueSnapshotTrigger.AFTER
            ).count(),
            1,
        )


class SaveAfterSnapshotEndToEndTest(TestCase):
    """The resolve-before-save fix: an issue resolved before the corrected
    geometry is saved gets a stale resolve-time `after`; the subsequent annotation
    save must append a fresh `after` reflecting the persisted correction. Drives
    schedule_job_after_snapshots -> on_commit -> enqueue -> run_job_after_snapshots
    with only the queue transport stubbed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.User.objects.create_user(username="save-e2e", password="x")

    def _run_inline(self, fn):
        with mock.patch(
            "cvat.apps.engine.issue_snapshots.django_rq.get_queue",
            return_value=_SyncQueue(),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                fn()

    def test_save_after_resolve_refreshes_after(self):
        _, job, labels = _make_job(label_names=("car",))
        shape = models.LabeledShape.objects.create(
            job=job,
            label=labels["car"],
            frame=1,
            type="rectangle",
            points=[1.0, 1.0, 2.0, 2.0],
            source="manual",
        )
        issue = models.Issue.objects.create(
            job=job, frame=1, position=[0.0, 0.0, 5.0, 5.0], resolved=True
        )
        # Resolve-before-save: the resolve-time `after` froze the pre-fix geometry.
        capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.AFTER)
        stale = IssueAnnotationSnapshot.objects.filter(issue=issue, trigger="after").latest("id")
        self.assertEqual(stale.data["objects"][0]["points"], [1.0, 1.0, 2.0, 2.0])

        # The fix is saved (the shape moves); the annotation-save hook fires.
        models.LabeledShape.objects.filter(pk=shape.pk).update(points=[8.0, 8.0, 10.0, 10.0])
        self._run_inline(lambda: schedule_job_after_snapshots(job.id))

        afters = IssueAnnotationSnapshot.objects.filter(issue=issue, trigger="after").order_by("id")
        self.assertEqual(afters.count(), 2)
        self.assertEqual(afters.last().data["objects"][0]["points"], [8.0, 8.0, 10.0, 10.0])
