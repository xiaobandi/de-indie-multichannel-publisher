#!/usr/bin/env python3
"""平台格式适配（零依赖）。

把一份主稿按目标平台的「字数 / 标题层级 / 标签 / 换行 / 语气」规则重排，
产出可预测的多平台版本，避免"一份稿子到处发"。

规则来源与版本（v2，2026-09 修订）
------------------------------------
`PLATFORMS` 是**内部基线**，不是官方规则：数值按平台公开文档与常见实践整理，
**未逐条核验官方最新条款**。上线前请用 `--rules` 传入已核验的规则 JSON
（形如 `{"小红书": {"max_chars": 1000, ...}}`），或在 `--rules-source` 里
写明你核验过的来源与日期。`rules_source` 会原样写进产出，避免下游把
「内部基线」当成「平台规定」引用（红线 7：引用规则前先校验时效）。

v1 的三个缺陷（实测抓到，见 reports/real-run/de-local-multichannel-ops-hub）
  1. 标签不足时用写死的「#话题 #干货 #分享」补齐 —— **凭空编造标签**；
     v2 起只输出主稿里真实出现过的标签，不足就少给并告警，绝不补假标签。
  2. 只内置 9 个平台，而工作流要求的平台清单更长，未知平台直接报错中断；
     v2 起扩到 15 个，并给出「未收录平台」的降级处置（按通用基线适配 + 告警）。
  3. 平台规则无来源与版本，与技能自身红线「引用平台规则前先校验时效」冲突；
     v2 起每条产出都带 `rules_source` / `rules_version` / `unverified`。

用法:
    python3 format_adapter.py --file main.md --platforms 小红书,抖音,公众号,知乎
    python3 format_adapter.py --file main.md --platform 小红书 --json
    python3 format_adapter.py --file main.md --platforms 小红书,快手 --rules verified.json

平台规则是「基线条」：平台会变，脚本不会替你判断内容是否合适，
只做机械重排 + 给出该平台的字数/结构约束提醒。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 规则版本：改动 PLATFORMS 时同步更新
RULES_VERSION = "2026.09-baseline"
DEFAULT_RULES_SOURCE = "内部基线（按平台公开文档整理，未逐条核验官方最新条款）"

# 平台规则基线：max_chars=正文建议上限, title_limit=标题上限, tags=推荐标签数,
# break_style=换行风格, tone=语气提示
PLATFORMS = {
    "小红书": {"max_chars": 1000, "title_limit": 20, "tags": 8, "break_style": "短段多空行", "tone": "口语、第一人称、emoji 适度"},
    "抖音":   {"max_chars": 300,  "title_limit": 55, "tags": 5, "break_style": "短句分行", "tone": "强钩子、口播感"},
    "快手":   {"max_chars": 300,  "title_limit": 55, "tags": 5, "break_style": "短句分行", "tone": "接地气、口语"},
    "视频号": {"max_chars": 1000, "title_limit": 22, "tags": 4, "break_style": "短段", "tone": "情感共鸣"},
    "公众号": {"max_chars": 3000, "title_limit": 64, "tags": 0, "break_style": "长段小标题", "tone": "书面、有逻辑分层"},
    "知乎":   {"max_chars": 5000, "title_limit": 50, "tags": 3, "break_style": "分点论述", "tone": "理性、有论据"},
    "微博":   {"max_chars": 2000, "title_limit": 30, "tags": 3, "break_style": "短段", "tone": "热点、话题标签"},
    "B站":    {"max_chars": 2000, "title_limit": 80, "tags": 6, "break_style": "分镜/章节", "tone": "圈层黑话、梗"},
    "今日头条": {"max_chars": 3000, "title_limit": 30, "tags": 3, "break_style": "长段小标题", "tone": "资讯、客观陈述"},
    "百家号": {"max_chars": 3000, "title_limit": 40, "tags": 3, "break_style": "长段小标题", "tone": "关键词前置、易被检索"},
    "豆瓣":   {"max_chars": 5000, "title_limit": 60, "tags": 3, "break_style": "长段", "tone": "文艺、真诚、无营销腔"},
    "贴吧":   {"max_chars": 2000, "title_limit": 40, "tags": 0, "break_style": "短段", "tone": "吧内语境、直白"},
    "淘宝":   {"max_chars": 2000, "title_limit": 60, "tags": 0, "break_style": "卖点分点", "tone": "结构化卖点、无极限词"},
    "拼多多": {"max_chars": 1000, "title_limit": 60, "tags": 0, "break_style": "卖点分点", "tone": "卖点直给、无极限词"},
    "闲鱼":   {"max_chars": 500,  "title_limit": 30, "tags": 0, "break_style": "短段", "tone": "真实、个人卖家口吻"},
}

# 未收录平台时的兜底基线（并在产出里明确告警「按通用基线适配」）
GENERIC_RULE = {"max_chars": 1000, "title_limit": 30, "tags": 3,
                "break_style": "短段", "tone": "通用（平台未收录，需人工确认规则）"}


def load_rules(path: str | None) -> tuple[dict, str, str]:
    """合并外部已核验规则。返回 (平台表, 来源说明, 版本)。"""
    rules = {k: dict(v) for k, v in PLATFORMS.items()}
    if not path:
        return rules, DEFAULT_RULES_SOURCE, RULES_VERSION
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    src = data.pop("_source", path)
    ver = data.pop("_version", "external")
    for plat, rule in data.items():
        rules.setdefault(plat, dict(GENERIC_RULE)).update(rule)
    return rules, src, ver


def split_title_body(text: str) -> tuple[str, str]:
    lines = [l for l in text.splitlines()]
    for i, l in enumerate(lines):
        if l.strip():
            if l.startswith("#"):
                return l.lstrip("# ").strip(), "\n".join(lines[i + 1:])
            return l.strip(), "\n".join(lines[i + 1:])
    return "", text


def condense(body: str, limit: int) -> str:
    body = body.strip()
    if len(body) <= limit:
        return body
    cut = body[:limit]
    for sep in ("\n\n", "。", "！", "？", "\n"):
        idx = cut.rfind(sep)
        if idx > limit * 0.6:
            return cut[: idx + len(sep)]
    return cut


def extract_tags(body: str) -> list[str]:
    """只取主稿里**真实出现过**的标签，不补任何模板标签。"""
    seen: list[str] = []
    for t in re.findall(r"#([\w\u4e00-\u9fff]+)", body):
        if t not in seen:
            seen.append(t)
    return seen


def adapt(title: str, body: str, platform: str, rules: dict,
          rules_source: str, rules_version: str) -> dict:
    unverified = platform not in PLATFORMS
    rule = rules.get(platform) or dict(GENERIC_RULE)

    t = title.strip()[: rule["title_limit"]]
    condensed = condense(body, rule["max_chars"])

    if rule["break_style"] in ("短段多空行", "短段", "短句分行"):
        parts = re.split(r"(?<=[。！？!?])\s*", condensed)
        condensed = "\n\n".join(p.strip() for p in parts if p.strip())

    warns: list[str] = []
    tag_line = ""
    if rule["tags"]:
        found = extract_tags(body)
        tags = found[: rule["tags"]]
        tag_line = " ".join("#" + x for x in tags)
        if len(tags) < rule["tags"]:
            warns.append(
                f"主稿只出现 {len(tags)} 个标签，低于该平台建议的 {rule['tags']} 个；"
                f"脚本不编造标签，请人工补充真实话题标签后再发布"
            )

    if len(body) > rule["max_chars"]:
        warns.append(f"正文由 {len(body)} 字压缩到 {rule['max_chars']} 字上限，已按句边界截断，建议人工复核结尾（可能砍掉转化钩子）")
    if len(title) > rule["title_limit"]:
        warns.append(f"标题超过 {rule['title_limit']} 字，已截断")
    if unverified:
        warns.append(f"平台「{platform}」未收录在基线表中，已按通用基线适配；请人工确认该平台字数与标签规则")

    return {
        "platform": platform,
        "title": t,
        "body": condensed,
        "tags": tag_line,
        "tags_found": len(extract_tags(body)),
        "tags_expected": rule["tags"],
        "tone_hint": rule["tone"],
        "rules_source": rules_source,
        "rules_version": rules_version,
        "unverified": unverified,
        "warnings": warns,
    }


def _selftest() -> int:
    """内嵌回归自测：核心断言是「不编造标签」「未收录平台要告警」「规则要带来源」。"""
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    rules, src, ver = load_rules(None)
    ck("规则来源非空", bool(src))
    ck("规则版本非空", bool(ver))
    ck("内置平台数 >= 15", len(PLATFORMS) >= 15, f"实际 {len(PLATFORMS)}")

    # 1) 主稿无标签 + 该平台需要标签 → 不得编造
    r = adapt("标题", "这是一段没有标签的正文。", "小红书", rules, src, ver)
    ck("无标签主稿不编造标签", r["tags"] == "", f"实际 {r['tags']!r}")
    ck("无标签主稿给出告警",
       any("不编造" in w for w in r["warnings"]), f"{r['warnings']}")

    # 2) 主稿有 2 个标签 → 只输出这 2 个，且不得混入模板词
    body2 = "正文内容。#手作 #香薰"
    r2 = adapt("标题", body2, "小红书", rules, src, ver)
    ck("只输出主稿真实标签", r2["tags"] == "#手作 #香薰", f"实际 {r2['tags']!r}")
    ck("不混入 话题/干货/分享 等模板标签",
       not any(x in r2["tags"] for x in ("话题", "干货", "分享")),
       f"实际 {r2['tags']!r}")
    ck("标签数低于建议值时告警", any("低于该平台建议" in w for w in r2["warnings"]))

    # 3) 未收录平台：降级 + 告警，不中断
    r3 = adapt("标题", "正文。", "某小众平台", rules, src, ver)
    ck("未收录平台标记 unverified", r3["unverified"] is True)
    ck("未收录平台给告警", any("未收录" in w for w in r3["warnings"]))
    ck("未收录平台仍产出结果", bool(r3["body"]))

    # 4) 每条产出都带规则来源（红线：引用规则先校验时效）
    for item in (r, r2, r3):
        ck(f"{item['platform']} 产出带 rules_source", bool(item["rules_source"]))
        ck(f"{item['platform']} 产出带 rules_version", bool(item["rules_version"]))

    # 5) 标题超限要截断并告警
    long_title = "标" * 60
    r5 = adapt(long_title, "正文。", "小红书", rules, src, ver)
    ck("标题超限被截断", len(r5["title"]) == PLATFORMS["小红书"]["title_limit"])
    ck("标题超限有告警", any("标题超过" in w for w in r5["warnings"]))

    # 6) 正文超限截断后要提醒复核结尾（可能砍掉转化钩子）
    r6 = adapt("标题", "字" * 5000, "抖音", rules, src, ver)
    ck("正文超限有告警", any("压缩到" in w for w in r6["warnings"]))
    ck("正文超限告警提醒复核结尾",
       any("复核结尾" in w for w in r6["warnings"]))

    fails = [(n, d) for n, ok, d in checks if not ok]
    for n, ok, d in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}" + (f" —— {d}" if not ok and d else ""))
    print(f"format_adapter 自测：{len(checks) - len(fails)}/{len(checks)} 通过")
    return 1 if fails else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    ap = argparse.ArgumentParser(description="多平台格式适配")
    ap.add_argument("--file", help="主稿；缺省 stdin")
    ap.add_argument("--platform", help="单个平台")
    ap.add_argument("--platforms", help="逗号分隔的多个平台")
    ap.add_argument("--rules", help="已核验的平台规则 JSON（可用 _source / _version 声明来源）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not text.strip():
        print("错误：主稿为空", file=sys.stderr)
        return 2

    rules, rules_source, rules_version = load_rules(args.rules)

    plats = [p.strip() for p in (args.platforms.split(",") if args.platforms else [args.platform or "小红书"]) if p.strip()]
    if not plats:
        print("错误：未指定平台", file=sys.stderr)
        return 2

    title, body = split_title_body(text)
    results = [adapt(title, body, p, rules, rules_source, rules_version) for p in plats]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"规则来源：{rules_source}　版本：{rules_version}")
        for r in results:
            print(f"\n{'=' * 46}\n【{r['platform']}】语气提示：{r['tone_hint']}\n{'=' * 46}")
            print(f"# {r['title']}\n")
            print(r["body"])
            if r["tags"]:
                print(f"\n{r['tags']}")
            for w in r["warnings"]:
                print(f"  ⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
