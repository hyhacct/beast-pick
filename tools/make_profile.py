import hashlib
import json
from pathlib import Path
import pefile

root=Path(__file__).resolve().parents[1]
binary=Path(r'D:\App\Steam\steamapps\common\Dying Light The Beast\ph_ft\work\bin\x64')
modules={}
for name in ['engine_x64_rwdi.dll','gamedll_ph_x64_rwdi.dll']:
    p=binary/name
    pe=pefile.PE(str(p),fast_load=True)
    modules[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':pe.OPTIONAL_HEADER.SizeOfImage,'timestamp':pe.FILE_HEADER.TimeDateStamp}
profile={'id':'beast-1.7.1.0na-local','label':'困兽 1.7.1.0na（当前安装构建）','modules':modules,
 'scheduler_return_rva':0xbc3d22,'player_transform_slot':151,'players_slot':152,'local_entity_slot':153,
 'body_init_rva':0x118b090,'body_take_rva':0x1185870,'body_init_slot':220,'body_loot_offset':984,
 'body_state_offset':0x388,'body_items_offsets':[0x4c8,0x4d8],
 'item_execute_rva':0x11944b0,'item_execute_slot':197,'item_used_offset':0x4f0,
 'trigger_enabled_offsets':[0x1c8,0x1c9]}
out=root/'beast_pick'/'profiles'/'current.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(profile,indent=2,ensure_ascii=False),encoding='utf-8')
print(out)
