#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一次运行的全部档案（卡片/评审/辩论/终审）渲染成一个清晰的网页报告。

用法：python make_html_report.py runs/<某次运行的目录>
生成 runs/<目录>/final/报告.html 并自动用浏览器打开（--no-open 可关闭）。"""
import json
import sys
import html
from pathlib import Path

VERDICT_CN = {"advance": "✅ 可进实验", "revise": "🔁 继续迭代", "kill": "❌ 已毙掉"}
VERDICT_CLS = {"advance": "ok", "revise": "mid", "kill": "bad"}
ROLE_CN = {"B": "B · 领域查重", "C": "C · 跨域迁移", "D": "D · 理论红队"}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def load(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def badge(verdict):
    cls = VERDICT_CLS.get(verdict, "mid")
    return f'<span class="badge {cls}">{esc(VERDICT_CN.get(verdict, verdict))}</span>'


def score_chips(scores):
    if not scores:
        return ""
    keys = [("novelty", "新颖"), ("feasibility", "可行"), ("significance", "价值")]
    return " ".join(
        f'<span class="chip">{cn} <b>{esc(scores.get(k, "-"))}</b></span>'
        for k, cn in keys)


def render_card(card):
    ep = card.get("evaluation_plan") or {}
    ep_html = "".join(
        f'<li><b>{esc(k)}</b>：{esc("、".join(v) if isinstance(v, list) else v)}</li>'
        for k, v in ep.items())
    rw = card.get("key_related_work") or []
    rw_html = "".join(
        f'<li><b>{esc(w.get("title", w) if isinstance(w, dict) else w)}</b>'
        f'{" —— 重叠点：" + esc(w.get("overlap")) if isinstance(w, dict) and w.get("overlap") else ""}</li>'
        for w in rw)
    risks = card.get("risks") or []
    risks_html = "".join(f"<li>{esc(r)}</li>" for r in risks)
    return f"""
    <div class="card">
      <h3>{esc(card.get('title', ''))}</h3>
      <p><b>❓ 问题</b>：{esc(card.get('problem'))}</p>
      <p><b>🧪 核心假设（可证伪）</b>：{esc(card.get('hypothesis'))}</p>
      <p><b>🛠 方法草图</b>：{esc(card.get('method_sketch'))}</p>
      <p><b>🎯 预期结果</b>：{esc(card.get('expected_result'))}</p>
      <p><b>💡 新颖性声明</b>：{esc(card.get('novelty_claim'))}</p>
      <h4>最接近的先行工作</h4><ul>{rw_html}</ul>
      <h4>评估计划</h4><ul>{ep_html}</ul>
      <h4>主要风险</h4><ul>{risks_html}</ul>
    </div>"""


def idea_section(run_dir, idea_id, rounds, ranked_info):
    """一个 idea 的完整展示：轨迹 + 每轮评审 + 最终卡片。"""
    timeline, review_blocks = [], []
    final_card = None
    for rnd in rounds:
        d = run_dir / f"round_{rnd}" / idea_id
        if not d.exists():
            continue
        meta = load(d / "meta.json") or {}
        reviews = {r: load(d / "reviews" / f"{r}.json") for r in "BCD"}
        debate = load(d / "debate" / "rebuttals.json") or {}
        rows = ""
        for r in "BCD":
            rev = reviews.get(r) or {}
            scores = rev.get("scores") or {}
            adj = ((debate.get(r) or {}).get("score_adjustment")) or {}
            adj_txt = "，辩论调整 " + " ".join(
                f"{k}{int(v):+d}" for k, v in adj.items() if v) if adj else ""
            wk = (rev.get("weaknesses") or [])[:2]
            wk_html = "<br>".join("· " + esc(w) for w in wk)
            rows += (f"<tr><td>{ROLE_CN[r]}</td><td>{score_chips(scores)}"
                     f"<div class='adj'>{esc(adj_txt)}</div></td>"
                     f"<td class='wk'>{wk_html}</td></tr>")
        review_blocks.append(f"""
        <details {'open' if rnd == 1 else ''}><summary>第 {rnd} 轮评审档案</summary>
        <table><tr><th style="width:22%">评审</th><th style="width:38%">打分</th><th>主要质疑（前两条）</th></tr>
        {rows}</table>
        <p><b>导师终审</b>：{badge((meta.get('verdict') or '').lower())}
        {esc(meta.get('rationale'))}</p></details>""")
        for v in range(rnd, 0, -1):
            c = load(d / f"card_v{v}.json")
            if c and final_card is None:
                final_card = c
        h = ranked_info["history"][rnd - 1] if rnd - 1 < len(ranked_info.get("history", [])) else {}
        timeline.append(
            f'<div class="step"><span class="rnd">第{rnd}轮</span> '
            f'加权 <b>{esc(h.get("weighted", "?"))}</b> {badge((h.get("verdict") or "").lower())}</div>')
    card_html = render_card(final_card or {})
    tldr = load(run_dir / "final" / f"tldr_{idea_id}.json")
    tldr_html = ""
    if tldr:
        inn = "".join(f"<li>{esc(x)}</li>"
                      for x in (tldr.get("core_innovation") or []))
        tldr_html = (
            f'<div class="tldr"><div class="oneliner">💡 {esc(tldr.get("one_liner", ""))}</div>'
            f'<b>核心创新</b><ul>{inn}</ul>'
            f'<p><b>方法核心</b>：{esc(tldr.get("method_core"))}</p>'
            f'<p><b>和最接近工作的区别</b>：{esc(tldr.get("vs_prior"))}</p>'
            f'<p><b>凭什么成立</b>：{esc(tldr.get("why_works"))}</p>'
            f'<p><b>成功标准</b>：{esc(tldr.get("success_criteria"))}</p>'
            f'<p><b>先做的验证</b>：{esc(tldr.get("how_to_verify"))}</p>'
            f'<p><b>最大的坑</b>：{esc(tldr.get("biggest_risk"))}</p></div>')
        card_html = (f'{tldr_html}<details><summary>展开完整卡片（字段全文，较长）</summary>'
                     f'{card_html}</details>')
    return f"""
    <details class="idea"><summary>
      <b>{esc(idea_id)}</b>｜{esc(ranked_info.get('title', ''))}
      <span class="traj">{''.join(timeline)}</span></summary>
      {card_html}
      {''.join(review_blocks)}
    </details>"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    cfg = load(run_dir / "run_config.json") or {}
    usage = load(run_dir / "usage.json") or {}
    ranked = load(run_dir / "final" / "ranked_ideas.json") or []
    # 主题优先从 report.md 第一段读，读不到再用目录名
    title = ""
    report_md_path = run_dir / "final" / "report.md"
    if report_md_path.exists():
        import re
        m = re.search(r"研究主题\*\*：(.+)", report_md_path.read_text(encoding="utf-8"))
        if m:
            title = m.group(1).strip()
    if not title:
        title = run_dir.name.split("_", 2)[-1]
    n_papers = 0
    papers = load(run_dir / "survey" / "papers.json") or []
    n_papers = len(papers)
    survey_exists = (run_dir / "survey" / "survey.md").exists()
    seed_mode = (run_dir / "round_0" / "idea_cards.json").exists() \
        and not (run_dir / "survey" / "papers.json").exists()
    if seed_mode:
        retr_txt = "续跑模式：本场跳过文献调研，沿用上一场的检索结果"
    else:
        retr_txt = f"检索论文 {n_papers} 篇（{'综述已生成' if survey_exists else '无综述'}）"

    max_round = 0
    for p in run_dir.glob("round_*"):
        if p.is_dir() and p.name != "round_0":
            try:
                max_round = max(max_round, int(p.name.split("_")[1]))
            except ValueError:
                pass

    sections = "".join(
        idea_section(run_dir, e["id"], list(range(1, max_round + 1)), e)
        for e in ranked)
    spec_files = sorted((run_dir / "final").glob("experiment_spec_*.md")) \
        if (run_dir / "final").exists() else []

    page = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>科研Idea迭代报告 · {esc(title)}</title><style>
body{{font-family:"Microsoft YaHei",system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#222;line-height:1.7;background:#fafafa}}
h1{{font-size:1.5em;border-bottom:3px solid #2c6fbb;padding-bottom:8px}}
.meta{{color:#666;font-size:.9em}}
.flow{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:16px 0}}
.flow .node{{background:#eaf2fb;border:1px solid #b7d0ec;border-radius:8px;padding:6px 12px;font-size:.9em}}
.flow .arrow{{color:#2c6fbb;font-weight:bold}}
details.idea{{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 16px;margin:14px 0}}
details.idea>summary{{cursor:pointer;font-size:1.05em}}
.badge{{padding:2px 10px;border-radius:12px;font-size:.85em;color:#fff}}
.badge.ok{{background:#2e8b57}}.badge.mid{{background:#d98e04}}.badge.bad{{background:#c0392b}}
.step{{display:inline-block;background:#f4f4f4;border-radius:8px;padding:2px 10px;margin-left:8px;font-size:.85em}}
.rnd{{color:#2c6fbb;font-weight:bold}}
table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:.92em}}
th,td{{border:1px solid #e3e3e3;padding:8px;text-align:left;vertical-align:top}}
th{{background:#f0f4f9}}
.chip{{background:#f0f4f9;border-radius:10px;padding:1px 8px;margin-right:4px;display:inline-block}}
.adj{{color:#888;font-size:.85em}}
.wk{{color:#8a3b12}}
.card{{background:#fbfbf6;border:1px dashed #c9c9a8;border-radius:8px;padding:12px 16px}}
.tldr{{background:#fffbe8;border:1px solid #e6d28a;border-radius:8px;padding:10px 14px;margin:10px 0}}
.tldr .oneliner{{font-size:1.06em;font-weight:bold;margin-bottom:6px;color:#7a5c00}}
.tldr p{{margin:6px 0}}.tldr ul{{margin:4px 0}}
.card h3{{margin-top:4px}}.card h4{{margin-bottom:2px}}
details{{margin:8px 0}}details>summary{{cursor:pointer;font-weight:bold}}
</style></head><body>
<h1>科研 Idea 迭代报告</h1>
<p class="meta">主题：{esc(title)}｜{retr_txt}｜
LLM 调用 {usage.get("calls", "?")} 次 / {usage.get("total_tokens", "?")} tokens｜流程共 {max_round} 轮</p>
<div class="flow">
<span class="node">📖 文献调研（A）</span><span class="arrow">→</span>
<span class="node">💡 提出 {len(ranked)} 个 idea（A）</span><span class="arrow">→</span>
<span class="node">⚖️ 独立评审（B/C/D 互不可见）</span><span class="arrow">→</span>
<span class="node">🗣 匿名辩论（±2分微调）</span><span class="arrow">→</span>
<span class="node">🧑‍🏫 导师终审</span><span class="arrow">→</span>
<span class="node">✏️ 修订（A）</span><span class="arrow">→</span>
<span class="node">🔁 下一轮 / 📋 实验规格</span>
</div>
<h2>各 idea 的命运</h2>
{sections}
<h2>实验规格（人工卡点后的下一步）</h2>
{''.join(f'<p>📄 <code>{esc(f.name)}</code>（右键→打开方式→记事本，或见 final 文件夹）</p>' for f in spec_files)
     or "<p class='meta'>本次无存活的 idea，故未生成实验规格。</p>"}
<p class="meta">更完整的档案（每轮卡片版本、检索到的先行工作、辩论全文）见运行目录下各 JSON 文件。</p>
</body></html>"""
    out = run_dir / "final" / "报告.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"已生成：{out}")
    if "--no-open" not in sys.argv:
        import os
        os.startfile(out)


if __name__ == "__main__":
    main()
