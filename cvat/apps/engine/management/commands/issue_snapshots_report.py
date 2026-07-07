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
            "--issue",
            type=int,
            default=None,
            help="Dump one issue's initial before vs final after, object by object.",
        )
        parser.add_argument(
            "--job",
            type=int,
            default=None,
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

        by_trigger = {
            row["trigger"]: row["n"] for row in qs.values("trigger").annotate(n=Count("id"))
        }
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
            IssueAnnotationSnapshot.objects.filter(issue_id=issue_id).order_by(
                "trigger", "created_date", "id"
            )
        )
        if not snaps:
            raise CommandError(f"No snapshots for issue {issue_id}")

        befores = [s for s in snaps if s.trigger == IssueSnapshotTrigger.BEFORE]
        afters = [s for s in snaps if s.trigger == IssueSnapshotTrigger.AFTER]
        # `after` rows accumulate on each resolve transition AND on each annotation
        # save that changes the frame while resolved, so this counts captures, not
        # resolves. The final `after` is the freshest saved corrected state.
        self.stdout.write(
            f"Issue {issue_id}: {len(befores)} before, {len(afters)} after (after_count={len(afters)})"
        )

        before = befores[0] if befores else None  # initial bad
        after = afters[-1] if afters else None  # final accepted good
        if before is None or after is None:
            self.stdout.write("  Incomplete correction — need one before and one after to diff.")
            return

        before_objs = {_object_key(o): o for o in before.data.get("objects", [])}
        after_objs = {_object_key(o): o for o in after.data.get("objects", [])}
        keys = sorted(set(before_objs) | set(after_objs), key=lambda k: (k[0], str(k[1])))

        self.stdout.write(f"  {'object':<16}{'before':<28}{'after':<28}{'delta'}")
        for key in keys:
            before_obj = before_objs.get(key)
            after_obj = after_objs.get(key)
            if before_obj and after_obj:
                delta = self._delta(before_obj, after_obj)
            else:
                delta = "<UNMATCHED>"
            self.stdout.write(
                f"  {self._fmt_key(key):<16}{self._fmt(before_obj):<28}"
                f"{self._fmt(after_obj):<28}{delta}"
            )

    @staticmethod
    def _fmt_key(key) -> str:
        return f"{key[0]}#{key[1]}"

    @staticmethod
    def _delta(before_obj, after_obj) -> str:
        """Summarise how much geometry moved between before and after: the point of
        the whole dataset. ``moved M/N max=D`` counts vertices/keypoints displaced
        by >0.5px and the largest displacement; ``same`` means an empty correction
        (issue resolved without touching the object — Phase-2 export should drop it)."""
        b_els = {e["label"]: e for e in before_obj.get("elements", [])}
        a_els = {e["label"]: e for e in after_obj.get("elements", [])}
        if b_els and a_els:  # skeleton: match keypoints by sublabel name
            pairs = [
                (b_els[label].get("points", []), a_els[label].get("points", []))
                for label in b_els.keys() & a_els.keys()
            ]
        else:  # plain shape: pair vertices positionally when counts match
            bp, ap = before_obj.get("points", []), after_obj.get("points", [])
            if len(bp) != len(ap):
                return "changed"
            pairs = [(bp[i : i + 2], ap[i : i + 2]) for i in range(0, len(bp) - 1, 2)]

        moved = 0
        max_d = 0.0
        counted = 0
        for bp, ap in pairs:
            if len(bp) < 2 or len(ap) < 2:
                continue
            counted += 1
            d = ((ap[0] - bp[0]) ** 2 + (ap[1] - bp[1]) ** 2) ** 0.5
            if d > 0.5:
                moved += 1
            max_d = max(max_d, d)
        if counted == 0:
            return "-"
        return f"moved {moved}/{counted} max={max_d:.1f}" if moved else "same"

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
