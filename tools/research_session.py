"""Local developer console. No network listener; all instrumentation unloads on exit."""
import json
import sys
from pathlib import Path

import frida

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
OUT.mkdir(exist_ok=True)

source = r"""
const engine = Process.getModuleByName('engine_x64_rwdi.dll');
const gameDll = Process.getModuleByName('gamedll_ph_x64_rwdi.dll');
const exportsByName = new Map(engine.enumerateExports().map(x=>[x.name,x.address]));
const samples = {};
const listeners = [];
let gamePtr = null;
let levelPtr = null;
function exported(name) {
  const p=exportsByName.get(name);
  if (!p) throw Error('Missing export: '+name);
  return p;
}
function describe(p) {
  const m=Process.findModuleByAddress(p);
  return {address:p.toString(),module:m?.name,rva:m?p.sub(m.base).toString():null};
}
function className(p) {
  try {
    const vf=p.readPointer();
    const mod=Process.findModuleByAddress(vf);
    const col=vf.sub(8).readPointer();
    const td=mod.base.add(col.add(12).readU32());
    return td.add(16).readCString();
  }catch(e){return null;}
}
for(const name of [
  '?GetActiveLevel@IGame@@QEAAPEAVILevel@@XZ',
  '?GetIGuiManager@IGame@@QEBAPEAVIManager@gui@@XZ',
  '?GetPlayerWorldXForm@IGame@@UEBAAEBVmtx34@@XZ',
  '?GetLocalPlayerEntity@IGame@@UEBAPEAVCEntity@cbs@@XZ',
  '?GetFramesCounter@ILevel@@QEBAHXZ',
  '?GetTimeWeatherSystem@ILevel@@QEBAPEAVCSystem@TimeWeather@@XZ',
  '?UpdateGameInputs@IGame@@UEAAXXZ',
  '?GetGameTimeDelta@IGame@@QEBAMXZ',
  '?GetIGuiManager@IGame@@QEBAPEAVIManager@gui@@XZ',
  '?GetIVarlistManager@ILevel@@QEBAPEAVIVarlistManager@@XZ'
]) {
  if(!exportsByName.has(name)) continue;
  try { listeners.push(Interceptor.attach(exported(name),{
    onEnter(args) {
      const p=args[0];
      if(samples[name]===undefined) samples[name]={this:describe(p),type:className(p),count:0};
      samples[name].count++;
      if(name.includes('@IGame@@'))gamePtr=p;
      if(name.includes('@ILevel@@'))levelPtr=p;
    }
  })); } catch(e) { send({hookSkipped:name,error:String(e)}); }
}
rpc.exports={
  evaluate(code){return (0,eval)(code);},
  snapshot(){return {game:gamePtr?.toString(),level:levelPtr?.toString(),samples};}
};
send({ready:true,engine:describe(engine.base),gameDll:describe(gameDll.base)});
"""


def main():
    device = frida.get_local_device()
    matches = [p for p in device.enumerate_processes() if p.name == "DyingLightGame_TheBeast_x64_rwdi.exe"]
    if len(matches) != 1:
        raise SystemExit(f"Expected one game process, got {len(matches)}")
    session = device.attach(matches[0].pid)
    script = session.create_script(source)
    script.on("message", lambda message, data: print(json.dumps(message, ensure_ascii=False), flush=True))
    script.load()
    try:
        for line in sys.stdin:
            try:
                command = json.loads(line)
                result = script.exports_sync.evaluate(command["js"]) if "js" in command else script.exports_sync.snapshot()
                if "save" in command:
                    target = OUT / Path(command["save"]).name
                    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps({"saved": str(target)}, ensure_ascii=False), flush=True)
                else:
                    print(json.dumps({"result": result}, ensure_ascii=False), flush=True)
            except Exception as exc:
                print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
    finally:
        script.unload()
        session.detach()


if __name__ == "__main__":
    main()
