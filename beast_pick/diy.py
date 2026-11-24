"""Weapon catalogue and DIY plan model for the second page.

The catalogue is extracted from the game's own scripts (tools/build_weapon_catalog.py).
Nothing here talks to the game process; validation and preview stay pure so they can be
unit tested without attaching.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / 'data' / 'weapons.json'
PROFILE = Path(__file__).parent / 'profiles' / 'current.json'

# Editable instance stats, with the range the game itself uses for generated loot.
STAT_LIMITS = {
    'CriticalProb': (0.0, 1.0),        # 0–100 %
    'CriticalDamage': (1.0, 20.0),     # multiplier
    'CriticalCondition': (1.0, 20000.0),  # durability
    'DamageRange': (0.0, 10.0),
    'DamageSize': (0.0, 20.0),
    'StaminaUsage': (0.0, 5.0),
    'StaminaDamage': (0.0, 20000.0),
    'PhysicsDamageMul': (0.0, 100.0),
    'PowerAttackDamageMul': (0.0, 10.0),
    'ConfusionProb': (0.0, 1.0),
}

STAT_LABELS = {
    'CriticalProb': ('暴击率', '%'),
    'CriticalDamage': ('暴击伤害', '×'),
    'CriticalCondition': ('耐久度', ''),
    'DamageRange': ('伤害浮动', ''),
    'DamageSize': ('伤害范围', ''),
    'StaminaUsage': ('耐力消耗', ''),
    'StaminaDamage': ('耐力伤害', ''),
    'PhysicsDamageMul': ('物理伤害倍率', '×'),
    'PowerAttackDamageMul': ('重击伤害倍率', '×'),
    'ConfusionProb': ('击晕几率', '%'),
}

MAX_AFFIXES = 8


@lru_cache(maxsize=1)
def catalogue() -> dict:
    return json.loads(DATA.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def diy_layout() -> dict:
    """The calibrated write layout for this build (`profiles/current.json` → `diy`)."""
    try:
        profile = json.loads(PROFILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return profile.get('diy') or {}


@lru_cache(maxsize=1)
def writable_stats() -> dict[str, dict]:
    """Stats this build can actually write, taken from the calibrated profile.

    Empty means the build has no measured layout; the page then keeps those
    fields read-only instead of promising a write that would be refused.
    """
    return diy_layout().get('stats') or {}


@lru_cache(maxsize=1)
def writable_kind() -> str:
    """Which weapon kind the measured offsets belong to.

    The offsets were located inside `ItemDescMelee`. A firearm instance embeds a
    different description class, so the same numbers would land on unrelated
    fields — the page must not offer them there.
    """
    desc = str(diy_layout().get('desc_type') or '')
    if 'Firearm' in desc:
        return 'firearm'
    if 'Melee' in desc:
        return 'melee'
    return ''


def writable_for(entry: dict | None) -> bool:
    """True when this weapon's description class matches the calibrated layout."""
    if not writable_stats():
        return False
    return not writable_kind() or not entry or entry.get('kind') == writable_kind()



def weapons() -> dict:
    return catalogue()['weapons']


LEVEL_BAND = re.compile(r'_r(\d+)$')
# In source order (inventorystuff.scr), the masks are 1, 2, 4 and 8. Display
# order is independent and follows the catalogue's localized slot list.
CRAFT_SLOT_FLAGS = ('MOD_SLOT_SHAFT', 'MOD_SLOT_TIP', 'MOD_SLOT_GRIP', 'MOD_SLOT_CHARM')
STAT_SUFFIXES = {'Percent': '%', 'SignedPercent': '%', 'Seconds': ' 秒',
                 'Minutes': ' 分钟', 'Meters': ' 米'}


def _weapon_slot_keys(entry: dict) -> tuple[str, ...]:
    raw = entry.get('s', {}).get('CraftingSlots')
    if not isinstance(raw, str):
        return ()
    flags = [part.strip().lower() for part in raw.split(',')]
    if len(flags) != len(CRAFT_SLOT_FLAGS) or any(part not in ('true', 'false') for part in flags):
        return ()
    return tuple(key for key, part in zip(CRAFT_SLOT_FLAGS, flags) if part == 'true')


@lru_cache(maxsize=1)
def families() -> dict[str, dict]:
    """One row per real weapon.

    The generator emits every level band of a weapon separately (`..._r1` through
    `..._r15`), which is 2,735 definitions for only a few hundred actual weapons.
    They share a name, subtype, damage table, quality and slots, so the page shows
    one entry per weapon and keeps the band ids as variants. The highest band is the
    representative because its Condition values are the ones players recognise.
    """
    groups: dict[tuple, list[str]] = {}
    for key, entry in sorted(weapons().items()):
        signature = (entry['n'], entry['kind'], entry['sub'], entry.get('tbl') or '', entry.get('q'),
                     _weapon_slot_keys(entry))
        groups.setdefault(signature, []).append(key)
    result = {}
    for signature, keys in groups.items():
        chosen = max(keys, key=lambda key: (int(LEVEL_BAND.search(key).group(1)) if LEVEL_BAND.search(key) else 0,
                                           key))
        entry = dict(weapons()[chosen])
        entry['id'] = chosen
        entry['variants'] = keys
        result[chosen] = entry
    return result


@lru_cache(maxsize=1)
def variant_index() -> dict[str, str]:
    return {variant: family['id'] for family in families().values() for variant in family['variants']}


def find_weapon(weapon_id: str) -> dict | None:
    """Resolve a definition ID (any level band) to its catalogue entry."""
    return families().get(weapon_id) or families().get(variant_index().get(weapon_id, ''))


def mods() -> dict:
    return catalogue()['mods']


def affixes() -> dict:
    return catalogue()['affixes']


def colors() -> list[dict]:
    return catalogue()['colors']


def slots() -> list[dict]:
    return catalogue()['slots']


def weapon_slots(weapon_id: str) -> list[dict]:
    keys = _weapon_slot_keys(weapons().get(weapon_id, {}))
    return [slot for slot in slots() if slot['key'] in keys]


def tiers() -> dict:
    return catalogue()['tiers']


def special() -> dict:
    """Damage tables defined as a formula over the target's health, not a number."""
    return catalogue().get('special') or {}


def color_name(value: int | None) -> str:
    for entry in colors():
        if entry['value'] == value:
            return entry['name']
    return f'品质 {value}'


def mod_label(mod_id: str) -> str:
    """Attachment names repeat across tiers, so show the tier and quality."""
    entry = mods().get(mod_id) or {}
    name = entry.get('n') or mod_id
    tags = []
    if entry.get('level'):
        tags.append(f"T{entry['level'][0]}")
    if entry.get('color'):
        tags.append(str(entry['color']))
    if entry.get('element') and entry['element'] not in name:
        tags.append(entry['element'])
    return f"{name}（{'·'.join(tags)}）" if tags else name


def mod_details(mod_id: str) -> str:
    """Use the game's player-facing stats, not internal crafting-effect values."""
    entry = mods().get(mod_id)
    if not entry:
        return ''
    heading = [f"品质：{entry.get('color') or '未标注'}"]
    if entry.get('element'):
        heading.append(f"元素：{entry['element']}")
    details = ['　'.join(heading)]
    for stat in entry.get('uistats', []):
        value = stat.get('value')
        if value is None:
            continue
        unit = stat.get('format')
        number = f'{value:+g}' if unit == 'SignedPercent' else f'{value:g}'
        suffix = STAT_SUFFIXES.get(unit, '')
        scaling = '（基准值，随等级缩放）' if stat.get('scale') else ''
        details.append(f"{stat['name']}：{number}{suffix}{scaling}")
    if len(details) == 1:
        details.append('游戏目录未标注具体属性。')
    return '\n'.join(details)


def affix_label(affix_key: str) -> str:
    entry = affixes().get(affix_key) or {}
    name = entry.get('n') or affix_key
    if '_Coop_Base' in affix_key:
        return f"{name}（联机）"
    return name


def damage_table(weapon_id: str) -> list:
    entry = weapons().get(weapon_id) or {}
    return tiers().get(entry.get('tbl', ''), [])


def damage_formula(weapon_id: str) -> str | None:
    """Quest / gimmick weapons scale off the victim's health instead of a table."""
    entry = weapons().get(weapon_id) or {}
    return special().get(entry.get('tbl', ''))


def damage_at(weapon_id: str, level: int) -> float | None:
    table = damage_table(weapon_id)
    if not table or not 0 <= level < len(table):
        return None
    return float(table[level])


def mod_effects(plan: dict) -> dict:
    """Sum the crafting effects of the chosen attachments (percentage values).

    A few definitions list the same effect twice; counting it twice would claim a
    bonus the item does not actually give, so identical pairs are counted once.
    """
    total: dict[str, float] = {}
    for slot_key, mod_id in (plan.get('mods') or {}).items():
        entry = mods().get(mod_id or '')
        if not entry:
            continue
        seen = set()
        for effect in entry.get('effects', []):
            if effect.get('value') is None:
                continue
            signature = (effect['key'], float(effect['value']))
            if signature in seen:
                continue
            seen.add(signature)
            total[effect['key']] = total.get(effect['key'], 0.0) + float(effect['value'])
    return total


def validate_plan(plan: dict) -> dict:
    """Return a normalised plan or raise ValueError with a Chinese explanation."""
    if not isinstance(plan, dict):
        raise ValueError('DIY 方案格式不正确')
    weapon_id = plan.get('weapon')
    if weapon_id not in weapons():
        raise ValueError('未知武器 ID')

    quality = plan.get('quality', 0)
    if isinstance(quality, bool) or not isinstance(quality, int) or not any(c['value'] == quality for c in colors()):
        raise ValueError('品质应为 0–6 之间的整数')

    level = plan.get('level', 0)
    table = damage_table(weapon_id)
    if isinstance(level, bool) or not isinstance(level, int) or level < 0:
        raise ValueError('档位不正确')
    if table and level >= len(table):
        raise ValueError(f'该武器档位范围为 0–{len(table) - 1}')

    stats = {}
    for key, value in (plan.get('stats') or {}).items():
        if key not in STAT_LIMITS:
            raise ValueError(f'不支持的属性：{key}')
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'属性 {key} 必须是数字')
        low, high = STAT_LIMITS[key]
        if not low <= float(value) <= high:
            raise ValueError(f'属性 {STAT_LABELS[key][0]} 应在 {low:g}–{high:g} 之间')
        stats[key] = float(value)

    chosen_mods = {}
    known_slots = {slot['key']: slot['name'] for slot in slots()}
    available_slots = {slot['key'] for slot in weapon_slots(weapon_id)}
    for slot, mod_id in (plan.get('mods') or {}).items():
        if mod_id in (None, ''):
            continue
        if slot not in known_slots:
            raise ValueError(f'未知配件插槽：{slot}')
        if slot not in available_slots:
            raise ValueError(f"该武器不支持「{known_slots[slot]}」插槽")
        entry = mods().get(mod_id)
        if not entry:
            raise ValueError('未知配件')
        if slot not in entry['slots']:
            raise ValueError(f"配件「{entry['n']}」不能安装到「{known_slots[slot]}」插槽")
        chosen_mods[slot] = mod_id

    chosen_affixes = []
    for affix in plan.get('affixes') or []:
        if affix not in affixes():
            raise ValueError('未知词条')
        if affix not in chosen_affixes:
            chosen_affixes.append(affix)
    if len(chosen_affixes) > MAX_AFFIXES:
        raise ValueError(f'最多选择 {MAX_AFFIXES} 条词条')

    return {
        'weapon': weapon_id,
        'quality': quality,
        'level': level,
        'stats': stats,
        'mods': chosen_mods,
        'affixes': chosen_affixes,
    }


def prepare_generation(plan: dict) -> dict:
    """Validate the writable melee-only subset and resolve the game's item ID.

    The catalog groups same-named level variants. The selected level is encoded
    by the concrete `_rN` definition ID passed to the game's inventory grant
    routine; stats are applied to the created instance by the runtime agent.
    Quality, attachments, and affixes are definition-side fields not calibrated
    for runtime writes, so generation rejects non-default selections instead of
    silently claiming they were applied.
    """
    normalized = validate_plan(plan)
    family = find_weapon(normalized['weapon'])
    if not family or family.get('kind') != 'melee':
        raise ValueError('生成到背包目前只支持已标定的近战武器')
    if not normalized['stats']:
        raise ValueError('至少勾选一项已支持属性，再生成到背包')
    unsupported = sorted(set(normalized['stats']) - set(writable_stats()))
    if unsupported:
        labels = '、'.join(STAT_LABELS.get(key, (key, ''))[0] for key in unsupported)
        raise ValueError('当前构建未标定这些属性：' + labels)
    if normalized['quality'] != int(family.get('q') or 0):
        raise ValueError('自定义品质尚未标定；请保持该武器定义的默认品质')
    if normalized['mods'] or normalized['affixes']:
        raise ValueError('自定义配件与词条尚未标定；清空配件和词条后再生成')

    variants = family.get('variants') or [family['id']]
    table = damage_table(family['id'])
    if table:
        suffix = f'_r{normalized["level"] + 1}'
        candidate = re.sub(r'_r\d+$', suffix, family['id'])
        if candidate not in variants or candidate not in weapons():
            matches = [key for key in variants if key.endswith(suffix)]
            if not matches:
                raise ValueError('所选档位没有对应的游戏武器定义')
            candidate = matches[0]
    else:
        candidate = family['id']
    return {**normalized, 'item_id': candidate, 'kind': 'melee'}


def preview(plan: dict) -> dict:
    """Human readable summary of what the plan produces."""
    plan = validate_plan(plan)
    weapon = weapons()[plan['weapon']]
    base = damage_at(plan['weapon'], plan['level'])
    effects = mod_effects(plan)
    bonus = effects.get('CraftingEffect_IncreasedDamageMul', 0.0)
    total = None if base is None else round(base * (1 + bonus / 100.0), 1)
    durability = plan['stats'].get('CriticalCondition', weapon['s'].get('CriticalCondition'))
    return {
        'name': weapon['n'],
        'subtype': weapon['sub'],
        'quality': color_name(plan['quality']),
        'level': plan['level'],
        'damage': base,
        'damage_formula': damage_formula(plan['weapon']),
        'damage_bonus': bonus,
        'damage_total': total,
        'durability': durability,
        'mods': [{'slot': slot, 'name': mod_label(mod), 'element': mods()[mod].get('element')}
                 for slot, mod in plan['mods'].items()],
        'affix_names': [affix_label(key) for key in plan['affixes']],
        'effects': [{'key': key, 'value': value} for key, value in effects.items()],
    }


def export_plan(plan: dict) -> str:
    """Portable JSON for sharing a build with someone else."""
    plan = validate_plan(plan)
    summary = preview(plan)
    payload = {
        'tool': 'BP DIY 武器方案',
        'version': catalogue()['version'],
        'weapon': plan['weapon'],
        'weapon_name': summary['name'],
        'subtype': summary['subtype'],
        'quality': summary['quality'],
        'level': plan['level'],
        'damage': summary['damage_total'],
        'stats': plan['stats'],
        'mods': plan['mods'],
        'affixes': plan['affixes'],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
