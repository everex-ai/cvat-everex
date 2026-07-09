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


class _SyncQueue:
    """Stand-in for the RQ queue that runs the job inline, so a test drives the
    real enqueue -> worker -> capture chain without a live Redis/worker."""

    def enqueue(self, func, *args, **kwargs):
        return func(*args)


class IssueCreateEndToEndTest(TestCase):
    """Unmocked wiring: perform_create -> on_commit -> enqueue -> (inline)
    run_issue_snapshot_capture -> a persisted ``before`` snapshot row. Only the
    queue transport is stubbed."""

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
