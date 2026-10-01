# 定时发布

> 生成发布计划 → 调用 MultiPost 类连接器/官方 API → 失败重试提醒

工作流 `wf-indie-publisher-schedule`　·　归属 多平台发布与数据回捞助理　·　触发 定时　·　
复杂度 M　·　阶段 P1

## 调用链

- `定时排期`（scheduled-dispatch）

## 文档

- [`WORKFLOW.md`](WORKFLOW.md) — 完整编排、闸门、降级与验收标准
- [`tests/cases.yaml`](tests/cases.yaml) — 端到端 / 闸门 / 降级用例

## 一句话试用

```text
帮我跑 多平台发布与数据回捞助理 的「定时发布」：<你的输入>
```
