# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Add an axis-aligned bbox field to Shape (LabeledShape, TrackedShape).

Skeleton parents previously had no persisted object bbox; the wrapping rectangle
was recomputed on the canvas each render. This migration introduces a first-class
`bbox = [xtl, ytl, xbr, ybr]` field on both shape tables.

No backfill is performed. Existing skeletons keep an empty bbox and every consumer
derives a fitted wrapping rect from the child keypoints on the fly:

* Canvas render: an empty / degenerate ``[0,0,0,0]`` bbox falls back to the
  keypoint extent plus ``SKELETON_RECT_MARGIN`` (see ``canvasView.ts``), so the
  on-screen box is unchanged from before this field existed.
* Export (COCO Keypoints, etc.): an empty bbox emits no ``__cvat_bbox`` transport
  attribute, so Datumaro writes the tight keypoint-extent bbox exactly as it did
  before this feature — no behaviour change for existing data.

A persisted bbox is written lazily the first time an annotator edits the skeleton
(soft-snap on a keypoint move, or an explicit bbox-handle resize). This keeps the
migration a pure additive schema change: it adds two columns and touches no
existing row data, so it cannot lose or alter any annotation coordinates.

Earlier drafts of this migration backfilled the column from child keypoints. That
was dropped because (a) the TrackedShape backfill was unimplementable as written —
TrackedShape has no parent self-FK, so the parent_id join raised FieldError and
crashed the migration — and (b) backfilling LabeledShape baked the 20px visual
margin into exported bboxes, diverging from both pre-feature output and the
(empty) TrackedShape rows. Deriving on the fly avoids all of that.
"""

import cvat.apps.engine.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("engine", "0097_drop_legacy_analytics_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="labeledshape",
            name="bbox",
            field=cvat.apps.engine.models.FloatArrayField(default=[]),
        ),
        migrations.AddField(
            model_name="trackedshape",
            name="bbox",
            field=cvat.apps.engine.models.FloatArrayField(default=[]),
        ),
    ]
