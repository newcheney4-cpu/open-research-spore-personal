# Open Research Spore 2.2.0+personal.1

**私人偏好版。** 此包把当前用户已保存的导师偏好放回 `payload/research/PREFERENCES.md`，供其本人使用；分享本包或由它导出的后代前，应检查偏好是否适合随包传播。需要中性起点时使用 `open-research-spore-v2.2.0.zip`。本包与中性版有不同的构建 ID 和 ZIP 哈希，不能把二者当作同一验收对象。

Open Research Spore is an editable research workflow that can be installed in a project and exported into new mentor or student packages. The project host decides how much of it to adopt; installation alone does not establish independent execution or research effectiveness.

一个可以萌发、在工作中成长、并继续生成后代的研究工作范式。它保留证据诚实、主动证伪、裁定更正与自主推进；工作强度随问题变化，不设固定阶段数、伙伴数或逐轮审计。

本目录包含 2.2.0 的偏好变体封装源码，按 `LICENSE` 的 CC BY-NC-SA 4.0 条款提供（署名—非商业性使用—相同方式共享，非 OSI 开源许可）。当前验证状态与未验证范围见 `VERIFICATION.md`，包级认定见 `CERTIFICATE.md`；最终 ZIP 的哈希和运行记录保存在归档旁及包外。本变体随其独立仓库公开（`open-research-spore-personal`），tag 为 `v2.2.0-personal.1`。

## 开始使用

直接对接收的 AI 说“在当前项目使用这个孢子”即可。项目宿主先看项目已有的目录与规则，再决定：只借用相关方法；在无同路径冲突时安装；对已有范式逐处有界接管；或暂不采用。轻试用只需阅读相关方法，无须声称已经安装。

选择安装时先预演，再根据结果写入：

```text
python install.py --root <目标工作区>
python install.py --root <目标工作区> --write
```

第一条只显示计划，第二条在完整预检后写入。非空项目中无关文件保留；若同路径已有不同内容，整次安装拒绝写入。已有个体来自不同构建时也拒绝重复安装，须由宿主按需迁移。选择 `--host codex` 或 `--host claude` 时，预演还会显示对相应宿主入口标记块的改动；块内内容由安装器维护，重复安装时可被替换，块外内容保留。已有范式的身份、方法和记录不由安装器决定。安装不联网，不安装修复，不改全局配置。

脚本路径至少需要 Python 3.10；没有 Python 时可按 `payload/research/MANUAL-L0.md` 使用文件路径。实际运行过的系统与版本仅以本版验收记录为准。

## 安装后从哪里开始

- 导师工作区：`research/WAKEUP.md` → 当前任务及必要的 `research/PROTOCOL.md`、`research/PREFERENCES.md`、`research/STATE.md`、技能与材料；后续短任务直接推进。
- 学生工作区：`START.md` → `PREFERENCES.md`、`skills/open-student/SKILL.md`，以及 `public/` 中的任务包。

寻找可调用能力、调整继承或导出时再读 `INHERITANCE.json`。其 `use: current/callable/archive` 只是描述，不提供自动检索或调度。

## 成长与繁殖

- 方法与偏好分开维护：`PROTOCOL.md` 是通用方法，`PREFERENCES.md` 是当前个性化偏好，两者都可改、可删、可停用。本私人包已带入当前用户的偏好；每个使用者可继续改写，并按继承选择传给后代。
- `INHERITANCE.json`（schemaVersion 2）登记当前选择：`kind` 为 method/preference/resource，`use` 为 current/callable/archive，`requires` 给出依赖，`inherit:false` 是明确排除。
- 一次重要采用、失败或明显改写的背景若会改变后代的使用判断，把简短来源、适用情形和局限写在相应方法或技能旁；普通改字无需建立审批或评分。
- 导师导出：`python research/tools/spore.py --source-root <工作区> --output <新.zip> --write`
- 学生导出：`python tools/export_student_spore.py --student-root <学生工作区> --output <新.zip> --write`
- 导出只收集选中单元与依赖，加上继续生成所需的运行资源与空白模板；当前项目台账、个人原始记录、日志与交接回执不会进入新项目状态。
- 学生或伙伴把可复用材料放进自己的 `public/` 后，导师可以预览并采用：

```text
python research/tools/adopt_student.py --student-root <来源个体> --source <public/下路径> --destination <modules|skills|templates|student-seed|archive 下路径>
```

已有不同内容默认拒绝；确认替换后加 `--replace`。采用只搬运公开字节并记录来源，语义合并仍是一次正常编辑。

## 学生交接

```text
python research/tools/first_student.py --student-root <绝对路径> --task-pack <任务文件>
python research/tools/record_student.py --report <学生 public/ 下的绝对路径>
```

一次交接产生一条 `research/receipts/<student-id>/<task-id>.json`；已存在的学生只接收新任务，不重装、不覆盖其方法。回执只记录机械事实与实际观察，不证明独立上下文、权限隔离或结论正确。

## 主要材料

- `payload/research/`：导师载荷（个体目录内容）。
- `payload/student/`（在导出的学生孢子中）：学生载荷，安装到学生工作区根目录。
- `MANIFEST.json`：封版构建后记录完整文件清单、`formatVersion`、`version`、`profile`、`buildId` 与直接来源。
- `install.py`、`build_spore.py`：薄入口，规则全部由 `payload/*/tools/_spore_core.py` 实现。
- `build_manifest.py`、`build_archive.py`、`verify.py`：发行入口与验收入口，均调用同一共享实现。

```text
python -B build_manifest.py --write
python -B payload/research/tools/check.py --package .
python -B build_archive.py --output ..\open-research-spore-v2.2.0-personal.zip --write
python -B verify.py --work <新临时目录> --archive ..\open-research-spore-v2.2.0-personal.zip
```

这些是封版与验收入口，不表示本快照已经运行或通过。以 `_` 开头的临时目录（例如 scratch 与 `_qa_*`）和 `*.zip` 不进入发行清单。

## 升级已有工作区（有界迁移）

重复安装不会覆盖个体目录中已有且内容不同的文件，也不会把旧版本静默替换；选择宿主适配时标记块内的内容可按预演更新。迁移由项目宿主按需执行，不读全仓历史：

1. 找到实际生效的方法、偏好、工具与入口，只读要修改的部分；保留台账、学生个人区、身份、已有报告与宿主标记块之外的内容。
2. 在版本管理或有限备份中保存将被替换的文件。
3. 补齐当前 `INHERITANCE.json`（schemaVersion 2）、运行资源与空白模板；把已有偏好独立整理并保留原意，原清单留作来源，不改写成祖先哈希。
4. 把操作入口换成局部检查，并更新相关引用；学生模板升级只影响之后新建的学生，已有学生自行采用改进。
5. 对本次修改做相关检查，再从迁移后的个体完成一次后代导出；遇到冲突处理该处，不全量覆盖研究区；无法证明来源时如实记录“接管/手工迁移”。

## 边界

清单与哈希只识别快照；它们不证明方法有效、结论正确、伙伴独立或宿主已隔离。材料已携带、入口已接入、工具或学生已运行、方法已见效，分别需要相应证据。机械检查通过不能替代研究判断。本版的未验证范围在包根 `VERIFICATION.md` 中列出，包级认定与失效条件见 `CERTIFICATE.md`。许可为 CC BY-NC-SA 4.0（已含许可文件），偏好文本的实际效果不在本包验证范围内——它是一份可编辑的起点，不是经过验证的标准。

## 致谢

本包由 New Cheney 设计、决策与验收；实现、核对与文档整理使用 AI 协作工具完成（以下署名由权利人声明）：ChatGPT（OpenAI）、DeepSeek、Codex（OpenAI 智能体；本版发布重建的运行时模型为 DeepSeek V4.1 Flash）。

AI 工具不作为作者或著作权人；版权与责任归 New Cheney。
