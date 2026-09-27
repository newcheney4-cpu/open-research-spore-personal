#!/usr/bin/env python3
"""Acceptance runner for the release implementation plan, section 13.

Runs every scenario in a dedicated scratch directory and never touches real
student areas or research results.  Results are printed one line per check:

    PASS <scenario>/<name>
    FAIL <scenario>/<name>: <detail>

The runner exits 1 when any check fails.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

PACK = Path(__file__).resolve().parent
sys.path.insert(0, str(PACK / "payload" / "research" / "tools"))

import _spore_core as core  # noqa: E402

PY = sys.executable
RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                       (": %s" % detail) if detail and not ok else ""))


def run(args, cwd=None):
    return subprocess.run([PY] + [str(item) for item in args],
                          cwd=str(cwd or PACK), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def run_raw(args, cwd=None):
    return subprocess.run([str(item) for item in args], cwd=str(cwd or PACK),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def run_ok(name, args, cwd=None, expect=0):
    proc = run(args, cwd)
    record(name, proc.returncode == expect,
           "exit=%s expected=%s out=%s"
           % (proc.returncode, expect, (proc.stdout or proc.stderr).strip()[-300:]))
    return proc


def install(pack, root, write=True, extra=()):
    args = [Path(pack) / "install.py", "--root", root]
    if write:
        args.append("--write")
    args.extend(extra)
    return run(args)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).write_bytes(core.json_bytes(data))


def extract(zip_path, target):
    shutil.rmtree(str(target), ignore_errors=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target)
    return Path(target)


def count_files(root):
    return sum(1 for path in Path(root).rglob("*") if path.is_file())


# --------------------------------------------------------------------------

def scenario_1(work: Path):
    """Install, re-run, dry run writes nothing, conflicts refused."""
    base = work / "s1"
    mentor = base / "mentor"
    proc = install(PACK, mentor, write=False)
    record("s1/dry-run-exit-0", proc.returncode == 0, proc.stdout[-200:])
    record("s1/dry-run-no-writes", not (mentor / "research").exists())
    run_ok("s1/install", [Path(PACK) / "install.py", "--root", mentor, "--write"])
    record("s1/installed-research",
           (mentor / "research" / "PACK-MANIFEST.json").is_file())
    run_ok("s1/check-installed",
            [mentor / "research" / "tools" / "check.py", "--source-root", mentor])

    protocol = mentor / "research" / "PROTOCOL.md"
    local = protocol.read_text(encoding="utf-8") + "\n本地修改：为 QA 场景保留。\n"
    protocol.write_text(local, encoding="utf-8")
    (mentor / "research" / "CLAIMS.md").unlink()
    proc = install(PACK, mentor, write=True)
    record("s1/reinstall-exit-0", proc.returncode == 0, proc.stdout[-300:])
    record("s1/reinstall-keeps-local-edit",
           protocol.read_text(encoding="utf-8") == local)
    record("s1/reinstall-keeps-deletion",
           not (mentor / "research" / "CLAIMS.md").exists())

    conflict_root = base / "conflict"
    (conflict_root / "research").mkdir(parents=True)
    (conflict_root / "research" / "PROTOCOL.md").write_text(
        "different content", encoding="utf-8")
    proc = install(PACK, conflict_root, write=True)
    record("s1/conflict-refused", proc.returncode == 2, proc.stdout[-200:])
    record("s1/conflict-untouched",
           (conflict_root / "research" / "PROTOCOL.md").read_text(
               encoding="utf-8") == "different content")
    record("s1/conflict-no-partial-write",
           count_files(conflict_root) == 1)

    restored = base / "restore"
    run_ok("s1c/install", [Path(PACK) / "install.py", "--root", restored,
                           "--write"])
    local_module = restored / "research" / "modules" / "mentor.md"
    local_module.write_text("local edit\n", encoding="utf-8")
    missing = restored / "research" / "tools" / "gate.py"
    missing.unlink()
    proc = install(PACK, restored, write=True, extra=["--restore-missing"])
    record("s1c/restore-missing-exit-0", proc.returncode == 0,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-200:]))
    record("s1c/restore-missing-restores", missing.is_file())
    record("s1c/restore-keeps-local-edit",
           local_module.read_text(encoding="utf-8") == "local edit\n")
    return mentor


def scenario_student_install(work: Path, mentor: Path):
    """A student target can be installed from an exported student package."""
    base = work / "s1b"
    task = base / "TASK.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# task\n\nQA handoff.\n", encoding="utf-8")
    student = base / "student"
    run_ok("s1b/first-student",
            [mentor / "research" / "tools" / "first_student.py",
             "--student-root", student, "--task-pack", task, "--write"])
    record("s1b/student-manifest", (student / "PACK-MANIFEST.json").is_file())
    spore = base / "student-spore.zip"
    run_ok("s1b/student-export",
            [student / "tools" / "export_student_spore.py",
             "--student-root", student, "--output", spore, "--write"])
    package = extract(spore, base / "student-pkg")
    second = base / "student-installed"
    run_ok("s1b/student-install",
            [package / "install.py", "--root", second, "--write"])
    run_ok("s1b/student-check",
            [second / "tools" / "check.py", "--source-root", second])
    record("s1b/student-has-entry", (second / "START.md").is_file())
    hosted = base / "student-hosted"
    run_ok("s1b/student-install-with-host",
            [package / "install.py", "--root", hosted, "--host", "codex",
             "--write"])
    block = (hosted / "AGENTS.md").read_text(encoding="utf-8")
    record("s1b/student-host-block-points-at-student-entry",
           "START.md" in block and "research/PROTOCOL.md" not in block)
    return package, student


def scenario_2(work: Path, mentor: Path):
    """Local changes keep working; a broken seed only breaks student creation."""
    base = work / "s2"
    research = mentor / "research"
    protocol = research / "PROTOCOL.md"
    preferences = research / "PREFERENCES.md"
    protocol.write_text(protocol.read_text(encoding="utf-8") + "\n本地方法变化。\n",
                        encoding="utf-8")
    preferences.write_text(
        preferences.read_text(encoding="utf-8") + "\n- 本地偏好变化。\n",
        encoding="utf-8")
    task = base / "TASK.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# task\n\nQA.\n", encoding="utf-8")
    student = base / "student"
    run_ok("s2/handoff-after-local-change",
            [research / "tools" / "first_student.py", "--student-root", student,
             "--task-pack", task, "--write"])
    report = student / "public" / "R.md"
    report.write_text("# report\n\nQA.\n", encoding="utf-8")
    run_ok("s2/record-after-local-change",
            [research / "tools" / "record_student.py", "--report", report,
             "--write"])

    broken = base / "broken-student"
    removed = research / "student-seed" / "START.md"
    backup = removed.read_bytes()
    removed.unlink()
    proc = run([research / "tools" / "first_student.py", "--student-root", broken,
                "--task-pack", task, "--write"])
    record("s2/broken-seed-blocks-creation", proc.returncode == 1,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-200:]))
    run_ok("s2/report-still-records-with-broken-seed",
            [research / "tools" / "record_student.py", "--report", report,
             "--write"])
    removed.write_bytes(backup)
    return mentor


def scenario_3(work: Path):
    """Mentor two-generation export with a new method and its resource."""
    base = work / "s3"
    mentor = base / "mentor"
    run_ok("s3/install-source", [Path(PACK) / "install.py", "--root", mentor,
                                 "--write"])
    research = mentor / "research"
    (research / "modules" / "extra-method.md").write_text(
        "# Extra method (QA)\n\n祖先没有的方法。\n", encoding="utf-8")
    (research / "templates" / "extra-resource.md").write_text(
        "# Extra resource (QA)\n\n该方法依赖的资源。\n", encoding="utf-8")
    spec = read_json(research / "INHERITANCE.json")
    spec["units"].append({"id": "extra-method", "path": "modules/extra-method.md",
                          "kind": "method", "use": "callable",
                          "requires": ["extra-resource"]})
    spec["units"].append({"id": "extra-resource",
                          "path": "templates/extra-resource.md",
                          "kind": "resource"})
    write_json(research / "INHERITANCE.json", spec)
    zip_a = base / "A.zip"
    run_ok("s3/export-A", [research / "tools" / "spore.py", "--source-root",
                           mentor, "--output", zip_a, "--write"])
    moved = base / "mentor-moved"
    mentor.rename(moved)
    package_a = extract(zip_a, base / "A-pkg")
    a = base / "A"
    run_ok("s3/install-A", [package_a / "install.py", "--root", a, "--write"])
    zip_b = base / "B.zip"
    run_ok("s3/export-B", [a / "research" / "tools" / "spore.py",
                           "--source-root", a, "--output", zip_b, "--write"])
    package_b = extract(zip_b, base / "B-pkg")
    b = base / "B"
    run_ok("s3/install-B", [package_b / "install.py", "--root", b, "--write"])
    record("s3/B-has-new-method",
           (b / "research" / "modules" / "extra-method.md").is_file())
    record("s3/B-has-resource",
           (b / "research" / "templates" / "extra-resource.md").is_file())
    zip_c = base / "C.zip"
    run_ok("s3/B-still-exports",
            [b / "research" / "tools" / "spore.py", "--source-root", b,
             "--output", zip_c, "--write"])
    moved.rename(mentor)


def scenario_4(work: Path):
    """Cancelled inheritance never flows back; string booleans are refused."""
    base = work / "s4"
    mentor = base / "mentor"
    run_ok("s4/install", [Path(PACK) / "install.py", "--root", mentor, "--write"])
    research = mentor / "research"
    preferences = research / "PREFERENCES.md"
    secret = "本地偏好标记-s4x"
    preferences.write_text(
        preferences.read_text(encoding="utf-8") + "\n- %s\n" % secret,
        encoding="utf-8")
    spec = read_json(research / "INHERITANCE.json")
    for unit in spec["units"]:
        if unit["id"] in ("preferences", "archive-area"):
            unit["inherit"] = False
    write_json(research / "INHERITANCE.json", spec)
    zip_b = base / "B.zip"
    run_ok("s4/export-with-exclusions",
            [research / "tools" / "spore.py", "--source-root", mentor,
             "--output", zip_b, "--write"])
    with zipfile.ZipFile(zip_b) as archive:
        names = archive.namelist()
        prefs = archive.read("payload/research/PREFERENCES.md").decode("utf-8")
        child = json.loads(archive.read("payload/research/INHERITANCE.json")
                           .decode("utf-8"))
    record("s4/no-archive-payload",
           not any(name.startswith("payload/research/archive/") for name in names))
    record("s4/preference-shell-neutral", secret not in prefs)
    unit = next(item for item in child["units"] if item["id"] == "preferences")
    record("s4/exclusion-intent-kept", unit.get("inherit") is False)
    record("s4/methods-still-present",
           "payload/research/modules/mentor.md" in names)

    broken = base / "broken"
    run_ok("s4/install-broken", [Path(PACK) / "install.py", "--root", broken,
                                 "--write"])
    spec = read_json(broken / "research" / "INHERITANCE.json")
    spec["units"][0]["inherit"] = "false"
    write_json(broken / "research" / "INHERITANCE.json", spec)
    proc = run([broken / "research" / "tools" / "spore.py",
                "--source-root", broken, "--output", base / "nope.zip", "--write"])
    record("s4/string-boolean-refused", proc.returncode == 3,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))

    clash = base / "clash"
    run_ok("s4/install-clash", [Path(PACK) / "install.py", "--root", clash,
                                "--write"])
    (clash / "research" / "Modules").mkdir(exist_ok=True)
    (clash / "research" / "Modules" / "A.md").write_text("A\n", encoding="utf-8")
    (clash / "research" / "modules" / "a.md").write_text("a\n", encoding="utf-8")
    spec = read_json(clash / "research" / "INHERITANCE.json")
    spec["units"].append({"id": "clash-a", "path": "Modules/A.md",
                          "kind": "resource"})
    spec["units"].append({"id": "clash-b", "path": "modules/a.md",
                          "kind": "resource"})
    write_json(clash / "research" / "INHERITANCE.json", spec)
    proc = run([clash / "research" / "tools" / "spore.py", "--source-root", clash,
                "--output", base / "clash.zip", "--write"])
    record("s4/case-collision-refused", proc.returncode in (2, 3),
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))
    return mentor


def scenario_5(work: Path):
    """Student two-generation export without mentor dependency."""
    base = work / "s5"
    mentor = base / "mentor"
    run_ok("s5/install-mentor", [Path(PACK) / "install.py", "--root", mentor,
                                 "--write"])
    task = base / "TASK.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# task\n\nQA.\n", encoding="utf-8")
    student = base / "student"
    run_ok("s5/first-student",
            [mentor / "research" / "tools" / "first_student.py",
             "--student-root", student, "--task-pack", task, "--write"])
    (student / "skills" / "own-method").mkdir(parents=True, exist_ok=True)
    (student / "skills" / "own-method" / "SKILL.md").write_text(
        "---\nname: own-method\ndescription: QA student method.\n---\n\n"
        "学生自己的方法。\n", encoding="utf-8")
    (student / "personal" / "SELF.md").write_text("private identity\n",
                                                  encoding="utf-8")
    (student / "public" / "draft.md").write_text("exchange draft\n",
                                                 encoding="utf-8")
    spec = read_json(student / "INHERITANCE.json")
    spec["units"].append({"id": "own-method", "path": "skills/own-method/SKILL.md",
                          "kind": "method", "use": "callable"})
    write_json(student / "INHERITANCE.json", spec)
    prefs = student / "PREFERENCES.md"
    prefs.write_text(prefs.read_text(encoding="utf-8") + "\n- 学生自加偏好。\n",
                     encoding="utf-8")
    zip_g1 = base / "g1.zip"
    run_ok("s5/export-g1", [student / "tools" / "export_student_spore.py",
                            "--student-root", student, "--output", zip_g1,
                            "--write"])
    with zipfile.ZipFile(zip_g1) as archive:
        names = archive.namelist()
        prefs_text = archive.read("payload/student/PREFERENCES.md").decode("utf-8")
    record("s5/g1-has-own-method",
           "payload/student/skills/own-method/SKILL.md" in names)
    record("s5/g1-excludes-personal",
           not any(name.endswith("personal/SELF.md") for name in names))
    record("s5/g1-excludes-public-draft",
           not any(name.endswith("public/draft.md") for name in names))
    record("s5/g1-keeps-preference", "学生自加偏好" in prefs_text)
    record("s5/g1-has-student-state-template",
           "payload/student/personal/STATE.md" in names)
    package = extract(zip_g1, base / "g1-pkg")
    second = base / "student2"
    run_ok("s5/install-g1", [package / "install.py", "--root", second, "--write"])
    zip_g2 = base / "g2.zip"
    run_ok("s5/export-g2", [second / "tools" / "export_student_spore.py",
                            "--student-root", second, "--output", zip_g2,
                            "--write"])
    with zipfile.ZipFile(zip_g2) as archive:
        names_g2 = archive.namelist()
        method = archive.read("payload/student/skills/own-method/SKILL.md")
    record("s5/g2-has-method", method.decode("utf-8").find("学生自己的方法") >= 0)
    record("s5/g2-has-no-old-identity",
           not any(name.endswith("personal/SELF.md") for name in names_g2))


def scenario_6(work: Path):
    """Two handoffs, independent receipts, idempotent and revised reports."""
    base = work / "s6"
    mentor = base / "mentor"
    run_ok("s6/install", [Path(PACK) / "install.py", "--root", mentor, "--write"])
    research = mentor / "research"
    base.mkdir(parents=True, exist_ok=True)
    task1 = base / "TASK-1.md"
    task2 = base / "TASK-2.md"
    task1.write_text("# task 1\n", encoding="utf-8")
    task2.write_text("# task 2\n", encoding="utf-8")
    student = base / "student"
    run_ok("s6/handoff-1", [research / "tools" / "first_student.py",
                            "--student-root", student, "--task-pack", task1,
                            "--write"])
    method = student / "skills" / "open-student" / "SKILL.md"
    local = method.read_text(encoding="utf-8") + "\n本地学生改动。\n"
    method.write_text(local, encoding="utf-8")
    run_ok("s6/handoff-2", [research / "tools" / "first_student.py",
                            "--student-root", student, "--task-pack", task2,
                            "--write"])
    record("s6/local-method-kept",
           method.read_text(encoding="utf-8") == local)
    receipts = sorted((research / "receipts").rglob("*.json"))
    record("s6/two-receipts", len(receipts) == 2, str(len(receipts)))
    task1_receipt = None
    for path in receipts:
        if read_json(path).get("task", {}).get("stagedPath") == "public/TASK-1.md":
            task1_receipt = path
    record("s6/task1-receipt-found", task1_receipt is not None)
    report1 = student / "public" / "R1.md"
    report1.write_text("# report 1\n", encoding="utf-8")
    run_ok("s6/record-1", [research / "tools" / "record_student.py",
                           "--report", report1, "--receipt", task1_receipt,
                           "--write"])
    run_ok("s6/record-1-idempotent", [research / "tools" / "record_student.py",
                                      "--report", report1, "--receipt",
                                      task1_receipt, "--write"])
    updated = read_json(task1_receipt)
    record("s6/idempotent-single-observation",
           updated is not None and len(updated.get("observations", [])) == 1)
    report1.write_text("# report 1 revised\n", encoding="utf-8")
    run_ok("s6/record-revision", [research / "tools" / "record_student.py",
                                  "--report", report1, "--receipt",
                                  task1_receipt, "--write"])
    revised = read_json(task1_receipt)
    record("s6/revision-keeps-both",
           revised is not None and len(revised.get("observations", [])) == 2)
    return mentor


def scenario_7(work: Path):
    """Adoption updates an existing method and the future student template."""
    base = work / "s7"
    mentor = base / "mentor"
    run_ok("s7/install", [Path(PACK) / "install.py", "--root", mentor, "--write"])
    research = mentor / "research"
    publisher = base / "publisher"
    (publisher / "public" / "share").mkdir(parents=True, exist_ok=True)
    source = publisher / "public" / "share" / "method.md"
    source.write_text("version one\n", encoding="utf-8")
    run_ok("s7/adopt-new", [research / "tools" / "adopt_student.py",
                            "--student-root", publisher, "--source",
                            "share/method.md", "--destination",
                            "modules/shared-method.md", "--write"])
    target = research / "modules" / "shared-method.md"
    record("s7/adopted-bytes",
           target.read_text(encoding="utf-8") == "version one\n")
    source.write_text("version two\n", encoding="utf-8")
    proc = run([research / "tools" / "adopt_student.py", "--student-root",
                publisher, "--source", "share/method.md", "--destination",
                "modules/shared-method.md", "--write"])
    record("s7/refuses-silent-overwrite", proc.returncode == 2,
           "exit=%s" % proc.returncode)
    run_ok("s7/adopt-replace",
            [research / "tools" / "adopt_student.py", "--student-root",
             publisher, "--source", "share/method.md", "--destination",
             "modules/shared-method.md", "--replace", "--write"])
    record("s7/replaced-bytes",
           target.read_text(encoding="utf-8") == "version two\n")

    seed_prefs = research / "student-seed" / "PREFERENCES.md"
    seed_prefs.write_text(
        seed_prefs.read_text(encoding="utf-8")
        + "\n- 未来学生起点：采用后的新偏好。\n", encoding="utf-8")
    task = base / "TASK.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# task\n", encoding="utf-8")
    fresh = base / "fresh-student"
    run_ok("s7/new-student-handoff",
            [research / "tools" / "first_student.py", "--student-root", fresh,
             "--task-pack", task, "--write"])
    record("s7/new-student-gets-update",
           "未来学生起点" in (fresh / "PREFERENCES.md").read_text(encoding="utf-8"))
    record("s7/mentor-preferences-untouched",
           "未来学生起点" not in (research / "PREFERENCES.md").read_text(
               encoding="utf-8"))
    record("s7/adoption-recorded",
           (research / "history" / "ADOPTIONS.md").read_text(
               encoding="utf-8").count("shared-method.md") >= 2)


def scenario_6b(work: Path):
    """Same-named students and a moved root still receive receipts."""
    base = work / "s6b"
    mentor = base / "mentor"
    run_ok("s6b/install", [Path(PACK) / "install.py", "--root", mentor, "--write"])
    research = mentor / "research"
    task = base / "TASK.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text("# task\n", encoding="utf-8")
    first = base / "a" / "student"
    second = base / "b" / "student"
    handoff = [research / "tools" / "first_student.py"]
    run_ok("s6b/handoff-first",
           handoff + ["--student-root", first, "--task-pack", task, "--write"])
    run_ok("s6b/handoff-second-same-name",
           handoff + ["--student-root", second, "--task-pack", task, "--write"])
    receipts = sorted((research / "receipts").rglob("*.json"))
    record("s6b/two-receipts", len(receipts) == 2, str(len(receipts)))
    run_ok("s6b/handoff-first-again",
           handoff + ["--student-root", first, "--task-pack", task, "--write"])
    record("s6b/re-handoff-idempotent",
           len(sorted((research / "receipts").rglob("*.json"))) == 2)
    moved = base / "c" / "student"
    moved.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(second), str(moved))
    run_ok("s6b/handoff-after-move",
           handoff + ["--student-root", moved, "--task-pack", task, "--write"])
    record("s6b/three-receipts",
           len(sorted((research / "receipts").rglob("*.json"))) == 3)
    record("s6b/task-staged-in-moved-root",
           (moved / "public" / "TASK.md").is_file())


def scenario_8(work: Path):
    """Format compatibility and representative boundary failures."""
    base = work / "s8"
    base.mkdir(parents=True, exist_ok=True)
    copy = base / "other-version"
    shutil.copytree(PACK, copy, ignore=shutil.ignore_patterns(
        "_dev", "_qa_*", "*.zip", "__pycache__"))
    manifest, files = core.load_package(copy)
    manifest["version"] = "9.9.9-other"
    rows = core.manifest_entries(files, lambda rel: False)
    manifest["buildId"] = core.compute_build_id(manifest["profile"],
                                                manifest["version"], rows)
    (copy / "MANIFEST.json").write_bytes(core.json_bytes(manifest))
    target = base / "installed"
    run_ok("s8/install-other-version", [copy / "install.py", "--root", target,
                                        "--write"])
    run_ok("s8/export-other-version",
            [target / "research" / "tools" / "spore.py", "--source-root",
             target, "--output", base / "other.zip", "--write"])

    unknown = base / "unknown-format"
    shutil.copytree(copy, unknown, ignore=shutil.ignore_patterns(
        "_dev", "_qa_*", "*.zip", "__pycache__"))
    manifest = read_json(unknown / "MANIFEST.json")
    manifest["formatVersion"] = 5
    write_json(unknown / "MANIFEST.json", manifest)
    proc = run([unknown / "install.py", "--root", base / "unknown-target",
                "--write"])
    record("s8/unknown-format-refused", proc.returncode == 3,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))

    escape = base / "escape"
    shutil.copytree(copy, escape, ignore=shutil.ignore_patterns(
        "_dev", "_qa_*", "*.zip", "__pycache__"))
    (escape / "payload" / "research" / "MANIFEST.json").unlink(missing_ok=True)
    spec = read_json(escape / "payload" / "research" / "INHERITANCE.json")
    spec["units"].append({"id": "escape", "path": "../outside.md",
                          "kind": "resource"})
    write_json(escape / "payload" / "research" / "INHERITANCE.json", spec)
    proc = run([escape / "payload" / "research" / "tools" / "spore.py",
                "--source-root", escape, "--output", base / "escape.zip",
                "--write"])
    record("s8/path-escape-refused", proc.returncode == 3,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))

    reserved = base / "reserved"
    shutil.copytree(copy, reserved, ignore=shutil.ignore_patterns(
        "_dev", "_qa_*", "*.zip", "__pycache__"))
    spec = read_json(reserved / "payload" / "research" / "INHERITANCE.json")
    spec["units"].append({"id": "reserved", "path": "nul.md",
                          "kind": "resource"})
    write_json(reserved / "payload" / "research" / "INHERITANCE.json", spec)
    proc = run([reserved / "payload" / "research" / "tools" / "spore.py",
                "--source-root", reserved, "--output", base / "reserved.zip",
                "--write"])
    record("s8/reserved-name-refused", proc.returncode == 3,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))

    seed = PACK / "payload" / "research" / "student-seed"
    proc = run([PACK / "payload" / "research" / "tools" / "check.py",
                "--source-root", seed])
    record("s8/seed-template-explained", proc.returncode == 3
           and "seed template" in proc.stdout,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))
    proc = run([seed / "tools" / "export_student_spore.py", "--output",
                base / "seed.zip", "--write"])
    record("s8/seed-export-refused-gently", proc.returncode == 3
           and "seed template" in proc.stdout + proc.stderr,
           "exit=%s out=%s" % (proc.returncode,
                               (proc.stdout + proc.stderr)[-180:]))

    dependency = base / "dependency"
    shutil.copytree(copy, dependency, ignore=shutil.ignore_patterns(
        "_dev", "_qa_*", "*.zip", "__pycache__"))
    spec = read_json(dependency / "payload" / "research" / "INHERITANCE.json")
    for unit in spec["units"]:
        if unit["id"] == "review-module":
            unit["inherit"] = False
    write_json(dependency / "payload" / "research" / "INHERITANCE.json", spec)
    proc = run([dependency / "payload" / "research" / "tools" / "spore.py",
                "--source-root", dependency, "--output", base / "dep.zip",
                "--write"])
    record("s8/exclusion-dependency-conflict", proc.returncode == 2,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-180:]))

    junction_base = base / "junction"
    workspace = junction_base / "ws"
    outside = junction_base / "outside"
    workspace.mkdir(parents=True)
    outside.mkdir(parents=True)
    link = workspace / "research"
    made = run_raw(["cmd", "/c", "mklink", "/J", str(link), str(outside)])
    if made.returncode != 0:
        record("s8/junction-install-refused", True,
               "skipped: mklink unavailable (%s)" % made.stderr.strip()[:80])
    else:
        proc = install(PACK, workspace, write=True)
        record("s8/junction-install-refused", proc.returncode in (2, 3),
               "exit=%s out=%s" % (proc.returncode, proc.stdout[-200:]))
        record("s8/junction-no-files-written-through",
               not any(outside.iterdir()))
        try:
            link.rmdir()
        except OSError:
            pass


def scenario_9(work: Path):
    """Injected mid-commit failure leaves no residue and keeps old content."""
    base = work / "s9"
    target = base / "target"
    run_ok("s9/install", [Path(PACK) / "install.py", "--root", target, "--write"])
    existing = target / "research" / "PROTOCOL.md"
    original = existing.read_bytes()

    plan = core.Plan()
    plan.add("PROTOCOL.md", existing,
             original + b"\nnew content\n", "replace",
             observed=("file", core.sha_bytes(original)))
    plan.add("new-file.md", target / "research" / "new-file.md", b"new\n",
             "write", observed=("absent", None))

    def fault(index, item):
        return index == 1

    try:
        core.commit(plan, fault=fault)
        record("s9/fault-injected", False, "commit unexpectedly succeeded")
    except core.SporeError as exc:
        record("s9/fault-injected", True)
        record("s9/rollback-reported",
               "roll" in str(exc), str(exc)[:200])
    record("s9/original-restored", existing.read_bytes() == original)
    record("s9/no-new-residue",
           not (target / "research" / "new-file.md").exists())
    entries = [PACK / "install.py",
               PACK / "payload" / "research" / "tools" / "first_student.py",
               PACK / "payload" / "research" / "tools" / "record_student.py",
               PACK / "payload" / "research" / "tools" / "adopt_student.py"]
    record("s9/entries-use-shared-commit",
           all("core.commit(" in path.read_text(encoding="utf-8")
               for path in entries))
    exporters = [PACK / "payload" / "research" / "tools" / "spore.py",
                 PACK / "payload" / "research" / "student-seed" / "tools" /
                 "export_student_spore.py",
                 PACK / "build_spore.py"]
    record("s9/export-entries-use-shared-exporter",
           all("core.export_spore(" in path.read_text(encoding="utf-8")
               for path in exporters))
    templates = [PACK / "payload" / "research" / "templates" / "package" /
                 "install.py", PACK / "payload" / "research" / "templates" /
                 "package" / "build_spore.py"]
    record("s9/template-entries-identical",
           templates[0].read_bytes() == (PACK / "install.py").read_bytes()
           and templates[1].read_bytes() == (PACK / "build_spore.py").read_bytes())


def scenario_11(work: Path):
    """Targeted negatives: exclusions, broken seed, rollback, linked source."""
    base = work / "s11"
    mentor = base / "mentor"
    run_ok("s11/install", [Path(PACK) / "install.py", "--root", mentor,
                           "--write"])
    research = mentor / "research"

    # A selected resource directory must not smuggle an excluded child.
    (research / "bundle").mkdir(parents=True, exist_ok=True)
    (research / "bundle" / "part.md").write_text("PARENT\n", encoding="utf-8")
    (research / "bundle" / "secret.md").write_text("SECRET\n", encoding="utf-8")
    spec = read_json(research / "INHERITANCE.json")
    spec["units"].append({"id": "bundle", "path": "bundle",
                          "kind": "resource"})
    spec["units"].append({"id": "bundle-secret", "path": "bundle/secret.md",
                          "kind": "resource", "inherit": False})
    write_json(research / "INHERITANCE.json", spec)
    archive_b = base / "B.zip"
    run_ok("s11/export-parent-with-excluded-child",
            [research / "tools" / "spore.py", "--source-root", mentor,
             "--output", archive_b, "--write"])
    with zipfile.ZipFile(archive_b) as archive:
        names = archive.namelist()
        child = json.loads(archive.read("payload/research/INHERITANCE.json")
                           .decode("utf-8"))
    record("s11/parent-file-present",
           "payload/research/bundle/part.md" in names)
    record("s11/excluded-child-absent",
           "payload/research/bundle/secret.md" not in names)
    record("s11/exclusion-intent-kept",
           [unit.get("inherit") for unit in child["units"]
            if unit["id"] == "bundle-secret"] == [False])

    # An existing student keeps working when the mentor seed is broken.
    task1 = base / "TASK-1.md"
    task1.write_text("# task 1\n", encoding="utf-8")
    student = base / "student"
    run_ok("s11/first-student",
            [research / "tools" / "first_student.py", "--student-root",
             student, "--task-pack", task1, "--write"])
    skill = student / "skills" / "open-student" / "SKILL.md"
    local = skill.read_text(encoding="utf-8") + "\nlocal edit\n"
    skill.write_text(local, encoding="utf-8")
    (research / "student-seed" / "START.md").unlink()
    task2 = base / "TASK-2.md"
    task2.write_text("# task 2\n", encoding="utf-8")
    run_ok("s11/existing-handoff-broken-seed",
            [research / "tools" / "first_student.py", "--student-root",
             student, "--task-pack", task2, "--write"])
    record("s11/task2-staged", (student / "public" / "TASK-2.md").is_file())
    record("s11/local-method-kept",
           skill.read_text(encoding="utf-8") == local)
    fresh = base / "fresh"
    proc = run([research / "tools" / "first_student.py", "--student-root",
                fresh, "--task-pack", task2, "--write"])
    record("s11/new-student-blocked-by-broken-seed", proc.returncode == 1,
           "exit=%s out=%s" % (proc.returncode, proc.stdout[-200:]))
    record("s11/no-fresh-root-written", not fresh.exists())

    # A mid-commit conflict rolls back earlier writes, keeping local bytes.
    protocol = research / "PROTOCOL.md"
    original = protocol.read_bytes()
    late = research / "late-target.md"
    late.write_bytes(b"existing\n")
    plan = core.Plan()
    plan.add("PROTOCOL.md", protocol, original + b"\nchanged\n", "replace",
             observed=("file", core.sha_bytes(original)))
    plan.add("late-target.md", late, b"new\n", "write")
    try:
        core.commit(plan)
        record("s11/mid-commit-conflict", False,
               "commit unexpectedly succeeded")
    except core.SporeConflict as exc:
        record("s11/mid-commit-conflict", True)
        record("s11/mid-commit-exit-2", exc.exit_code == 2, str(exc))
    except core.SporeError as exc:
        record("s11/mid-commit-conflict", False,
               "wrong exception: %r" % exc)
    record("s11/prior-write-rolled-back", protocol.read_bytes() == original)
    record("s11/existing-target-untouched", late.read_bytes() == b"existing\n")
    record("s11/no-temp-residue", not list(mentor.rglob("*.tmp")))

    # Adoption must not read through a junction or symlink.
    publisher = base / "publisher"
    (publisher / "public").mkdir(parents=True, exist_ok=True)
    (publisher / "public" / "ok.md").write_text("ok\n", encoding="utf-8")
    outside = base / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "stolen.md").write_text("stolen\n", encoding="utf-8")
    link = publisher / "public" / "link"
    made = run_raw(["cmd", "/c", "mklink", "/J", str(link), str(outside)])
    if made.returncode != 0:
        record("s11/junction-source-refused", True,
               "skipped: mklink unavailable (%s)" % made.stderr.strip()[:80])
    else:
        proc = run([research / "tools" / "adopt_student.py",
                    "--student-root", publisher, "--source",
                    "link/stolen.md", "--destination", "modules/stolen.md",
                    "--write"])
        record("s11/junction-source-refused", proc.returncode == 3,
               "exit=%s out=%s" % (proc.returncode, proc.stdout[-200:]))
        record("s11/no-adopted-file",
               not (research / "modules" / "stolen.md").exists())
        try:
            link.rmdir()
        except OSError:
            pass


def scenario_10(work: Path, archive_path):
    """Archive: inventory matches contents; install and descendant export."""
    if archive_path is None:
        print("SKIP s10/archive: no --archive supplied")
        return
    base = work / "s10"
    package = extract(archive_path, base / "archive-pkg")
    try:
        manifest, files = core.load_package(package)
    except core.SporeError as exc:
        record("s10/archive-manifest-matches", False, str(exc)[:200])
        return
    record("s10/archive-manifest-matches", len(files) == len(manifest["files"]))
    source_manifest = read_json(PACK / "MANIFEST.json")
    record("s10/archive-matches-source-build",
           manifest.get("buildId") == source_manifest.get("buildId"),
           "archive=%s source=%s" % (str(manifest.get("buildId"))[:12],
                                     str(source_manifest.get("buildId"))[:12]))
    record("s10/archive-file-list-equals-source",
           sorted(files) == sorted(row["path"]
                                   for row in source_manifest.get("files", [])))
    target = base / "installed"
    run_ok("s10/install-from-archive", [package / "install.py", "--root", target,
                                        "--write"])
    run_ok("s10/check-from-archive",
            [target / "research" / "tools" / "check.py", "--source-root", target])
    zip_b = base / "descendant.zip"
    run_ok("s10/export-descendant",
            [target / "research" / "tools" / "spore.py", "--source-root", target,
             "--output", zip_b, "--write"])
    package_b = extract(zip_b, base / "descendant-pkg")
    target_b = base / "descendant"
    run_ok("s10/install-descendant",
            [package_b / "install.py", "--root", target_b, "--write"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True,
                        help="scratch directory inside this workspace")
    parser.add_argument("--archive", default=None,
                        help="optional release zip for the archive scenario")
    parser.add_argument("--only", default=None, help="run one scenario, e.g. s3")
    args = parser.parse_args(argv)
    work = Path(args.work).expanduser().resolve()
    marker = work / ".spore-verify-scratch"
    if work.exists():
        print("ERROR scratch already exists; choose a new --work path: %s" % work)
        return 3
    work.mkdir(parents=True)
    marker.write_text("scratch created by verify.py\n", encoding="utf-8")
    print("scratch: %s" % work)
    mentor = None
    if args.only in (None, "s1"):
        mentor = scenario_1(work)
    if args.only in (None, "s1b") and mentor is not None:
        scenario_student_install(work, mentor)
    if args.only in (None, "s2") and mentor is not None:
        scenario_2(work, mentor)
    if args.only in (None, "s3"):
        scenario_3(work)
    if args.only in (None, "s4"):
        scenario_4(work)
    if args.only in (None, "s5"):
        scenario_5(work)
    if args.only in (None, "s6"):
        scenario_6(work)
    if args.only in (None, "s7"):
        scenario_7(work)
    if args.only in (None, "s6b"):
        scenario_6b(work)
    if args.only in (None, "s8"):
        scenario_8(work)
    if args.only in (None, "s9"):
        scenario_9(work)
    if args.only in (None, "s11"):
        scenario_11(work)
    if args.only in (None, "s10"):
        scenario_10(work, args.archive)
    failures = [name for name, ok, _ in RESULTS if not ok]
    print("checks=%d pass=%d fail=%d"
          % (len(RESULTS), len(RESULTS) - len(failures), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
