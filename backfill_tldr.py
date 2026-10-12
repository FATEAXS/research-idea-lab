#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为已有运行回填「一页看懂」简报（tldr_<id>.json），然后重新生成网页报告。
用法：python backfill_tldr.py runs/某目录 runs_pv/另一目录 ..."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab.config import load_config
from lab.llm import OpenAICompatClient, Usage, call_json
from lab import promptkit
from lab.pipeline import load_survivors


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_dirs = sys.argv[1:]
    if not run_dirs:
        sys.exit("用法：python backfill_tldr.py runs/某目录 ...")
    cfg = load_config("config.yaml" if Path("config.yaml").exists() else None)
    usage = Usage()
    llm = OpenAICompatClient(cfg, usage)
    prompts = Path(__file__).resolve().parent / "prompts"
    model = cfg["llm"]["models"]["researcher"]

    for rd in run_dirs:
        run_dir = Path(rd)
        cards = load_survivors(run_dir)
        print(f"\n== {run_dir.name[:46]}：{len(cards)} 个存活 idea ==")
        for c in cards:
            out = run_dir / "final" / f"tldr_{c.id}.json"
            if out.exists():
                print(f"  跳过 {c.id}（已有简报）")
                continue
            try:
                system, user = promptkit.render(prompts, "a_tldr",
                                                idea_card=c.to_json())
                t = call_json(llm, model, "tldr", system, user)
                out.write_text(json.dumps(t, ensure_ascii=False, indent=2),
                               encoding="utf-8")
                print(f"  ✓ {c.id}：{t.get('one_liner', '')[:44]}")
            except Exception as e:
                print(f"  ✗ {c.id}：{e}")

    # 重新生成网页报告（--no-open：不打扰当前浏览器窗口）
    import make_html_report
    for rd in run_dirs:
        sys.argv = ["make_html_report.py", rd, "--no-open"]
        make_html_report.main()
    print("\n全部完成：网页报告已重新生成（含一页看懂简报）")


if __name__ == "__main__":
    main()
