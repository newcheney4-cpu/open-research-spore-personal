#!/usr/bin/env python3
"""Thin entry: export this student's selected methods and preferences.

The student's own current files are the only source.  Nothing is read from the
mentor's seed or private area.  Preview is the default; --write creates the
descendant package.

Inside the mentor's `student-seed/` this script is only a template: the seed
has no runtime tools, so it cannot run here.  Assemble a student with
`research/tools/first_student.py`, then run this entry from that student root.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))

try:
    import _spore_core as core  # noqa: E402
except ImportError:
    print("ERROR %s: %s"
          % (ROOT, "this directory is a student seed template, not a runnable "
                   "student individual (no tools/_spore_core.py). Assemble a "
                   "student with research/tools/first_student.py, or install "
                   "an exported student package with its install.py"))
    sys.exit(3)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student-root", default=str(ROOT),
                        help="this student workspace (defaults to the script's "
                             "own root)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest, files, warnings, _ = core.export_spore(
            args.student_root, args.output, args.write)
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code
    for line in core.describe_export(manifest, files, warnings):
        print(line)
    if not args.write:
        print("dry run: no files written; use --write to create the "
              "descendant package")
        return 0
    print("student descendant package: %s"
          % Path(args.output).expanduser().resolve())
    print("buildId=%s" % manifest["buildId"][:16])
    print("NOTE only the selected content and the runtime were re-checked for "
          "this snapshot; the methods themselves were not re-run here")
    return 0


if __name__ == "__main__":
    sys.exit(main())
