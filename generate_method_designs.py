#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为冠军 idea 批量生成《详细方法与流程设计》（纯 Markdown，伪代码级）并渲染成网页。
用法：python generate_method_designs.py "<runs目录glob>:idea-4" ["<glob>:idea-3" ...]
生成 final/method_design_<id>.md 与 .html，并自动打开网页。"""
import glob
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lab.config import load_config
from lab.llm import OpenAICompatClient, Usage, call_json
from lab import promptkit


def latest_card(run_dir: Path, idea_id: str) -> dict:
    rounds = sorted(
        (int(p.name.split("_")[1]) for p in run_dir.glob("round_*")
         if p.is_dir() and p.name != "round_0" and p.name.split("_")[1].isdigit()),
        reverse=True)
    for rnd in rounds:
        d = run_dir / f"round_{rnd}" / idea_id
        if not d.exists():
            continue
        for v in range(rnd + 1, 0, -1):
            f = d / f"card_v{v}.json"
            if f.exists():
                return json.loads(f.read_text(encoding="utf-8")), f
    f = run_dir / "round_0" / "idea_cards.json"
    for d in json.loads(f.read_text(encoding="utf-8")):
        if d.get("id") == idea_id:
            return d, f
    raise FileNotFoundError(f"{run_dir} 中找不到 {idea_id} 的卡片")


def generate(run_dir: Path, idea_id: str) -> Path:
    cfg = load_config("config.yaml" if Path("config.yaml").exists() else None)
    llm = OpenAICompatClient(cfg, Usage())
    prompts = Path(__file__).resolve().parent / "prompts"
    card, src = latest_card(run_dir, idea_id)
    print(f"[{idea_id}] 卡片来源: {src}")
    system, user = promptkit.render(prompts, "a_method_design",
                                    idea_card=json.dumps(card, ensure_ascii=False))
    md = ""
    for attempt in range(3):
        try:
            md = llm.chat([{"role": "system", "content": system},
                           {"role": "user", "content": user}],
                          model=cfg["llm"]["models"]["researcher"],
                          task="method_design", max_tokens=16000)
            md = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", md.strip())
            if len(md) > 2000 and md.lstrip().startswith("#"):
                break
            print(f"  第{attempt+1}次输出过短（{len(md)}字），重试...")
            md = ""
        except Exception as e:
            print(f"  第{attempt+1}次失败：{str(e)[:80]}，重试...")
            time.sleep(5)
    if not md:
        raise RuntimeError(f"{idea_id} 方法设计生成失败")
    out = run_dir / "final" / f"method_design_{idea_id}.md"
    out.write_text(md, encoding="utf-8")
    print(f"  ✓ {out}（{len(md)} 字）")
    return out


def main():
    run_dirs = sys.argv[1:]
    mds = []
    for spec in run_dirs:
        glob_part, idea_id = spec.rsplit(":idea-", 1)
        idea_id = f"idea-{idea_id}"
        hits = glob.glob(glob_part)
        assert hits, f"未匹配到目录: {glob_part}"
        mds.append(generate(Path(hits[0]), idea_id))
    import md_preview
    sys.argv = ["md_preview.py"] + [str(m) for m in mds]
    md_preview.main()
    print("\n全部完成")


if __name__ == "__main__":
    main()
