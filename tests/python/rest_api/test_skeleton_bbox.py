# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Tests for the skeleton bbox field (xtl/ytl/xbr/ybr) on LabeledShape and TrackedShape.

Covers:
- POST/PATCH: skeleton bbox is optional. Omitted or empty [] is the
  "not yet persisted" state (accepted); non-skeleton must not carry bbox.
- Normal [xtl,ytl,xbr,ybr] (xtl<xbr, ytl<ybr) and degenerate [0,0,0,0] are accepted.
- Zero-area-non-degenerate / inverted / non-4-element bbox is rejected.
- Old SDK / old client write paths stay compatible (bbox optional — migration 0098
  does not backfill; empty bbox is derived from keypoints on the fly).
- Read paths remain compatible (responses always carry bbox key for skeleton).
"""

from http import HTTPStatus

import pytest

from rest_api.utils import create_task
from shared.utils.config import get_method, make_api_client, patch_method
from shared.utils.helpers import generate_image_files


SKELETON_LABEL_SPEC = {
    "name": "person",
    "color": "#5c5eba",
    "attributes": [],
    "type": "skeleton",
    "sublabels": [
        {"name": "head", "color": "#d12345", "attributes": [], "type": "points"},
        {"name": "foot", "color": "#350dea", "attributes": [], "type": "points"},
    ],
    "svg": (
        '<line x1="20" y1="20" x2="50" y2="50" stroke="black" data-type="edge" '
        'data-node-from="1" stroke-width="0.5" data-node-to="2"></line>'
        '<circle r="1.5" stroke="black" fill="#b3b3b3" cx="20" cy="20" '
        'stroke-width="0.1" data-type="element node" data-element-id="1" '
        'data-node-id="1" data-label-id="103"></circle>'
        '<circle r="1.5" stroke="black" fill="#b3b3b3" cx="50" cy="50" '
        'stroke-width="0.1" data-type="element node" data-element-id="2" '
        'data-node-id="2" data-label-id="104"></circle>'
    ),
}


@pytest.mark.usefixtures("restore_db_per_function")
@pytest.mark.usefixtures("restore_cvat_data_per_function")
@pytest.mark.usefixtures("restore_redis_ondisk_per_function")
@pytest.mark.usefixtures("restore_redis_ondisk_after_class")
@pytest.mark.usefixtures("restore_redis_inmem_per_function")
class TestSkeletonBbox:
    _USERNAME = "admin1"

    @pytest.fixture
    def skeleton_task(self):
        spec = {"name": "skeleton bbox task", "labels": [SKELETON_LABEL_SPEC]}
        task_data = {"image_quality": 75, "client_files": generate_image_files(3)}
        task_id, _ = create_task(self._USERNAME, spec, task_data)

        response = get_method(self._USERNAME, "labels", task_id=f"{task_id}")
        label_ids = {}
        for root_label in response.json()["results"]:
            for label in [root_label] + root_label["sublabels"]:
                label_ids.setdefault(label["type"], []).append(label["id"])

        response = get_method(self._USERNAME, "jobs", task_id=f"{task_id}")
        job_id = response.json()["results"][0]["id"]
        return job_id, label_ids

    def _skeleton_shape(self, label_ids, bbox=None, elements=None):
        shape = {
            "type": "skeleton",
            "occluded": False,
            "outside": False,
            "z_order": 0,
            "rotation": 0,
            "points": [],
            "frame": 0,
            "label_id": label_ids["skeleton"][0],
            "group": 0,
            "source": "manual",
            "attributes": [],
            "elements": elements
            or [
                {
                    "type": "points",
                    "occluded": False,
                    "outside": False,
                    "z_order": 0,
                    "rotation": 0,
                    "points": [25.0, 25.0],
                    "frame": 0,
                    "label_id": label_ids["points"][0],
                    "group": 0,
                    "source": "manual",
                    "attributes": [],
                },
                {
                    "type": "points",
                    "occluded": False,
                    "outside": False,
                    "z_order": 0,
                    "rotation": 0,
                    "points": [80.0, 90.0],
                    "frame": 0,
                    "label_id": label_ids["points"][1],
                    "group": 0,
                    "source": "manual",
                    "attributes": [],
                },
            ],
        }
        if bbox is not None:
            shape["bbox"] = bbox
        return shape

    # ---------- POST (create) path ----------

    def test_create_skeleton_with_normal_bbox(self, skeleton_task):
        """Covers R1: annotator-drawn bbox is persisted and returned in response."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[10.0, 20.0, 100.0, 200.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK

        response = get_method(self._USERNAME, f"jobs/{job_id}/annotations")
        assert response.status_code == HTTPStatus.OK
        shapes = response.json()["shapes"]
        assert len(shapes) == 1
        assert shapes[0]["type"] == "skeleton"
        assert shapes[0]["bbox"] == [10.0, 20.0, 100.0, 200.0]

    def test_create_skeleton_without_bbox_is_accepted(self, skeleton_task):
        """Omitting bbox is allowed: the skeleton is stored with an empty
        (not-yet-persisted) bbox and the canvas/export derive a fitted rect from
        keypoints. Keeps old SDK/client write paths backward-compatible."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=None)],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK

        response = get_method(self._USERNAME, f"jobs/{job_id}/annotations")
        shapes = response.json()["shapes"]
        assert len(shapes) == 1
        assert shapes[0]["type"] == "skeleton"
        assert shapes[0].get("bbox", []) == []

    def test_create_skeleton_with_empty_bbox_is_accepted(self, skeleton_task):
        """Explicit empty bbox [] is the 'not yet persisted' state — accepted, stored as []."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK

        response = get_method(self._USERNAME, f"jobs/{job_id}/annotations")
        shapes = response.json()["shapes"]
        assert shapes[0].get("bbox", []) == []

    def test_create_skeleton_with_inverted_bbox_is_rejected(self, skeleton_task):
        """xbr<xtl or ybr<ytl is rejected."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[100.0, 200.0, 10.0, 20.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_create_skeleton_with_zero_width_non_degenerate_is_rejected(self, skeleton_task):
        """Zero-area bbox that is NOT exactly [0,0,0,0] is rejected (only one degenerate state allowed)."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[10.0, 10.0, 10.0, 20.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_create_skeleton_with_degenerate_bbox_is_accepted(self, skeleton_task):
        """[0,0,0,0] is the allowed degenerate state (e.g. all keypoints outside)."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[0.0, 0.0, 0.0, 0.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK

    def test_create_rectangle_with_bbox_is_rejected(self, skeleton_task):
        """Non-skeleton shape must not carry bbox."""
        _, label_ids = skeleton_task
        # Need a non-skeleton label for this; we create one in a fresh task.
        spec = {
            "name": "rect task",
            "labels": [{"name": "box", "color": "#aaaaaa", "attributes": [], "type": "rectangle"}],
        }
        task_id, _ = create_task(
            self._USERNAME, spec, {"image_quality": 75, "client_files": generate_image_files(1)}
        )
        response = get_method(self._USERNAME, "labels", task_id=f"{task_id}")
        rect_label_id = response.json()["results"][0]["id"]
        response = get_method(self._USERNAME, "jobs", task_id=f"{task_id}")
        rect_job_id = response.json()["results"][0]["id"]

        payload = {
            "shapes": [
                {
                    "type": "rectangle",
                    "occluded": False,
                    "outside": False,
                    "z_order": 0,
                    "rotation": 0,
                    "points": [1.0, 2.0, 3.0, 4.0],
                    "bbox": [1.0, 2.0, 3.0, 4.0],
                    "frame": 0,
                    "label_id": rect_label_id,
                    "group": 0,
                    "source": "manual",
                    "attributes": [],
                }
            ],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{rect_job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_create_rectangle_without_bbox_succeeds(self, skeleton_task):
        """Regression: non-skeleton creation paths must remain compatible — bbox omission is allowed."""
        spec = {
            "name": "rect compat task",
            "labels": [{"name": "box", "color": "#aaaaaa", "attributes": [], "type": "rectangle"}],
        }
        task_id, _ = create_task(
            self._USERNAME, spec, {"image_quality": 75, "client_files": generate_image_files(1)}
        )
        response = get_method(self._USERNAME, "labels", task_id=f"{task_id}")
        rect_label_id = response.json()["results"][0]["id"]
        response = get_method(self._USERNAME, "jobs", task_id=f"{task_id}")
        rect_job_id = response.json()["results"][0]["id"]

        payload = {
            "shapes": [
                {
                    "type": "rectangle",
                    "occluded": False,
                    "outside": False,
                    "z_order": 0,
                    "rotation": 0,
                    "points": [1.0, 2.0, 3.0, 4.0],
                    "frame": 0,
                    "label_id": rect_label_id,
                    "group": 0,
                    "source": "manual",
                    "attributes": [],
                }
            ],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{rect_job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK

    # ---------- PATCH (update) path ----------

    def test_update_skeleton_without_bbox_is_accepted(self, skeleton_task):
        """PATCH may omit bbox: it resets to the empty 'not yet persisted' state.
        Old clients that never send bbox keep working (no breaking change)."""
        job_id, label_ids = skeleton_task
        # Create with valid bbox first.
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[10.0, 20.0, 100.0, 200.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK
        created_id = response.json()["shapes"][0]["id"]

        # Now PATCH the same shape with bbox stripped.
        update = self._skeleton_shape(label_ids, bbox=None)
        update["id"] = created_id
        update_payload = {
            "shapes": [update],
            "tracks": [],
            "tags": [],
            "version": 1,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", update_payload, action="update"
        )
        assert response.status_code == HTTPStatus.OK

    def test_update_skeleton_with_new_bbox_succeeds(self, skeleton_task):
        """PATCH with a Normal-state bbox replaces the stored value."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[10.0, 20.0, 100.0, 200.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK
        created_id = response.json()["shapes"][0]["id"]

        update = self._skeleton_shape(label_ids, bbox=[20.0, 30.0, 200.0, 300.0])
        update["id"] = created_id
        update_payload = {
            "shapes": [update],
            "tracks": [],
            "tags": [],
            "version": 1,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", update_payload, action="update"
        )
        assert response.status_code == HTTPStatus.OK

        response = get_method(self._USERNAME, f"jobs/{job_id}/annotations")
        shapes = response.json()["shapes"]
        assert shapes[0]["bbox"] == [20.0, 30.0, 200.0, 300.0]

    def test_update_skeleton_to_degenerate_bbox_succeeds(self, skeleton_task):
        """PATCH back to the degenerate state is allowed (e.g., all keypoints became outside)."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[10.0, 20.0, 100.0, 200.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK
        created_id = response.json()["shapes"][0]["id"]

        update = self._skeleton_shape(label_ids, bbox=[0.0, 0.0, 0.0, 0.0])
        update["id"] = created_id
        update_payload = {
            "shapes": [update],
            "tracks": [],
            "tags": [],
            "version": 1,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", update_payload, action="update"
        )
        assert response.status_code == HTTPStatus.OK

    # ---------- Read path ----------

    def test_get_skeleton_response_carries_bbox_key(self, skeleton_task):
        """Covers R7 read-only compatibility: bbox is present in response."""
        job_id, label_ids = skeleton_task
        payload = {
            "shapes": [self._skeleton_shape(label_ids, bbox=[10.0, 20.0, 100.0, 200.0])],
            "tracks": [],
            "tags": [],
            "version": 0,
        }
        response = patch_method(
            self._USERNAME, f"jobs/{job_id}/annotations", payload, action="create"
        )
        assert response.status_code == HTTPStatus.OK

        response = get_method(self._USERNAME, f"jobs/{job_id}/annotations")
        shapes = response.json()["shapes"]
        # parent skeleton has bbox; child elements have empty bbox.
        assert "bbox" in shapes[0]
        assert shapes[0]["bbox"] == [10.0, 20.0, 100.0, 200.0]
        for element in shapes[0].get("elements", []):
            assert element.get("bbox", []) == []
