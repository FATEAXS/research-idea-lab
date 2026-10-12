#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境自检（不花钱）：
  1) Mock 模式跑通整条流水线（验证代码本身没问题）；
  2) 真实联网检索各查一条（验证 arXiv / Semantic Scholar 可达）。
用法：python smoke_test.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab.config import load_config
from lab.pipeline import Pipeline


def test_mock_pipeline():
    print("=" * 50)
    print("[1/2] Mock 模式端到端测试（不联网、不花钱）...")
    cfg = load_config(None)
    cfg["llm"]["provider"] = "mock"
    cfg["pipeline"]["num_ideas"] = 2
    cfg["pipeline"]["max_rounds"] = 2
    run_dir = Path(tempfile.mkdtemp(prefix="idea_lab_smoke_"))
    pipe = Pipeline(cfg, run_dir)
    entries, _ = pipe.run("低资源场景下的高效大模型微调（smoke test）")
    assert entries, "流水线没有产出任何条目"
    ids = [e["id"] for e in entries]
    assert "idea-2" in ids, "Mock 场景中 idea-2 应该在第1轮被毙掉但仍应出现在报告里"
    killed = [e for e in entries if e["id"] == "idea-2"][0]
    assert killed["verdict"] == "kill", "idea-2 应为 kill"
    report = run_dir / "final" / "report.md"
    assert report.exists() and report.stat().st_size > 500, "report.md 缺失或过小"
    print(f"[OK] 流水线跑通。输出目录：{run_dir}")
    print(f"[OK] 排名：{[(e['id'], e['weighted'], e['verdict']) for e in entries]}")


def test_retrieval():
    print("=" * 50)
    print("[2/2] 真实联网检索测试...")
    from lab import retrieval
    cfg = load_config(None)
    cfg["retrieval"]["max_per_query"] = 3
    retrieval.configure(cfg["retrieval"])
    ok = {}
    try:
        got = retrieval.search_arxiv("parameter efficient fine-tuning", 3)
        ok["arXiv"] = f"{len(got)} 篇，例：{got[0].title[:50]}..." if got else "0 篇"
    except Exception as e:
        ok["arXiv"] = f"失败：{e}"
    try:
        got = retrieval.search_s2("chain of thought reasoning", 3)
        ok["SemanticScholar"] = f"{len(got)} 篇，例：{got[0].title[:50]}..." if got else "0 篇"
    except Exception as e:
        ok["SemanticScholar"] = f"失败：{e}"
    for k, v in ok.items():
        status = "OK " if not v.startswith("失败") else "WARN"
        print(f"[{status}] {k}: {v}")
    print("（检索失败通常意味着网络不可达或被限流，不影响代码正确性；"
          "S2 无 key 时限流较严，建议申请免费 key 填入配置）")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    test_mock_pipeline()
    test_retrieval()
    print("=" * 50)
    print("自检完成。真实运行：python main.py --topic \"你的研究方向\"")
