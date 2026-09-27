# 按需资源：学生建立、投递与回执细节

首次真正派发时才读本文件；安装本包不会创建学生。

## 建立或接续

```text
python research/tools/first_student.py --student-root <绝对路径> --task-pack <任务文件>
python research/tools/first_student.py --student-root <绝对路径> --task-pack <任务文件> --write
```

- 空目录：从 `student-seed/`、当前运行资源与空白模板组装学生个体，并把任务放进 `public/`。
- 已存在的学生（有自己的 `PACK-MANIFEST.json`，或经复核确认的 `START.md` + `INHERITANCE.json` 且加 `--existing`）：只投入新任务，不重写种子文件、不覆盖学生方法。
- 无法确认来源且非空：拒绝，先做一次性迁移或换新目录；不要凭同名文件假认。

学生的运行资源来自导师当前版本（`_spore_core.py`、`check.py`、模板）；学生不需要导师的派发工具，也不回读导师的私有材料。

## 一次交接一条回执

每次投递在导师侧生成 `research/receipts/<student-id>/<task-id>.json`，记录学生根、任务文件指纹与准备状态；下一次任务创建新记录，不覆盖上一次。学生根与任务哈希相同则幂等。

目录准备与回执只代表 `prepared-not-launched`；宿主是否真的启动了第二个上下文、是否隔离文件权限，必须单独观察并如实记录。

## 记录报告

```text
python research/tools/record_student.py --report <学生 public/ 下的绝对路径>
```

同一报告重复记录幂等；修订报告追加新观察并保留旧指纹。宿主、会话与模型名只在确实观察到时填写，并标为调用方声明值。

## 恢复与升级

恢复学生的会话时让它读自己的状态（`personal/` 下的状态与笔记）与上次交付，不重放初始化。导师模板升级只影响之后新建的学生；已有学生可以自己采用改进，导师也可以用 `tools/adopt_student.py` 从学生的公开区取件。

回执记录的是当时的学生根路径：移动或复制学生工作区后，旧回执不再匹配新位置的报告，需要重新交接，或在明确知道对应关系时用 `--receipt` 指向并核对后的回执；不要凭猜测把报告挂到旧回执上。
