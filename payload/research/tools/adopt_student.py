#!/usr/bin/env python3
"""Take, preview and record one public reusable submission.

The source is read from the other individual's public/ area only.  New files
are written directly; an existing file that differs is refused unless
--replace is passed deliberately.  Semantic merging stays a normal edit by
the receiving agent; this tool only moves bytes and records provenance.
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
                        help="absolute root of the individual that published "
                             "the material (usually a student)")
    parser.add_argument("--source", required=True,
                        help="file or directory inside that root's public/ area")
    parser.add_argument("--destination", required=True,
                        help="path under modules/, skills/, templates/, "
                             "student-seed/ or archive/ in this research area")
    parser.add_argument("--replace", action="store_true",
                        help="deliberately update an existing differing file")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    raw = Path(args.student_root).expanduser()
    if not raw.is_absolute():
        print("ERROR source root must be an explicit absolute path")
        return 3
    try:
        plan = core.adoption_plan(RESEARCH, raw.resolve(), args.source,
                                  args.destination, replace=args.replace)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    for line in core.describe_plan(plan):
        print(line)
    print("This selects public material; it does not certify quality or "
          "independence.")
    if plan.conflicts:
        print("REFUSED: %d conflict(s); no files written" % len(plan.conflicts))
        return 2
    if not args.write:
        print("dry run: no files written; use --write after reviewing the plan")
        return 0
    try:
        core.commit(plan)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    print("adopted and recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
