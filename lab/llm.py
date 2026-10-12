# -*- coding: utf-8 -*-
"""大模型调用层：OpenAI 兼容协议 + Mock（离线演示）。
所有任务都要求模型只输出一个 JSON 对象；解析失败会带着错误信息让模型重试。"""
import json
import logging
import time

import requests

log = logging.getLogger("lab")


class Usage:
    """累计 token 用量，写进 usage.json 让每次运行的成本文之有据。"""

    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, usage: dict):
        if not usage:
            return
        self.prompt_tokens += usage.get("prompt_tokens", 0) or 0
        self.completion_tokens += usage.get("completion_tokens", 0) or 0

    def total(self):
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self):
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total(),
        }


def extract_json(text: str) -> dict:
    """从模型输出里抠出第一个完整 JSON 对象（容忍代码围栏、前后解释文字）。"""
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("输出里找不到 JSON 对象")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("JSON 对象不完整")


class OpenAICompatClient:
    """任何 OpenAI 兼容服务（智谱/DeepSeek/Qwen/OpenAI/vLLM/Ollama...）。"""

    def __init__(self, cfg: dict, usage: Usage):
        self.cfg = cfg["llm"]
        self.usage = usage
        if not self.cfg.get("api_key"):
            raise RuntimeError(
                "未配置 api_key。请设置环境变量 IDEA_LAB_API_KEY，"
                "或在 config.yaml 的 llm.api_key 里填写。"
            )

    def chat(self, messages, model: str, task: str) -> str:
        url = self.cfg["base_url"].rstrip("/") + "/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "temperature": self.cfg.get("temperature", 0.7),
            # 不设会给 4K 默认值，长 JSON 会被截断成不完整对象
            "max_tokens": self.cfg.get("max_tokens", 8000),
        }
        headers = {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type": "application/json",
        }
        last_err = None
        for attempt in range(4):
            try:
                resp = requests.post(
                    url, json=body, headers=headers,
                    timeout=self.cfg.get("timeout", 120),
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    time.sleep(2 * (attempt + 1))
                    continue
                resp.raise_for_status()
                data = resp.json()
                self.usage.calls += 1
                self.usage.add(data.get("usage"))
                return data["choices"][0]["message"]["content"]
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"LLM 调用失败（任务 {task}，模型 {model}）：{last_err}")


def call_json(llm, model: str, task: str, system: str, user: str,
              max_retries: int = 3) -> dict:
    """调用模型并强制解析为 JSON；失败则把错误反馈给模型重试。"""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    for attempt in range(max_retries):
        raw = llm.chat(messages, model=model, task=task)
        try:
            return extract_json(raw)
        except Exception as e:
            log.warning("任务 %s 第 %d 次输出解析失败：%s", task, attempt + 1, e)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content":
                    "你的上一条输出无法解析为 JSON。请重新输出：只输出一个合法的 JSON "
                    "对象，不要包含任何解释文字、前后缀或代码围栏。"},
            ]
    raise RuntimeError(f"任务 {task} 连续 {max_retries} 次无法解析 JSON")


# ---------------------------------------------------------------------------
# Mock 模式：不联网、不花钱，让整条流水线可以离线跑通（联调/演示用）。
# ---------------------------------------------------------------------------
def _mock_user(messages):
    return messages[-1]["content"] if messages else ""


def _mock_card(idx: int, revised=False):
    suffix = "（修订版）" if revised else ""
    return {
        "id": f"idea-{idx}",
        "title": f"低资源场景下基于{['课程式子集选择', '跨模态知识迁移'][idx - 1]}的高效微调框架{suffix}",
        "problem": "低资源场景下全参数微调成本高、小样本易过拟合。",
        "hypothesis": "用数据子集选择+轻量适配器的组合，能在1%数据量下达到全量微调95%以上的效果。",
        "method_sketch": "第一阶段用课程式难度排序筛选子集；第二阶段只在子集上训练适配器并做正则约束。",
        "key_related_work": [
            {"title": "LoRA: Low-Rank Adaptation of Large Language Models",
             "overlap": "同用轻量适配器，但未做数据子集选择"},
        ],
        "expected_result": "在3个分类基准上用1%数据达到全量微调的95%性能。",
        "evaluation_plan": {
            "datasets": ["SuperGLUE子集", "CLUE"],
            "baselines": ["全量微调", "LoRA", "Prefix-Tuning"],
            "metrics": ["准确率", "显存占用", "训练时长"],
        },
        "risks": ["子集选择可能引入偏差", "适配器在极小数据上可能欠拟合"],
        "novelty_claim": "与LoRA相比，首次把数据课程选择与适配器训练联合建模。",
    }


MOCK_RESPONSES = {
    "survey_queries": lambda msgs: json.dumps(
        {"queries": ["low-resource fine-tuning large language models",
                     "parameter efficient adaptation survey",
                     "data subset selection for training"]},
        ensure_ascii=False),
    "write_survey": lambda msgs: json.dumps(
        {"survey": "# 调研综述（Mock数据）\n\n## 核心问题\n低资源适配的性价比。\n\n"
                   "## 主流路线\n1. 参数高效微调（LoRA等）[1]\n2. 数据选择与课程学习[2]\n\n"
                   "## 开放问题\n- 子集选择与适配器训练的联合优化尚无系统研究。\n",
         "key_insights": ["数据选择与参数高效微调可以联合建模",
                          "低资源场景缺少统一评测协议",
                          "跨模态迁移可能缓解数据稀缺"]},
        ensure_ascii=False),
    "ideate": lambda msgs: json.dumps(
        {"ideas": [_mock_card(1), _mock_card(2)]}, ensure_ascii=False),
    "prior_queries": lambda msgs: json.dumps(
        {"queries": ["data efficient fine-tuning prior art",
                     "curriculum learning subset selection"]}, ensure_ascii=False),
    "review_b": lambda msgs: json.dumps(
        {"scores": {"novelty": 4, "feasibility": 6, "significance": 6},
         "closest_prior_work": [
             {"title": "MockPaper: Data-Efficient LLM Fine-tuning (2024)",
              "why_similar": "同样做低资源微调，但未联合建模子集选择"}],
         "strengths": ["问题真实", "评估计划具体"],
         "weaknesses": ["与[1]的差异论证不足", "未说明子集选择的计算开销"],
         "action_items": ["补充与LoRA系列的正面对比", "给出子集选择的开销估算"]},
        ensure_ascii=False),
    "review_c": lambda msgs: json.dumps(
        {"scores": {"novelty": 6, "feasibility": 5, "significance": 5},
         "closest_prior_work": [],
         "strengths": ["可借鉴主动学习中的子集选择理论"],
         "weaknesses": ["迁移方案未具体化", "与推荐系统中的课程采样结构相似"],
         "action_items": ["引用主动学习做理论支撑", "明确迁移的具体机制"]},
        ensure_ascii=False),
    "review_d": lambda msgs: json.dumps(
        {"scores": {"novelty": 5, "feasibility": 3, "significance": 5},
         "hidden_assumptions": ["假设难度排序与下游收益单调相关"],
         "failure_modes": ["1%数据可能不足以训练适配器", "课程排序本身可能比训练更贵"],
         "feasibility_estimate": "单卡A100可行，但子集选择阶段需额外约20%算力",
         "strengths": ["假设可证伪"],
         "weaknesses": ["可行性被高估", "缺少统计显著性检验方案"],
         "action_items": ["增加多随机种子与显著性检验", "先在玩具设定验证核心假设"]},
        ensure_ascii=False),
    "debate": lambda msgs: json.dumps(
        {"agree_with": ["D: 可行性顾虑部分成立"],
         "disagree_with": [{"reviewer": "B", "point": "新颖性不足",
                            "rebuttal": "检索到的先行工作均未做联合建模，差异真实存在"}],
         "score_adjustment": {"novelty": 1, "feasibility": 0, "significance": 0},
         "final_comment": "建议修订后继续"},
        ensure_ascii=False),
    "meta": lambda msgs: _mock_meta(msgs),
    "revise": lambda msgs: _mock_revise(msgs),
    "tldr": lambda msgs: json.dumps(
        {"one_liner": "用课程式子集选择+适配器联合建模，1%数据达到全量微调95%效果",
         "core_innovation": ["首次把数据选择与参数高效微调联合建模",
                             "给出可行性边界的定量刻画"],
         "method_core": "先用课程式难度排序筛选代表性子集，再只在子集上训练轻量适配器，输出校准后的低成本模型",
         "vs_prior": "LoRA等只做参数高效，主动学习只做数据选择，没人把两者放进一个目标函数",
         "why_works": "数据子集决定梯度质量，适配器容量匹配小数据，两者互补",
         "success_criteria": "3个基准上用1%数据达到全量微调95%的准确率",
         "how_to_verify": "先在SST-2每类8样本上验证子集选择带来的梯度信噪比提升",
         "biggest_risk": "子集选择本身的开销可能抵消训练节省"},
        ensure_ascii=False),
    "spec": lambda msgs: json.dumps(
        {"markdown": "# 实验规格（预注册，Mock）\n\n## 冻结项\n- 数据集：SuperGLUE子集、CLUE\n"
                     "- 基线：全量微调 / LoRA / Prefix-Tuning\n- 指标：准确率、显存、时长\n"
                     "- 种子：{0,1,2,42}，报均值±标准差\n\n## 执行阶梯\n"
                     "1. sanity check：100条数据过拟合，通过标准：acc>0.95\n"
                     "2. 玩具设定：小模型+1%数据验证核心假设\n"
                     "3. 小规模：1个基准全量跑通\n4. 全量：3个基准+消融\n"},
        ensure_ascii=False),
}


def _mock_meta(msgs):
    user = _mock_user(msgs)
    import re
    m = re.search(r"第\s*(\d+)\s*轮", user)
    rnd = int(m.group(1)) if m else 1
    if "idea-2" in user and rnd == 1:
        verdict, ready = "kill", False
        rationale = "新颖性证据不成立且可行性有硬伤，毙掉。"
        actions = []
    elif rnd >= 2:
        verdict, ready = "advance", True
        rationale = "修订已解决主要顾虑，可进入实验设计。"
        actions = ["按实验规格执行", "先跑sanity check"]
    else:
        verdict, ready = "revise", False
        rationale = "方向可行，但需补充与先行工作的正面对比和显著性方案。"
        actions = ["补充与LoRA的对比", "增加统计显著性检验"]
    return json.dumps(
        {"verdict": verdict, "rationale": rationale, "action_items": actions,
         "ready_for_experiment": ready, "weighted_score": 5.1},
        ensure_ascii=False)


def _mock_revise(msgs):
    import re
    user = _mock_user(msgs)
    m = re.search(r"idea-(\d+)", user)
    idx = int(m.group(1)) if m else 1
    return json.dumps(_mock_card(idx, revised=True), ensure_ascii=False)


class MockClient:
    """按任务名返回固定 JSON，让流水线可以零成本联调。"""

    def __init__(self, cfg: dict, usage: Usage):
        self.usage = usage

    def chat(self, messages, model: str, task: str) -> str:
        if task not in MOCK_RESPONSES:
            raise KeyError(f"Mock 模式未实现任务：{task}")
        self.usage.calls += 1
        self.usage.prompt_tokens += 100
        self.usage.completion_tokens += 300
        return MOCK_RESPONSES[task](messages)
