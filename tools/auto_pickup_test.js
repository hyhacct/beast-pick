(() => {
 globalThis.pickupAutoResult=null;
 const context=Memory.alloc(128);
 if(!pickupTrace.length)throw Error('Need captured context');
 context.writeByteArray(pickupTrace[0].context);
 let done=false;
 globalThis.pickupAutoHook=Interceptor.attach(exported('?GetGameTimeDelta@IGame@@QEBAMXZ'),{
  onEnter(a){this.run=this.returnAddress.equals(engine.base.add(0xbc3d22))&&a[0].equals(gamePtr);},
  onLeave(){
   if(!this.run||done)return;
   if(new NativeFunction(exported('?IsTimerFrozen@ILevel@@QEBA_NXZ'),'bool',['pointer'])(levelPtr))return;
   done=true;
   try{
    const query=(0,eval)(File.readAllText('D:/Projects/dying-light-beast-pick/tools/query.js'));
    const p=nearbyObjects.find(p=>className(p)==='.?AVDroppedItem@@');
    if(!p)throw Error('Item no longer nearby');
    const f=p.sub(16),vf=f.readPointer();
    const check=new NativeFunction(vf.add(196*8).readPointer(),'bool',['pointer','int','pointer'])(f,1,context);
    let ok=false;
    if(check)ok=new NativeFunction(vf.add(197*8).readPointer(),'bool',['pointer','int','pointer'])(f,1,context);
    pickupAutoResult={target:p.toString(),check,ok,tid:Process.getCurrentThreadId(),position:query.position};
   }catch(e){pickupAutoResult={error:String(e),stack:e.stack};}
   send({pickupAutoResult});
  }
 });
 return {scheduled:true};
})()
