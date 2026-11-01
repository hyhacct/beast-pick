"""Bounded production-agent container check; stops and detaches on every exit."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from beast_pick.backend import PROCESS, checked_settings, load_profile, validate_modules
from beast_pick.categories import ITEM_TYPES

parser = argparse.ArgumentParser()
parser.add_argument('--radius', type=float, default=2)
parser.add_argument('--seconds', type=float, default=0)
parser.add_argument('--output', default='container-check.json')
args = parser.parse_args()
assert 0 <= args.seconds <= 20

EXTRA = r"""
let wantedSample=false, containerSample=null;
rpc.exports.requestsample=()=>{wantedSample=true;containerSample=null;};
rpc.exports.containersample=()=>containerSample;
rpc.exports.installprobe=()=>{
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
  onEnter(a){this.game=a[0];this.run=this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva));},
  onLeave(){
   if(!this.run || !wantedSample || !level || Date.now()-levelSeen>1000)return;
   wantedSample=false;
   try{
    const pos=xyz(vf(this.game,profile.player_transform_slot,'pointer',['pointer'])(this.game));
    pos.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(capacity);
    query(level,vector,center,config.radius,ptr(0),0,ptr(0));
    const n=size(vector),base=data(vector),targets=[];
    for(let i=0;i<n;i++){
     const p=base.add(i*8).readPointer(),name=type(p),f=p.sub(16);
     if(!['.?AVContainer@@','.?AVComplexContainer@@','.?AVContainerItem@@','.?AVDroppedItem@@'].includes(name))continue;
     const row={address:String(f),type:name,distance:Math.hypot(...xyz(worldTransform(p)).map((v,j)=>v-pos[j])),enabled:allowed(f)};
     if(name==='.?AVContainer@@'){row.snapshot=targetSnapshot(f);row.selection=bodySelection(f);}
     else if(name==='.?AVComplexContainer@@')row.state=f.add(profile.body_state_offset).readS32();
     else{row.category=category(f.add(name==='.?AVDroppedItem@@'?profile.dropped_description_offset:profile.item_description_offset));row.accepted=accepts(row.category);}
     targets.push(row);
    }
    containerSample={position:pos,objects:n,targets};
   }catch(e){containerSample={error:String(e),stack:e.stack};}
  }
 }));
};
"""

events, report = [], {'radius': args.radius}
session = frida.get_local_device().attach(PROCESS)
source = '\n'.join((ROOT/'beast_pick'/name).read_text(encoding='utf-8') for name in ('filters.js','agent.js'))
script = session.create_script(source+'\n'+EXTRA)
script.on('message', lambda m,d: events.append(m.get('payload',m)))
try:
    script.load()
    profile = load_profile()
    validate_modules(profile, script.exports_sync.modules())
    profile['item_categories'] = {key: ids for key,(_,ids) in ITEM_TYPES.items()}
    script.exports_sync.init(profile)
    script.exports_sync.installprobe()
    settings = checked_settings(args.radius,False,True,False,{key:key!='weapons' for key in ITEM_TYPES},containers=True)
    script.exports_sync.configure(settings)

    def snapshot():
        script.exports_sync.requestsample()
        for _ in range(100):
            value=script.exports_sync.containersample()
            if value is not None:
                assert 'error' not in value,value
                return value
            time.sleep(.05)
        raise RuntimeError('No game callback')

    report['before']=snapshot()
    if args.seconds:
        settings['enabled']=True
        script.exports_sync.configure(settings)
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            report['state']=script.exports_sync.heartbeat()
            assert not report['state'].get('error'),report['state']
            time.sleep(.25)
        script.exports_sync.stop()
        report['after']=snapshot()
        assert report['state']['scans'] > 0, 'No active scan: keep the game in the foreground and retry'
        report['loot_events']=[e for e in events if e.get('event')=='loot']
        assert all(e.get('category') not in (0,1) for e in report['loot_events'])
    report['ok']=True
finally:
    try:
        script.exports_sync.stop()
        script.exports_sync.shutdown()
    finally:
        script.eternalize()
        session.detach()
    report['events']=events
    (ROOT/'artifacts'/Path(args.output).name).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='events'},ensure_ascii=False,indent=2))
