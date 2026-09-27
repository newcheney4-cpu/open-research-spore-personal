#!/usr/bin/env python3
"""Build a descendant package from this package's current selection.

Thin entry: it calls the same shared exporter the installed individual uses.
"""
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

PACK = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=str(PACK))
    parser.add_argument("--output", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = PACK / "payload"
    for name in ("research", "student"):
        tools = payload / name / "tools"
        if (tools / "_spore_core.py").is_file():
            sys.path.insert(0, str(tools))
            break
    else:
        print("ERROR no payload with tools/_spore_core.py in %s" % payload)
        return 3
    import _spore_core as core  # noqa: E402

    try:
        manifest, files, warnings, _ = core.export_spore(
            args.source_root, args.output, args.write)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    for line in core.describe_export(manifest, files, warnings):
        print(line)
    if not args.write:
        print("dry run: no files written; use --write to create the package")
        return 0
    print("descendant package: %s" % Path(args.output).expanduser().resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
