#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科研 Idea 迭代实验室 —— 入口

用法：
  python main.py --topic "你的研究方向"              # 真实运行（需配置 api_key）
  python main.py --topic "你的研究方向" --mock       # 离线演示，不调模型不联网检索
  python main.py --config config.yaml --topic "..." --rounds 3 --ideas 5
"""
import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab.config import load_config
from lab.pipeline import Pipeline


def setup_logging(run_dir: Path):
    logger = logging.getLogger("lab")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logfile = logging.FileHandler(run_dir / "events.log", encoding="utf-8")
    logfile.setLevel(logging.DEBUG)
    logfile.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(console)
    logger.addHandler(logfile)


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip())[:40]
    return s.strip("_") or "run"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="科研Idea迭代实验室")
    ap.add_argument("--topic", required=True, help="研究方向/主题")
    ap.add_argument("--config", default="config.yaml", help="配置文件路径")
    ap.add_argument("--mock", action="store_true",
                    help="离线演示：不调用大模型、不联网检索")
    ap.add_argument("--rounds", type=int, help="覆盖最大评审轮数")
    ap.add_argument("--ideas", type=int, help="覆盖第一轮生成的idea数量")
    ap.add_argument("--no-debate", action="store_true", help="关闭匿名辩论环节")
    ap.add_argument("--out", help="输出目录（默认 runs/）")
    ap.add_argument("--continue-from", metavar="RUN_DIR",
                    help="续跑模式：加载上一次运行中存活的 idea，跳过调研直接继续迭代")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if cfg_path.exists():
        cfg = load_config(str(cfg_path))
    else:
        print(f"[提示] 未找到 {cfg_path}，使用内置默认配置。"
              f"真实运行请先：复制 config.example.yaml 为 config.yaml 并配置 api_key。")
        cfg = load_config(None)
    if args.mock:
        cfg["llm"]["provider"] = "mock"
    if args.rounds:
        cfg["pipeline"]["max_rounds"] = args.rounds
    if args.ideas:
        cfg["pipeline"]["num_ideas"] = args.ideas
    if args.no_debate:
        cfg["pipeline"]["debate"] = False
    if args.out:
        cfg["run"]["output_dir"] = args.out

    run_dir = Path(cfg["run"]["output_dir"]) / \
        f"{time.strftime('%Y%m%d_%H%M%S')}_{slugify(args.topic)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(run_dir)
    log = logging.getLogger("lab")

    snapshot = json.loads(json.dumps(cfg, ensure_ascii=False))
    if snapshot["llm"].get("api_key"):
        snapshot["llm"]["api_key"] = "***（已隐藏）"
    (run_dir / "run_config.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    mode = "MOCK（离线演示）" if cfg["llm"].get("provider") == "mock" else "真实运行"
    log.info("运行目录：%s ｜ 模式：%s", run_dir, mode)

    pipeline = Pipeline(cfg, run_dir)
    seed_cards = None
    if args.continue_from:
        from lab.pipeline import load_survivors
        seed_cards = load_survivors(args.continue_from)
        if not seed_cards:
            log.error("续跑目录 %s 中没有存活的 idea，退出", args.continue_from)
            return
        log.info("从 %s 载入 %d 个存活 idea 继续迭代", args.continue_from, len(seed_cards))
    entries, summary_lines = pipeline.run(args.topic, seed_cards=seed_cards)
    for line in summary_lines:
        print(line)


if __name__ == "__main__":
    main()
