# 孢子包 {{version}}（{{profile}}）

本包由成熟个体按当前继承选择导出，属于**衍生包**：来源与父代记录见 `MANIFEST.json` 的 `parent` 字段。它不是重新通过正式验收的发行版，也不代表包内方法一定有效。

父代若携带个人偏好，所选 `PREFERENCES.md` 也会进入本包；对外分享前请检查它的内容与继承选择。

父代摘要：{{parentSummary}}  
导出时间（UTC）：{{builtAtUtc}}

## 安装

可直接告诉接收的 AI“在当前项目使用这个孢子”，由项目宿主查看现有项目后选择借用方法、无冲突安装、有界接管或暂不采用。脚本入口至少需要 Python 3.10；没有 Python 时可先阅读随包方法，手工复制须逐处检查同路径冲突，也不等于完成机械校验。

```text
python install.py --root <目标工作区>
python install.py --root <目标工作区> --write
```

第一条只显示计划，第二条在完整预检后写入。`{{profile}}` 配置把载荷安装到：

- 导师配置：`<目标>/research/`
- 学生配置：`<目标>/`（学生工作区根目录）

非空项目先预演：无同路径冲突时可安装，原有无关文件保留；已有不同内容会使整次安装拒绝写入。选择 `--host codex` 或 `--host claude` 时也要预览相应宿主入口的标记块；块内内容由安装器维护，重复安装时可被替换，块外内容保留。重复安装同一构建会保留个体目录中的本地修改与有意删除；不同构建会被拒绝并提示有界迁移，已有学生不随导师包重装。

## 安装后从哪里开始

- 导师：`research/WAKEUP.md`、`research/PROTOCOL.md`、`research/PREFERENCES.md`、`research/STATE.md`
- 学生：`START.md`、`PREFERENCES.md`、`skills/open-student/SKILL.md`、`public/` 中的任务

## 继续生成后代

- 导师：`python research/tools/spore.py --source-root <工作区> --output <新.zip> --write`
- 学生：`python tools/export_student_spore.py --student-root <学生工作区> --output <新.zip> --write`

导出只携带 `INHERITANCE.json` 中选择的内容，加上该 profile 继续生成所需的运行资源与空白模板；当前项目台账、个人记录、日志与交接回执不会进入新项目状态。

## 边界

- 文件清单与哈希只识别快照，不判断方法效果、结论正确性或伙伴独立性。
- 没有运行过的检查不会被写成已完成；本衍生包只声明已做的机械导出与安装检查。
- 手动复制（无 Python）时按 `MANUAL-L0.md` 操作，并如实说明未做机械校验。
