"""Bounded production-agent check; optional live pickup with --run-seconds N.

Uses the real foreground/loading gates. Always stops and detaches on exit.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import frida
from beast_pick.backend import PROCESS, load_profile, validate_modules, checked_settings
from beast_pick.categories import ITEM_TYPES

parser = argparse.ArgumentParser()
parser.add_argument('--run-seconds', type=float, default=0)
options = parser.parse_args()
assert 0 <= options.run_seconds <= 30

EXTRA = r"""
let sampleRequested = false, filterSample = null;
rpc.exports.requestsample = () => { sampleRequested = true; filterSample = null; };
rpc.exports.filtersample = () => filterSample;
rpc.exports.installprobe = () => {
 listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'), {
  onEnter(a) { this.game=a[0]; this.run=this.returnAddress.equals(engine.base.add(profile.scheduler_return_rva)); },
  onLeave() {
   if(!this.run || !sampleRequested || !level || Date.now()-levelSeen>1000) return;
   sampleRequested=false;
   try {
    const pos=xyz(vf(this.game,profile.player_transform_slot,'pointer',['pointer'])(this.game));
    pos.forEach((v,i)=>center.add(i*4).writeFloat(v));
    vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(capacity);
    query(level,vector,center,config.radius,ptr(0),0,ptr(0));
    const n=size(vector),base=data(vector),targets=[];
    for(let i=0;i<n;i++) {
     const p=base.add(i*8).readPointer(),name=type(p);
     if(!['.?AVBodyContainer@@','.?AVDroppedItem@@','.?AVContainerItem@@'].includes(name))continue;
     const f=p.sub(16),distance=Math.hypot(...xyz(worldTransform(p)).map((v,j)=>v-pos[j]));
     const row={address:String(f),type:name,distance,enabled:allowed(f)};
     if(name==='.?AVBodyContainer@@') row.selection=bodySelection(f);
     else { row.category=category(f.add(name==='.?AVDroppedItem@@'?profile.dropped_description_offset:profile.item_description_offset));row.accepted=accepts(row.category); }
     targets.push(row);
    }
    filterSample={objects:n,targets};
   }catch(e){filterSample={error:String(e),stack:e.stack};}
  }
 }));
};
"""

events = []
session = frida.get_local_device().attach(PROCESS)
source = '\n'.join((ROOT/'beast_pick'/name).read_text(encoding='utf-8') for name in ('filters.js','agent.js'))
script = session.create_script(source+'\n'+EXTRA)
script.on('message', lambda m,d: events.append(m.get('payload',m)))
report = {}
try:
    script.load()
    profile = load_profile()
    validate_modules(profile, script.exports_sync.modules())
    profile['item_categories'] = {key: ids for key,(_,ids) in ITEM_TYPES.items()}
    script.exports_sync.init(profile)
    script.exports_sync.installprobe()
    selection = {key:key!='weapons' for key in ITEM_TYPES}
    settings = checked_settings(500,True,True,False,selection)
    script.exports_sync.configure(settings)

    def snapshot():
        script.exports_sync.requestsample()
        for _ in range(100):
            value=script.exports_sync.filtersample()
            if value is not None:
                assert 'error' not in value, value
                return value
            time.sleep(.05)
        raise RuntimeError('No simulation callback sample')

    report['before'] = snapshot()
    weapons=[t for t in report['before']['targets'] if t.get('category') in (0,1)]
    assert weapons, 'Need at least one loaded weapon sample'
    assert all(t['accepted'] is False for t in weapons)
    report['weapons_rejected'] = len(weapons)
    report['range'] = 500
    if options.run_seconds:
        settings['enabled']=True
        script.exports_sync.configure(settings)
        deadline=time.monotonic()+options.run_seconds
        while time.monotonic()<deadline:
            report['state']=script.exports_sync.heartbeat()
            assert not report['state'].get('error'),report['state']
            time.sleep(.25)
        script.exports_sync.stop()
        report['after']=snapshot()
        remaining={t['address'] for t in report['after']['targets']}
        report['weapons_still_present']=sum(t['address'] in remaining for t in weapons)
        report['loot_events']=[e for e in events if e.get('event')=='loot']
        assert all(e.get('category') not in (0,1) for e in report['loot_events'])
        if report['state']['scans']:
            assert report['weapons_still_present']==len(weapons),'Weapon sample moved or disappeared; inspect scene'
    report['ok']=True
finally:
    try:
        script.exports_sync.stop()
        script.exports_sync.shutdown()
    finally:
        script.unload()
        session.detach()
    (ROOT/'artifacts/filter-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('before','after')},ensure_ascii=False,indent=2))
