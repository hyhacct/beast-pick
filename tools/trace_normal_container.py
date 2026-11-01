"""Observe a manual container interaction; never executes an interaction."""
import json
import argparse
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import frida
from beast_pick.backend import PROCESS,load_profile,validate_modules
from beast_pick.catalog import load_catalog
from beast_pick.categories import ITEM_TYPES

EXTRA=r"""
rpc.exports.tracecontainer=()=>{
 function address(a){const m=Process.findModuleByAddress(a);return m?m.name+'+'+a.sub(m.base):String(a);}
 for(const [label,rva]of Object.entries({execute:0x1193f50,state:0x1124200,initialize:0x1137790,visual:0x11b9dd0,lootA:0x1149690,lootB:0x11f6520})){
  listeners.push(Interceptor.attach(gameDll.base.add(rva),{
   onEnter(a){
    this.watch=false;
    try{
     if(type(a[0])!=='.?AVComplexContainer@@')return;
     this.watch=true;this.target=a[0];
     const row={event:'trace',label,phase:'enter',object:String(a[0]),state:a[0].add(0x388).readS32(),
      arg1:a[1].toInt32(),metadataCount:a[0].add(0x4e0).readU32(),childCount:a[0].add(0x580).readU32(),caller:address(this.returnAddress)};
     if(label==='execute'){
      row.context=hexdump(a[2],{length:128});
      row.stack=Thread.backtrace(this.context,Backtracer.ACCURATE).map(address);
     }
     send(row);
    }catch(e){send({event:'trace_error',error:String(e)});}
   },
   onLeave(ret){
    if(!this.watch)return;
    try{send({event:'trace',label,phase:'leave',object:String(this.target),result:String(ret),
     state:this.target.add(0x388).readS32(),metadataCount:this.target.add(0x4e0).readU32(),childCount:this.target.add(0x580).readU32()});}
    catch(e){send({event:'trace_error',error:String(e)});}
   }
  }));
 }
};
"""
session=frida.get_local_device().attach(PROCESS)
script=session.create_script('\n'.join((ROOT/'beast_pick'/n).read_text(encoding='utf-8')for n in ('filters.js','agent.js'))+'\n'+EXTRA)
events=[]
parser=argparse.ArgumentParser()
parser.add_argument('--seconds',type=float,default=300)
parser.add_argument('--output',default='manual-container-trace-2.json')
args=parser.parse_args()
assert 0<args.seconds<=600
out=ROOT/'artifacts'/Path(args.output).name
def message(m,data):
    event=m.get('payload',m)
    if event.get('event')=='stats':return
    events.append(event)
    if event.get('label')=='execute' or event.get('event')=='trace_error':
        print(json.dumps(event,ensure_ascii=False),flush=True)
script.on('message',message)
try:
    script.load();p=load_profile();validate_modules(p,script.exports_sync.modules())
    p.update(item_categories={k:v[1] for k,v in ITEM_TYPES.items()},item_catalog=load_catalog())
    script.exports_sync.init(p);script.exports_sync.tracecontainer()
    print(f'READY: read-only manual trace, {args.seconds} seconds',flush=True)
    end=time.monotonic()+args.seconds
    while time.monotonic()<end:
        out.write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
        time.sleep(1)
finally:
    script.exports_sync.shutdown();script.eternalize();session.detach()
    out.write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
