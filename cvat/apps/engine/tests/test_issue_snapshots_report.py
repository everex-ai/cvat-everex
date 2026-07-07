# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Tests for the issue_snapshots_report management command (plan U4)."""

import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from cvat.apps.engine import models
from cvat.apps.engine.models import IssueAnnotationSnapshot, IssueSnapshotTrigger


def _run(**kwargs) -> str:
    out = io.StringIO()
    call_command("issue_snapshots_report", stdout=out, **kwargs)
    return out.getvalue()


class IssueSnapshotsReportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.task = models.Task.objects.create(name="report-test", mode="annotation")
        cls.segment = models.Segment.objects.create(task=cls.task, start_frame=0, stop_frame=5)
        cls.job = models.Job.objects.create(segment=cls.segment, type=models.JobType.ANNOTATION)

    def _issue(self, frame=0):
        return models.Issue.objects.create(job=self.job, frame=frame, position=[0.0, 0.0, 1.0, 1.0])

    def _snap(self, issue, trigger, objects):
        return IssueAnnotationSnapshot.objects.create(
            issue=issue,
            job=issue.job,
            trigger=trigger,
            frame=issue.frame,
            data={"frame": issue.frame, "objects": objects},
        )

    def test_summary_empty(self):
        out = _run()
        self.assertIn("IssueAnnotationSnapshot rows: 0", out)

    def test_summary_aggregates_triggers_and_pairs(self):
        paired = self._issue(frame=0)
        self._snap(paired, IssueSnapshotTrigger.BEFORE, [])
        self._snap(paired, IssueSnapshotTrigger.AFTER, [])
        self._snap(paired, IssueSnapshotTrigger.AFTER, [])  # reject -> re-accept

        before_only = self._issue(frame=1)
        self._snap(before_only, IssueSnapshotTrigger.BEFORE, [])

        out = _run()
        self.assertIn("IssueAnnotationSnapshot rows: 4", out)
        self.assertIn("before: 2", out)
        self.assertIn("after: 2", out)
        self.assertIn(f"job {self.job.id}: 2/2", out)
        self.assertIn("2 total, 1 with before+after, 1 before-only, 0 after-only", out)

    def test_job_filter_restricts_scope(self):
        issue = self._issue()
        self._snap(issue, IssueSnapshotTrigger.BEFORE, [])
        out = _run(job=999999)  # no snapshots for this job
        self.assertIn("IssueAnnotationSnapshot rows: 0 (job 999999)", out)

    def test_issue_dump_matches_and_flags_unmatched(self):
        issue = self._issue()
        skeleton_before = {
            "id": 1,
            "type": "skeleton",
            "label": "face",
            "elements": [
                {"id": 11, "type": "points", "label": "left_eye", "outside": False},
                {"id": 12, "type": "points", "label": "right_eye", "outside": True},
            ],
        }
        rect = {"id": 2, "type": "rectangle", "label": "car", "points": [0, 0, 10, 10]}
        skeleton_after = {
            "id": 1,
            "type": "skeleton",
            "label": "face",
            "elements": [
                {"id": 11, "type": "points", "label": "left_eye", "outside": False},
                {"id": 12, "type": "points", "label": "right_eye", "outside": False},
            ],
        }
        self._snap(issue, IssueSnapshotTrigger.BEFORE, [skeleton_before, rect])
        self._snap(issue, IssueSnapshotTrigger.AFTER, [skeleton_after])  # rect dropped

        out = _run(issue=issue.id)
        self.assertIn(f"Issue {issue.id}: 1 before, 1 after (after_count=1)", out)
        self.assertIn("shape#1", out)  # skeleton matched
        self.assertIn("kpts=1/2", out)  # before: 1 visible keypoint
        self.assertIn("kpts=2/2", out)  # after: 2 visible keypoints
        self.assertIn("shape#2", out)  # rectangle only in before
        self.assertIn("<UNMATCHED>", out)

    def test_issue_dump_delta_reports_moved_keypoints(self):
        issue = self._issue()
        before = {
            "id": 1,
            "type": "skeleton",
            "label": "person",
            "elements": [
                {"id": 11, "type": "points", "label": "nose", "points": [10.0, 10.0]},
                {"id": 12, "type": "points", "label": "chin", "points": [20.0, 20.0]},
            ],
        }
        after = {
            "id": 1,
            "type": "skeleton",
            "label": "person",
            "elements": [
                {"id": 11, "type": "points", "label": "nose", "points": [10.0, 10.0]},  # unchanged
                {"id": 12, "type": "points", "label": "chin", "points": [55.0, 60.0]},  # moved
            ],
        }
        self._snap(issue, IssueSnapshotTrigger.BEFORE, [before])
        self._snap(issue, IssueSnapshotTrigger.AFTER, [after])
        out = _run(issue=issue.id)
        self.assertIn("moved 1/2", out)  # one keypoint displaced

    def test_issue_dump_delta_reports_same_for_empty_correction(self):
        issue = self._issue()
        obj = {"id": 1, "type": "rectangle", "label": "car", "points": [0.0, 0.0, 10.0, 10.0]}
        self._snap(issue, IssueSnapshotTrigger.BEFORE, [dict(obj)])
        self._snap(issue, IssueSnapshotTrigger.AFTER, [dict(obj)])  # resolved, nothing moved
        out = _run(issue=issue.id)
        self.assertIn("same", out)

    def test_issue_dump_missing_after_is_incomplete(self):
        issue = self._issue()
        self._snap(issue, IssueSnapshotTrigger.BEFORE, [])
        out = _run(issue=issue.id)
        self.assertIn("Incomplete correction", out)

    def test_issue_dump_no_snapshots_raises(self):
        with self.assertRaises(CommandError):
            _run(issue=424242)
