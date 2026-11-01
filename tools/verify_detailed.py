"""Bounded actual-agent check; default is read-only, with an exact item exclusion."""
import argparse
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import frida
from beast_pick.backend import PROCESS, checked_settings, load_profile, validate_modules
from beast_pick.catalog import load_catalog
from beast_pick.categories import ITEM_TYPES

parser=argparse.ArgumentParser()
parser.add_argument('--radius',type=float,default=16)
parser.add_argument('--seconds',type=float,default=0)
parser.add_argument('--wait-foreground',type=float,default=0)
parser.add_argument('--open',action='store_true')
parser.add_argument('--locked',action='store_true')
parser.add_argument('--output',default='detailed-live-check.json')
args=parser.parse_args()
assert 0<=args.seconds<=30
assert 0<=args.wait_foreground<=120

EXTRA=r"""
let detailedSample=null,wantedSample=false;
rpc.exports.sample=()=>detailedSample;
rpc.exports.request=()=>{detailedSample=null;wantedSample=true;};
rpc.exports.install=()=>{
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
  onEnter(a){this.game=a[0];this.run=this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva));},
  onLeave(){
   if(!this.run||!wantedSample||!level||Date.now()-levelSeen>1000)return;
   wantedSample=false;
   try{
    const position=xyz(vf(this.game,profile.player_transform_slot,'pointer',['pointer'])(this.game));
    position.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(capacity);
    query(level,vector,center,config.radius,ptr(0),0,ptr(0));
    const rows=[];
    for(let i=0;i<size(vector);i++){
     const p=data(vector).add(i*8).readPointer(),name=type(p),f=p.sub(16);
     if(!['.?AVContainer@@','.?AVComplexContainer@@','.?AVContainerItem@@','.?AVDroppedItem@@','.?AVBodyContainer@@'].includes(name))continue;
     const row={type:name,position:xyz(worldTransform(p)),enabled:allowed(f)};
     row.distance=Math.hypot(...row.position.map((v,j)=>v-position[j]));
     if(name==='.?AVComplexContainer@@'||name==='.?AVContainer@@'){
      const activeGetter=p.readPointer().add(67*8).readPointer();const activeMod=Process.findModuleByAddress(activeGetter);row.activeGetter={module:activeMod?.name,rva:activeMod?String(activeGetter.sub(activeMod.base)):null};row.metadataCount=name==='.?AVComplexContainer@@'?f.add(0x4e0).readU32():null;row.childCount=name==='.?AVComplexContainer@@'?f.add(0x580).readU32():null;row.state=f.add(profile.body_state_offset).readS32();row.info=containerInfo(f,name==='.?AVComplexContainer@@');
      row.canOpen=LootPolicy.canOpenContainer(name,row.state,row.info,config);
      if(name==='.?AVContainer@@')row.selection=bodySelection(f);
     }else if(name==='.?AVBodyContainer@@')row.selection=bodySelection(f);
     else{
      row.item=itemIdentity(f.add(name==='.?AVDroppedItem@@'?profile.dropped_description_offset:profile.item_description_offset));
      row.accepted=accepts(row.item);
     }
     rows.push(row);
    }
    detailedSample={position,objects:size(vector),targets:rows.sort((a,b)=>a.distance-b.distance)};
   }catch(e){detailedSample={error:String(e),stack:e.stack};}
  }
 }));
};
"""
session=frida.get_local_device().attach(PROCESS)
script=session.create_script('\n'.join((ROOT/'beast_pick'/n).read_text(encoding='utf-8')for n in ('filters.js','agent.js'))+'\n'+EXTRA)
events=[];script.on('message',lambda m,d:events.append(m.get('payload',m)))
report={'radius':args.radius}
try:
    script.load();p=load_profile();validate_modules(p,script.exports_sync.modules())
    p.update(item_categories={k:v[1] for k,v in ITEM_TYPES.items()},item_catalog=load_catalog())
    script.exports_sync.init(p);script.exports_sync.install()
    settings=checked_settings(args.radius,False,True,False,{'weapons':False},containers=True,
        item_rules={'items':{'Water_FT':False}},open_containers=args.open,locked_containers=args.locked)
    script.exports_sync.configure(settings)
    def sample():
        script.exports_sync.request()
        for _ in range(100):
            value=script.exports_sync.sample()
            if value is not None:
                assert 'error'not in value,value
                return value
            time.sleep(.05)
        raise RuntimeError('No simulation sample')
    report['before']=sample()
    if args.seconds:
        settings['enabled']=True;script.exports_sync.configure(settings)
        ready_until=time.monotonic()+args.wait_foreground
        while args.wait_foreground and time.monotonic()<ready_until:
            report['state']=script.exports_sync.heartbeat()
            assert not report['state'].get('error'),report['state']
            if report['state']['scans']>0:
                break
            time.sleep(.25)
        end=time.monotonic()+args.seconds
        while time.monotonic()<end:
            report['state']=script.exports_sync.heartbeat()
            assert not report['state'].get('error'),report['state']
            time.sleep(.25)
        script.exports_sync.stop();report['after']=sample()
        assert report['state']['scans']>0,'Game must be in foreground'
    report['loot']=[x for x in events if x.get('event')=='loot']
    assert not any(x.get('id')=='Water_FT' or x.get('category')in(0,1)for x in report['loot'])
    report['ok']=True
finally:
    script.exports_sync.shutdown();script.eternalize();session.detach()
    report['events']=events
    (ROOT/'artifacts'/Path(args.output).name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k not in ('before','after','events')},ensure_ascii=False,indent=2))
print(json.dumps({'before':report.get('before'),'after':report.get('after')},ensure_ascii=False,indent=2)[:12000])
