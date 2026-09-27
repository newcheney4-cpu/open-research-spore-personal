#!/usr/bin/env python3
"""Prepare a first student handoff or a later task handoff.

Default is a dry run.  An empty directory is assembled from the student seed,
the current runtime and the blank templates.  A recognised existing student
gets only the new task; seed files are never rewritten and local methods are
never reset.  Preparing directories is not execution and is not isolation.
"""
import argparse
import sys
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(RESEARCH / "tools"))

import _spore_core as core  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student-root", required=True,
                        help="absolute path of the student workspace")
    parser.add_argument("--task-pack", required=True,
                        help="existing task file in the mentor workspace")
    parser.add_argument("--student-id", default=None,
                        help="stable id for the receipt folder; defaults to "
                             "the student directory name")
    parser.add_argument("--existing", action="store_true",
                        help="hand this task to a reviewed existing student "
                             "root that has no install manifest")
    parser.add_argument("--write", action="store_true",
                        help="commit the handoff after the preview")
    args = parser.parse_args(argv)
    raw = Path(args.student_root).expanduser()
    if not raw.is_absolute():
        print("ERROR student root must be an explicit absolute path")
        return 3
    student_root = raw.resolve()
    task = Path(args.task_pack).expanduser().resolve()
    try:
        plan = core.first_student_plan(RESEARCH, student_root, task,
                                       student_id=args.student_id,
                                       existing=args.existing)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    print("mentor=%s" % RESEARCH.parent)
    print("student=%s" % student_root)
    for line in core.describe_plan(plan):
        print(line)
    if plan.conflicts:
        print("REFUSED: %d conflict(s); no files written" % len(plan.conflicts))
        return 2
    if not args.write:
        print("dry run: no files written; use --write at the handoff")
        return 0
    try:
        written = core.commit(plan)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    print("wrote=%d" % written)
    print("PREPARED, NOT LAUNCHED. A separate host session must do the work.")
    print("This receipt is an operation record; it is not execution, "
          "independence or isolation evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
