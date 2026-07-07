# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Add IssueAnnotationSnapshot.

Frozen densified annotation geometry of an issue's frame, captured server-side
when the issue is created (``before``) and at each resolve transition (``after``).
Accumulates the raw material for a later ``{bad -> feedback -> good}`` keypoint
correction dataset (see docs/plans/2026-07-07-001-...).

Pure additive schema change — one new table, no changes to existing rows.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("engine", "0098_add_skeleton_bbox"),
    ]

    operations = [
        migrations.CreateModel(
            name="IssueAnnotationSnapshot",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_date", models.DateTimeField(auto_now_add=True)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                (
                    "trigger",
                    models.CharField(
                        choices=[("before", "before"), ("after", "after")], max_length=16
                    ),
                ),
                ("frame", models.PositiveIntegerField()),
                ("data", models.JSONField()),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="annotation_snapshots",
                        related_query_name="annotation_snapshot",
                        to="engine.issue",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_annotation_snapshots",
                        to="engine.job",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
