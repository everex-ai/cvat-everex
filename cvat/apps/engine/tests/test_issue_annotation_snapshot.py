# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Model-level tests for IssueAnnotationSnapshot (plan U1).

Covers the two behaviours the schema deliberately guarantees:
  * multiple snapshot rows may coexist for one issue (one ``before`` plus one
    ``after`` per resolve transition — no uniqueness constraint), and
  * snapshots are removed by CASCADE when their issue (or the owning job) goes
    away, so they never outlive the annotation context they describe.

The migration-integrity check (``makemigrations --check``) is run separately in
CI / by the developer; it is not expressed as a unit test here.
"""

from django.test import TestCase

from cvat.apps.engine.models import (
    IssueAnnotationSnapshot,
    IssueSnapshotTrigger,
    Issue,
    Job,
    Segment,
    Task,
)


class IssueAnnotationSnapshotModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.task = Task.objects.create(name="snapshot-test", mode="annotation")
        cls.segment = Segment.objects.create(task=cls.task, start_frame=0, stop_frame=5)
        cls.job = Job.objects.create(segment=cls.segment)
        cls.issue = Issue.objects.create(
            job=cls.job, frame=0, position=[0.0, 0.0, 10.0, 10.0]
        )

    def _snapshot(self, issue, trigger, frame=0, data=None):
        return IssueAnnotationSnapshot.objects.create(
            issue=issue,
            job=issue.job,
            trigger=trigger,
            frame=frame,
            data=data if data is not None else {"frame": frame, "objects": []},
        )

    def test_multiple_rows_per_issue(self):
        # One `before` plus two `after` rows (reopen -> re-resolve) coexist.
        self._snapshot(self.issue, IssueSnapshotTrigger.BEFORE)
        self._snapshot(self.issue, IssueSnapshotTrigger.AFTER)
        self._snapshot(self.issue, IssueSnapshotTrigger.AFTER)

        self.assertEqual(self.issue.annotation_snapshots.count(), 3)
        self.assertEqual(
            self.issue.annotation_snapshots.filter(
                trigger=IssueSnapshotTrigger.AFTER
            ).count(),
            2,
        )

    def test_json_data_round_trips(self):
        payload = {
            "frame": 0,
            "objects": [{"id": 7, "type": "skeleton", "label": "person"}],
        }
        snap = self._snapshot(self.issue, IssueSnapshotTrigger.BEFORE, data=payload)
        snap.refresh_from_db()
        self.assertEqual(snap.data, payload)
        self.assertEqual(snap.trigger, "before")

    def test_cascade_on_issue_delete(self):
        self._snapshot(self.issue, IssueSnapshotTrigger.BEFORE)
        self._snapshot(self.issue, IssueSnapshotTrigger.AFTER)
        self.assertEqual(IssueAnnotationSnapshot.objects.count(), 2)

        self.issue.delete()

        self.assertEqual(IssueAnnotationSnapshot.objects.count(), 0)

    def test_cascade_on_job_delete(self):
        issue = Issue.objects.create(
            job=self.job, frame=1, position=[0.0, 0.0, 5.0, 5.0]
        )
        self._snapshot(issue, IssueSnapshotTrigger.BEFORE, frame=1)
        self.assertEqual(IssueAnnotationSnapshot.objects.count(), 1)

        self.job.delete()

        self.assertEqual(IssueAnnotationSnapshot.objects.count(), 0)
