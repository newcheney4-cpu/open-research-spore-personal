---
name: open-mentor
description: Use an independent student to explore a competing route or counterexample when it could change a substantive result, and to adopt reusable public submissions; not for routine short answers.
---

# Open mentor

Read the current state and the user's direction. Keep advancing the main deliverable while a student explores another route. Give the student the question, raw materials, decision criteria, authorization boundary and room to challenge the framing; do not prescribe the answer.

Use a student only when the distinct context, student-owned workspace and memory, and observable return justify the cost. Read `CAPABILITIES.md` and `modules/handoff.md` when the first handoff is actually needed; run `research/tools/first_student.py` in preview, then add `--write` for the authorized handoff. The tool prepares but does not launch, and each handoff gets its own receipt.

Record a received report with `research/tools/record_student.py --report <absolute path>`; host, session and model are included only when actually observed. Before relying on a result, check the decisive claim independently and record the verdict (`skills/adjudicate/SKILL.md`). A report alone proves output, not context or permission isolation.

## 采用公开提交

```text
python research/tools/adopt_student.py --student-root <学生根> --source <public/下路径> --destination <目标路径>
```

- 只读取来源个体的 `public/`；其个人区与当前任务状态不参与。
- 目标是本工作区 `modules/`、`skills/`、`templates/`、`student-seed/` 或 `archive/` 下的路径；目录来源会被整体复制。
- 已有不同内容默认拒绝；确认替换后加 `--replace`，工具会把来源、目标与时间记录到 `history/ADOPTIONS.md`。
- 采用只搬运字节并登记来源。语义合并、冲突处理和是否更新未来学生模板仍是一次正常编辑：先理解用途与局限，再改当前方法，最后按需要更新 `student-seed/`，让下一次新建学生获得改进；已有学生保留自己的版本。

采用不是质量证书，也不要求每次再向用户申请许可；在既有授权内由 AI 判断并记录理由。
