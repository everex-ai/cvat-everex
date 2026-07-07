# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Tests for the issue annotation snapshot capture service (plan U2).

Two layers:
  * pure ``_serialize_shape`` unit tests over dataset_manager namedtuples — field
    trimming, skeleton element recursion (sublabel name + per-keypoint
    occluded/outside), track_id / bbox presence; and
  * ``capture_issue_snapshot`` integration tests over minimal real jobs built
    directly via the ORM — densification (track interpolation), mask exclusion,
    empty frames, the task-relative frame coordinate under frame_step != 1, and
    the deleted-issue / out-of-range no-ops.
"""

from django.test import TestCase

from cvat.apps.dataset_manager.bindings import CommonData
from cvat.apps.engine import models
from cvat.apps.engine.issue_snapshots import (
    _serialize_shape,
    build_snapshot_data,
    capture_issue_snapshot,
)
from cvat.apps.engine.models import IssueAnnotationSnapshot, IssueSnapshotTrigger


class SerializeShapeTest(TestCase):
    def test_plain_shape_fields(self):
        shape = CommonData.LabeledShape(
            type="rectangle", frame=3, label="car", points=[1.0, 2.0, 3.0, 4.0],
            occluded=True, attributes=[], source="manual", rotation=15.0,
            group=2, z_order=1, elements=(), outside=False, id=55, bbox=(),
        )
        out = _serialize_shape(shape)
        self.assertEqual(out["id"], 55)
        self.assertEqual(out["type"], "rectangle")
        self.assertEqual(out["label"], "car")
        self.assertEqual(out["points"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(out["group"], 2)
        self.assertEqual(out["rotation"], 15.0)
        self.assertTrue(out["occluded"])
        self.assertFalse(out["outside"])
        self.assertNotIn("track_id", out)  # plain shapes carry no track id
        self.assertNotIn("bbox", out)      # empty bbox is omitted
        self.assertNotIn("elements", out)

    def test_skeleton_elements_recurse_with_sublabels(self):
        left = CommonData.LabeledShape(
            type="points", frame=2, label="left_eye", points=[15.0, 15.0],
            occluded=False, attributes=[], source="manual", outside=False, id=101,
        )
        right = CommonData.LabeledShape(
            type="points", frame=2, label="right_eye", points=[25.0, 25.0],
            occluded=True, attributes=[], source="manual", outside=True, id=102,
        )
        skeleton = CommonData.LabeledShape(
            type="skeleton", frame=2, label="face", points=[], occluded=False,
            attributes=[], source="manual", group=3, id=100,
            bbox=(10.0, 10.0, 30.0, 30.0), elements=(left, right),
        )
        out = _serialize_shape(skeleton)
        self.assertEqual(out["type"], "skeleton")
        self.assertEqual(out["label"], "face")
        self.assertEqual(out["group"], 3)
        self.assertEqual(out["bbox"], [10.0, 10.0, 30.0, 30.0])
        self.assertEqual(len(out["elements"]), 2)
        self.assertEqual(out["elements"][0]["label"], "left_eye")
        self.assertFalse(out["elements"][0]["outside"])
        self.assertEqual(out["elements"][1]["label"], "right_eye")
        self.assertTrue(out["elements"][1]["occluded"])
        self.assertTrue(out["elements"][1]["outside"])

    def test_tracked_shape_carries_track_id(self):
        shape = CommonData.TrackedShape(
            type="rectangle", frame=2, points=[20.0, 20.0, 30.0, 30.0],
            occluded=False, outside=False, keyframe=False, attributes=[],
            rotation=0.0, source="manual", group=0, z_order=0, label="car",
            track_id=77, elements=(), id=None, bbox=(),
        )
        out = _serialize_shape(shape)
        self.assertEqual(out["track_id"], 77)
        self.assertEqual(out["type"], "rectangle")
        self.assertEqual(out["points"], [20.0, 20.0, 30.0, 30.0])


def _make_job(*, frame_step=1, start_frame=0, size=5, label_names=("obj",)):
    """Minimal ORM fixture: Data + Images + Task + Labels + Segment + Job covering
    task-relative frames 0..size-1. Returns (task, job, {label_name: Label})."""
    stop = start_frame + (size - 1) * frame_step
    db_data = models.Data.objects.create(
        size=size,
        start_frame=start_frame,
        stop_frame=stop,
        image_quality=50,
        frame_filter=(f"step={frame_step}" if frame_step != 1 else ""),
    )
    for i in range(size):
        models.Image.objects.create(
            data=db_data, path=f"frame_{i:06d}.png",
            frame=start_frame + i * frame_step, width=100, height=100,
        )
    task = models.Task.objects.create(
        name="snap-cap", mode="annotation", data=db_data,
        dimension=models.DimensionType.DIM_2D,
    )
    labels = {
        name: models.Label.objects.create(task=task, name=name)
        for name in label_names
    }
    segment = models.Segment.objects.create(task=task, start_frame=0, stop_frame=size - 1)
    job = models.Job.objects.create(segment=segment, type=models.JobType.ANNOTATION)
    return task, job, labels


class CaptureIssueSnapshotTest(TestCase):
    def _issue(self, job, frame):
        return models.Issue.objects.create(
            job=job, frame=frame, position=[0.0, 0.0, 5.0, 5.0]
        )

    def test_deleted_issue_is_noop(self):
        self.assertIsNone(capture_issue_snapshot(999999, IssueSnapshotTrigger.BEFORE))
        self.assertEqual(IssueAnnotationSnapshot.objects.count(), 0)

    def test_out_of_range_frame_is_noop(self):
        _, job, _ = _make_job(size=3)  # rel frames 0..2
        issue = self._issue(job, frame=2)
        # Force the stored frame outside the segment without model validation.
        models.Issue.objects.filter(pk=issue.pk).update(frame=99)
        self.assertIsNone(capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.BEFORE))
        self.assertEqual(IssueAnnotationSnapshot.objects.count(), 0)

    def test_empty_frame_is_stored(self):
        _, job, _ = _make_job()
        issue = self._issue(job, frame=1)
        snap = capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.BEFORE)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.trigger, "before")
        self.assertEqual(snap.frame, 1)
        self.assertEqual(snap.data["objects"], [])
        self.assertEqual(snap.data["frame"], 1)

    def test_plain_shape_captured(self):
        _, job, labels = _make_job(label_names=("car",))
        models.LabeledShape.objects.create(
            job=job, label=labels["car"], frame=2, type="rectangle",
            points=[10.0, 10.0, 20.0, 20.0], occluded=False, outside=False,
            z_order=0, group=0, rotation=0.0, source="manual",
        )
        issue = self._issue(job, frame=2)
        snap = capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.AFTER)
        objects = snap.data["objects"]
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["type"], "rectangle")
        self.assertEqual(objects[0]["label"], "car")
        self.assertEqual(objects[0]["points"], [10.0, 10.0, 20.0, 20.0])

    def test_mask_is_excluded(self):
        _, job, labels = _make_job(label_names=("car", "region"))
        models.LabeledShape.objects.create(
            job=job, label=labels["car"], frame=2, type="rectangle",
            points=[10.0, 10.0, 20.0, 20.0], source="manual",
        )
        models.LabeledShape.objects.create(
            job=job, label=labels["region"], frame=2, type="mask",
            points=[1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 3.0, 3.0], source="manual",
        )
        issue = self._issue(job, frame=2)
        snap = capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.BEFORE)
        types = [o["type"] for o in snap.data["objects"]]
        self.assertEqual(types, ["rectangle"])  # mask dropped

    def test_interpolated_track_captured(self):
        _, job, labels = _make_job(size=5, label_names=("car",))
        track = models.LabeledTrack.objects.create(
            job=job, label=labels["car"], frame=0, group=0, source="manual"
        )
        models.TrackedShape.objects.create(
            track=track, frame=0, type="rectangle",
            points=[0.0, 0.0, 10.0, 10.0], occluded=False, outside=False,
        )
        models.TrackedShape.objects.create(
            track=track, frame=4, type="rectangle",
            points=[40.0, 40.0, 50.0, 50.0], occluded=False, outside=False,
        )
        issue = self._issue(job, frame=2)  # no keyframe here -> interpolated
        snap = capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.AFTER)
        objects = snap.data["objects"]
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["type"], "rectangle")
        self.assertIn("track_id", objects[0])
        # Linear interpolation at the midpoint frame.
        for got, want in zip(objects[0]["points"], [20.0, 20.0, 30.0, 30.0]):
            self.assertAlmostEqual(got, want, places=3)

    def test_frame_coordinate_under_frame_step(self):
        # step=2, media offset 100: task-relative issue.frame must be passed
        # through verbatim (NOT via rel_frame_id, which would raise for step!=1).
        _, job, labels = _make_job(frame_step=2, start_frame=100, size=5,
                                    label_names=("car",))
        models.LabeledShape.objects.create(
            job=job, label=labels["car"], frame=2, type="rectangle",
            points=[7.0, 7.0, 8.0, 8.0], source="manual",
        )
        issue = self._issue(job, frame=2)
        snap = capture_issue_snapshot(issue.pk, IssueSnapshotTrigger.BEFORE)
        self.assertEqual(len(snap.data["objects"]), 1)
        self.assertEqual(snap.data["objects"][0]["points"], [7.0, 7.0, 8.0, 8.0])
        self.assertEqual(snap.data["abs_frame"], 104)  # 2*2 + 100

    def test_build_snapshot_data_out_of_range_raises(self):
        _, job, _ = _make_job(size=3)
        with self.assertRaises(ValueError):
            build_snapshot_data(job, 50)
