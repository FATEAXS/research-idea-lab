#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无人值守驱动器：让科研 Agent 一直跑。

它解决「不停」的两个关键问题：
1. 循环驱动：按 --topics 文件里的方向轮流开跑，跑完一场自动开下一场，永远循环；
   每场先全新探索一轮，再对存活 idea 自动续跑一轮做深挖。
2. 故障不停车：单场崩溃/超时/解析失败只记录到状态文件，驱动器本身继续下一场。
3. 预算闸门：累计 token 超过上限自动优雅停车（「不停」≠无限烧钱），并告知成果位置。

用法：
  python forever.py --topics topics.txt                 # 按方向清单永远循环
  python forever.py --topic "某个方向" --max-cycles 3    # 单方向跑3轮探索-深挖
  python forever.py --topics topics.txt --mock          # 离线试跑驱动器本身

停车条件（满足其一）：累计 tokens 超过 --max-total-tokens；跑满 --max-cycles；Ctrl+C。
进度随时看 runs/forever_state.json。
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def newest_run_dir(runs_dir: Path):
    candidates = sorted(Path(runs_dir).glob("*/run_config.json"),
                        key=lambda p: p.stat().st_mtime)
    return candidates[-1].parent if candidates else None


def read_tokens(run_dir: Path) -> int:
    u = run_dir / "usage.json"
    if u.exists():
        try:
            return json.loads(u.read_text(encoding="utf-8")).get("total_tokens", 0)
        except Exception:
            return 0
    return 0


def save_state(state: dict, path: Path):
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def launch(args, extra) -> int:
    cmd = [sys.executable, "main.py"] + extra
    if args.mock:
        cmd.append("--mock")
    if args.config and Path(args.config).exists():
        cmd += ["--config", args.config]
    if args.out:
        cmd += ["--out", args.out]  # 必须转发，否则驱动器在 --out 里找不到运行结果
    return subprocess.call(cmd)


def run_one_topic(args, topic: str, state: dict, state_path: Path) -> bool:
    """跑一场（探索 + 可选深挖）。返回 False 表示应触发停车。"""
    runs_dir = Path(args.out)
    runs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n===== 【第 {state['cycles'] + 1} 轮】全新探索：{topic} =====", flush=True)
    rc = launch(args, ["--topic", topic])
    fresh_dir = newest_run_dir(runs_dir)
    if rc != 0 or fresh_dir is None:
        state["errors"].append({"at": datetime.now().isoformat(timespec="seconds"),
                                "topic": topic, "stage": "fresh", "rc": rc})
        save_state(state, state_path)
        print(f"[驱动器] 本场探索异常（rc={rc}），跳过并继续下一场——不停机。", flush=True)
        return True

    tokens = read_tokens(fresh_dir)
    state["total_tokens"] += tokens
    state["runs"].append({"dir": str(fresh_dir), "tokens": tokens, "mode": "explore"})
    print(f"[驱动器] 探索完成：{fresh_dir}（本场 {tokens} tokens）", flush=True)

    if not args.no_continue:
        print(f"===== 对存活 idea 自动深挖一轮 =====", flush=True)
        rc2 = launch(args, ["--topic", topic, "--continue-from", str(fresh_dir)])
        cont_dir = newest_run_dir(runs_dir)
        if rc2 == 0 and cont_dir is not None:
            t2 = read_tokens(cont_dir)
            state["total_tokens"] += t2
            state["runs"].append({"dir": str(cont_dir), "tokens": t2, "mode": "continue"})
            print(f"[驱动器] 深挖完成：{cont_dir}（本场 {t2} tokens）", flush=True)
        else:
            state["errors"].append({"at": datetime.now().isoformat(timespec="seconds"),
                                    "topic": topic, "stage": "continue", "rc": rc2})
            print("[驱动器] 深挖环节异常，不影响后续——继续。", flush=True)

    state["cycles"] += 1
    save_state(state, state_path)

    if state["total_tokens"] > args.max_total_tokens:
        print(f"\n[驱动器] 预算闸门触发：累计 {state['total_tokens']} tokens > "
              f"上限 {args.max_total_tokens}。优雅停车，成果都在 runs/ 下。", flush=True)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="无人值守驱动器")
    ap.add_argument("--topics", help="方向清单文件（每行一个方向，# 开头为注释）")
    ap.add_argument("--topic", help="单个方向（和 --topics 二选一）")
    ap.add_argument("--mock", action="store_true", help="离线演示模式")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--sleep", type=int, default=60, help="每场之间的休息秒数")
    ap.add_argument("--max-cycles", type=int, default=0, help="最多跑几场（0=不限）")
    ap.add_argument("--max-total-tokens", type=int, default=5_000_000,
                    help="累计 token 上限（默认500万，约几十元量级）")
    ap.add_argument("--no-continue", action="store_true",
                    help="只做全新探索，不对存活idea自动深挖")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--tag", default="", help="并发运行时的标签（状态文件隔离用）")
    args = ap.parse_args()

    if args.topics:
        lines = Path(args.topics).read_text(encoding="utf-8").splitlines()
        topics = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    elif args.topic:
        topics = [args.topic]
    else:
        sys.exit("需要 --topics 或 --topic")

    state_path = Path(args.out) / (f"forever_state_{args.tag}.json" if args.tag
                                   else "forever_state.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {"started_at": datetime.now().isoformat(timespec="seconds"),
             "topics": topics, "cycles": 0, "total_tokens": 0,
             "runs": [], "errors": []}
    save_state(state, state_path)

    print(f"[驱动器] 启动：{len(topics)} 个方向轮流跑｜预算闸门 "
          f"{args.max_total_tokens} tokens｜进度见 {state_path}", flush=True)
    i = 0
    try:
        while True:
            topic = topics[i % len(topics)]
            keep_going = run_one_topic(args, topic, state, state_path)
            if not keep_going:
                break
            if args.max_cycles and state["cycles"] >= args.max_cycles:
                print(f"[驱动器] 已跑满 {args.max_cycles} 场，正常收工。", flush=True)
                break
            i += 1
            if i % len(topics) == 0 or len(topics) == 1:
                print(f"[驱动器] 休息 {args.sleep} 秒后继续……（Ctrl+C 可随时停车）",
                      flush=True)
                time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\n[驱动器] 手动停车。已完成成果见 runs/ 下各目录与 forever_state.json。",
              flush=True)

    print(f"\n[驱动器] 总结：共 {state['cycles']} 场，累计 "
          f"{state['total_tokens']} tokens，异常 {len(state['errors'])} 次。"
          f"各场报告在 runs/*/final/报告.html（可用 make_html_report.py 重新生成）。",
          flush=True)


if __name__ == "__main__":
    main()
