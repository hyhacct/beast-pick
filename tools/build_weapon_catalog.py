"""Extract the weapon / quality / attachment / affix tables used by the DIY page.

Read-only: the game's own scripts inside data0.pak and the Chinese localization in
datacn.pak are parsed into beast_pick/data/weapons.json. Nothing is written to the
game installation.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = Path(r'D:\App\Steam\steamapps\common\Dying Light The Beast\ph_ft\source')
TARGET = ROOT / 'beast_pick' / 'data' / 'weapons.json'

# A plain damage value is a number, optionally scaled (`110.0 *0.01`).
PLAIN_DAMAGE = re.compile(r'^-?\d+(?:\.\d+)?(?:\s*\*\s*-?\d+(?:\.\d+)?)*$')

# Fields that describe a weapon instance and are worth showing / editing.
WEAPON_FIELDS = [
    'DamageType', 'StatsType', 'CriticalProb', 'CriticalDamage', 'CriticalCondition', 'DamageRange',
    'DamageSize', 'StaminaUsage', 'StaminaDamage', 'PowerAttackDamageMul', 'PhysicsDamageMul',
    'ConfusionProb', 'TwoHanded', 'Reparable', 'Condition', 'CraftingSlots', 'ItemLevel',
    'AmmoCount', 'ShotTime', 'ReloadTime', 'BulletsPerShot', 'BulletSpeed', 'FirePointDamage',
]

SUBTYPE_LABELS = {
    'ItemType_Stick': '棍棒类', 'ItemType_Knuckles': '指虎', 'ItemType_Collision': '碰撞类',
    'ItemType_Fists': '特殊近身', 'ItemType_Pistol': '手枪', 'ItemType_Revolver': '左轮手枪',
    'ItemType_Rifle': '步枪', 'ItemType_Shotgun': '霰弹枪', 'ItemType_SubMachineGun': '冲锋枪',
    'ItemType_GrenadeLauncher': '榴弹发射器', 'ItemType_SawbladeLauncher': '锯片发射器',
    'ItemType_FlameThrower': '喷火器', 'ItemType_SummoningTool': '召唤工具',
    'EWpnSubtype_Axe': '斧头', 'EWpnSubtype_Machete': '砍刀', 'EWpnSubtype_Mace': '钉头锤',
    'EWpnSubtype_Hammer': '锤子', 'EWpnSubtype_Stick': '棍棒类', 'EWpnSubtype_Sword': '长剑',
    'EWpnSubtype_Halberd': '长柄武器', 'EWpnSubtype_Knife': '刀具', 'EWpnSubtype_Bow': '弓',
    'EWpnSubtype_Crossbow': '弩', 'EWpnSubtype_TwoHandedAxe': '双手斧', 'EWpnSubtype_TwoHandedHammer': '双手锤',
    'CategoryType_Melee': '近战武器',
}

SLOT_LABELS = {
    'MOD_SLOT_TIP': '刀尖', 'MOD_SLOT_SHAFT': '刀柄', 'MOD_SLOT_GRIP': '握把', 'MOD_SLOT_CHARM': '挂饰',
}

COLOR_LABELS = [
    ('Color_White', '白色', 0), ('Color_Green', '绿色', 1), ('Color_Blue', '蓝色', 2),
    ('Color_Violet', '紫色', 3), ('Color_Orange', '橙色', 4), ('Color_Platinum', '铂金', 5),
    ('Color_Exotic', '异域', 6),
]

ELEMENT_LABELS = {
    'Elemental_Burning': '燃烧', 'Elemental_Shock': '电击', 'Elemental_Toxic': '毒素',
    'Elemental_Bleeding': '流血', 'Elemental_Freezing': '冰冻', 'Elemental_Acid': '腐蚀',
}

EFFECT_LABELS = {
    'CraftingEffect_IncreasedDamageMul': '伤害提升', 'CraftingEffect_IncreasedDurabilityAdd': '耐久提升',
    'CraftingEffect_DecreasedStaminaUsage': '减少耐力消耗',
    'CraftingEffect_DecreasedStaminaUsageMeleeAttacks': '减少攻击耐力消耗',
    'CraftingEffect_IncreasedArmorDamage': '护甲伤害提升',
    'CraftingEffect_DecreasedDurabilityDamage': '减少耐久损耗',
    'CraftingEffect_IncreasedBackStabDamage': '背刺伤害提升',
}

LAYER_VALUE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*("([^"]*)"|[^()]*?)\s*\)')
UI_STAT = re.compile(
    r'\bUIStat(?:Scalable)?\(\s*"&([^&]+)&"\s*,\s*(-?\d+(?:\.\d+)?)\s*'
    r'(?:,\s*"([^"]+)")?(?:\s*,\s*"([^"]+)")?\s*\)'
)
# Inline styling the game renderer understands but a plain label must not show.
MARKUP = re.compile(r'%[A-Za-z_]\w*(?:\([^)]*\))?')
NOISE_WORDS = {'mod', 'mods', 'affix', 'ft', 'dlc', 'data', 'random', 'invisible'}
OUTFIT_PREFIXES = ('Outfit', 'Outfits', 'Tankmonster', 'Dragonwarrior', 'pilgrimpo', 'Lubu', 'Vampire')


def clean_label(text: str) -> str:
    text = MARKUP.sub('', text or '')
    return re.sub(r'\s+', ' ', text).strip()


def humanize(token: str) -> str:
    """Readable stand-in for definitions the Chinese localisation never covered."""
    words = []
    for chunk in re.split(r'[_\s]+', token or ''):
        for word in re.findall(r'[A-Z]+(?![a-z])\d*|[A-Z][a-z]+\d*|[a-z]+\d+|\d+', chunk) or [chunk]:
            if word and word.lower() not in NOISE_WORDS:
                words.append(word)
    return ' '.join(words) or token


def localization(blob: bytes) -> dict:
    def array(name: bytes):
        offset = blob.index(name) + len(name) + 4
        count = struct.unpack_from('<I', blob, offset)[0]
        offset += 4
        result = []
        for _ in range(count):
            length = struct.unpack_from('<H', blob, offset)[0]
            offset += 2
            result.append(blob[offset:offset + length].decode('utf-8'))
            offset += length
        return result

    keys, values = array(b'm_keys'), array(b'm_Values')
    assert len(keys) == len(values)
    return dict(zip(keys, values))


def blocks(text: str):
    """Yield (sub_name, item_id, category, body) with comments stripped."""
    text = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/', '', text)
    pattern = re.compile(r'\b(sub\s+(\w+)\s*\([^)]*\)|Item\s*\(\s*"([^"]+)"\s*,\s*(\w+)\s*\))\s*\{')
    for match in pattern.finditer(text):
        start = match.end()
        depth, quoted, escaped, i = 1, False, False, start
        while i < len(text) and depth:
            c = text[i]
            if escaped:
                escaped = False
            elif c == '\\' and quoted:
                escaped = True
            elif c == '"':
                quoted = not quoted
            elif not quoted:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
            i += 1
        if depth:
            raise ValueError('Unbalanced block: ' + str(match.group(2) or match.group(3)))
        yield match.group(2), match.group(3), match.group(4), text[start:i - 1]


def resolved_label(key: str, translations: dict, fallback: str) -> str:
    original = fallback
    translated = translations.get(key.lower())
    label = translated or original
    for _ in range(16):
        if '&' not in label:
            break
        updated = re.sub(r'&([^&\r\n]+)&', lambda m: translations.get(m[1].lower(), m[0]), label)
        if updated == label:
            label = original
            break
        label = updated
    label = clean_label(label)
    if translated is None or not label:
        label = humanize(original)
    return label


class Fields:
    """Resolve `use macro()` chains into one flat field map per definition."""

    def __init__(self, macros: dict):
        self.macros = macros

    def of(self, body: str, seen=()) -> dict:
        result = {}
        for match in LAYER_VALUE.finditer(body):
            key, raw = match.group(1), match.group(2)
            if key == 'use':
                continue
            if key in self.macros:
                if key in seen or len(seen) > 16:
                    continue
                continue
            value = raw.strip()
            if value.startswith('"'):
                value = value[1:-1]
            result[key] = value
        # `use x();` expands to the macro body, later overrides win.
        for name in re.findall(r'\buse\s+(\w+)\s*\(\s*\)', body):
            if name in self.macros and name not in seen:
                result.update(self.of(self.macros[name], seen + (name,)))
        for match in LAYER_VALUE.finditer(body):
            key, raw = match.group(1), match.group(2)
            if key == 'use' or key in self.macros:
                continue
            value = raw.strip()
            if value.startswith('"'):
                value = value[1:-1]
            result[key] = value
        return result


def numeric(value):
    if value is None:
        return None
    text = str(value).strip()
    match = re.match(r'^(-?\d+(?:\.\d+)?)', text)
    if not match:
        return None
    number = float(match.group(1))
    if text.replace(' ', '') != match.group(1) and '*' in text:
        for factor in re.findall(r'\*\s*(-?\d+(?:\.\d+)?)', text):
            number *= float(factor)
    return int(number) if number == int(number) else number


def ui_stats(body: str, loc: dict) -> list[dict]:
    result = []
    for key, value, unit, scale in dict.fromkeys(UI_STAT.findall(body)):
        stat = {'key': key, 'name': resolved_label(key, loc, key), 'value': numeric(value)}
        if unit:
            stat['format'] = unit
        if scale and scale != 'None':
            stat['scale'] = scale
        result.append(stat)
    return result


def damage_number(text: str):
    """Damage table entries are either one number, a scaled number or a min–max range."""
    text = str(text).strip()
    bounds = re.fullmatch(r'(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)', text)
    if bounds:
        number = (float(bounds.group(1)) + float(bounds.group(2))) / 2
        return int(number) if number == int(number) else round(number, 1)
    if PLAIN_DAMAGE.match(text):
        return numeric(text)
    return None


def main() -> None:
    with zipfile.ZipFile(SOURCE / 'data_lang' / 'datacn.pak') as z:
        loc = {k.lower(): v for k, v in localization(z.read('texts/pc/pc_cn_lang.binsloc')).items()}

    macros: dict[str, str] = {}
    items: dict[str, tuple[str, str]] = {}
    texts: dict[str, str] = {}
    with zipfile.ZipFile(SOURCE / 'data0.pak') as z:
        for name in z.namelist():
            if not name.startswith('scripts/inventory/') or not name.endswith('.scr'):
                continue
            if '/' in name[len('scripts/inventory/'):]:
                continue
            text = z.read(name).decode('utf-8-sig', errors='replace')
            texts[name] = text
            for macro, item, category, body in blocks(text):
                if macro:
                    macros[macro] = body
                elif item:
                    previous = items.get(item)
                    items[item] = (category, (previous[1] + '\n' if previous else '') + body)

    fields = Fields(macros)

    # Damage tables: every Damage("<table>_<tier>") block holds one damage-type value.
    damage: dict[str, dict] = {}
    formula: dict[str, str] = {}
    damage_text = ''
    with zipfile.ZipFile(SOURCE / 'data0.pak') as z:
        for name in ('scripts/damagedefinitions.scr', 'scripts/inventory/damagedefinitions.scr'):
            try:
                damage_text += z.read(name).decode('utf-8-sig', errors='replace')
            except KeyError:
                continue
    for table, body in re.findall(r'Damage\("([a-z0-9_]+)"\)\s*\{([^}]*)\}', damage_text):
        raw = {k: v.strip() for k, v in re.findall(r'(Blunt|Cut|Bullet|Explosion|Fire|Poison|Shock|Freeze)\("([^"]*)"\)', body)}
        values = {k: damage_number(v) for k, v in raw.items()}
        # Quest and gimmick weapons scale off the victim's health (`Cut("1%-101% of
        # MaxHealth")`). Those cannot be shown as a fixed number, so they are kept
        # aside instead of being flattened into a misleading "1 damage".
        if any(value is None for value in values.values()):
            formula[table] = next(iter(raw.values()))
            continue
        if values:
            damage[table] = values
    tiers: dict[str, list] = {}
    for name in damage:
        match = re.match(r'^(.*?)(?:_(\d+))$', name)
        if not match:
            continue
        base, index = match.group(1), int(match.group(2))
        row = tiers.setdefault(base, [])
        while len(row) <= index:
            row.append(None)
        entry = damage[name]
        row[index] = entry.get('Cut', entry.get('Blunt', entry.get('Bullet'))) or next(iter(entry.values()))
    tiers = {base: [x for x in row if x is not None]
             for base, row in tiers.items() if any(x is not None for x in row)}
    special = {}
    for table, text in formula.items():
        special.setdefault(re.sub(r'_\d+$', '', table), text)

    weapons: dict[str, dict] = {}
    mods: dict[str, dict] = {}
    for identity, (category, body) in items.items():
        attrs = fields.of(body)
        number = int(re.match(r'-?\d+', category).group()) if category.lstrip('-').isdigit() else None
        if number is None:
            enum = re.search(r'CategoryType_(\w+)', category)
            number = {'Melee': 0, 'Firearm': 1}.get(enum.group(1) if enum else '', None)
        if number not in (0, 1) and attrs.get('ItemType') != 'ItemType_CraftPart':
            continue
        name_key = attrs.get('Name', '').strip('&') or identity + '_n'
        label = resolved_label(name_key, loc, identity)
        localized = loc.get(name_key.lower()) is not None
        if number in (0, 1):
            # Unlocalised definitions are effect/ability items (shockwaves, fury
            # procs) that share the melee category but can never be an inventory
            # weapon, so they would only pollute the catalogue.
            if not localized or re.search(r'debug|test|playtest|npc', identity, re.I):
                continue
            subtype = attrs.get('WpnSubtype') or attrs.get('ItemType') or 'CategoryType_Melee'
            entry = {
                'n': label,
                'kind': 'melee' if number == 0 else 'firearm',
                'sub': SUBTYPE_LABELS.get(subtype, re.sub(r'^(EWpnSubtype_|ItemType_|CategoryType_)', '', subtype)),
            }
            stats = {}
            for key in WEAPON_FIELDS:
                if key not in attrs:
                    continue
                value = attrs[key]
                number_value = numeric(value)
                stats[key] = number_value if number_value is not None else value
            for key in ('TwoHanded', 'Reparable'):
                if key in stats:
                    stats[key] = str(stats[key]).strip().lower() == 'true'
            entry['s'] = stats
            table = str(attrs.get('DamageTiers', '')).strip()
            if table in tiers or table in special:
                entry['tbl'] = table
            elif f"dlc_ft_{table}" in tiers or f"dlc_ft_{table}" in special:
                entry['tbl'] = f"dlc_ft_{table}"
            color_key = attrs.get('Color')
            if color_key:
                entry['q'] = next((value for key, _, value in COLOR_LABELS if key == color_key), None)
            slots = re.findall(r'MOD_SLOT_\w+', str(attrs.get('OccupiedModSlots', '')))
            if slots:
                entry['mods'] = sorted(set(slots))
            startup = re.findall(r'"([A-Za-z0-9_]+)"', attrs.get('StartupMod', ''))
            if startup:
                entry['startup'] = startup
            weapons[identity] = entry
            continue
        # Weapon attachments: crafted parts that occupy a weapon slot.
        # Unnamed definitions are the auto-rolled "invisible" variants the loot
        # generator attaches by itself; the player can never pick them.
        if not localized:
            continue
        slots = re.findall(r'MOD_SLOT_\w+', body)
        if not slots:
            continue
        element_hit = re.search(r'Elemental\(([^)]*)\)', body)
        element_key = None
        if element_hit:
            element_key = next((key for key in ELEMENT_LABELS if key in element_hit.group(1)), None)
        effects = re.findall(r'Effect\(\s*(CraftingEffect_\w+)\s*(?:,\s*([^)]*))?\)', body)
        level = re.findall(r'ItemLevel\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)', body)
        color = attrs.get('Color', '')
        mods[identity] = {
            'n': label,
            'slot': slots[0],
            'slots': sorted(set(slots)),
            'element': ELEMENT_LABELS.get(element_key) if element_key else None,
            'effects': [{'key': key, 'name': EFFECT_LABELS.get(key, key), 'value': numeric(value)}
                        for key, value in effects],
            'uistats': ui_stats(body, loc),
            'level': [int(level[0][0]), int(level[0][1])] if level else None,
            'color': next((label_ for key, label_, _ in ((k, l, v) for k, l, v in COLOR_LABELS) if key == color), color),
        }

    affixes: dict[str, dict] = {}
    affix_text = texts.get('scripts/inventory/itemaffixes.scr') or ''
    for name, body in re.findall(r'Affix\("([A-Za-z0-9_]+)"\)\s*\{([\s\S]*?)\n\s{0,8}\}\s*\n', affix_text):
        if name.startswith('Affix_'):
            continue
        # Outfit/character affixes share names with weapon affixes but belong to
        # clothing, so they would only show up as duplicates here.
        if name.startswith(OUTFIT_PREFIXES):
            continue
        # Affixes without a localised name are internal coop/script buffs that the
        # game never shows in a mod slot.
        if ('affix_' + name + '_name').lower() not in loc:
            continue
        curves = re.findall(r'ValueSpread(?:Min|Max)Curve\("([^"]+)"\)', body)
        # Effect_Outfit* curves belong to clothing/gear sets.
        if curves and all(curve.startswith('Effect_Outfit') for curve in curves):
            continue
        buff = re.search(r'BuffID\("([^"]+)"\)', body)
        affixes[name] = {
            'n': resolved_label('Affix_' + name + '_Name', loc, name),
            'd': resolved_label('Affix_' + name + '_Desc', loc, ''),
            'buff': buff.group(1) if buff else None,
            'curves': sorted(set(curves)),
        }
    # Several definitions can land on the same visible name; keep the weapon one.
    def rank(key: str):
        return (not key.startswith('Weapon_'), '_Coop_Base' in key, len(key), key)

    unique: dict[tuple, str] = {}
    for key, entry in affixes.items():
        signature = (entry['n'], tuple(entry['curves']))
        current = unique.get(signature)
        if current is None or rank(key) < rank(current):
            unique[signature] = key
    affixes = {key: affixes[key] for key in unique.values()}

    output = {
        'version': 1,
        'source': {
            'data0.pak': hashlib.file_digest((SOURCE / 'data0.pak').open('rb'), 'sha256').hexdigest(),
            'datacn.pak': hashlib.file_digest((SOURCE / 'data_lang' / 'datacn.pak').open('rb'), 'sha256').hexdigest(),
        },
        'colors': [{'key': key, 'name': name, 'value': value} for key, name, value in COLOR_LABELS],
        'slots': [{'key': key, 'name': SLOT_LABELS[key]} for key in ('MOD_SLOT_TIP', 'MOD_SLOT_SHAFT', 'MOD_SLOT_GRIP', 'MOD_SLOT_CHARM')
                  if any(key in mod['slots'] for mod in mods.values())],
        'tiers': tiers,
        'special': special,
        'weapons': weapons,
        'mods': mods,
        'affixes': affixes,
    }
    TARGET.parent.mkdir(exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=TARGET.parent, suffix='.tmp', mode='w',
                                         encoding='utf-8', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(output, stream, ensure_ascii=False, separators=(',', ':'))
        temporary.replace(TARGET)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({
        'weapons': len(weapons), 'melee': sum(1 for w in weapons.values() if w['kind'] == 'melee'),
        'firearm': sum(1 for w in weapons.values() if w['kind'] == 'firearm'),
        'mods': len(mods), 'slots': len(output['slots']), 'affixes': len(affixes), 'tier_tables': len(tiers),
        'bytes': TARGET.stat().st_size,
        'sample_weapon': next(iter(weapons.items())),
        'sample_mod': next(iter(mods.items())) if mods else None,
        'sample_affix': next(iter(affixes.items())) if affixes else None,
    }, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
