#!/usr/bin/env python3
"""Record an observed report against the receipt of this handoff.

The record keeps every distinct observation, so a revised report keeps the
earlier fingerprint instead of replacing it.  Re-recording the same report is
idempotent.  This records output only; it is not proof of independent context,
claim validity or filesystem isolation.
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
    parser.add_argument("--report", required=True,
                        help="absolute path to the report under student/public")
    parser.add_argument("--receipt", default=None,
                        help="receipt path when it cannot be located uniquely")
    parser.add_argument("--host-label", default="unknown")
    parser.add_argument("--session-ref", default="unknown")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    raw = Path(args.report).expanduser()
    if not raw.is_absolute():
        print("ERROR report path must be absolute")
        return 3
    try:
        plan = core.record_plan(RESEARCH, raw, receipt_path=args.receipt,
                                host_label=args.host_label,
                                session_ref=args.session_ref,
                                model=args.model)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    for line in core.describe_plan(plan):
        print(line)
    print("host=%s session=%s model=%s"
          % (args.host_label, args.session_ref, args.model))
    print("This records observed output, not independent context or isolation.")
    if plan.conflicts:
        print("REFUSED: %d conflict(s); no files written" % len(plan.conflicts))
        return 2
    if not plan.writes:
        print("no change needed")
        return 0
    if not args.write:
        print("dry run: no files written; use --write to record the observation")
        return 0
    try:
        core.commit(plan)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    print("recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
