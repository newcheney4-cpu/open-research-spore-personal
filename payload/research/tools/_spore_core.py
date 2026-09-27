#!/usr/bin/env python3
"""Shared implementation for mentor and student spore operations.

Single source of truth for the engineering operations of one individual
(a mentor workspace or a student workspace):

* portable path and inventory rules,
* INHERITANCE.json schema v2: selection, dependency closure, exclusions,
* package manifests (formatVersion 2) and installed PACK-MANIFEST.json,
* one shared "preview -> preflight -> commit" write path with rollback,
* descendant export for both profiles,
* package installation for both payload layouts,
* first-student assembly, per-task handoff receipts, report recording, adoption.

Standard library only.  This module never judges research truth, independence
or host permissions; only mechanical facts are reported here.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

PACKAGE_NAME = "open-research-spore"
FORMAT_VERSION = 2
INHERITANCE_SCHEMA = 2
RECEIPT_SCHEMA = 1
MENTOR = "mentor"
STUDENT = "student"
PROFILES = (MENTOR, STUDENT)
PROFILE_PAYLOAD = {MENTOR: "payload/research", STUDENT: "payload/student"}
PROFILE_INDIVIDUAL_DIR = {MENTOR: "research", STUDENT: "."}
UNIT_KINDS = ("method", "preference", "resource")
UNIT_USES = ("current", "callable", "archive")
DEFAULT_USE = {"method": "callable", "preference": "current", "resource": None}

# Runtime that every complete individual of a profile must keep so that it can
# still install, check and generate a descendant.  Paths are individual-relative
# and may name a file or a directory.
RUNTIME_UNITS = {
    MENTOR: (
        "tools/_spore_core.py", "tools/check.py", "tools/spore.py",
        "tools/first_student.py", "tools/record_student.py",
        "tools/adopt_student.py",
        "templates/package", "templates/blank/mentor",
    ),
    STUDENT: (
        "tools/_spore_core.py", "tools/check.py",
        "tools/export_student_spore.py",
        "templates/package", "templates/blank/student",
    ),
}

# A directory carrying this marker is a template to assemble from, not an
# individual that can be checked or exported from directly.
SEED_MARKER = "SEED.json"
SEED_GUIDANCE = (
    "this directory is the mentor's student seed template, not a runnable "
    "individual: it has no runtime tools, no install manifest and no current "
    "state. Assemble a student with research/tools/first_student.py, or "
    "install an exported student package with its install.py")

# Fresh state written into every descendant.  These paths are reserved: a
# selected content unit cannot override them, and a value of None means the
# path is never copied from the current individual.
STATE_TARGETS = {
    MENTOR: ("STATE.md", "CLAIMS.md", "CORRECTIONS.md", "OPEN.md",
             "DELIVERABLES.md", "history/ADOPTIONS.md",
             "PACK-MANIFEST.json"),
    STUDENT: ("PACK-MANIFEST.json",),
}
STATE_DIR_PREFIXES = {
    MENTOR: ("receipts/",),
    STUDENT: ("personal/", "public/"),
}

IGNORED_DIR_NAMES = {
    "__pycache__", ".git", ".hg", ".svn", ".idea", ".vscode",
    "node_modules", ".pytest_cache", ".agents", ".codex",
}
IGNORED_SUFFIXES = (".pyc", ".pyo", ".pyd", ".tmp", ".zip")
EXPORT_LOG_SUFFIXES = (".log",)

WINDOWS_RESERVED = (
    {"con", "prn", "aux", "nul"}
    | {"com%d" % index for index in range(1, 10)}
    | {"lpt%d" % index for index in range(1, 10)}
)


class SporeError(Exception):
    """Input, format, dependency or I/O error (exit code 3)."""

    exit_code = 3


class SporeConflict(SporeError):
    """Content conflict; nothing was committed (exit code 2)."""

    exit_code = 2


class SporeFault(SporeError):
    """A check found an actual local fault (exit code 1)."""

    exit_code = 1


class SporeInput(SporeError):
    """Unreadable input: manifest shape, schema, unsupported format."""

    exit_code = 3


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path) -> str:
    return sha_bytes(Path(path).read_bytes())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n").encode("utf-8")


def load_json(path: Path, context: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise SporeError("%s could not be read: %s" % (context, exc))
    except ValueError as exc:
        raise SporeError("%s is not valid JSON: %s" % (context, exc))


def portability_problem(part: str) -> bool:
    if part.rstrip(" .") != part or not part:
        return True
    if any(ord(char) < 32 or char in ':<>"|?*' for char in part):
        return True
    return part.split(".")[0].casefold() in WINDOWS_RESERVED


def check_relative(raw, context="path") -> PurePosixPath:
    """Validate one forward-slash, individual-relative path."""
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise SporeError("%s must be a non-empty forward-slash relative path" % context)
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise SporeError("absolute paths are not allowed in %s: %s" % (context, raw))
    components = raw.split("/")
    if any(part in ("", ".", "..") for part in components):
        raise SporeError("unsafe %s: %s" % (context, raw))
    rel = PurePosixPath(raw)
    if rel.is_absolute() or not rel.parts:
        raise SporeError("unsafe %s: %s" % (context, raw))
    for part in rel.parts:
        if portability_problem(part):
            raise SporeError("portable path required in %s: %s" % (context, raw))
    return rel


def is_inside(path, root) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def is_link_like(path) -> bool:
    """True for symlinks and Windows junctions / other reparse points.

    ``Path.is_symlink()`` returns False for NTFS junctions, so a reparse-point
    check is needed on Windows; the scheme below works on Python 3.8+.
    """
    path = Path(path)
    try:
        if path.is_symlink():
            return True
    except OSError:
        return False
    if os.name != "nt":
        return False
    try:
        info = os.lstat(str(path))
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def find_symlink(target: Path, root: Path):
    """First symlink/junction component of target under root, if any."""
    target = Path(target)
    root = Path(root)
    try:
        rel = target.relative_to(root)
    except ValueError:
        return root
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if is_link_like(cursor):
            return cursor
    return None


def ignored_rel(rel: str, *, logs: bool = False) -> bool:
    parts = PurePosixPath(rel).parts
    if any(part in IGNORED_DIR_NAMES for part in parts):
        return True
    name = parts[-1]
    if name.endswith(IGNORED_SUFFIXES):
        return True
    if logs and name.endswith(EXPORT_LOG_SUFFIXES):
        return True
    return False


def is_dev_path(rel: str) -> bool:
    """Working-tree paths that are never part of a released snapshot."""
    first = PurePosixPath(rel).parts[0]
    return first.startswith("_") or rel.casefold().endswith(".zip")


def walk_files(root: Path, *, logs: bool = False) -> list:
    """Sorted individual-relative file paths under root."""
    root = Path(root)
    out = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if ignored_rel(rel, logs=logs):
            continue
        if find_symlink(path, root) is not None:
            continue
        out.append(rel)
    return sorted(out)


def write_atomic(target: Path, data: bytes) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=str(target.parent), prefix="." + target.name + ".", suffix=".tmp",
        delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(data)
        os.replace(temporary, target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def zip_bytes(files: dict) -> bytes:
    """One shared archive writer for exports and release builds."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(files):
            archive.writestr(rel, files[rel])
    return buffer.getvalue()


def write_zip_exclusive(output, files: dict) -> Path:
    """Create a new ZIP; never overwrite an existing file."""
    output = Path(output).expanduser()
    if output.exists():
        raise SporeConflict("output already exists: %s" % output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = zip_bytes(files)
    created = False
    try:
        with output.open("xb") as handle:
            created = True
            handle.write(payload)
    except OSError as exc:
        if created:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
        raise SporeConflict("could not create the archive: %s" % exc)
    return output


# --------------------------------------------------------------------------
# plan / preflight / commit
# --------------------------------------------------------------------------

class Plan:
    """A complete write plan.  Previews print it; commits replay it."""

    def __init__(self):
        self.items = []       # dicts: target, rel, data, mode, note
        self.conflicts = []   # list of strings
        self.notes = []       # list of strings
        self.observed = {}    # rel -> ("absent"|"file", sha|None) at preflight
        self.sources = {}     # source path -> hash at the byte read

    def add(self, rel, target, data, mode, note="", observed=None):
        self.items.append({"rel": rel, "target": Path(target), "data": data,
                           "mode": mode, "note": note,
                           "parent": Path(target).parent.resolve()})
        if observed is not None:
            self.observed[rel] = observed

    @property
    def writes(self):
        return [item for item in self.items
                if item["mode"] in ("write", "replace")]

    def conflict(self, message):
        self.conflicts.append(message)

    def note(self, message):
        self.notes.append(message)

    def source(self, path, data):
        self.sources[Path(path)] = sha_bytes(data)


def blocker(root: Path, target: Path):
    """Describe an existing non-directory that blocks writing target."""
    root = Path(root)
    target = Path(target)
    try:
        rel = target.relative_to(root)
    except ValueError:
        return "target escapes root: %s" % target
    try:
        target.parent.resolve().relative_to(root.resolve())
    except ValueError:
        return "resolved path escapes root (link or junction): %s" % target
    cursor = root
    for part in rel.parts[:-1]:
        cursor = cursor / part
        if cursor.exists() and not cursor.is_dir():
            return "parent path is not a directory: %s" % cursor
    if target.exists() and not target.is_file():
        return "target is not a regular file: %s" % target
    symlink = find_symlink(target, root)
    if symlink is not None:
        return "symbolic link or junction in path: %s" % symlink
    return None


def observe(target: Path):
    target = Path(target)
    if not target.exists():
        return ("absent", None)
    return ("file", sha_file(target))


def revalidate(plan: Plan) -> None:
    """Refuse the commit when a planned target changed after preflight."""
    for path, expected in plan.sources.items():
        if not path.is_file() or sha_file(path) != expected:
            raise SporeConflict("source changed after preflight: %s" % path)
    for rel, expected in plan.observed.items():
        item = next((i for i in plan.items if i["rel"] == rel), None)
        if item is None:
            continue
        current = observe(item["target"])
        if current != expected:
            raise SporeConflict(
                "target changed after preflight: %s" % item["target"])
    for item in plan.writes:
        if item["target"].parent.resolve() != item["parent"]:
            raise SporeConflict("target parent changed after preflight: %s"
                                % item["target"])


def commit(plan: Plan, fault=None) -> int:
    """Write the planned items; roll back this operation on a caught failure.

    ``fault`` is a test-only callable ``fault(index, item) -> bool`` used by
    the acceptance runner to inject a mid-commit failure.
    """
    written = 0
    undo = []
    if plan.conflicts:
        raise SporeConflict("; ".join(plan.conflicts))
    revalidate(plan)
    try:
        for index, item in enumerate(plan.writes):
            if fault is not None and fault(index, item):
                raise OSError("injected fault at item %d" % index)
            target = item["target"]
            if target.parent.resolve() != item["parent"]:
                raise SporeConflict("target parent changed during commit: %s"
                                    % target)
            previous = target.read_bytes() if target.exists() else None
            previous_sha = sha_bytes(previous) if previous is not None else None
            if item["mode"] == "write" and previous is not None:
                raise SporeConflict("target appeared after preflight: %s" % target)
            if item["mode"] == "replace" and previous is None:
                raise SporeConflict("planned replacement vanished: %s" % target)
            expected = plan.observed.get(item["rel"])
            if expected is not None and expected[0] == "file" and previous_sha != expected[1]:
                raise SporeConflict("target changed after preflight: %s" % target)
            write_atomic(target, item["data"])
            undo.append((target, previous, sha_bytes(item["data"])))
            written += 1
    except (OSError, SporeError) as exc:
        failures = []
        for target, previous, written_sha in reversed(undo):
            try:
                if not target.is_file() or sha_file(target) != written_sha:
                    failures.append("%s (changed after this operation wrote it)" % target)
                    continue
                if previous is None:
                    target.unlink(missing_ok=True)
                else:
                    write_atomic(target, previous)
            except OSError as undo_exc:
                failures.append("%s (%s)" % (target, undo_exc))
        if failures:
            raise SporeFault(
                "write failed (%s) and rollback was incomplete: %s"
                % (exc, "; ".join(failures)))
        if isinstance(exc, SporeError):
            raise exc
        raise SporeError("write failed; this operation was rolled back: %s" % exc)
    return written


def describe_plan(plan: Plan) -> list:
    lines = []
    for item in plan.items:
        lines.append("%-18s %s%s" % (
            item["mode"], item["rel"],
            ("  (%s)" % item["note"]) if item["note"] else ""))
    for conflict in plan.conflicts:
        lines.append("CONFLICT           %s" % conflict)
    for note in plan.notes:
        lines.append("NOTE               %s" % note)
    return lines


def describe_export(manifest: dict, files: dict, warnings) -> list:
    """One shared preview/report shape for every export entry."""
    profile = manifest["profile"]
    prefix = PROFILE_PAYLOAD[profile] + "/"
    child = json.loads(files[prefix + "INHERITANCE.json"].decode("utf-8"))
    units = child.get("units", [])
    excluded = [unit["id"] for unit in units if not unit.get("inherit", True)]
    state = [path[len(prefix):] for path in files
             if path.startswith(prefix)
             and path[len(prefix):] in STATE_TARGETS[profile]]
    child_paths = {path[len(prefix):] for path in files if path.startswith(prefix)}
    export_entry = "tools/spore.py" if profile == MENTOR else \
        "tools/export_student_spore.py"
    capabilities = ["export=%s" % (
        "kept" if export_entry in child_paths
        and "tools/_spore_core.py" in child_paths else "reduced")]
    if profile == MENTOR:
        capabilities.append("handoff=%s" % (
            "kept" if any(path.startswith("student-seed/") for path in child_paths)
            else "reduced"))
        capabilities.append("adopt=%s" % (
            "kept" if "tools/adopt_student.py" in child_paths else "reduced"))
    lines = ["profile=%s version=%s files=%d inherited-units=%d "
             "excluded-units=%d state-reset=%d"
             % (profile, manifest["version"], len(files),
                len(units) - len(excluded), len(excluded), len(state))]
    lines.append("capabilities: %s" % " ".join(capabilities))
    if excluded:
        lines.append("excluded: %s" % ", ".join(sorted(excluded)))
    for warning in warnings:
        lines.append("WARNING %s" % warning)
    lines.append("unverified: the applied methods were not re-run for this "
                 "snapshot; independence, host permissions and research "
                 "effect remain unproven")
    return lines


# --------------------------------------------------------------------------
# release metadata, package manifests, installed manifests
# --------------------------------------------------------------------------

def load_release(individual_root: Path) -> dict:
    """The only version-metadata source kept with one individual."""
    path = Path(individual_root) / "templates" / "package" / "RELEASE.json"
    data = load_json(path, "templates/package/RELEASE.json")
    if not isinstance(data, dict):
        raise SporeError("RELEASE.json must be an object")
    if data.get("formatVersion") != FORMAT_VERSION:
        raise SporeError("unsupported release format: %r"
                         % data.get("formatVersion"))
    if not isinstance(data.get("version"), str) or not data["version"]:
        raise SporeError("RELEASE.json needs a non-empty version string")
    return data


def compute_build_id(profile: str, version: str, files) -> str:
    digest = hashlib.sha256()
    digest.update(("format=%d\nprofile=%s\nversion=%s\n"
                   % (FORMAT_VERSION, profile, version)).encode("utf-8"))
    for item in sorted(files, key=lambda row: row["path"].casefold()):
        digest.update(("%s\0%s\n" % (item["path"], item["sha256"])).encode("utf-8"))
    return digest.hexdigest()


def manifest_entries(files: dict, editable) -> list:
    rows = []
    for rel in sorted(files, key=str.casefold):
        data = files[rel]
        rows.append({"path": rel, "sha256": sha_bytes(data), "bytes": len(data),
                     "editable": bool(editable(rel))})
    return rows


def build_package_manifest(files: dict, profile: str, version: str,
                           parent=None, built_at=None, kind="package") -> dict:
    rows = manifest_entries(files, lambda rel: not rel.startswith(
        (PROFILE_PAYLOAD[profile] + "/tools/",
         PROFILE_PAYLOAD[profile] + "/templates/package/")))
    manifest = {
        "name": PACKAGE_NAME,
        "formatVersion": FORMAT_VERSION,
        "version": version,
        "profile": profile,
        "kind": kind,
        "builtAtUtc": built_at or utc_now(),
        "buildId": compute_build_id(profile, version, rows),
        "files": rows,
    }
    if parent:
        manifest["parent"] = parent
    return manifest


def load_package(pack: Path):
    """Strict check of one release snapshot.  Returns (manifest, files)."""
    pack = Path(pack)
    manifest = load_json(pack / "MANIFEST.json", "MANIFEST.json")
    if not isinstance(manifest, dict):
        raise SporeInput("MANIFEST.json must be an object")
    if manifest.get("name") != PACKAGE_NAME:
        raise SporeInput("unsupported package name: %r" % manifest.get("name"))
    if manifest.get("formatVersion") != FORMAT_VERSION:
        raise SporeInput(
            "unsupported package format %r; this build reads format %d only"
            % (manifest.get("formatVersion"), FORMAT_VERSION))
    profile = manifest.get("profile")
    if profile not in PROFILES:
        raise SporeInput("unsupported package profile: %r" % profile)
    if not isinstance(manifest.get("version"), str) or not manifest["version"]:
        raise SporeInput("package manifest needs a version string")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise SporeInput("package manifest files must be a non-empty list")
    files = {}
    seen = {}
    if not isinstance(manifest.get("buildId"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", manifest["buildId"]):
        raise SporeInput("package manifest needs a SHA-256 buildId")
    for row in rows:
        if not isinstance(row, dict):
            raise SporeInput("manifest entries must be objects")
        rel = check_relative(row.get("path"), "manifest path").as_posix()
        if rel == "MANIFEST.json":
            raise SporeInput("MANIFEST.json cannot list itself")
        folded = rel.casefold()
        if folded in seen:
            raise SporeInput("case-insensitive duplicate manifest path: %s" % rel)
        seen[folded] = rel
        source = pack / Path(*PurePosixPath(rel).parts)
        if (find_symlink(source, pack) is not None or not source.is_file()
                or not is_inside(source, pack)):
            raise SporeFault("missing or escaping package file: %s" % rel)
        data = source.read_bytes()
        if type(row.get("bytes")) is not int or row["bytes"] != len(data):
            raise SporeFault("package byte count mismatch: %s" % rel)
        if not isinstance(row.get("sha256"), str) or sha_bytes(data) != row["sha256"]:
            raise SporeFault("package hash mismatch: %s" % rel)
        if "editable" in row and not isinstance(row["editable"], bool):
            raise SporeInput("manifest editable must be boolean: %s" % rel)
        files[rel] = data
    build_id = compute_build_id(profile, manifest["version"],
                                manifest_entries(files, lambda rel: False))
    if manifest["buildId"] != build_id:
        raise SporeFault("package buildId does not match its contents")
    unlisted = [rel for rel in walk_files(pack)
                if rel not in files and rel != "MANIFEST.json"
                and not is_dev_path(rel)]
    if unlisted:
        raise SporeFault("package inventory has unlisted files: %s"
                         % ", ".join(unlisted[:5]))
    return manifest, files


def installed_manifest_bytes(manifest: dict, profile: str, entries) -> bytes:
    payload = {
        "name": PACKAGE_NAME,
        "formatVersion": FORMAT_VERSION,
        "version": manifest["version"],
        "profile": profile,
        "sourceBuildId": manifest.get("buildId", "unknown"),
        "sourceKind": manifest.get("kind", "package"),
        "installedAtUtc": utc_now(),
        "note": ("Mechanical provenance snapshot. Differences from it are "
                 "local changes, not failures. It is not a quality, truth or "
                 "independence certificate."),
        "files": entries,
    }
    return json_bytes(payload)


def profile_of_individual(individual_root: Path):
    path = Path(individual_root) / "INHERITANCE.json"
    if not path.is_file():
        return None
    spec = load_json(path, "INHERITANCE.json")
    if not isinstance(spec, dict):
        return None
    return spec.get("profile")


def resolve_individual(source_root: Path):
    """Locate exactly one individual (individual dir, profile) under source."""
    source = Path(source_root).expanduser()
    candidates = []
    for rel in ("INHERITANCE.json", "research/INHERITANCE.json",
                "payload/research/INHERITANCE.json",
                "payload/student/INHERITANCE.json"):
        path = source / Path(*PurePosixPath(rel).parts)
        if path.is_file():
            profile = profile_of_individual(path.parent)
            if profile in PROFILES:
                candidates.append((path.parent.resolve(), profile))
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    if not unique:
        raise SporeError(
            "no individual found under %s: expected INHERITANCE.json with "
            "profile mentor (workspace research/) or student (workspace root)"
            % source)
    for root, _ in unique:
        if (root / SEED_MARKER).is_file():
            raise SporeError("%s: %s" % (root, SEED_GUIDANCE))
    if len(unique) > 1:
        raise SporeError("ambiguous source: several individuals found: %s"
                         % ", ".join(str(root) for root, _ in unique))
    return unique[0]


# --------------------------------------------------------------------------
# inheritance schema v2
# --------------------------------------------------------------------------

class Inheritance:
    def __init__(self, root: Path, spec: dict, units: dict, selected: set):
        self.root = root
        self.spec = spec
        self.units = units
        self.selected = selected
        self.profile = spec["profile"]

    @property
    def excluded(self):
        return {key for key, unit in self.units.items()
                if not unit.get("inherit", True)}

    def ordered_selected(self):
        return [self.units[key] for key in sorted(self.selected)]


def normalize_unit(raw, context="inheritance unit"):
    if not isinstance(raw, dict):
        raise SporeError("%s must be an object" % context)
    unit_id = raw.get("id")
    if not isinstance(unit_id, str) or not unit_id:
        raise SporeError("%s needs a non-empty id" % context)
    rel = check_relative(raw.get("path"), "%s path (%s)" % (context, unit_id))
    kind = raw.get("kind")
    if kind not in UNIT_KINDS:
        raise SporeError("unit %s needs kind in %s" % (unit_id, UNIT_KINDS))
    use = raw.get("use", DEFAULT_USE[kind])
    if use is not None and use not in UNIT_USES:
        raise SporeError("unit %s has unsupported use %r" % (unit_id, use))
    inherit = raw.get("inherit", True)
    if not isinstance(inherit, bool):
        raise SporeError(
            "unit %s: inherit must be a JSON boolean (\"false\" is invalid)"
            % unit_id)
    requires = raw.get("requires", [])
    if not isinstance(requires, list) or any(
            not isinstance(item, str) or not item for item in requires):
        raise SporeError("unit %s: requires must be a list of unit ids" % unit_id)
    unit = {"id": unit_id, "path": rel.as_posix(), "kind": kind,
            "inherit": inherit, "requires": list(requires)}
    if use is not None:
        unit["use"] = use
    if "editable" in raw:
        if not isinstance(raw["editable"], bool):
            raise SporeError("unit %s: editable must be boolean" % unit_id)
        unit["editable"] = raw["editable"]
    if "note" in raw:
        if not isinstance(raw["note"], str):
            raise SporeError("unit %s: note must be a string" % unit_id)
        unit["note"] = raw["note"]
    return unit


def load_inheritance(root: Path, expected_profile=None) -> Inheritance:
    root = Path(root)
    spec = load_json(root / "INHERITANCE.json", "INHERITANCE.json")
    return parse_inheritance(root, spec, expected_profile)


def parse_inheritance(root: Path, spec: dict,
                      expected_profile=None) -> Inheritance:
    """Validate the same model for disk individuals and staged students."""
    root = Path(root)
    if not isinstance(spec, dict):
        raise SporeError("INHERITANCE.json must be an object")
    if spec.get("schemaVersion") != INHERITANCE_SCHEMA:
        raise SporeError(
            "unsupported INHERITANCE.json schemaVersion %r; this build reads "
            "%d only" % (spec.get("schemaVersion"), INHERITANCE_SCHEMA))
    profile = spec.get("profile")
    if profile not in PROFILES:
        raise SporeError("INHERITANCE.json needs profile mentor or student")
    if expected_profile is not None and profile != expected_profile:
        raise SporeError("INHERITANCE.json profile %s does not match %s"
                         % (profile, expected_profile))
    raw_units = spec.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise SporeError("INHERITANCE.json units must be a non-empty list")
    lineage = spec.get("lineage", [])
    if not isinstance(lineage, list):
        raise SporeError("INHERITANCE.json lineage must be a list when present")
    units = {}
    paths = {}
    for raw in raw_units:
        unit = normalize_unit(raw)
        if unit["id"] in units:
            raise SporeError("duplicate unit id: %s" % unit["id"])
        folded = unit["path"].casefold()
        if folded in paths:
            raise SporeError("two units share one path: %s and %s"
                             % (paths[folded], unit["id"]))
        paths[folded] = unit["id"]
        units[unit["id"]] = unit
    for unit in units.values():
        for dependency in unit["requires"]:
            if dependency not in units:
                raise SporeError("unknown dependency %s required by %s"
                                 % (dependency, unit["id"]))
    selected = {key for key, unit in units.items() if unit["inherit"]}
    pending = list(selected)
    while pending:
        unit = units[pending.pop()]
        for dependency in unit["requires"]:
            if dependency in selected:
                continue
            if not units[dependency]["inherit"]:
                raise SporeConflict(
                    "unit %s is selected but requires %s, which is excluded "
                    "(inherit=false); adjust the selection or the method"
                    % (unit["id"], dependency))
            selected.add(dependency)
            pending.append(dependency)
    return Inheritance(root, spec, units, selected)


def unit_covers(unit_path: str, rel: str) -> bool:
    if rel == unit_path:
        return True
    return rel.startswith(unit_path.rstrip("/") + "/")


def collect_unit_files(root: Path, rel: str) -> dict:
    """Bytes of one selected file or resource directory."""
    root = Path(root)
    target = root / Path(*PurePosixPath(rel).parts)
    symlink = find_symlink(target, root)
    if symlink is not None:
        raise SporeError("symbolic link or junction is not followed: %s" % symlink)
    if target.is_file():
        if not is_inside(target, root):
            raise SporeError("selected path escapes the individual: %s" % rel)
        return {rel: target.read_bytes()}
    if not target.is_dir():
        raise SporeFault("selected resource is missing: %s" % rel)
    out = {}
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        inner = path.relative_to(root).as_posix()
        if ignored_rel(inner, logs=True):
            continue
        link = find_symlink(path, root)
        if link is not None:
            raise SporeError(
                "symbolic link or junction inside a selected resource is not "
                "followed: %s" % link)
        if not is_inside(path, root):
            raise SporeError("selected path escapes the individual: %s" % inner)
        out[inner] = path.read_bytes()
    return out


def collect_units(root: Path, inheritance: Inheritance, keys) -> dict:
    files = {}
    folded = {}
    exclusions = [inheritance.units[key]["path"]
                  for key in inheritance.excluded]
    for unit_id in sorted(keys):
        unit = inheritance.units[unit_id]
        if any(unit_covers(excluded, unit["path"])
               for excluded in exclusions):
            raise SporeConflict(
                "selected unit %s lies inside an explicitly excluded path: %s"
                % (unit_id, unit["path"]))
        for rel, data in collect_unit_files(root, unit["path"]).items():
            if any(unit_covers(excluded, rel) for excluded in exclusions):
                continue
            key = rel.casefold()
            if key in folded and folded[key] != rel:
                raise SporeConflict(
                    "case-insensitive path collision in the selection: %s and %s"
                    % (folded[key], rel))
            if rel in files and files[rel] != data:
                raise SporeConflict(
                    "two selected units give different content for %s" % rel)
            folded[key] = rel
            files[rel] = data
    return files


def add_runtime_units(inheritance: Inheritance, warnings: list) -> dict:
    """Keep the runtime required for a complete, reproducible descendant."""
    root = inheritance.root
    files = {}
    for root_rel in RUNTIME_UNITS[inheritance.profile]:
        exact = [unit for unit in inheritance.units.values()
                 if unit["path"] == root_rel]
        parents = [unit for unit in inheritance.units.values()
                   if unit_covers(unit["path"], root_rel)]
        if exact:
            unit = exact[0]
            if not unit["inherit"]:
                raise SporeConflict(
                    "required runtime entry is excluded: %s" % root_rel)
            unit_id = unit["id"]
        elif parents:
            if not any(unit["inherit"] for unit in parents):
                raise SporeConflict(
                    "required runtime entry is covered by an excluded unit: %s"
                    % root_rel)
            continue
        else:
            unit_id = "runtime-" + re.sub(r"[^a-z0-9]+", "-",
                                          root_rel.casefold()).strip("-")
            while unit_id in inheritance.units:
                unit_id += "-x"
            inheritance.units[unit_id] = {
                "id": unit_id, "path": root_rel, "kind": "resource",
                "inherit": True, "requires": [],
                "note": "added by export so the descendant can keep generating",
            }
            inheritance.selected.add(unit_id)
        for rel, data in collect_unit_files(root, root_rel).items():
            files.setdefault(rel, data)
    if inheritance.profile == MENTOR:
        covers = [unit for unit in inheritance.units.values()
                  if unit_covers(unit["path"], "student-seed")
                  or unit_covers("student-seed", unit["path"])]
        if not covers or not any(unit["inherit"] for unit in covers):
            raise SporeConflict(
                "a complete mentor descendant requires a selected student-seed")
    return files


def load_blank_state(root: Path, profile: str) -> dict:
    base = Path(root) / "templates" / "blank" / profile / "state"
    if not base.is_dir():
        raise SporeFault("blank state templates are missing: %s" % base)
    out = {}
    for rel in walk_files(base):
        out[rel] = (base / Path(*PurePosixPath(rel).parts)).read_bytes()
    if not out:
        raise SporeFault("blank state templates are empty: %s" % base)
    return out


def load_shells(root: Path, profile: str) -> dict:
    base = Path(root) / "templates" / "blank" / profile / "shell"
    out = {}
    if not base.is_dir():
        return out
    for rel in walk_files(base):
        out[rel] = (base / Path(*PurePosixPath(rel).parts)).read_bytes()
    return out


def is_state_path(profile: str, rel: str) -> bool:
    if rel in STATE_TARGETS[profile]:
        return True
    return any(rel.startswith(prefix) for prefix in STATE_DIR_PREFIXES[profile])


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

def render_template(text: str, values: dict) -> str:
    out = text
    for key, value in values.items():
        out = out.replace("{{%s}}" % key, str(value))
    return out


def render_package_root(individual_root: Path, profile: str, version: str,
                        parent_summary: str, built_at: str) -> dict:
    base = Path(individual_root) / "templates" / "package"
    if not base.is_dir():
        raise SporeFault("package templates are missing: %s" % base)
    if profile == MENTOR:
        state_note = ("当前任务台账（`STATE.md`、`CLAIMS.md`、`CORRECTIONS.md`、"
                      "`OPEN.md`、`DELIVERABLES.md`）已重置为空白模板")
        verification_note = ("未验证事项：本衍生包未重新完成正式发行验收；见包根 "
                             "README 的边界说明")
    else:
        state_note = ("个人区 `personal/` 与交换区 `public/` 已重置为空白说明文件；"
                      "上一代的身份、笔记与任务材料没有进入本包")
        verification_note = ("未验证事项：见包根 README 的边界说明；学生个体不携带"
                             "发行验收记录")
    values = {"version": version, "profile": profile,
              "parentSummary": parent_summary, "builtAtUtc": built_at,
              "stateNote": state_note, "verificationNote": verification_note}
    out = {}
    for rel in walk_files(base):
        if rel == "RELEASE.json":
            continue
        data = (base / Path(*PurePosixPath(rel).parts)).read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            out[rel] = data
            continue
        out[rel] = render_template(text, values).encode("utf-8")
    required = {"install.py", "README.md"}
    missing = required - set(out)
    if missing:
        raise SporeFault("package templates incomplete: %s" % ", ".join(sorted(missing)))
    return out


def source_fingerprint(root: Path, rels) -> dict:
    out = {}
    for rel in rels:
        path = Path(root) / Path(*PurePosixPath(rel).parts)
        if path.is_file():
            out[rel] = sha_file(path)
    return out


def current_used_files(individual: Path, inheritance: Inheritance,
                       warnings: list) -> dict:
    """Collect selected content plus the runtime of this profile."""
    for key in inheritance.selected:
        path = inheritance.units[key]["path"]
        if is_state_path(inheritance.profile, path):
            raise SporeConflict(
                "current project state cannot be selected for inheritance: %s"
                % path)
    used = collect_units(individual, inheritance, inheritance.selected)
    used.update(add_runtime_units(inheritance, warnings))
    excluded = [inheritance.units[key]["path"]
                for key in inheritance.excluded]
    used = {rel: data for rel, data in used.items()
            if not any(unit_covers(path, rel) for path in excluded)}
    for runtime in RUNTIME_UNITS[inheritance.profile]:
        if not any(unit_covers(runtime, rel) for rel in used):
            raise SporeConflict("required runtime is excluded or missing: %s"
                                % runtime)
    if inheritance.profile == MENTOR:
        required_seed = (
            "student-seed/INHERITANCE.json",
            "student-seed/README.md",
            "student-seed/START.md",
            "student-seed/PREFERENCES.md",
            "student-seed/skills/open-student/SKILL.md",
            "student-seed/tools/export_student_spore.py",
        )
        for path in required_seed:
            if path not in used:
                shell = "templates/blank/student/shell/" + path[len("student-seed/"):]
                if (path in excluded and shell in used
                        and path not in ("student-seed/INHERITANCE.json",
                                         "student-seed/tools/export_student_spore.py")):
                    used[path] = used[shell]
                else:
                    raise SporeConflict(
                        "student seed needed for future handoffs is missing: %s"
                        % path)
    return used


def signature(files: dict) -> dict:
    return {rel: sha_bytes(data) for rel, data in files.items()}


def export_spore(source_root, output, write: bool, fault=None):
    """Build one descendant package from the current individual."""
    individual, profile = resolve_individual(Path(source_root))
    output = Path(output).expanduser().absolute()
    if is_inside(output, individual):
        raise SporeError("output archive must be outside the individual: %s"
                         % output)
    if output.exists():
        raise SporeConflict("output already exists: %s" % output)
    inheritance_sha = sha_file(individual / "INHERITANCE.json")
    inheritance = load_inheritance(individual, profile)
    release = load_release(individual)
    version = release["version"]
    warnings = []

    used = current_used_files(individual, inheritance, warnings)

    content = {}
    for rel, data in used.items():
        if is_state_path(profile, rel):
            warnings.append("state path ignored instead of inherited: %s" % rel)
            continue
        if rel == "INHERITANCE.json":
            continue
        content[rel] = data
    fingerprint = signature(used)

    blank = load_blank_state(individual, profile)
    shells = load_shells(individual, profile)
    final = dict(content)
    for rel, data in blank.items():
        if rel in final and final[rel] != data:
            warnings.append("blank state replaces selected content: %s" % rel)
        final[rel] = data
    for rel, data in shells.items():
        if rel not in final:
            final[rel] = data

    own_build = None
    own_manifest_path = individual / "PACK-MANIFEST.json"
    if own_manifest_path.is_file():
        try:
            own_manifest = load_json(own_manifest_path, "PACK-MANIFEST.json")
            own_build = {
                "version": own_manifest.get("version", version),
                "sourceBuildId": own_manifest.get("sourceBuildId", "unknown"),
            }
        except SporeError:
            own_build = None

    built_at = utc_now()
    parent_record = {"profile": profile, "version": version}
    if own_build:
        parent_record.update(own_build)
    child_lineage = list(inheritance.spec.get("lineage", []))
    child_lineage.append({"role": "parent-individual", "exportedAtUtc": built_at,
                          "profile": profile, "version": version,
                          "sourceBuildId": (own_build or {}).get(
                              "sourceBuildId", "unknown")})
    child_spec = {
        "schemaVersion": INHERITANCE_SCHEMA,
        "profile": profile,
        "units": [inheritance.units[key] for key in sorted(inheritance.units)],
        "lineage": child_lineage,
    }
    final["INHERITANCE.json"] = json_bytes(child_spec)

    parent_summary = "%s %s (%s)" % (PACKAGE_NAME, version, profile)
    root_assets = render_package_root(individual, profile, version,
                                      parent_summary, built_at)
    files = dict(root_assets)
    prefix = PROFILE_PAYLOAD[profile] + "/"
    for rel, data in sorted(final.items()):
        files[prefix + rel] = data
    manifest = build_package_manifest(files, profile, version,
                                      parent=parent_record, built_at=built_at,
                                      kind="derived")
    files["MANIFEST.json"] = json_bytes(manifest)

    leaks = []
    markers = {str(individual), individual.as_posix()}
    machine_path = re.compile(
        r"(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+[\\/]|" + "file" + r"://)")
    for rel, data in sorted(final.items()):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if any(marker in text for marker in markers) or machine_path.search(text):
            leaks.append(rel)
    if leaks:
        warnings.append(
            "selected files contain absolute machine paths, so descendants "
            "will carry them: %s"
            % ", ".join(leaks[:5]))

    if not write:
        return manifest, files, warnings, fingerprint

    if sha_file(individual / "INHERITANCE.json") != inheritance_sha:
        raise SporeConflict("INHERITANCE.json changed during export; retry")
    recheck = signature(current_used_files(individual, inheritance, []))
    if recheck != fingerprint:
        added = sorted(set(recheck) - set(fingerprint))
        removed = sorted(set(fingerprint) - set(recheck))
        changed = sorted(rel for rel in set(recheck) & set(fingerprint)
                         if recheck[rel] != fingerprint[rel])
        raise SporeConflict(
            "source changed during export (added=%s removed=%s changed=%s); "
            "retry after the edit settles"
            % (added[:3], removed[:3], changed[:3]))

    output = write_zip_exclusive(output, files)
    return manifest, files, warnings, fingerprint


# --------------------------------------------------------------------------
# install
# --------------------------------------------------------------------------

BEGIN_MARK = "<!-- open-research-workflow:begin"
END_MARK = "<!-- open-research-workflow:end -->"
HOST_FILES = {"codex": "AGENTS.md", "claude": "CLAUDE.md"}


def host_block_plan(workspace: Path, package: Path, host: str,
                    profile: str) -> Plan:
    plan = Plan()
    if host == "none":
        return plan
    name = HOST_FILES[host]
    candidates = [Path(package) / "adapters" / ("%s.block.%s.md" % (host, profile)),
                  Path(package) / "adapters" / (host + ".block.md")]
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        raise SporeFault("host block template is missing for %s/%s"
                         % (host, profile))
    block = source.read_bytes()
    plan.source(source, block)
    target = Path(workspace) / name
    issue = blocker(workspace, target)
    if issue:
        plan.conflict(issue)
        return plan
    if not target.exists():
        plan.add(name, target, block, "write", observed=("absent", None))
        return plan
    old = target.read_bytes()
    occurrences = old.count(BEGIN_MARK.encode("utf-8"))
    end_count = old.count(END_MARK.encode("utf-8"))
    if occurrences != end_count:
        plan.conflict("damaged open-research-workflow markers in %s" % target)
        return plan
    if occurrences == 0:
        separator = b"" if old.endswith(b"\n") or not old else b"\n"
        plan.add(name, target, old + separator + block, "replace",
                 observed=("file", sha_bytes(old)))
        return plan
    if occurrences > 1:
        plan.conflict("multiple open-research-workflow blocks in %s" % target)
        return plan
    start = old.index(BEGIN_MARK.encode("utf-8"))
    end = old.find(END_MARK.encode("utf-8"), start)
    if end < 0:
        plan.conflict("incomplete open-research-workflow block in %s" % target)
        return plan
    end += len(END_MARK.encode("utf-8"))
    existing = old[start:end]
    if existing.strip() == block.strip():
        plan.add(name, target, old, "skip")
        return plan
    updated = old[:start] + block.rstrip(b"\n") + old[end:]
    plan.add(name, target, updated, "replace",
             observed=("file", sha_bytes(old)))
    return plan


def load_installed_manifest(individual_root: Path):
    path = Path(individual_root) / "PACK-MANIFEST.json"
    if not path.is_file():
        return None
    data = load_json(path, "PACK-MANIFEST.json")
    if not isinstance(data, dict):
        raise SporeError("PACK-MANIFEST.json must be an object")
    return data


def install_plan(package: Path, target_root: Path, host="none",
                 restore_missing=False) -> Plan:
    package = Path(package).expanduser()
    target_root = Path(target_root).expanduser()
    manifest, files = load_package(package)
    profile = manifest["profile"]
    prefix = PROFILE_PAYLOAD[profile] + "/"
    relative_dir = PROFILE_INDIVIDUAL_DIR[profile]
    individual = target_root if relative_dir == "." else target_root / relative_dir
    if is_inside(target_root, package) or is_inside(package, target_root):
        raise SporeError("target root and package must not contain each other")

    plan = Plan()
    plan.source(package / "MANIFEST.json",
                (package / "MANIFEST.json").read_bytes())
    for rel, data in files.items():
        plan.source(package / Path(*PurePosixPath(rel).parts), data)
    existing = None
    try:
        existing = load_installed_manifest(individual)
    except SporeError as exc:
        plan.conflict("existing PACK-MANIFEST.json is unusable: %s" % exc)
        return plan

    payload = []
    for rel in sorted(files):
        if not rel.startswith(prefix):
            continue
        local = rel[len(prefix):]
        payload.append((local, rel, files[rel]))
    if not payload:
        raise SporeError("package has no %s payload" % profile)

    entries = [{"path": local, "packagePath": package_rel,
                "sha256": sha_bytes(data), "bytes": len(data),
                "editable": True}
               for local, package_rel, data in payload]
    generated = installed_manifest_bytes(manifest, profile, entries)

    recognized = (isinstance(existing, dict)
                  and existing.get("name") == PACKAGE_NAME
                  and existing.get("profile") == profile
                  and existing.get("formatVersion") == FORMAT_VERSION)

    if existing is not None and not recognized:
        plan.conflict(
            "existing installation has a different identity; use the "
            "migration steps instead of reinstalling (%s)" % individual)
        return plan

    repeat = False
    if recognized:
        if existing.get("sourceBuildId") and manifest.get("buildId") \
                and existing["sourceBuildId"] != manifest["buildId"]:
            plan.conflict(
                "installed individual came from build %s, this package is %s; "
                "use the migration steps instead of overwriting (repeat "
                "installation never replaces a different version silently)"
                % (existing["sourceBuildId"][:12], manifest["buildId"][:12]))
            return plan
        repeat = True

    for local, package_rel, data in payload:
        target = individual / Path(*PurePosixPath(local).parts)
        issue = blocker(target_root, target)
        if issue:
            plan.conflict(issue)
            continue
        mode = "write"
        observed = observe(target)
        if target.exists():
            if target.read_bytes() == data:
                mode = "skip"
            elif repeat:
                mode = "keep"
                plan.note("local change kept: %s" % local)
            else:
                plan.conflict(
                    "existing file differs: %s (edit or migrate it "
                    "deliberately; installation never overwrites it)" % local)
                continue
        elif repeat:
            if restore_missing:
                plan.note("restoring absent file: %s" % local)
            else:
                mode = "keep"
                plan.note("absent locally (kept as-is, not restored): %s" % local)
        plan.add(local, target, data, mode, observed=observed)

    manifest_target = individual / "PACK-MANIFEST.json"
    issue = blocker(target_root, manifest_target)
    if issue:
        plan.conflict(issue)
    else:
        current = manifest_target.read_bytes() if manifest_target.is_file() else None
        if current == generated:
            plan.add("PACK-MANIFEST.json", manifest_target, generated, "skip")
        elif current is None:
            plan.add("PACK-MANIFEST.json", manifest_target, generated, "write",
                     observed=("absent", None))
        elif repeat:
            plan.note("installation manifest already describes this source build")
            plan.add("PACK-MANIFEST.json", manifest_target, generated, "skip")
        else:
            plan.conflict("existing PACK-MANIFEST.json differs: %s" % manifest_target)

    host_plan = host_block_plan(target_root, package, host, profile)
    plan.items.extend(host_plan.items)
    plan.conflicts.extend(host_plan.conflicts)
    plan.notes.extend(host_plan.notes)
    plan.observed.update(host_plan.observed)
    plan.sources.update(host_plan.sources)
    plan.notes.append("package: %s %s (%s), build %s"
                      % (manifest["name"], manifest["version"], profile,
                         manifest.get("buildId", "?")[:12]))
    return plan


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_package(pack: Path) -> tuple:
    lines = []
    try:
        manifest, files = load_package(pack)
    except SporeError as exc:
        return exc.exit_code, ["FAIL package manifest: %s" % exc]
    lines.append("scope: release package %s" % Path(pack).resolve())
    lines.append("identity: %s %s (%s) format %d build %s"
                 % (manifest["name"], manifest["version"], manifest["profile"],
                    manifest["formatVersion"], manifest.get("buildId", "?")[:12]))
    lines.append("files: %d listed and hash-verified, 0 unlisted" % len(files))
    parent = manifest.get("parent")
    if parent:
        lines.append("parent: %s" % json.dumps(parent, ensure_ascii=False,
                                               sort_keys=True))
    if manifest.get("kind") == "derived":
        lines.append("NOTE derived package: it was exported by an individual "
                     "and has not been re-accepted as a formal release")
    lines.append("NOTE inventory and hashes only; research truth, independence "
                 "and host permissions are not tested here")
    return 0, lines


def check_individual(source_root: Path, for_operation: str | None = None) -> tuple:
    lines = []
    problems = []
    try:
        individual, profile = resolve_individual(Path(source_root))
    except SporeError as exc:
        return 3, ["ERROR source: %s" % exc]
    lines.append("scope: individual %s (%s)" % (individual, profile))
    if for_operation in ("record", "handoff-existing", "adopt", "handoff"):
        if profile != MENTOR:
            return 3, ["ERROR %s requires a mentor individual" % for_operation]
        if for_operation == "record":
            lines.append("operation scope: report recording; the chosen receipt "
                         "and public report are checked when supplied")
        elif for_operation == "handoff-existing":
            lines.append("operation scope: existing student handoff; current "
                         "student files and task target are checked when supplied")
        elif for_operation == "adopt":
            if not (individual / "history" / "ADOPTIONS.md").is_file():
                return 1, lines + ["FAIL adoption history is missing"]
            lines.append("operation scope: public method adoption")
        else:
            try:
                seed = individual / "student-seed"
                for rel in ("START.md", "README.md", "PREFERENCES.md",
                            "INHERITANCE.json", "skills/open-student/SKILL.md",
                            "tools/export_student_spore.py"):
                    if not (seed / Path(*PurePosixPath(rel).parts)).is_file():
                        raise SporeFault("student seed is missing: %s" % rel)
                student_runtime_files(individual)
                load_blank_state(individual, STUDENT)
                load_release(individual)
            except SporeError as exc:
                return 1, lines + ["FAIL student creation: %s" % exc]
            lines.append("operation scope: first student assembly")
        lines.append("0 FAIL")
        return 0, lines
    if for_operation not in (None, "export"):
        return 3, lines + ["ERROR unknown operation scope: %s" % for_operation]
    try:
        inheritance = load_inheritance(individual, profile)
    except SporeConflict as exc:
        return 2, ["CONFLICT inheritance: %s" % exc]
    except SporeError as exc:
        return exc.exit_code, ["FAIL inheritance: %s" % exc]
    lines.append("inheritance: schema %d, %d units, %d selected, %d excluded"
                 % (inheritance.spec["schemaVersion"], len(inheritance.units),
                    len(inheritance.selected), len(inheritance.excluded)))
    missing = []
    for unit_id in sorted(inheritance.selected):
        unit = inheritance.units[unit_id]
        try:
            collect_unit_files(individual, unit["path"])
        except SporeFault as exc:
            missing.append("%s (%s)" % (unit["path"], exc))
        except SporeError as exc:
            problems.append("unit %s: %s" % (unit_id, exc))
    if missing:
        problems.extend("selected resource missing: %s" % item for item in missing)
    installed = None
    path = individual / "PACK-MANIFEST.json"
    if path.is_file():
        try:
            installed = load_json(path, "PACK-MANIFEST.json")
        except SporeError as exc:
            problems.append(str(exc))
    changed = []
    absent = []
    if isinstance(installed, dict):
        for row in installed.get("files", []):
            local = row.get("path")
            target = individual / Path(*PurePosixPath(local).parts)
            if not target.is_file():
                absent.append(local)
            elif sha_file(target) != row.get("sha256"):
                changed.append(local)
        lines.append("installed snapshot: %d files, %d local changes, %d absent"
                     % (len(installed.get("files", [])), len(changed), len(absent)))
        if changed:
            lines.append("NOTE local changes (not failures): %s"
                         % ", ".join(sorted(changed)[:8]))
        if absent:
            lines.append("NOTE absent locally (not restored): %s"
                         % ", ".join(sorted(absent)[:8]))
    else:
        lines.append("installed snapshot: none (this individual did not come "
                     "from install.py; provenance unknown)")

    runtime_missing = []
    for root_rel in RUNTIME_UNITS[profile]:
        target = individual / Path(*PurePosixPath(root_rel).parts)
        if not target.exists():
            runtime_missing.append(root_rel)
    if runtime_missing:
        operation = for_operation or "current individual"
        problems.append(
            "runtime entries needed by operation '%s' are missing: %s"
            % (operation, ", ".join(runtime_missing)))
    lines.append("operation scope: %s" % (for_operation or "current individual"))
    for problem in problems:
        lines.append("FAIL %s" % problem)
    if problems:
        return 1, lines
    lines.append("0 FAIL")
    lines.append("NOTE mechanical check only; it cannot show that a method is "
                 "effective, a conclusion is true or a partner was independent")
    return 0, lines


# --------------------------------------------------------------------------
# receipts, first student, record, adoption
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).casefold()).strip("-")
    return slug or "item"


def receipts_root(research: Path) -> Path:
    return Path(research) / "receipts"


def load_receipt(path: Path) -> dict:
    data = load_json(path, "receipt %s" % path)
    if not isinstance(data, dict) or data.get("schemaVersion") != RECEIPT_SCHEMA:
        raise SporeError("unsupported receipt schema: %s" % path)
    return data


def all_receipts(research: Path) -> list:
    base = receipts_root(research)
    out = []
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*.json")):
        if path.is_file():
            if find_symlink(path, base) is not None:
                raise SporeError("receipt path uses a link or junction: %s" % path)
            out.append((path, load_receipt(path)))
    return out


def student_runtime_files(mentor_research: Path) -> dict:
    """Runtime + templates the assembled student needs, taken from the mentor."""
    out = {}
    pairs = (
        ("tools/_spore_core.py", "tools/_spore_core.py"),
        ("tools/check.py", "tools/check.py"),
    )
    for source_rel, target_rel in pairs:
        source = Path(mentor_research) / Path(*PurePosixPath(source_rel).parts)
        if not source.is_file():
            raise SporeFault("mentor runtime missing: %s" % source_rel)
        out[target_rel] = source.read_bytes()
    for dir_rel in ("templates/package", "templates/blank/student"):
        base = Path(mentor_research) / Path(*PurePosixPath(dir_rel).parts)
        if not base.is_dir():
            raise SporeFault("mentor template missing: %s" % dir_rel)
        for rel in walk_files(base):
            data = (base / Path(*PurePosixPath(rel).parts)).read_bytes()
            out["%s/%s" % (dir_rel, rel)] = data
    return out


def first_student_plan(mentor_research: Path, student_root: Path, task_pack: Path,
                       student_id: str | None = None, existing=False) -> Plan:
    mentor_research = Path(mentor_research)
    student_root = Path(student_root)
    mentor_root = mentor_research.parent
    task_pack = Path(task_pack)
    plan = Plan()
    if is_inside(student_root, mentor_root) or is_inside(mentor_root, student_root):
        raise SporeError("student root and mentor root must not contain each other")
    if not task_pack.is_file():
        raise SporeError("task pack does not exist: %s" % task_pack)
    if student_id is not None and (not isinstance(student_id, str) or not student_id):
        raise SporeError("student id must be a non-empty string")

    recognized = False
    student_manifest = student_root / "PACK-MANIFEST.json"
    if student_manifest.is_file():
        data = load_json(student_manifest, "student PACK-MANIFEST.json")
        if isinstance(data, dict) and data.get("name") == PACKAGE_NAME \
                and data.get("profile") == STUDENT \
                and data.get("formatVersion") == FORMAT_VERSION \
                and isinstance(data.get("sourceBuildId"), str) \
                and isinstance(data.get("files"), list) \
                and profile_of_individual(student_root) == STUDENT:
            recognized = True
    if not recognized:
        looks_like_student = ((student_root / "START.md").is_file()
                              and (student_root / "INHERITANCE.json").is_file())
        entries = []
        if student_root.is_dir():
            entries = [item.name for item in student_root.iterdir()]
        if entries and not (existing and looks_like_student):
            plan.conflict(
                "%s is not an empty, recognised student workspace; choose a "
                "new directory or pass --existing after a reviewed migration"
                % student_root)
            return plan
        if existing and looks_like_student:
            if profile_of_individual(student_root) != STUDENT:
                raise SporeError("reviewed existing student has no student profile")
            plan.note("existing student recognised by START.md and "
                      "INHERITANCE.json; no seed files will be written")
            recognized = True

    if not recognized:
        seed = mentor_research / "student-seed"
        if not seed.is_dir():
            raise SporeFault("student seed is missing from the mentor: %s" % seed)
        seed_selection = load_inheritance(seed, STUDENT)
        selected_paths = [unit["path"] for unit in
                          seed_selection.ordered_selected()]
        excluded_paths = [seed_selection.units[key]["path"]
                          for key in seed_selection.excluded]
        student_shells = load_shells(mentor_research, STUDENT)
        required_seed = ("START.md", "README.md", "PREFERENCES.md",
                         "INHERITANCE.json", "skills/open-student/SKILL.md",
                         "tools/export_student_spore.py")
        missing_seed = [rel for rel in required_seed
                        if not (seed / Path(*PurePosixPath(rel).parts)).is_file()
                        and not (rel in student_shells and any(
                            unit_covers(path, rel) for path in excluded_paths))]
        if missing_seed:
            raise SporeFault(
                "student seed is incomplete; a new student would lack: %s"
                % ", ".join(missing_seed))
        for rel in walk_files(seed):
            if (rel in (SEED_MARKER, "INHERITANCE.json")
                    or is_state_path(STUDENT, rel)
                    or any(unit_covers(path, rel) for path in excluded_paths)
                    or not any(unit_covers(path, rel)
                               for path in selected_paths)):
                continue
            source = seed / Path(*PurePosixPath(rel).parts)
            data = source.read_bytes()
            plan.source(source, data)
            plan.add(rel, student_root / Path(*PurePosixPath(rel).parts), data,
                     "write", observed=("absent", None))
        seed_spec_path = seed / "INHERITANCE.json"
        seed_spec_data = seed_spec_path.read_bytes()
        plan.source(seed_spec_path, seed_spec_data)
        plan.add("INHERITANCE.json", student_root / "INHERITANCE.json",
                 seed_spec_data, "write", observed=("absent", None))
        assembled_at = utc_now()
        spec_item = next((item for item in plan.items
                          if item["rel"] == "INHERITANCE.json"), None)
        if spec_item is not None:
            spec = json.loads(spec_item["data"].decode("utf-8"))
            spec["lineage"] = list(spec.get("lineage", [])) + [{
                "role": "assembled-from-mentor",
                "assembledAtUtc": assembled_at,
                "mentorVersion": load_release(mentor_research)["version"],
            }]
            spec_item["data"] = json_bytes(spec)
        for rel, data in student_runtime_files(mentor_research).items():
            source = mentor_research / Path(*PurePosixPath(rel).parts)
            plan.source(source, data)
            plan.add(rel, student_root / Path(*PurePosixPath(rel).parts), data,
                     "write", observed=("absent", None))
        blanks = load_blank_state(mentor_research, STUDENT)
        for rel, data in blanks.items():
            source = (mentor_research / "templates" / "blank" / STUDENT
                      / "state" / Path(*PurePosixPath(rel).parts))
            plan.source(source, data)
            plan.add(rel, student_root / Path(*PurePosixPath(rel).parts), data,
                     "write", observed=("absent", None))
        staged_rels = {item["rel"] for item in plan.items}
        for rel, data in student_shells.items():
            if rel not in staged_rels:
                source = (mentor_research / "templates" / "blank" / STUDENT
                          / "shell" / Path(*PurePosixPath(rel).parts))
                plan.source(source, data)
                plan.add(rel, student_root / Path(*PurePosixPath(rel).parts),
                         data, "write", observed=("absent", None))
        manifest = mentor_identity(mentor_research)
        entries = []
        for item in plan.items:
            entries.append({"path": item["rel"],
                            "packagePath": "assembled/" + item["rel"],
                            "sha256": sha_bytes(item["data"]),
                            "bytes": len(item["data"]), "editable": True})
        student_manifest_bytes = installed_manifest_bytes(
            manifest, STUDENT, entries)
        plan.add("PACK-MANIFEST.json", student_manifest, student_manifest_bytes,
                 "write", observed=("absent", None))
        assembled_spec = json.loads(
            spec_item["data"].decode("utf-8")) if spec_item is not None else {}
        assembled = parse_inheritance(student_root, assembled_spec, STUDENT)
        rels = [item["rel"] for item in plan.items]
        if len(rels) != len(set(rel.casefold() for rel in rels)):
            raise SporeConflict("assembled student has duplicate target paths")
        assembled_rels = {item["rel"] for item in plan.items}
        unassembled = []
        for unit in assembled.ordered_selected():
            path = unit["path"]
            covered = (path in assembled_rels
                       or any(rel.startswith(path.rstrip("/") + "/")
                              for rel in assembled_rels))
            if not covered:
                unassembled.append("%s (%s)" % (path, unit["id"]))
        if unassembled:
            raise SporeFault(
                "assembled student would miss selected resources: %s"
                % ", ".join(unassembled))

    staged_rel = "public/" + task_pack.name
    staged = student_root / "public" / task_pack.name
    task_data = task_pack.read_bytes()
    plan.source(task_pack, task_data)
    issue = blocker(student_root, staged)
    if issue:
        plan.conflict(issue)
    else:
        data = task_data
        if staged.is_file() and staged.read_bytes() == data:
            plan.add(staged_rel, staged, data, "skip")
        elif staged.exists():
            plan.conflict("different file already staged: %s" % staged_rel)
        else:
            plan.add(staged_rel, staged, data, "write", observed=("absent", None))

    identity = student_id or student_root.name
    root_key = sha_bytes(str(student_root).casefold().encode("utf-8"))[:6]
    receipt_dir = receipts_root(mentor_research) / ("%s-%s" % (slugify(identity),
                                                               root_key))
    task_sha = sha_bytes(task_data)
    task_id = "%s-%s-%s" % (utc_now()[:10].replace("-", ""),
                            slugify(task_pack.stem), task_sha[:8])
    receipt_path = receipt_dir / (task_id + ".json")
    for path, receipt in all_receipts(mentor_research):
        if receipt.get("task", {}).get("sha256") == task_sha \
                and receipt.get("task", {}).get("stagedPath") == staged_rel \
                and receipt.get("task", {}).get("source") == task_pack.name \
                and Path(receipt.get("studentRoot", "")).resolve() == student_root.resolve():
            plan.note("receipt already exists: %s" % path)
            receipt_path = path
            break
    else:
        suffix = 1
        while receipt_path.exists():
            suffix += 1
            if suffix > 50:
                raise SporeConflict(
                    "too many receipts for this student and task: %s"
                    % receipt_path)
            receipt_path = receipt_dir / ("%s-%d.json" % (task_id, suffix))
        receipt = {
            "schemaVersion": RECEIPT_SCHEMA,
            "studentId": "%s-%s" % (slugify(identity), root_key),
            "studentRoot": str(student_root),
            "status": "prepared-not-launched",
            "createdAtUtc": utc_now(),
            "mentorResearch": str(mentor_research),
            "task": {"stagedPath": staged_rel, "sha256": task_sha,
                     "bytes": len(task_data),
                     "source": task_pack.name},
            "note": ("Prepared directories and staged files are not execution "
                     "evidence; this record is an operation receipt only."),
        }
        plan.add(receipt_path.relative_to(mentor_research).as_posix(),
                 receipt_path, json_bytes(receipt), "write",
                 observed=observe(receipt_path))
    plan.note("receipt: %s" % receipt_path)
    return plan


def mentor_identity(mentor_research: Path) -> dict:
    """Version metadata of the mentor individual for provenance records."""
    release = load_release(mentor_research)
    build_id = "assembled-from-mentor"
    installed = Path(mentor_research) / "PACK-MANIFEST.json"
    if installed.is_file():
        try:
            data = load_json(installed, "mentor PACK-MANIFEST.json")
            if isinstance(data, dict) and data.get("sourceBuildId"):
                build_id = str(data["sourceBuildId"])
                if data.get("version"):
                    return {"name": PACKAGE_NAME, "version": str(data["version"]),
                            "buildId": build_id}
        except SporeError:
            pass
    return {"name": PACKAGE_NAME, "version": release["version"],
            "buildId": build_id}


def record_plan(mentor_research: Path, report: Path, receipt_path=None,
                host_label="unknown", session_ref="unknown",
                model="unknown") -> Plan:
    mentor_research = Path(mentor_research)
    report = Path(report)
    plan = Plan()
    candidates = []
    if receipt_path is not None:
        path = Path(receipt_path)
        if not path.is_absolute():
            path = mentor_research / path
        if (not is_inside(path, receipts_root(mentor_research))
                or find_symlink(path, mentor_research) is not None):
            raise SporeError("receipt must be a regular path under the mentor's receipts area")
        receipt = load_receipt(path)
        candidates.append((path, receipt))
    else:
        for path, receipt in all_receipts(mentor_research):
            root_text = receipt.get("studentRoot")
            if not isinstance(root_text, str):
                continue
            root = Path(root_text)
            if (is_inside(report, root / "public") and report.is_file()
                    and find_symlink(report, root) is None):
                candidates.append((path, receipt))
        if len(candidates) > 1:
            try:
                rel_guess = report.relative_to(
                    Path(candidates[0][1]["studentRoot"])).as_posix()
            except (ValueError, KeyError, TypeError):
                rel_guess = report.name
            exact = [item for item in candidates
                     if item[1].get("task", {}).get("stagedPath") ==
                     report.relative_to(Path(item[1]["studentRoot"])).as_posix()]
            if len(exact) == 1:
                candidates = exact
            else:
                raise SporeConflict(
                    "several receipts mention this student directory and "
                    "none uniquely matches the report path (%s); pass "
                    "--receipt explicitly: %s"
                    % (rel_guess, ", ".join(str(path) for path, _ in candidates)))
    if not candidates:
        raise SporeError(
            "no receipt matches the report; prepare the student handoff first "
            "or pass --receipt")
    path, receipt = candidates[0]
    root = Path(receipt["studentRoot"])
    if not report.is_file():
        raise SporeError("report does not exist: %s" % report)
    if not is_inside(report, root / "public"):
        raise SporeError("report must live under the student's public area")
    if find_symlink(report, root) is not None:
        raise SporeError("report path uses a symbolic link or junction")
    data = report.read_bytes()
    plan.source(report, data)
    if not data:
        raise SporeError("report is empty")
    digest = sha_bytes(data)
    rel = report.relative_to(root).as_posix()
    observations = receipt.get("observations", [])
    if not isinstance(observations, list):
        raise SporeError("receipt observations must be a list")
    for prior in observations:
        if isinstance(prior, dict) and prior.get("sha256") == digest \
                and prior.get("report") == rel:
            plan.note("already recorded: %s sha256=%s" % (rel, digest[:12]))
            return plan
    updated = dict(receipt)
    updated["observations"] = observations + [{
        "observedAtUtc": utc_now(),
        "report": rel,
        "sha256": digest,
        "bytes": len(data),
        "hostLabel": host_label,
        "sessionRef": session_ref,
        "model": model,
        "metadataClass": ("caller-declared where provided; output observation "
                          "is not proof of independent context, isolation or "
                          "claim validity"),
    }]
    updated["status"] = "student-output-observed"
    plan.add(path.relative_to(mentor_research).as_posix(), path,
             json_bytes(updated), "replace", observed=("file", sha_file(path)))
    plan.note("observation recorded for %s" % rel)
    return plan


ADOPTION_DESTINATIONS = ("modules", "skills", "templates", "student-seed",
                         "archive")


def adoption_plan(mentor_research: Path, from_root: Path, source_rel: str,
                  destination_rel: str, replace=False) -> Plan:
    mentor_research = Path(mentor_research)
    from_root = Path(from_root)
    plan = Plan()
    source_rel = check_relative(source_rel, "adoption source").as_posix()
    if source_rel == "public":
        source_rel = ""
    elif source_rel.startswith("public/"):
        source_rel = source_rel[len("public/"):]
    public = from_root / "public"
    source = public / Path(*PurePosixPath(source_rel).parts)
    if find_symlink(source, from_root) is not None or not is_inside(source, public):
        raise SporeError("adoption source uses a link or escapes public/: %s"
                         % source)
    if not source_rel or (not source.is_file() and not source.is_dir()):
        raise SporeError("adoption source must be an existing file or directory "
                         "under the source individual's public/ area")
    destination = check_relative(destination_rel, "adoption destination")
    if destination.parts[0] not in ADOPTION_DESTINATIONS:
        raise SporeError("destination must start with one of %s"
                         % ", ".join(ADOPTION_DESTINATIONS))
    target_base = mentor_research / Path(*destination.parts)

    if source.is_dir():
        collected = collect_unit_files(from_root, "public/" + source_rel)
        pairs = [(rel[len("public/" + source_rel + "/"):], data,
                  "%s/%s" % (destination.as_posix(),
                              rel[len("public/" + source_rel + "/"):]))
                 for rel, data in sorted(collected.items())]
        if not pairs:
            raise SporeError("adoption source directory is empty: %s" % source_rel)
    else:
        pairs = [(None, source.read_bytes(), destination.as_posix())]

    for rel, data, target_rel in pairs:
        plan.source(source if rel is None else source / Path(*PurePosixPath(rel).parts), data)
        target = mentor_research / Path(*PurePosixPath(target_rel).parts)
        issue = blocker(mentor_research, target)
        if issue:
            plan.conflict(issue)
            continue
        observed = observe(target)
        if target.is_file() and target.read_bytes() == data:
            plan.add(target_rel, target, data, "skip", observed=observed)
        elif target.exists() and not replace:
            plan.conflict("destination already differs: %s (pass --replace to "
                          "update it deliberately)" % target_rel)
        elif target.exists():
            plan.add(target_rel, target, data, "replace",
                     note="replaces existing content", observed=observed)
        else:
            plan.add(target_rel, target, data, "write", observed=observed)

    records = mentor_research / "history" / "ADOPTIONS.md"
    if not records.is_file():
        raise SporeError("adoption history is missing: %s" % records)
    stamp = utc_now()
    lines = ["", "## Adopted public submission — %s" % stamp[:10], "",
             "- Source: `%s/%s`" % (from_root.name, "public/" + source_rel),
             "- Destination(s): %s" % ", ".join(
                 "`research/%s`" % target_rel for _, _, target_rel in pairs),
             "- Recorded: %s" % stamp,
             "- This records selection and transfer; it is not a quality "
             "certificate and does not replace independent checking.",
             ""]
    text = records.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(lines)
    if any(item["mode"] != "skip" for item in plan.items) or plan.conflicts:
        plan.add("history/ADOPTIONS.md", records,
                 text.encode("utf-8"), "replace",
                 observed=("file", sha_file(records)))
    return plan
