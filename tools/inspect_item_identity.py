"""Read item identity fields and getter tables on the verified game callback."""
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import frida
from beast_pick.backend import PROCESS,load_profile,validate_modules
from beast_pick.categories import ITEM_TYPES

EXTRA=r"""
let identityReport=null;
rpc.exports.identityreport=()=>identityReport;
rpc.exports.identityprobe=()=>{
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
  onEnter(a){this.game=a[0];this.run=this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva));},
  onLeave(){
   if(!this.run||identityReport!==null||!level||Date.now()-levelSeen>1000)return;
   try{
    const pos=xyz(vf(this.game,profile.player_transform_slot,'pointer',['pointer'])(this.game));
    pos.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(capacity);
    query(level,vector,center,500,ptr(0),0,ptr(0));
    const n=size(vector),base=data(vector),rows=[],tables={},seen=new Set();
    function inspect(desc,owner){
     const iface=desc.add(profile.description_context_offset);
     if(type(iface)!=='.?AVItemDescWithContext@@')return;
     const item=iface.add(8).readPointer();if(item.isNull()||seen.has(String(item)))return;seen.add(String(item));
     const row={owner,category:category(desc),item:String(item),type:type(item),strings:[],dump:hexdump(item,{length:160})};
     for(let off=8;off<0x300;off+=8){
      try{const p=ptr(item.add(off).readU64().and(uint64('0xffffffffffff')).toString());if(p.isNull())continue;
       const bytes=new Uint8Array(p.readByteArray(160)),end=bytes.indexOf(0);
       if(end<3)continue;const s=String.fromCharCode(...bytes.slice(0,end));
       if(/^[A-Za-z][A-Za-z0-9_&.\- ]+$/.test(s))row.strings.push({off,text:s});
      }catch(_){}
     }
     if(!tables[row.type])tables[row.type]=Array.from({length:120},(_,i)=>{const p=item.readPointer().add(i*8).readPointer(),m=Process.findModuleByAddress(p);return{slot:i,module:m?.name,rva:m?String(p.sub(m.base)):null};});
     if(!tables.context)tables.context=Array.from({length:120},(_,i)=>String(iface.readPointer().add(i*8).readPointer().sub(gameDll.base)));
     rows.push(row);
    }
    for(let i=0;i<n&&rows.length<32;i++){
     const p=base.add(i*8).readPointer(),name=type(p),full=p.sub(16);
     if(['.?AVBodyContainer@@','.?AVContainer@@'].includes(name)){
      const v=full.add(profile.body_items_offsets[0]),c=size(v),d=data(v);
      if(c<256)for(let j=0;j<Math.min(c,8);j++)inspect(d.add(j*profile.body_item_stride),name);
     }else if(['.?AVContainerItem@@','.?AVDroppedItem@@'].includes(name))inspect(full.add(name==='.?AVDroppedItem@@'?profile.dropped_description_offset:profile.item_description_offset),name);
    }
    identityReport={position:pos,objects:n,rows,tables};
   }catch(e){identityReport={error:String(e),stack:e.stack};}
  }
 }));
};
"""
session=frida.get_local_device().attach(PROCESS)
script=session.create_script('\n'.join((ROOT/'beast_pick'/n).read_text(encoding='utf-8')for n in ('filters.js','agent.js'))+'\n'+EXTRA)
try:
    script.load();p=load_profile();validate_modules(p,script.exports_sync.modules())
    p['item_categories']={k:ids for k,(_,ids)in ITEM_TYPES.items()}
    script.exports_sync.init(p);script.exports_sync.identityprobe()
    for _ in range(100):
        report=script.exports_sync.identityreport()
        if report is not None:break
        time.sleep(.1)
    else:raise RuntimeError('No simulation sample')
    (ROOT/'artifacts/item-identity-sample.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({**report,'tables':None,'rows':report.get('rows',[])[:3]},ensure_ascii=False,indent=2))
finally:
    script.exports_sync.shutdown();script.eternalize();session.detach()
