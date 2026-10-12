# -*- coding: utf-8 -*-
"""Idea Card：整个流程围绕这张卡迭代，而不是围绕聊天记录。
每轮讨论的输出是「修订后的卡片 + 明确的 action items」，卡片可以 diff，迭代才可度量。"""
import json


class IdeaCard:
    FIELDS = ["id", "title", "problem", "hypothesis", "method_sketch",
              "expected_result", "novelty_claim"]

    def __init__(self, data: dict, idx: int):
        self.id = str(data.get("id") or f"idea-{idx}")
        self.title = str(data.get("title") or f"未命名idea-{idx}")
        self.problem = str(data.get("problem") or "")
        self.hypothesis = str(data.get("hypothesis") or "")
        self.method_sketch = str(data.get("method_sketch") or "")
        self.key_related_work = data.get("key_related_work") or []
        if isinstance(self.key_related_work, str):
            self.key_related_work = [{"title": self.key_related_work, "overlap": ""}]
        self.expected_result = str(data.get("expected_result") or "")
        self.evaluation_plan = data.get("evaluation_plan") or {}
        if isinstance(self.evaluation_plan, str):
            self.evaluation_plan = {"说明": self.evaluation_plan}
        self.risks = data.get("risks") or []
        if isinstance(self.risks, str):
            self.risks = [self.risks]
        self.novelty_claim = str(data.get("novelty_claim") or "")
        # 保留模型输出的额外字段，不丢信息
        self.extra = {k: v for k, v in data.items()
                      if k not in FIELDS_KNOWN and not k.startswith("_")}

    def to_dict(self):
        d = {
            "id": self.id, "title": self.title, "problem": self.problem,
            "hypothesis": self.hypothesis, "method_sketch": self.method_sketch,
            "key_related_work": self.key_related_work,
            "expected_result": self.expected_result,
            "evaluation_plan": self.evaluation_plan,
            "risks": self.risks, "novelty_claim": self.novelty_claim,
        }
        d.update(self.extra)
        return d

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def render_markdown(self) -> str:
        lines = [f"## {self.id}：{self.title}", ""]
        lines += [f"**问题**：{self.problem}", ""]
        lines += [f"**核心假设（可证伪）**：{self.hypothesis}", ""]
        lines += [f"**方法草图**：{self.method_sketch}", ""]
        if self.key_related_work:
            lines += ["**最接近的先行工作与区别**："]
            for w in self.key_related_work:
                if isinstance(w, dict):
                    lines.append(f"- {w.get('title', '')} —— 重叠点：{w.get('overlap', '')}")
                else:
                    lines.append(f"- {w}")
            lines.append("")
        lines += [f"**预期结果**：{self.expected_result}", ""]
        ep = self.evaluation_plan
        if ep:
            lines.append("**评估计划**：")
            for k, v in ep.items():
                if isinstance(v, (list, tuple)):
                    v = "、".join(str(x) for x in v)
                lines.append(f"- {k}：{v}")
            lines.append("")
        if self.risks:
            lines.append("**主要风险**：")
            lines += [f"- {r}" for r in self.risks]
            lines.append("")
        lines += [f"**新颖性声明**：{self.novelty_claim}", ""]
        return "\n".join(lines)


FIELDS_KNOWN = set(IdeaCard.FIELDS) | {
    "key_related_work", "evaluation_plan", "risks"}
