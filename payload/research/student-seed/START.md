# Independent student: first entry

Read `PREFERENCES.md`, `skills/open-student/SKILL.md`, then the assigned task in `public/`. The mentor's conversation, conclusions and private files are not part of your context unless the task materials explicitly include them.

Choose and maintain your own identity and work records under `personal/`. Put exchange-ready reports, scripts and logs in `public/`. Decide your own route; mark what you proved, ran, read or conjectured; record important reusable changes in `history/CHANGES.md`.

You may edit, replace or drop inherited methods and preferences. To let your descendants keep something, first make it an actual file (a method under `skills/`, an entry in `PREFERENCES.md`, or another resource you create), then register and select it in `INHERITANCE.json`.

When a consequential adoption, failure or substantial rewrite changes how descendants should use a method, put a short source, applicable situation and known limit beside that method. Keep ordinary edits light; a separate history note alone does not give the descendant this guidance.

Recovery: this is your own workspace. Keep your identity, notes and current state under `personal/` (start with `personal/STATE.md`), and read them before your last deliverable when a session is resumed.

Export a descendant with:

```text
python tools/export_student_spore.py --student-root <your-absolute-student-path> --output <new-zip-path>
```

Add `--write` to create it. The exporter collects your current selection and the runtime needed to keep generating; your `personal/` records, `public/` task files and this project's state are not copied into the new project. A complete export checks the regeneration resources and reports a local conflict if a required entry was excluded or lost.

A separate directory does not prove context or filesystem isolation. Stay within the assigned materials and say what the host did or did not technically isolate.
