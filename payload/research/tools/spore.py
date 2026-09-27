#!/usr/bin/env python3
"""Export a descendant package from one individual (mentor or student).

Preview is the default: nothing is written without --write.  The exporter
collects exactly the current inheritance selection plus the runtime this
profile needs, resets the new project state from the blank templates and
reports remaining capabilities and unverified items.
"""
import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

import _spore_core as core  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=str(TOOLS.parent),
                        help="workspace, explicit individual directory or package")
    parser.add_argument("--output", required=True,
                        help="new zip path (must not already exist)")
    parser.add_argument("--write", action="store_true",
                        help="create the descendant package after the preview")
    args = parser.parse_args(argv)
    try:
        manifest, files, warnings, _ = core.export_spore(
            args.source_root, args.output, args.write)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    for line in core.describe_export(manifest, files, warnings):
        print(line)
    if not args.write:
        print("dry run: no files written; use --write to create the descendant "
              "package")
        return 0
    print("descendant package: %s" % Path(args.output).expanduser().resolve())
    print("buildId=%s" % manifest["buildId"][:16])
    print("NOTE inheritance, runtime and templates were re-checked for this "
          "snapshot; the applied methods themselves were not re-run here")
    return 0


if __name__ == "__main__":
    sys.exit(main())
