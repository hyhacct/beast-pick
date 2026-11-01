(() => {
  const mat = new NativeFunction(gamePtr.readPointer().add(151*8).readPointer(),'pointer',['pointer'])(gamePtr);
  const playerPos=[mat.add(12).readFloat(),mat.add(28).readFloat(),mat.add(44).readFloat()];
  const xform=new NativeFunction(exported('?GetWorldXform@IControlObject@@QEBAAEBVmtx34@@XZ'),'pointer',['pointer']);
  function count(p){const code=p.add(7).readU8();return code?code-1:p.add(8).readU32();}
  return {playerPos,paused:new NativeFunction(exported('?IsTimerFrozen@ILevel@@QEBA_NXZ'),'bool',['pointer'])(levelPtr),bodies:targetObjects.filter(p=>/Body/.test(className(p))).map(p=>{
    const f=p.sub(16),m=xform(p),pos=[m.add(12).readFloat(),m.add(28).readFloat(),m.add(44).readFloat()];
    return {p:p.toString(),distance:Math.hypot(...pos.map((v,i)=>v-playerPos[i])),state:new NativeFunction(f.readPointer().add(0x6c0).readPointer(),'int',['pointer'])(f),items:count(f.add(0x4c8)),otherItems:count(f.add(0x4d8)),flags:f.add(0x59e).readU8(),position:pos};
  })};
})()
