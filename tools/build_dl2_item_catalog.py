"""Generate DL2's selectable weapon and throwable IDs from installed game scripts."""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from build_item_catalog import blocks, localization, resolved_label

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'D:\App\Steam\steamapps\common\Dying Light 2\ph\source')


def build(source=SOURCE):
    with zipfile.ZipFile(source / 'data_lang' / 'datacn.pak') as z:
        translations = {k.lower(): v for k, v in localization(z.read('texts/pc/pc_cn_lang.binsloc')).items()}
    macros, items, texts = {}, {}, {}
    with zipfile.ZipFile(source / 'data0.pak') as z:
        for name in z.namelist():
            if not (name.startswith('scripts/inventory/') and name.endswith('.scr') and '/' not in name.removeprefix('scripts/inventory/')):
                continue
            text = z.read(name).decode('utf-8-sig', errors='replace')
            texts[name] = text
            for macro, identity, category, body in blocks(text):
                if macro:
                    macros[macro] = body
                else:
                    previous = items.get(identity)
                    items[identity] = (category, (previous[1] + '\n' if previous else '') + body)
    enum = {name: int(n) for name, n in re.findall(r'CategoryType_(\w+)\s*=\s*(-?\d+)', texts['scripts/inventory/inventorystuff.scr'])}
    token = re.compile(r'\buse\s+(\w+)\s*\([^;]*\)\s*;|\b(Name|ItemType|WpnSubtype)\s*\(\s*("[^"]*"|\w+)\s*\)')

    def fields(body, seen=()):
        values = {}
        for match in token.finditer(body):
            macro, key, value = match.groups()
            if macro and macro in macros and macro not in seen and len(seen) < 16:
                values.update(fields(macros[macro], (*seen, macro)))
            elif key:
                values[key] = value.strip('"')
        return values

    out = {}
    for identity, (category, body) in items.items():
        number = enum.get(category.removeprefix('CategoryType_'))
        if number not in (0, 1, 2, 13, 14):
            continue
        attrs = fields(body)
        namekey = attrs.get('Name', '').strip('&') or identity + '_n'
        label = resolved_label(namekey, translations, identity)
        out[identity] = {'name': label, 'category': number, 'group': 'weapons' if number in (0, 1) else 'throwables'}
    with (source / 'data0.pak').open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'version': 1, 'items': out, 'source_sha256': {'data0.pak': digest}}


def main():
    result = build()
    target = ROOT / 'beast_pick' / 'data' / 'dl2_weapon_items.json'
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix='.' + target.name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, separators=(',', ':'))
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(json.dumps({'items': len(result['items']), 'path': str(target)}, ensure_ascii=True))


if __name__ == '__main__':
    main()