"""Read-only item metadata sample on the verified simulation callback."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXTRA = r"""
let inspection = null, inspectRequested = true;
rpc.exports.inspection = () => inspection;
rpc.exports.begininspection = () => { inspection = null; inspectRequested = true; };
rpc.exports.probeinit = () => {
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'), {
  onEnter(a) { this.game = a[0]; this.run = this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva)); },
  onLeave() {
   if (!this.run || !inspectRequested || !level || Date.now()-levelSeen>1000) return;
   inspectRequested = false;
   try {
    const position = xyz(vf(this.game, profile.player_transform_slot, 'pointer', ['pointer'])(this.game));
    position.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage); vector.add(8).writeU32(0); vector.add(12).writeU32(capacity);
    query(level,vector,center,500,ptr(0),0,ptr(0));
    const n=size(vector), objects=data(vector), result=[];
    for(let i=0;i<n;i++) {
     const p=objects.add(i*8).readPointer(), name=type(p);
     if(!['.?AVDroppedItem@@','.?AVContainerItem@@','.?AVBodyContainer@@'].includes(name))continue;
     const full=p.sub(16), pos=xyz(worldTransform(p));
     const row={type:name,full:String(full),distance:Math.hypot(...pos.map((v,j)=>v-position[j]))};
     const descriptions = [];
     if(name==='.?AVBodyContainer@@') {
      for(const o of profile.body_items_offsets) {
       const v=full.add(o), count=size(v), d=data(v);
       const rows=[];
       if(o===0x4c8)for(let j=0;j<Math.min(count,32);j++) {
        const desc=d.add(j*0x160),iface=desc.add(0x38);
        rows.push({category:vf(iface,102,'int',['pointer'])(iface),itemType:vf(iface,103,'int',['pointer'])(iface),ifaceType:type(iface)});
       }
       descriptions.push({offset:o,count,rows});
      }
     } else {
      const desc=full.add(name==='.?AVDroppedItem@@'?0x5f0:0x380), iface=desc.add(0x38);
      row.desc=String(desc); row.descDump=hexdump(desc,{length:0x160});
      row.ifaceType=type(iface);
      const vt=iface.readPointer();
      row.functions=[0,1,4,86,102,103].map(s=>({slot:s,rva:String(vt.add(s*8).readPointer().sub(gameDll.base))}));
      row.category=vf(iface,102,'int',['pointer'])(iface);
      row.itemType=vf(iface,103,'int',['pointer'])(iface);
     }
     row.vectors=descriptions; result.push(row);
    }
    inspection={objects:n,position,targets:result};
   } catch(e) { inspection={error:String(e),stack:e.stack}; }
  }
 }));
};
"""

import frida
from beast_pick.backend import PROCESS, load_profile, validate_modules
from beast_pick.categories import ITEM_TYPES
device = frida.get_local_device()
session = device.attach(PROCESS)
source = '\n'.join((ROOT / 'beast_pick' / name).read_text(encoding='utf-8') for name in ('filters.js', 'agent.js'))
script = session.create_script(source + '\n' + EXTRA)
try:
    script.load()
    profile = load_profile()
    validate_modules(profile, script.exports_sync.modules())
    profile['item_categories'] = {key: ids for key, (_, ids) in ITEM_TYPES.items()}
    script.exports_sync.init(profile)
    script.exports_sync.probeinit()
    for _ in range(100):
        sample = script.exports_sync.inspection()
        if sample is not None:
            output = ROOT / 'artifacts/category-sample.json'
            output.write_text(json.dumps(sample,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({**sample,'targets':[{k:v for k,v in t.items() if k not in ('descDump','functions')} for t in sample.get('targets',[])]},ensure_ascii=False,indent=2))
            break
        time.sleep(.1)
    else:
        raise RuntimeError('No simulation callback sample within 10 seconds')
finally:
    script.exports_sync.shutdown()
    script.unload()
    session.detach()
