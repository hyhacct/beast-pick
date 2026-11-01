"""Exact inventory identities extracted from this supported game build."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    return json.loads((Path(__file__).parent / "data" / "items.json").read_text(encoding="utf-8"))


def checked_rules(value=None) -> dict:
    if value is None:
        return {"items": {}, "subtypes": {}}
    if not isinstance(value, dict) or set(value) - {"items", "subtypes"}:
        raise ValueError("详细筛选格式不正确")
    catalog = load_catalog()
    result = {}
    for kind in ("items", "subtypes"):
        rules = value.get(kind, {})
        if not isinstance(rules, dict) or any(key not in catalog[kind] or type(v) is not bool for key, v in rules.items()):
            raise ValueError("详细筛选包含未知物品、子类或无效规则")
        result[kind] = dict(rules)
    return result


def has_allowed(selection, rules) -> bool:
    return any(selection.values()) or any(v for group in rules.values() for v in group.values())
