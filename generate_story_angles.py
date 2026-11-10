#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为方向生成顶会「故事角度」并渲染成网页。
用法（复用已有场的调研与品味笔记，最快）：
  python generate_story_angles.py --name "Agent记忆" --topic "方向" \
      --survey "runs/某探索目录/survey/survey.md" \
      --taste  "runs/某探索目录/survey/taste_notes.json" --n 4
输出：story_angles_<名称>.md / .html，并自动打开网页。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lab.config import load_config
from lab.llm import OpenAICompatClient, Usage, call_json
from lab import promptkit
import md_preview


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="输出文件名标识")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--survey", required=True, help="调研综述路径")
    ap.add_argument("--taste", default="", help="品味笔记路径（可选）")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--out", default="story_angles", help="输出目录")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    cfg = load_config("config.yaml" if Path("config.yaml").exists() else None)
    llm = OpenAICompatClient(cfg, Usage())
    prompts = Path(__file__).resolve().parent / "prompts"

    from lab import openreview as _or
    oral = _or.build_oral_patterns(cfg.get("openreview", {}), mock=False,
                                   topic=args.topic)
    survey = Path(args.survey).read_text(encoding="utf-8") \
        if Path(args.survey).exists() else "（无）"
    taste = Path(args.taste).read_text(encoding="utf-8") \
        if args.taste and Path(args.taste).exists() else "（无）"

    system, user = promptkit.render(prompts, "a_story_angles", topic=args.topic,
                                    n=args.n, oral_patterns=oral,
                                    survey=survey[:20000], taste_notes=taste[:6000])
    model, base_url, api_key = None, None, None
    # 复用 pipeline 的角色解析（researcher 角色）
    from lab.pipeline import Pipeline  # 仅用其解析函数
    fake = Pipeline.__new__(Pipeline)
    fake.cfg = cfg
    model, base_url, api_key = Pipeline._resolve_model(fake, "researcher")

    resp = call_json(llm, model, "story_angles", system, user,
                     base_url=base_url, api_key=api_key, max_tokens=12000)
    angles = resp.get("angles") or []
    if not angles:
        raise SystemExit("没有生成任何角度")

    # ---- 独立评分：三家族评审模型盲评（互不可见），取平均 ----
    from lab.pipeline import Pipeline as _P  # 复用角色解析
    fake = _P.__new__(_P)
    fake.cfg = cfg
    score_models = ["reviewer_domain", "reviewer_cross", "meta"]
    angles_json = json.dumps(angles, ensure_ascii=False, indent=1)
    ssys, suser = promptkit.render(prompts, "a_angle_score", n=len(angles),
                                   angles_json=angles_json)
    per_model = {}
    for role in score_models:
        m, bu, ak = _P._resolve_model(fake, role)
        try:
            sc = call_json(llm, m, "angle_score", ssys, suser,
                           base_url=bu, api_key=ak, max_tokens=8000)
            per_model[role] = sc.get("scores") or []
            print(f"评分完成：{m}")
        except Exception as e:
            print(f"评分模型 {m} 失败（跳过）：{str(e)[:80]}")
    dims = ["narrative_hook", "evidence_support", "venue_fit",
            "feasibility", "differentiation"]
    for i, a in enumerate(angles, 1):
        dim_vals = {d: [] for d in dims}
        totals = []
        for role, scores in per_model.items():
            for s in scores:
                if int(s.get("index", -1)) == i:
                    for d in dims:
                        try:
                            dim_vals[d].append(float(s.get(d, 0)))
                        except (TypeError, ValueError):
                            pass
                    try:
                        totals.append(float(s.get("total", 0)))
                    except (TypeError, ValueError):
                        pass
        a["scores"] = {d: round(sum(v) / len(v), 1)
                       for d, v in dim_vals.items() if v}
        a["score"] = round(sum(totals) / len(totals), 2) if totals else 0.0
        a["score_detail"] = {r: next((s.get("total") for s in scores
                                      if int(s.get("index", -1)) == i), "-")
                             for r, scores in per_model.items()}
        a["judge_note"] = next((s.get("one_line", "") for role, scores
                                in per_model.items() for s in scores
                                if int(s.get("index", -1)) == i), "")
    angles.sort(key=lambda a: -a.get("score", 0))

    md = [f"# 「{args.name}」顶会故事角度候选（三评审模型独立盲评，按平均总分排序）", ""]
    md += ["| 排名 | 总分 | 故事一句话 | 贡献类型 |", "|---|---|---|---|"]
    for i, a in enumerate(angles, 1):
        md.append(f"| {i} | **{a.get('score')}** | {a.get('story_hook', '')[:48]} | "
                  f"{a.get('contribution_type', '')} |")
    md.append("")
    for i, a in enumerate(angles, 1):
        md += [f"## 排名{i}（{a.get('score')} 分）：{a.get('story_hook', '')}", ""]
        sc = a.get("scores") or {}
        if sc:
            labels = {"narrative_hook": "钩子", "evidence_support": "证据",
                      "venue_fit": "顶会契合", "feasibility": "可行性",
                      "differentiation": "差异化"}
            md += ["**五维评分**：" + "｜".join(
                f"{labels[d]} {sc[d]}" for d in labels if d in sc), ""]
        if a.get("score_detail"):
            md += ["**三评审分别给分**：" + "，".join(
                f"{k}={v}" for k, v in a["score_detail"].items()), ""]
        md += [f"**针对的问题**：{a.get('target_problem', '')}", ""]
        md += [f"**为什么是现在**：{a.get('why_now', '')}", ""]
        md += [f"**模式对标**：{a.get('pattern_match', '')}", ""]
        md += [f"**贡献类型**：{a.get('contribution_type', '')}", ""]
        md += [f"**验证路径**：{a.get('validation_path', '')}", ""]
        md += [f"**审稿人最可能攻击的点**：{a.get('risk', '')}", ""]
        if a.get("judge_note"):
            md += [f"**评审一句话**：{a['judge_note']}", ""]
    md_text = "\n".join(md)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_out = out_dir / f"story_angles_{args.name}.md"
    md_out.write_text(md_text, encoding="utf-8")
    print(f"已生成 {md_out}")
    sys.argv = ["md_preview.py", str(md_out)] + (["--no-open"] if args.no_open else [])
    md_preview.main()


if __name__ == "__main__":
    main()
