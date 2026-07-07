# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Tests for the enqueue/worker glue and the viewset capture hooks (plan U3).

Two capture points, driven through the real viewsets + serializers so we assert
exactly when a snapshot is scheduled:
  * ``IssueViewSet.perform_create`` schedules a ``before`` on issue creation; and
  * ``JobViewSet.perform_update`` schedules the job's ``after`` capture the first
    time the job reaches the accepted state (``stage=acceptance`` &
    ``state=completed``); a reject -> re-accept schedules again, and no other job
    update does.
Plus the worker entry + enqueue helpers — queue targeting and failure isolation
(plan R8).
"""

from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

from cvat.apps.engine import models
from cvat.apps.engine.issue_snapshots import (
    enqueue_issue_snapshot,
    enqueue_job_acceptance_snapshots,
    run_issue_snapshot_capture,
    run_job_acceptance_snapshots,
)
from cvat.apps.engine.models import IssueAnnotationSnapshot, IssueSnapshotTrigger
from cvat.apps.engine.serializers import IssueWriteSerializer, JobWriteSerializer
from cvat.apps.engine.tests.test_issue_snapshots_capture import _make_job
from cvat.apps.engine.views import IssueViewSet, JobViewSet

_ENQUEUE = "cvat.apps.engine.issue_snapshots.enqueue_issue_snapshot"
_VIEWS_ACCEPT = "cvat.apps.engine.views.schedule_job_acceptance_snapshots"
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
            self.assertIsNone(run_issue_snapshot_capture(42, IssueSnapshotTrigger.AFTER))

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

    def test_enqueue_acceptance_targets_notifications_queue(self):
        with mock.patch(_GET_QUEUE) as get_queue:
            queue = get_queue.return_value
            enqueue_job_acceptance_snapshots(11)
        get_queue.assert_called_once_with("notifications")
        queue.enqueue.assert_called_once_with(run_job_acceptance_snapshots, 11)

    def test_enqueue_acceptance_isolates_failure(self):
        with mock.patch(_GET_QUEUE, side_effect=ConnectionError("no redis")):
            # A job accept must not fail because snapshot enqueue is down.
            self.assertIsNone(enqueue_job_acceptance_snapshots(11))


class IssueCreateSnapshotHookTest(TestCase):
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


class JobAcceptanceHookTest(TestCase):
    """JobViewSet.perform_update schedules the acceptance capture exactly on the
    first transition into stage=acceptance & state=completed."""

    def setUp(self):
        self.user = models.User.objects.create_user(username="jrev", password="x")
        _, self.job, _ = _make_job()

    def _view(self):
        view = JobViewSet()
        view.request = SimpleNamespace(user=self.user)
        return view

    def _update(self, **data):
        serializer = JobWriteSerializer(instance=self.job, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        with mock.patch(_VIEWS_ACCEPT) as sched:
            self._view().perform_update(serializer)
        return sched

    def test_acceptance_schedules_capture(self):
        self._update(stage="acceptance", state="completed").assert_called_once_with(self.job.id)

    def test_plain_state_update_does_not_schedule(self):
        self._update(state="in progress").assert_not_called()

    def test_acceptance_stage_without_completed_does_not_schedule(self):
        # Changing stage alone resets state to `new`, so the job is not accepted yet.
        self._update(stage="acceptance").assert_not_called()

    def test_already_accepted_update_does_not_schedule(self):
        self._update(stage="acceptance", state="completed")  # first accept
        self.job.refresh_from_db()
        self._update(state="completed").assert_not_called()  # no fresh transition


class _SyncQueue:
    """Stand-in for the RQ queue that runs the job inline, so a test drives the
    real enqueue -> worker -> capture chain without a live Redis/worker."""

    def enqueue(self, func, *args, **kwargs):
        return func(*args)


class IssueCreateEndToEndTest(TestCase):
    """Unmocked wiring for the ``before`` side: perform_create -> on_commit ->
    enqueue -> (inline) run_issue_snapshot_capture -> a persisted snapshot row."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.User.objects.create_user(username="e2e", password="x")

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
        view = IssueViewSet()
        view.request = SimpleNamespace(user=self.user)
        self._run_inline(lambda: view.perform_create(serializer))
        self.assertEqual(
            IssueAnnotationSnapshot.objects.filter(
                issue=serializer.instance, trigger=IssueSnapshotTrigger.BEFORE
            ).count(),
            1,
        )


class AcceptanceSnapshotEndToEndTest(TestCase):
    """Unmocked wiring for the ``after`` side: accepting the job through the real
    JobViewSet -> on_commit -> enqueue -> (inline) run_job_acceptance_snapshots ->
    one persisted ``after`` per issue on the job. Only the queue is stubbed."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.User.objects.create_user(username="acc-e2e", password="x")

    def _run_inline(self, fn):
        with mock.patch(_GET_QUEUE, return_value=_SyncQueue()):
            with self.captureOnCommitCallbacks(execute=True):
                fn()

    def test_accept_persists_after_for_each_issue(self):
        _, job, labels = _make_job(label_names=("car",))
        models.LabeledShape.objects.create(
            job=job,
            label=labels["car"],
            frame=1,
            type="rectangle",
            points=[1.0, 1.0, 2.0, 2.0],
            source="manual",
        )
        i1 = models.Issue.objects.create(job=job, frame=1, position=[0.0, 0.0, 5.0, 5.0])
        i2 = models.Issue.objects.create(job=job, frame=2, position=[0.0, 0.0, 5.0, 5.0])

        serializer = JobWriteSerializer(
            instance=job, data={"stage": "acceptance", "state": "completed"}, partial=True
        )
        serializer.is_valid(raise_exception=True)
        view = JobViewSet()
        view.request = SimpleNamespace(user=self.user)
        self._run_inline(lambda: view.perform_update(serializer))

        for issue in (i1, i2):
            self.assertEqual(
                IssueAnnotationSnapshot.objects.filter(
                    issue=issue, trigger=IssueSnapshotTrigger.AFTER
                ).count(),
                1,
            )
