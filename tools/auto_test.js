(() => {
  globalThis.autoTestResult=null;
  let done=false;
  const frozen=new NativeFunction(exported('?IsTimerFrozen@ILevel@@QEBA_NXZ'),'bool',['pointer']);
  if(globalThis.autoTestHook)autoTestHook.detach();
  const mainThread=22972;
  globalThis.autoTestHook=Interceptor.attach(exported('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
    onEnter(args){this.isLevel=args[0].equals(gamePtr);},
    onLeave(){
      if(!this.isLevel||done||Process.getCurrentThreadId()!==mainThread||frozen(levelPtr))return;
      done=true;
      try {
        const query=(0,eval)(File.readAllText('D:/Projects/dying-light-beast-pick/tools/query.js'));
        const player=nearbyObjects.find(p=>/PlayerDI_PH/.test(className(p))).sub(16);
        const candidates=nearbyObjects.filter(p=>/BodyContainer/.test(className(p)));
        if(!candidates.length)throw Error('No body container in range');
        const control=candidates[0],full=control.sub(16),iface=full.add(984);
        const count=p=>p.add(7).readU8()?p.add(7).readU8()-1:p.add(8).readU32();
        const before={state:full.add(0x388).readS32(),items:count(full.add(0x4c8)),pending:count(full.add(0x4d8))};
        new NativeFunction(full.readPointer().add(0x6e0).readPointer(),'void',['pointer'])(full);
        const ok=new NativeFunction(iface.readPointer().add(32).readPointer(),'bool',['pointer','pointer','bool'])(iface,player,0);
        const after={state:full.add(0x388).readS32(),items:count(full.add(0x4c8)),pending:count(full.add(0x4d8))};
        autoTestResult={thread:Process.getCurrentThreadId(),target:control.toString(),before,ok,after};
      }catch(e){autoTestResult={error:String(e),stack:e.stack};}
      send({autoTestResult});
    }
  });
  return {scheduled:true,mainThread};
})()
