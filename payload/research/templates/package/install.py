#!/usr/bin/env python3
"""Install one open-research-spore package into a workspace.

The thin entry only locates the payload and delegates every rule to
payload/<profile>/tools/_spore_core.py: complete preflight first (targets,
parent paths, conflicts, host entry), then a single commit with rollback.
Default is a dry run.  Reinstalling the same build keeps local edits and
deletions; a different build is refused with a pointer to the migration steps.
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PACK = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="target workspace")
    parser.add_argument("--host", choices=("none", "codex", "claude"),
                        default="none")
    parser.add_argument("--write", action="store_true",
                        help="commit after a complete preflight")
    parser.add_argument("--restore-missing", action="store_true",
                        help="repair step: rewrite only files that are absent "
                             "from an already recognised individual")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads((PACK / "MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("ERROR MANIFEST.json could not be read: %s" % exc)
        return 3
    profile = manifest.get("profile")
    if profile not in ("mentor", "student"):
        print("ERROR unsupported package profile: %r" % profile)
        return 3
    payload = PACK / "payload" / ("research" if profile == "mentor" else "student")
    if not (payload / "tools" / "_spore_core.py").is_file():
        print("ERROR payload is incomplete: %s" % payload)
        return 3
    sys.path.insert(0, str(payload / "tools"))
    import _spore_core as core  # noqa: E402

    root = Path(args.root).expanduser()
    try:
        plan = core.install_plan(PACK, root, host=args.host,
                                 restore_missing=args.restore_missing)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    print("open-research-spore %s (%s) -> %s"
          % (manifest.get("version"), profile, root))
    for line in core.describe_plan(plan):
        print(line)
    if plan.conflicts:
        print("REFUSED: %d conflict(s); no files written" % len(plan.conflicts))
        return 2
    if not args.write:
        print("dry run: no files written; use --write to install")
        return 0
    try:
        written = core.commit(plan)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    print("installed: wrote=%d total-items=%d" % (written, len(plan.items)))
    print("NOTE this is a mechanical installation record, not a quality or "
          "independence certificate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
