"""One current nearby cabinet only; no pointer queue and no direct state writes."""
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from beast_pick.backend import PROCESS, load_profile, validate_modules
from beast_pick.catalog import load_catalog
from beast_pick.categories import ITEM_TYPES

EXTRA = r"""
let openReport=null, probeBusy=false;
rpc.exports.openreport=()=>openReport;
rpc.exports.probe=()=>{
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
  onEnter(a){this.game=a[0];this.run=this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva));},
  onLeave(){
   if(!this.run||probeBusy||openReport!==null||!level||Date.now()-levelSeen>1000||Date.now()-levelStable<1200||!foregroundGame())return;
   if(loading(level)||frozen(level))return;
   try{
    const players=vf(this.game,profile.players_slot,'pointer',['pointer'])(this.game);
    if(size(players)!==1)throw Error('Not single player');
    const position=xyz(vf(this.game,profile.player_transform_slot,'pointer',['pointer'])(this.game));
    position.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(capacity);
    query(level,vector,center,3.5,ptr(0),0,ptr(0));
    const targets=[];
    for(let i=0;i<size(vector);i++){
     const p=data(vector).add(i*8).readPointer();
     if(type(p)!=='.?AVComplexContainer@@')continue;
     const f=p.sub(16),distance=Math.hypot(...xyz(worldTransform(p)).map((v,j)=>v-position[j]));
     if(distance<=3.5&&allowed(f)&&f.add(0x388).readS32()===2)targets.push({f,distance});
    }
    if(targets.length!==1)throw Error('Need exactly one unopened ComplexContainer within 3.5m, found '+targets.length);
    const {f,distance}=targets[0],vt=f.readPointer();
    if(!vt.add(196*8).readPointer().equals(gameDll.base.add(0x1121730))||!vt.add(197*8).readPointer().equals(gameDll.base.add(0x1193f50)))throw Error('Build interface mismatch');
    // The reflected NativeScript fields are relative to CRTTIObject slot6's
    // data base (full+0x20 here), not to the complete object address.
    const obj=f.add(32),base=vf(obj,6,'pointer',['pointer'])(obj);
    if(!base.equals(obj))throw Error('Unexpected property data base');
    const lock=hexdump(base.add(1008),{length:8}),noLoot=base.add(1176).readU8();
    if(noLoot!==0)throw Error('Special no-loot container');
    interactionContext(getControl(vf(this.game,profile.local_entity_slot,'pointer',['pointer'])(this.game)).sub(16),distance);
    if(!vf(f,196,'bool',['pointer','int','pointer'])(f,7,context))throw Error('CanOpen rejected');
    probeBusy=true;
    const outcome={position,type:type(f),distance,before:2,lock,noLoot,attempted:true};
    outcome.result=vf(f,197,'bool',['pointer','int','pointer'])(f,7,context);
    outcome.after=f.add(0x388).readS32();
    openReport=outcome;
   }catch(e){openReport={error:String(e),stack:e.stack};}
  }
 }));
};
"""

session = frida.get_local_device().attach(PROCESS)
script = session.create_script('\n'.join((ROOT/'beast_pick'/n).read_text(encoding='utf-8') for n in ('filters.js','agent.js'))+'\n'+EXTRA)
try:
    script.load()
    p=load_profile();validate_modules(p,script.exports_sync.modules())
    p.update(item_categories={k:v[1] for k,v in ITEM_TYPES.items()},item_catalog=load_catalog())
    script.exports_sync.init(p);script.exports_sync.probe()
    for _ in range(200):
        report=script.exports_sync.openreport()
        if report is not None:break
        time.sleep(.1)
    else:raise RuntimeError('No ready foreground simulation callback')
    (ROOT/'artifacts/locked-container-open.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    script.exports_sync.shutdown();script.eternalize();session.detach()
