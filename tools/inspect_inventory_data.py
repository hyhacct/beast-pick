"""Read installed inventory definitions and localization structure without game mutations."""
import json
import re
import struct
import zipfile
from pathlib import Path

SOURCE = Path(r'D:\App\Steam\steamapps\common\Dying Light The Beast\ph_ft\source')
out = Path(__file__).resolve().parents[1] / 'artifacts/inventory-source'
out.mkdir(exist_ok=True)
with zipfile.ZipFile(SOURCE/'data_lang/datacn.pak') as archive:
    blob = archive.read('texts/pc/pc_cn_lang.binsloc')
offset = blob.index(b'm_keys') + len(b'm_keys')
block_size, count = struct.unpack_from('<II', blob, offset)
offset += 8
keys = []
for _ in range(count):
    length = struct.unpack_from('<H', blob, offset)[0]
    offset += 2
    keys.append(blob[offset:offset+length].decode('utf-8'))
    offset += length
print('localization keys', count, 'next offset', offset, 'tail', repr(blob[offset:offset+100]))
(out/'loc-keys.json').write_text(json.dumps(keys, ensure_ascii=False), encoding='utf-8')
offset = blob.index(b'm_Values') + len(b'm_Values') + 4
value_count = struct.unpack_from('<I', blob, offset)[0]
offset += 4
values = []
for _ in range(value_count):
    length = struct.unpack_from('<H', blob, offset)[0]
    offset += 2
    values.append(blob[offset:offset+length].decode('utf-8'))
    offset += length
assert len(keys) == len(values)
translations = dict(zip(keys, values))
(out/'localization.json').write_text(json.dumps(translations,ensure_ascii=False),encoding='utf-8')
print('name sample', {k:v for k,v in translations.items() if 'Throwable_ThrowingKnifeBleeding_FT_n' in k})
with zipfile.ZipFile(SOURCE/'data0.pak') as archive:
    for name in archive.namelist():
        if name.startswith('scripts/inventory/') and '/' not in name.removeprefix('scripts/inventory/') and name.endswith('.scr'):
            (out/Path(name).name).write_bytes(archive.read(name))
    text = archive.read('scripts/inventory/inventory_weapondefintions_ft.scr').decode('utf-8',errors='replace')
    print(text[:1500])
print('item header sample', re.findall(r'\bItem\([^\n]+', text)[:8])
