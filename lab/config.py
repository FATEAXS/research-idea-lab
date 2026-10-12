# -*- coding: utf-8 -*-
"""配置加载：内置默认值 <- 用户 config.yaml <- 环境变量覆盖。
字符串里的 ${VAR} 会被同名环境变量替换（用于 api_key 不落盘）。"""
import copy
import os
import re

import yaml

DEFAULTS = {
    "llm": {
        "provider": "openai_compat",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key": "",
        "temperature": 0.7,
        "timeout": 120,
        "max_tokens": 8000,
        "models": {
            "researcher": "glm-4.6",
            "reviewer_domain": "glm-4.6",
            "reviewer_cross": "glm-4.6",
            "reviewer_theory": "glm-4.6",
            "meta": "glm-4.6",
        },
    },
    "retrieval": {
        "providers": ["arxiv", "crossref"],
        "max_per_query": 8,
        "quality_filter": True,
        "s2_api_key": "",
        "arxiv_min_interval": 3.0,
        "s2_min_interval": 1.2,
        "openalex_min_interval": 0.5,
        "crossref_min_interval": 1.0,
    },
    "pipeline": {
        "num_ideas": 4,
        "max_rounds": 2,
        "debate": True,
        "kill_threshold": 4.5,
        "converge_epsilon": 0.3,
        "spec_top_k": 1,
    },
    "run": {"output_dir": "runs"},
}


def _expand_env(obj):
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    if isinstance(obj, str):
        return re.sub(
            r"\$\{(\w+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            obj,
        )
    return obj


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        cfg = deep_merge(cfg, _expand_env(user_cfg))
    # 环境变量优先级最高，方便不改文件临时切换
    if os.environ.get("IDEA_LAB_BASE_URL"):
        cfg["llm"]["base_url"] = os.environ["IDEA_LAB_BASE_URL"]
    if os.environ.get("IDEA_LAB_API_KEY"):
        cfg["llm"]["api_key"] = os.environ["IDEA_LAB_API_KEY"]
    return cfg
