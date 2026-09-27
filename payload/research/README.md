# 导师个体说明

这个目录是一个可继续成长、可再生成后代的导师工作范式。`PROTOCOL.md` 与 `PREFERENCES.md` 分别保存通用方法与当前使用者的偏好，两者都可编辑；`INHERITANCE.json` 决定哪些内容进入后代。

这个私人版本已带有当前用户的偏好。导出或分享后代前，检查 `PREFERENCES.md` 的内容和继承选择；已有偏好不会因后来收到中性发行包而自动被覆盖。

## 在已有项目使用

项目宿主先看现有目录和规则，再决定只借用相关方法、对无同路径冲突的目录安装，还是对已有范式逐处作有界接管；也可以暂不采用。接收包时可先运行 `python <包根>/install.py --root <目标工作区>` 预演。已有不同内容会使整次安装拒绝写入；接管不靠重复安装自动完成。无关的项目文件仍归原项目所有，已有学生的身份、方法与记录也由其本人保留。

## 日常

- 入口：`WAKEUP.md`；当前任务状态：`STATE.md`。初次理解个体时读当前任务和必要的方法、偏好；短任务直接推进。台账按任务需要维护，不要求每轮全写。
- 能力与方法：`skills/`、`modules/`；模板：`templates/`。按需读取。
- 寻找可调用能力、调整继承或导出时再读 `INHERITANCE.json`；`use` 只是用途标注，不提供自动检索或调度。
- 历史：`history/`。历史说明来由，不自动成为当前规则。
- 备选材料：`archive/`。它们不是当前活动方法，也不要求每轮读取。

## 生成后代

```text
python tools/spore.py --source-root <本工作区> --output <新.zip>
python tools/spore.py --source-root <本工作区> --output <新.zip> --write
```

导出只收集 `INHERITANCE.json` 中选中的单元（`inherit` 为真，含 `requires` 依赖闭包），加上本 profile 继续生成所需的运行资源与空白模板；`use`（current/callable/archive）是用途标注，不改变选择结果。当前项目台账、交接回执与个人记录被重置。新增文件在清单中登记后即可继承，不需要祖先清单收录。

## 学生与采用

- 首次确实需要独立探索时：`python tools/first_student.py --student-root <绝对路径> --task-pack <任务文件>`（先预览，再 `--write`）。已存在的学生只接收新任务，不重装、不覆盖其方法。
- 观察报告：`python tools/record_student.py --report <学生 public/ 下的绝对路径>`；同一报告重复记录幂等，修订报告保留先前指纹。
- 采用公开方法：`python tools/adopt_student.py --student-root <来源个体> --source <public/ 下路径> --destination <modules|skills|templates|student-seed|archive 下路径>`；已有不同内容默认拒绝，确认后加 `--replace` 有意更新。

## 检查

```text
python tools/check.py --source-root <本工作区>
python tools/check.py --package <发行目录>
```

个体检查把有意修改和删除显示为差异；只有选中内容或某项操作实际需要的资源缺失才算故障。包检查要求清单、路径与哈希完全相符。两者都不判断研究结论、独立性或宿主权限。

## 边界

刻意修改任何文件（包括工具与模板）都被允许；哈希变化本身不会让工作区失效。导出、安装与交接的写入都走同一套“预览—完整预检—提交”实现，失败会回滚本次操作。
