# -*- coding: utf-8 -*-
"""提示词模板加载：prompts/ 下每个 .md 文件 = SYSTEM 段 + 一行 '---' + USER 段。
变量用 {{name}} 占位，渲染用字符串替换（不能用 str.format——模板里有 JSON 花括号）。"""
from pathlib import Path

_CACHE = {}


def render(prompt_dir, name: str, **variables):
    """返回 (system, user) 两个字符串。"""
    key = (str(prompt_dir), name)
    tpl = _CACHE.get(key)
    if tpl is None:
        path = Path(prompt_dir) / f"{name}.md"
        raw = path.read_text(encoding="utf-8")
        if "\n---\n" in raw:
            system, user = raw.split("\n---\n", 1)
        else:
            system, user = "", raw
        tpl = (system.strip(), user.strip())
        _CACHE[key] = tpl
    system, user = tpl
    for k, v in variables.items():
        token = "{{" + k + "}}"
        system = system.replace(token, str(v))
        user = user.replace(token, str(v))
    return system, user
