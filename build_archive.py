#!/usr/bin/env python3
"""Preview or build a release ZIP and SHA-256 sidecar from one verified snapshot."""
import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
PACK = Path(__file__).resolve().parent
sys.path.insert(0, str(PACK / "payload" / "research" / "tools"))
import _spore_core as core  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest, files = core.load_package(PACK)
        output = Path(args.output).expanduser().absolute()
        if core.is_inside(output, PACK):
            raise core.SporeError("archive output must be outside the release tree")
        sidecar = Path(str(output) + ".sha256")
        for target in (output, sidecar):
            if target.exists():
                raise core.SporeConflict("output already exists: %s" % target)
            issue = core.blocker(target.parent, target)
            if issue:
                raise core.SporeConflict(issue)
        payload = {"MANIFEST.json": core.json_bytes(manifest)}
        payload.update(files)
        archive_data = core.zip_bytes(payload)
        digest = core.sha_bytes(archive_data)
        plan = core.Plan()
        plan.source(PACK / "MANIFEST.json",
                    (PACK / "MANIFEST.json").read_bytes())
        for rel, data in files.items():
            plan.source(PACK / Path(*core.PurePosixPath(rel).parts), data)
        plan.add(output.name, output, archive_data, "write",
                 observed=("absent", None))
        plan.add(sidecar.name, sidecar,
                 ("%s  %s\n" % (digest, output.name)).encode("utf-8"),
                 "write", observed=("absent", None))
        print("archive: %s entries=%d sha256=%s" % (output, len(payload), digest))
        if not args.write:
            print("dry run: no files written; use --write to commit")
            return 0
        core.commit(plan)
        print("committed: %s and %s" % (output, sidecar))
        return 0
    except core.SporeError as exc:
        print("ERROR %s" % exc)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
