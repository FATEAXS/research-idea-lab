# -*- coding: utf-8 -*-
"""最终报告：排行榜 + 每张卡的评分轨迹 + 终审意见 + 档案索引。"""
VERDICT_CN = {"advance": "✅ 可进实验", "revise": "🔁 继续迭代", "kill": "❌ 已毙掉"}


def generate_report(run_dir, topic: str, entries: list, usage, seed_mode=False):
    lines = ["# 科研 Idea 迭代报告", ""]
    lines += [f"- **研究主题**：{topic}",
              f"- **运行模式**：{'续跑（迭代已有idea）' if seed_mode else '全新探索'}",
              f"- **LLM 调用**：{usage.calls} 次，约 {usage.total()} tokens", ""]
    lines += ["> 这是「人工卡点」：请阅读本报告选定最终 idea；", ""
              "> 选定后参考 final/experiment_spec_<id>.md 开始实现。", ""]

    lines += ["## 排行榜", "",
              "| 排名 | Idea | 标题 | 各轮加权分 | 最终结论 |",
              "|---|---|---|---|---|"]
    for i, e in enumerate(entries, 1):
        traj = " → ".join(str(r["weighted"]) for r in e["history"])
        lines.append(f"| {i} | {e['id']} | {e['title'][:40]} | {traj} | "
                     f"{VERDICT_CN.get(e['verdict'], e['verdict'])} |")
    lines.append("")

    for e in entries:
        lines += [f"## {e['id']}：{e['title']}", ""]
        lines += ["### 评分轨迹", ""]
        lines += ["| 轮次 | novelty | feasibility | significance | 加权分 | 结论 |",
                  "|---|---|---|---|---|---|"]
        for r in e["history"]:
            ms = r.get("mean_scores", {})
            lines.append(
                f"| {r['round']} | {ms.get('novelty', '-')} | "
                f"{ms.get('feasibility', '-')} | {ms.get('significance', '-')} | "
                f"{r['weighted']} | {VERDICT_CN.get(r['verdict'], r['verdict'])} |")
        lines.append("")
        last = e["history"][-1]
        lines += ["### 导师终审意见（最后一轮）", "",
                  f"**结论**：{VERDICT_CN.get(last['verdict'], last['verdict'])}",
                  "", last.get("rationale") or "（无）", ""]

    lines += ["## 档案索引", ""]
    lines += ["每轮的卡片版本、三位评审的独立意见、辩论纪要、导师终审均已存档：", ""]
    for e in entries:
        lines.append(f"- **{e['id']}**（{len(e['history'])} 轮）：")
        for r in e["history"]:
            rnd = r["round"]
            lines.append(
                f"  - 第 {rnd} 轮：`round_{rnd}/{e['id']}/`"
                f"（card_v{rnd}.json → reviews/B,C,D.json → debate/ → meta.json"
                f" → card_v{rnd + 1}.json）")
    lines.append("")

    summary = ["", "========== 运行完成 =========="]
    for i, e in enumerate(entries, 1):
        summary.append(
            f"  {i}. [{e['id']}] {e['title'][:44]}  "
            f"加权 {e['weighted']}  {VERDICT_CN.get(e['verdict'], e['verdict'])}")
    summary.append(f"  完整报告：{run_dir / 'final' / 'report.md'}")
    summary.append("  下一步（人工卡点）：阅读报告选定 idea，"
                   "并查看 final/experiment_spec_*.md 开始实验。")
    return "\n".join(lines), summary
