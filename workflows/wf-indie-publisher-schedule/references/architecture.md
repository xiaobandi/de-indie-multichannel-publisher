# 定时发布 · 速查

| 项 | 内容 |
|---|---|
| slug | `wf-indie-publisher-schedule` |
| 层级 | L2-workflow |
| 归属 | 多平台发布与数据回捞助理（`de-indie-multichannel-publisher`） |
| 复杂度 / 阶段 | M / P1 |
| 能力族 | — |
| 定义出处 | — |
| 复用情况 | — |

## 调用的 SKILL

| 技能 | slug | 来源 |
|---|---|---|
| 定时排期 | `scheduled-dispatch` | agent-skills-core |

## 字段

| 项 | 内容 |
|---|---|
| 必需输入 | 本工作流的起始材料（见 `SKILL.md`「执行步骤」第 1 步）；用户身份与目标平台/渠道 |
| 可选输入 | 历史产出；账号人设；渠道规则；上一周期的数据 |
| 产出 | 失败重试提醒 |
| 脚本 | 无 |
