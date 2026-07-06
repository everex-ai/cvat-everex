# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import unittest

from cvat.apps.dataset_manager.formats._coco_job_meta import (
    annotate_images_with_job,
    build_stem_to_job,
    resolve_frame_jobs,
)


class ResolveFrameJobsTest(unittest.TestCase):
    def test_maps_each_frame_to_its_segment_job(self):
        segments = [
            {"job": {"id": 1, "state": "new", "stage": "annotation"},
             "start_frame": 0, "frames": [0, 1, 2]},
            {"job": {"id": 2, "state": "in progress", "stage": "validation"},
             "start_frame": 3, "frames": [3, 4, 5]},
        ]

        frame_jobs = resolve_frame_jobs(segments)

        self.assertEqual(frame_jobs[0]["id"], 1)
        self.assertEqual(frame_jobs[4]["id"], 2)
        self.assertEqual(frame_jobs[4]["stage"], "validation")

    def test_overlapping_frame_goes_to_smallest_start_frame_job(self):
        segments = [
            {"job": {"id": 10, "state": "new", "stage": "annotation"},
             "start_frame": 0, "frames": [0, 1, 2]},
            {"job": {"id": 20, "state": "new", "stage": "annotation"},
             "start_frame": 2, "frames": [2, 3, 4]},
        ]

        frame_jobs = resolve_frame_jobs(segments)

        self.assertEqual(frame_jobs[2]["id"], 10)
        self.assertEqual(frame_jobs[3]["id"], 20)


class BuildStemToJobTest(unittest.TestCase):
    def test_composes_stem_forms_across_frames(self):
        job_a = {"id": 1, "state": "new", "stage": "annotation"}
        job_b = {"id": 2, "state": "completed", "stage": "acceptance"}
        per_task = [(
            {0: job_a, 1: job_a, 3: job_b},
            {0: ("image_0",), 1: ("sub/image_1", "image_1"), 3: ("image_3",)},
        )]

        stem_to_job = build_stem_to_job(per_task)

        self.assertEqual(stem_to_job["image_0"]["id"], 1)
        self.assertEqual(stem_to_job["sub/image_1"]["id"], 1)
        self.assertEqual(stem_to_job["image_1"]["id"], 1)
        self.assertEqual(stem_to_job["image_3"]["id"], 2)

    def test_first_writer_wins_on_stem_collision(self):
        job_a = {"id": 1, "state": "new", "stage": "annotation"}
        job_b = {"id": 2, "state": "new", "stage": "annotation"}
        per_task = [
            ({0: job_a}, {0: ("dup",)}),
            ({5: job_b}, {5: ("dup",)}),
        ]

        stem_to_job = build_stem_to_job(per_task)

        self.assertEqual(stem_to_job["dup"]["id"], 1)


class AnnotateImagesWithJobTest(unittest.TestCase):
    def setUp(self):
        self.stem_to_job = {
            "image_0": {"id": 1, "state": "new", "stage": "annotation"},
            "image_1": {"id": 2, "state": "completed", "stage": "acceptance"},
        }

    def test_sets_nested_job_matching_by_full_stem(self):
        doc = {"images": [
            {"id": 1, "file_name": "image_0.jpg"},
            {"id": 2, "file_name": "image_1.jpg"},
        ]}

        matched, unmatched = annotate_images_with_job(doc, self.stem_to_job)

        self.assertEqual((matched, unmatched), (2, 0))
        self.assertEqual(
            doc["images"][0]["job"],
            {"id": 1, "state": "new", "stage": "annotation"},
        )

    def test_matches_by_basename_and_leaves_unmatched_untouched(self):
        doc = {"images": [
            {"id": 1, "file_name": "default/image_0.jpg"},
            {"id": 2, "file_name": "unknown.jpg"},
        ]}

        matched, unmatched = annotate_images_with_job(doc, self.stem_to_job)

        self.assertEqual((matched, unmatched), (1, 1))
        self.assertEqual(doc["images"][0]["job"]["id"], 1)
        self.assertNotIn("job", doc["images"][1])

    def test_missing_images_key_is_safe(self):
        self.assertEqual(annotate_images_with_job({}, self.stem_to_job), (0, 0))
