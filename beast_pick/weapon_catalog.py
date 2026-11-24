"""Game-specific selectable weapon and throwable definitions."""
from functools import lru_cache
import json
from pathlib import Path

from .catalog import load_catalog


@lru_cache(maxsize=2)
def weapon_items(game: str) -> dict:
    if game == 'beast':
        items = load_catalog()['items']
        return {key: {'name': entry['name'], 'group': entry['group'], 'category': entry['category']}
                for key, entry in items.items() if entry['group'] in ('weapons', 'throwables')}
    if game == 'dl2':
        path = Path(__file__).parent / 'data' / 'dl2_weapon_items.json'
        return json.loads(path.read_text(encoding='utf-8'))['items']
    raise ValueError('请先选择游戏。')


def checked_exclusions(game: str, value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20000 or any(not isinstance(x, str) for x in value):
        raise ValueError('武器排除列表格式不正确。')
    catalog = weapon_items(game)
    if any(key not in catalog for key in value):
        raise ValueError('排除列表中有不属于当前游戏的物品，请重新选择。')
    return sorted(set(value))


def weapon_groups(game: str) -> list[tuple[str, str, list[str]]]:
    groups = {}
    for identity, item in weapon_items(game).items():
        groups.setdefault((item['name'], item['group']), []).append(identity)
    return [(name, group, sorted(ids)) for (name, group), ids in
            sorted(groups.items(), key=lambda x: (x[0][0].casefold(), x[0][1]))]