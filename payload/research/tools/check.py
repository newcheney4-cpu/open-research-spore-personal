#!/usr/bin/env python3
"""Check one release package or one current individual; scope is printed.

Package scope: file inventory, paths, format and content hashes must match.
Individual scope: intentional local changes are differences, not failures;
only missing selected content or a missing runtime entry for the named
operation is a fault.  This script does not judge research truth.
"""
import argparse
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

import _spore_core as core  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", help="release directory with MANIFEST.json")
    group.add_argument("--source-root",
                       help="workspace or explicit individual directory")
    parser.add_argument("--for", dest="operation", default=None,
                        help="operation whose local resources are required "
                             "(export, handoff, record and so on)")
    args = parser.parse_args(argv)
    if args.package:
        code, lines = core.check_package(Path(args.package))
    else:
        code, lines = core.check_individual(Path(args.source_root),
                                           args.operation)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
