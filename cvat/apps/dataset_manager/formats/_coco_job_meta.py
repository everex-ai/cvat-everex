# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Pure (dependency-free) helpers for injecting per-image Job metadata into an
exported COCO Keypoints ``person_keypoints*.json``.

These functions intentionally avoid importing datumaro or Django so that the
bug-prone core logic — frame→job conflict resolution and image↔job joining —
can be unit-tested in isolation. The Django/ORM glue that feeds them lives in
``coco.py``.
"""

import os.path as osp
from typing import Any, Iterable, Mapping


def resolve_frame_jobs(segments: Iterable[Mapping[str, Any]]) -> dict[int, dict]:
    """Map each absolute frame id to the job that owns it.

    ``segments`` is an iterable of dicts shaped like::

        {"job": {"id", "state", "stage"}, "start_frame": int, "frames": Iterable[int]}

    When a frame belongs to more than one segment (interpolation overlap), the
    segment with the smallest ``start_frame`` wins; ties break on the smaller
    job id so the result is deterministic.
    """
    frame_jobs: dict[int, dict] = {}
    frame_keys: dict[int, tuple[int, int]] = {}
    for segment in segments:
        job = segment["job"]
        key = (segment["start_frame"], job["id"])
        for frame in segment["frames"]:
            if frame not in frame_keys or key < frame_keys[frame]:
                frame_keys[frame] = key
                frame_jobs[frame] = job
    return frame_jobs


def build_stem_to_job(
    per_task: Iterable[tuple[Mapping[int, dict], Mapping[int, Iterable[str]]]]
) -> dict[str, dict]:
    """Compose a ``{file_name_stem: job}`` map across one or more tasks.

    ``per_task`` yields ``(frame_jobs, frame_stems)`` pairs where ``frame_jobs``
    maps an absolute frame id to its job dict and ``frame_stems`` maps the same
    frame id to the stem forms (full path stem and/or basename stem) that may
    appear as a COCO ``file_name``. On a stem collision across tasks the first
    writer wins, keeping the result stable.
    """
    stem_to_job: dict[str, dict] = {}
    for frame_jobs, frame_stems in per_task:
        for frame, job in frame_jobs.items():
            for stem in frame_stems.get(frame, ()):
                stem_to_job.setdefault(stem, job)
    return stem_to_job


def annotate_images_with_job(
    doc: Mapping[str, Any], stem_to_job: Mapping[str, dict]
) -> tuple[int, int]:
    """Attach ``image["job"]`` to every matched entry of ``doc["images"]``.

    Each image is matched by the stem of its ``file_name`` (extension removed),
    first against the full relative stem, then against the basename stem. This
    mirrors how CVAT keys its own frame-matching map on import. Unmatched images
    are left untouched. The document is mutated in place; ``(matched, unmatched)``
    counts are returned.
    """
    images = doc.get("images")
    if not isinstance(images, list):
        return (0, 0)

    matched = 0
    unmatched = 0
    for image in images:
        file_name = image.get("file_name", "")
        full_stem = osp.splitext(file_name)[0]
        base_stem = osp.splitext(osp.basename(file_name))[0]

        job = stem_to_job.get(full_stem)
        if job is None:
            job = stem_to_job.get(base_stem)

        if job is None:
            unmatched += 1
            continue

        image["job"] = dict(job)
        matched += 1

    return (matched, unmatched)
