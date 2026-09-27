# 资格证 — Open Research Spore 2.2.0+personal.1（私人偏好版，包级）

本文件随包交付，说明本快照的身份、许可、能力范围与证据。**本证不内嵌自身的 `buildId` 与 ZIP SHA-256**（与 `VERIFICATION.md` 同一规则）；完整哈希、签发日期与运行记录见公开发布记录（本变体仓库的 Release 说明）与包外记录。

## 一、认定对象

| 项 | 值 |
|---|---|
| 名称 | open-research-spore |
| 版本 / 变体 | 2.2.0+personal.1 / 私人偏好版（`profile: mentor`，`variant: personal-preferences`） |
| 格式 | `formatVersion: 2`；`MANIFEST.json` 登记全部受管文件 |
| 许可 | CC BY-NC-SA 4.0（署名—非商业性使用—相同方式共享；**不是** OSI 认可的开源许可） |
| 版权署名 | Copyright (c) 2026 New Cheney |
| 签发主体 | New Cheney |
| 协作工具 | ChatGPT（OpenAI）、DeepSeek、Codex（OpenAI 智能体）；署名由权利人声明 |

## 二、合格判定（签发条件）

同时满足以下条件，方才认定为“合格的私人偏好快照”：

1. 清单可复现：`build_manifest.py` 预演能从树内内容重算出与记录一致的 `buildId`；
2. 包核对通过：`check.py --package` 无未登记文件、无哈希不符；
3. 归档一致：本版 ZIP 与源码树逐条目字节相同；
4. 行为证据：完整归档套件在本版最终 ZIP 上运行通过（针对共同实现）；
5. 许可与署名齐备。

**限定**：第 1–5 条只覆盖共同实现的机械与行为核对。本版带有的偏好文本对真实任务的影响**未验证**，不因本证被认定；使用或再分发本包及其后代前，应检查 `payload/research/PREFERENCES.md` 的内容与继承选择。

## 三、能力范围与不认定

- 可认定：包的身份（名称、版本、变体、受管文件完整性）；材料已携带、入口已接入；上述机械核对与行为套件结果。
- 能力范围：L0 文件连续性；L1 本地执行（可选）；L2 独立伙伴（可独立于 L1）；L3 专业工具（可选）。
- 不认定：偏好文本的实际效果；方法长期有效；研究结论正确；伙伴上下文独立；宿主权限隔离；安装后个体的实际运行。

## 四、失效条件

- 任何文件修改、清单或归档重建都会产生新的 `buildId` 与哈希，本证只对应重建时的快照。
- 本证不覆盖已安装个体，也不覆盖由本包导出的后代包。

## 五、核验（第三方可复跑）

```text
python -B build_manifest.py                     # 预演：从树内内容重算 buildId
python -B payload/research/tools/check.py --package .
```
