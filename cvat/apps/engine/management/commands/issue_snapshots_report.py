# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""Observability for captured issue annotation snapshots (plan U4).

Read-only. With no arguments it prints how many snapshots have accumulated,
broken down by trigger and job, plus how many issues have a complete
``before + after`` pair. With ``--issue <id>`` it dumps that issue's initial
``before`` against its final ``after`` object-by-object (matched on stable shape
/ track id) so a human can eyeball whether the captured pairs look usable before
any export tooling is built.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from cvat.apps.engine.models import IssueAnnotationSnapshot, IssueSnapshotTrigger


def _object_key(obj: dict) -> tuple:
    """Stable identity for matching an object across before/after snapshots:
    the DB track id for tracked shapes, else the DB shape id."""
    if "track_id" in obj:
        return ("track", obj["track_id"])
    return ("shape", obj.get("id"))


class Command(BaseCommand):
    help = "Report on captured IssueAnnotationSnapshot rows (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--issue", type=int, default=None,
            help="Dump one issue's initial before vs final after, object by object.",
        )
        parser.add_argument(
            "--job", type=int, default=None,
            help="Restrict the aggregate summary to a single job id.",
        )

    def handle(self, *args, **options):
        if options["issue"] is not None:
            self._dump_issue(options["issue"])
        else:
            self._summary(options["job"])

    # -- aggregate summary ---------------------------------------------------

    def _summary(self, job_id):
        qs = IssueAnnotationSnapshot.objects.all()
        if job_id is not None:
            qs = qs.filter(job_id=job_id)

        total = qs.count()
        scope = f" (job {job_id})" if job_id is not None else ""
        self.stdout.write(f"IssueAnnotationSnapshot rows: {total}{scope}")
        if total == 0:
            return

        by_trigger = {row["trigger"]: row["n"] for row in qs.values("trigger").annotate(n=Count("id"))}
        for trigger in IssueSnapshotTrigger.values:
            self.stdout.write(f"  {trigger}: {by_trigger.get(trigger, 0)}")

        per_job = defaultdict(lambda: defaultdict(int))
        for row in qs.values("job_id", "trigger").annotate(n=Count("id")):
            per_job[row["job_id"]][row["trigger"]] = row["n"]
        self.stdout.write("Per job (job_id: before/after):")
        for jid in sorted(per_job):
            counts = per_job[jid]
            self.stdout.write(f"  job {jid}: {counts.get('before', 0)}/{counts.get('after', 0)}")

        issue_triggers = defaultdict(set)
        for row in qs.values("issue_id", "trigger").distinct():
            issue_triggers[row["issue_id"]].add(row["trigger"])
        both = sum(1 for t in issue_triggers.values() if {"before", "after"} <= t)
        before_only = sum(1 for t in issue_triggers.values() if t == {"before"})
        after_only = sum(1 for t in issue_triggers.values() if t == {"after"})
        self.stdout.write(
            f"Issues: {len(issue_triggers)} total, {both} with before+after, "
            f"{before_only} before-only, {after_only} after-only"
        )

    # -- single-issue before/after diff -------------------------------------

    def _dump_issue(self, issue_id):
        snaps = list(
            IssueAnnotationSnapshot.objects.filter(issue_id=issue_id)
            .order_by("trigger", "created_date", "id")
        )
        if not snaps:
            raise CommandError(f"No snapshots for issue {issue_id}")

        befores = [s for s in snaps if s.trigger == IssueSnapshotTrigger.BEFORE]
        afters = [s for s in snaps if s.trigger == IssueSnapshotTrigger.AFTER]
        self.stdout.write(
            f"Issue {issue_id}: {len(befores)} before, {len(afters)} after "
            f"(resolve_count={len(afters)})"
        )

        before = befores[0] if befores else None   # initial bad
        after = afters[-1] if afters else None      # final accepted good
        if before is None or after is None:
            self.stdout.write("  Incomplete correction — need one before and one after to diff.")
            return

        before_objs = {_object_key(o): o for o in before.data.get("objects", [])}
        after_objs = {_object_key(o): o for o in after.data.get("objects", [])}
        keys = sorted(set(before_objs) | set(after_objs), key=lambda k: (k[0], str(k[1])))

        self.stdout.write(f"  {'object':<16}{'before':<28}{'after':<28}")
        for key in keys:
            before_obj = before_objs.get(key)
            after_obj = after_objs.get(key)
            tag = "" if (before_obj and after_obj) else "  <UNMATCHED>"
            self.stdout.write(
                f"  {self._fmt_key(key):<16}{self._fmt(before_obj):<28}{self._fmt(after_obj):<28}{tag}"
            )

    @staticmethod
    def _fmt_key(key) -> str:
        return f"{key[0]}#{key[1]}"

    @staticmethod
    def _fmt(obj) -> str:
        if obj is None:
            return "-"
        parts = [f"{obj['type']}:{obj['label']}"]
        if obj.get("elements"):
            elements = obj["elements"]
            visible = sum(1 for e in elements if not e.get("outside"))
            parts.append(f"kpts={visible}/{len(elements)}")
        else:
            parts.append(f"pts={len(obj.get('points', [])) // 2}")
        if obj.get("occluded"):
            parts.append("occ")
        if obj.get("outside"):
            parts.append("out")
        return " ".join(parts)
