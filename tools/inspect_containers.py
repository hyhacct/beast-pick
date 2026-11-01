"""Read-only ordinary-container inventory on the verified game callback."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from beast_pick.backend import PROCESS, load_profile, validate_modules
from beast_pick.categories import ITEM_TYPES

EXTRA = r"""
let containerReport=null;
rpc.exports.containerreport=()=>containerReport;
rpc.exports.containerprobe=()=>{
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
  onEnter(a){this.game=a[0];this.run=this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva));},
  onLeave(){
   if(!this.run || containerReport!==null || !level || Date.now()-levelSeen>1000)return;
   try{
    const position=xyz(vf(this.game,profile.player_transform_slot,'pointer',['pointer'])(this.game));
    position.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(capacity);
    query(level,vector,center,500,ptr(0),0,ptr(0));
    const n=size(vector),base=data(vector),types={},targets=[];
    const entity=vf(this.game,profile.local_entity_slot,'pointer',['pointer'])(this.game);
    const player=getControl(entity).sub(16);
    for(let i=0;i<n;i++){
     const p=base.add(i*8).readPointer(),name=type(p);
     types[name]=(types[name]||0)+1;
     if(!/Container|Loot|Backpack|Chest|Bag|Lock|Door/.test(name)||name==='.?AVBodyContainer@@'||name==='.?AVContainerItem@@')continue;
     const f=p.sub(16),distance=Math.hypot(...xyz(worldTransform(p)).map((v,j)=>v-position[j]));
     const row={name,pointer:String(p),full:String(f),distance,enabled:allowed(f),state:f.add(0x388).readS32()};
     if(name==='.?AVContainer@@') {
      row.counts=targetSnapshot(f);row.selection=bodySelection(f);row.linked=String(f.add(0x570).readPointer());
     }
     if(['.?AVContainer@@','.?AVComplexContainer@@'].includes(name)){
      interactionContext(player,distance);
      row.canOpen=vf(f,196,'bool',['pointer','int','pointer'])(f,7,context);
      if(name==='.?AVContainer@@')row.canTake=vf(f,196,'bool',['pointer','int','pointer'])(f,1,context);
     }
     targets.push(row);
    }
    targets.sort((a,b)=>a.distance-b.distance);
    const samples=[],seen=new Set();
    for(const t of targets){
     if(seen.has(t.name))continue;seen.add(t.name);
     const p=ptr(t.pointer),f=p.sub(16),vt=f.readPointer(),mod=Process.getModuleByAddress(vt),col=vt.sub(8).readPointer();
     const chd=mod.base.add(col.add(16).readU32()),count=chd.add(8).readU32(),arr=mod.base.add(chd.add(12).readU32());
     t.bases=Array.from({length:count},(_,i)=>{const b=mod.base.add(arr.add(i*4).readU32());return{name:mod.base.add(b.readU32()).add(16).readCString(),offset:b.add(8).readS32()};});
     t.table=Array.from({length:260},(_,i)=>{const a=vt.add(i*8).readPointer(),m=Process.findModuleByAddress(a);return{i,rva:m?String(a.sub(m.base)):null,module:m?.name};});
     if(t.name==='.?AVContainer@@') {
      t.counts=targetSnapshot(f);
      t.selection=bodySelection(f);
      const iface=f.add(0x3d8);
      t.lootTable=Array.from({length:7},(_,i)=>String(iface.readPointer().add(i*8).readPointer().sub(gameDll.base)));
     }
     const obj=p.add(16),rtti=vf(obj,2,'pointer',['pointer'])(obj);
     const getFields=native(exp('?GetFields@CRTTI@@QEBAAEBV?$vector@PEBVCRTTIField@@V?$heap_allocator@PEBVCRTTIField@@@vector_allocators@ttl@@$00@ttl@@XZ'),'pointer',['pointer']);
     const getName=native(exp('?GetName@CRTTIField@@QEBAPEBDXZ'),'pointer',['pointer']);
     const v=getFields(rtti);t.fields=[];
     for(let i=0;i<size(v);i++) { const field=data(v).add(i*8).readPointer(),ft=type(field);t.fields.push({name:getName(field).readCString(),type:ft,offset:field.add(0x50).readU32(),table:Array.from({length:52},(_,j)=>{const a=field.readPointer().add(j*8).readPointer(),m=Process.findModuleByAddress(a);return{module:m?.name,rva:m?String(a.sub(m.base)):null};})}); }
     const nativeData=vf(obj,6,'pointer',['pointer'])(obj);
     t.nativeData=String(nativeData);t.nativeFields=[];
     for(const fld of t.fields.filter(x=>/Lockpick|ForceNoLoot/.test(x.name))){
      const field=data(v).add(t.fields.indexOf(fld)*8).readPointer();
      const custom=field.add(0x60).readPointer();
      const row={name:fld.name,offset:fld.offset,custom:String(custom)};
      if(custom.isNull()&&fld.offset<0x2000&&!nativeData.isNull())row.bytes=hexdump(nativeData.add(fld.offset),{length:24});
      t.nativeFields.push(row);
     }
     t.dump=hexdump(f,{length:0x800});
     samples.push(t);
    }
    containerReport={objects:n,position,types,targets,samples};
   }catch(e){containerReport={error:String(e),stack:e.stack};}
  }
 }));
};
"""

session = frida.get_local_device().attach(PROCESS)
source = '\n'.join((ROOT / 'beast_pick' / n).read_text(encoding='utf-8') for n in ('filters.js', 'agent.js'))
script = session.create_script(source + '\n' + EXTRA)
try:
    script.load()
    profile = load_profile()
    validate_modules(profile, script.exports_sync.modules())
    profile['item_categories'] = {key: ids for key, (_, ids) in ITEM_TYPES.items()}
    script.exports_sync.init(profile)
    script.exports_sync.containerprobe()
    for _ in range(100):
        report = script.exports_sync.containerreport()
        if report is not None:
            (ROOT/'artifacts/container-sample.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'position':report.get('position'),'error':report.get('error'),'targets':[{k:v for k,v in t.items() if k in ('name','pointer','distance','state')} for t in report.get('targets',[])][:8],'samples':[{k:v for k,v in t.items() if k in ('name','nativeData','nativeFields')} for t in report.get('samples',[])]},ensure_ascii=False,indent=2))
            break
        time.sleep(.1)
    else:
        raise RuntimeError('No simulation callback within 10 seconds')
finally:
    script.exports_sync.shutdown()
    script.eternalize()
    session.detach()
