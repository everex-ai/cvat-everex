# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Capture a densified per-frame annotation snapshot for a review Issue.

Two capture points, one per side of a ``{bad -> feedback -> good}`` correction:

* ``before`` — when a reviewer *raises* an issue, we freeze the geometry on the
  issue's frame: the problematic state being flagged.
* ``after`` — when the issue's **job is accepted** (``stage=acceptance`` &
  ``state=completed``), we freeze every issue-frame of that job again: the final
  reviewed-and-accepted version.

Tying ``after`` to job acceptance (rather than to each issue resolve or each
annotation save) sidesteps the fragile ordering between resolving an issue and
saving the corrected annotations — those are independent requests with no ordering
guarantee, so a resolve-before-save would otherwise capture pre-fix geometry.
Acceptance is a single, unambiguous "this is the ground truth" signal; the
accepted job state is the good version for every frame it flagged. A job rejected
and re-accepted simply captures again, and a later phase takes the newest
``after`` per issue. The feedback text lives in ``Comment`` rows and is joined at
export time. Accumulated over many issues this yields the raw material for the
keypoint-correction dataset (export / before-after matching are a later phase —
see ``docs/plans/2026-07-07-001-...``).

Design notes
------------
* **Densification.** Tracks store only keyframes; non-keyframe frames are
  interpolated at read time. Rather than reimplement interpolation we reuse the
  dataset_manager read path (``JobAnnotation`` -> ``JobData.group_by_frame``),
  which yields the same fully-materialised per-frame shapes the exporters see.
* **Frame coordinate.** ``Issue.frame`` is task-relative — the same coordinate as
  ``JobData.rel_range`` (``range(segment.start_frame, segment.stop_frame + 1)``).
  It is passed to ``included_frames`` verbatim; it must NOT go through
  ``rel_frame_id`` (a media-absolute -> relative converter that raises for
  ``frame_step != 1``).
* **Stable object ids.** ``use_server_track_ids=True`` so a track's ``track_id`` is
  its DB id (stable across snapshots), which a later phase needs to line up the
  same object in the ``before`` and ``after`` snapshots.
* **Scope.** All vector shape types are captured (rectangle, polygon, polyline,
  points, ellipse, cuboid, skeleton + skeleton elements). ``mask`` is excluded —
  raw RLE is large and out of scope for keypoint correction.
"""

import logging

import django_rq
from django.conf import settings
from django.db import transaction

from cvat.apps.engine.models import (
    Issue,
    IssueAnnotationSnapshot,
    IssueSnapshotTrigger,
    Job,
)

logger = logging.getLogger(__name__)

# Shape types deliberately dropped from snapshots (see module docstring).
_EXCLUDED_SHAPE_TYPES = frozenset({"mask"})


def _serialize_shape(shape) -> dict:
    """Trim a dataset_manager exported shape namedtuple to the correction-relevant
    geometry. Recurses into skeleton ``elements`` (one child per keypoint)."""
    obj = {
        "id": shape.id,
        "type": shape.type,
        "label": shape.label,
        "group": shape.group,
        "frame": shape.frame,
        "points": list(shape.points) if shape.points else [],
        "rotation": shape.rotation,
        "occluded": bool(shape.occluded),
        "outside": bool(shape.outside),
        "z_order": shape.z_order,
    }

    # Present only on tracked shapes; with use_server_track_ids=True this is the
    # stable DB track id used later to match `before` <-> `after`.
    track_id = getattr(shape, "track_id", None)
    if track_id is not None:
        obj["track_id"] = track_id

    # Populated only for skeleton parents ([xtl, ytl, xbr, ybr]).
    bbox = getattr(shape, "bbox", None)
    if bbox:
        obj["bbox"] = list(bbox)

    elements = getattr(shape, "elements", None)
    if elements:
        obj["elements"] = [_serialize_shape(element) for element in elements]

    return obj


def build_snapshot_data(db_job, frame: int) -> dict:
    """Return the densified, filtered per-frame view for ``frame`` (task-relative)
    of ``db_job``. Raises ValueError if the frame is outside the job's segment."""
    # Imported lazily: dataset_manager is heavy and pulls in datumaro; keeping the
    # import inside the call avoids paying that cost on every web-process start and
    # sidesteps any import ordering concerns with engine.models.
    from cvat.apps.dataset_manager.bindings import JobData
    from cvat.apps.dataset_manager.task import JobAnnotation

    # Fetch the job with the label / attribute-spec prefetch that every other
    # JobAnnotation caller uses. A raw select_related job would N+1-query
    # label_set + attributespec_set on every capture — worst for skeletons, this
    # feature's own use case, where each keypoint sublabel is its own Label row.
    db_job = JobAnnotation.add_prefetch_info(Job.objects.filter(pk=db_job.id)).get()

    annotation = JobAnnotation(pk=db_job.id, db_job=db_job)
    annotation.init_from_db()

    job_data = JobData(
        annotation_ir=annotation.ir_data,
        db_job=db_job,
        host="",
        use_server_track_ids=True,
        included_frames={frame},
    )

    if frame not in job_data.rel_range:
        raise ValueError(
            f"frame {frame} is outside job {db_job.id} segment range {job_data.rel_range}"
        )

    # A frame inside the segment but absent from the included set is deleted or
    # excluded (ground-truth / specific-frames job); there is no annotation state
    # to capture, so no-op instead of storing a misleading empty snapshot.
    if frame not in job_data.get_included_frames():
        raise ValueError(f"frame {frame} is deleted or excluded in job {db_job.id}")

    data = {
        "frame": frame,  # task-relative, matches IssueAnnotationSnapshot.frame
        "abs_frame": None,
        "name": None,
        "width": None,
        "height": None,
        "objects": [],
    }

    # included_frames={frame} makes group_by_frame yield at most this one frame;
    # include_empty=True keeps it even when the frame carries no annotations.
    for materialized in job_data.group_by_frame(include_empty=True):
        if materialized.idx != frame:
            continue
        data["abs_frame"] = materialized.frame
        data["name"] = materialized.name
        data["width"] = materialized.width
        data["height"] = materialized.height
        data["objects"] = [
            _serialize_shape(shape)
            for shape in materialized.labeled_shapes
            if shape.type not in _EXCLUDED_SHAPE_TYPES
        ]
        break

    return data


def capture_issue_snapshot(issue_id: int, trigger: str) -> IssueAnnotationSnapshot | None:
    """Capture and persist a snapshot for ``issue_id`` with the given ``trigger``.

    Returns the created row, or ``None`` when there is nothing to capture (the
    issue was deleted before the worker ran, or its frame is out of range). Any
    other failure propagates to the caller, which is responsible for isolating it
    (a capture failure must never break the triggering request — see plan R8).
    """
    if trigger not in IssueSnapshotTrigger.values:
        raise ValueError(f"unknown snapshot trigger {trigger!r}")

    issue = Issue.objects.select_related("job__segment__task__data").filter(pk=issue_id).first()
    if issue is None:
        # Issue was deleted between enqueue and execution — nothing to capture.
        logger.info("Issue %s no longer exists; skipping %s snapshot", issue_id, trigger)
        return None

    try:
        data = build_snapshot_data(issue.job, issue.frame)
    except ValueError as exc:
        logger.warning("Skipping %s snapshot for issue %s: %s", trigger, issue_id, exc)
        return None

    snapshot = IssueAnnotationSnapshot.objects.create(
        issue=issue,
        job=issue.job,
        trigger=trigger,
        frame=issue.frame,
        data=data,
    )
    logger.info(
        "Captured %s snapshot %s for issue %s (job %s, frame %s, %d objects)",
        trigger,
        snapshot.id,
        issue_id,
        issue.job_id,
        issue.frame,
        len(data["objects"]),
    )
    return snapshot


def run_issue_snapshot_capture(issue_id: int, trigger: str) -> None:
    """RQ worker entry point (notifications queue).

    Isolates every capture failure: a snapshot is best-effort observability and
    must never surface as an error to the reviewer who created/resolved the issue
    (plan R8). The enqueue itself already happened after commit, so by the time we
    run the issue may be gone — ``capture_issue_snapshot`` handles that as a no-op.
    """
    try:
        capture_issue_snapshot(issue_id, trigger)
    except Exception:  # noqa: BLE001 - deliberate catch-all; capture must not escalate
        logger.exception("Failed to capture %s snapshot for issue %s", trigger, issue_id)


def enqueue_issue_snapshot(issue_id: int, trigger: str) -> None:
    """Enqueue a capture job on the notifications queue (served by the utils
    worker). Enqueue failures are swallowed and logged — see R8. Used for the
    ``before`` capture on issue creation."""
    try:
        queue = django_rq.get_queue(settings.CVAT_QUEUES.NOTIFICATIONS.value)
        queue.enqueue(run_issue_snapshot_capture, issue_id, trigger)
    except Exception:  # noqa: BLE001 - enqueue must not break issue creation
        logger.exception("Failed to enqueue %s snapshot for issue %s", trigger, issue_id)


def schedule_issue_snapshot(issue_id: int, trigger: str) -> None:
    """Schedule the capture to be enqueued once the surrounding request
    transaction commits, so the worker reads the persisted committed state.

    ``robust=True`` keeps a failing callback from breaking the commit; the enqueue
    is additionally guarded, so a Redis hiccup never fails issue creation.
    """
    transaction.on_commit(
        lambda: enqueue_issue_snapshot(issue_id, trigger),
        robust=True,
    )


def run_job_acceptance_snapshots(job_id: int) -> None:
    """RQ worker entry (notifications queue): a job has been accepted, so freeze the
    accepted geometry as the ``after`` for every issue on that job — one accepted
    version is the ground-truth good state for all frames it flagged. Each issue is
    isolated so one failure cannot drop the others, and the whole thing is
    best-effort — it must never surface to the reviewer who accepted the job (R8)."""
    try:
        issue_ids = list(Issue.objects.filter(job_id=job_id).values_list("id", flat=True))
    except Exception:  # noqa: BLE001 - capture is best-effort; never escalate
        logger.exception("Failed to list issues for accepted job %s", job_id)
        return

    for issue_id in issue_ids:
        try:
            capture_issue_snapshot(issue_id, IssueSnapshotTrigger.AFTER)
        except Exception:  # noqa: BLE001 - isolate per issue
            logger.exception("Failed acceptance after snapshot for issue %s", issue_id)


def enqueue_job_acceptance_snapshots(job_id: int) -> None:
    """Enqueue the acceptance ``after`` capture on the notifications queue. Enqueue
    failures are swallowed and logged — accepting a job must never fail because
    snapshot observability is down (see R8)."""
    try:
        queue = django_rq.get_queue(settings.CVAT_QUEUES.NOTIFICATIONS.value)
        queue.enqueue(run_job_acceptance_snapshots, job_id)
    except Exception:  # noqa: BLE001 - enqueue must not break job acceptance
        logger.exception("Failed to enqueue acceptance after snapshots for job %s", job_id)


def schedule_job_acceptance_snapshots(job_id: int) -> None:
    """Schedule the acceptance ``after`` capture once the job-update transaction
    commits, so the worker reads the persisted accepted state."""
    transaction.on_commit(
        lambda: enqueue_job_acceptance_snapshots(job_id),
        robust=True,
    )
