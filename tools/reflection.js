(() => {
  const getFields = new NativeFunction(exported('?GetFields@CRTTI@@QEBAAEBV?$vector@PEBVCRTTIField@@V?$heap_allocator@PEBVCRTTIField@@@vector_allocators@ttl@@$00@ttl@@XZ'), 'pointer', ['pointer']);
  const getMethods = new NativeFunction(exported('?GetMethods@CRTTI@@QEBAAEBV?$vector@PEBVCRTTIMethod@@V?$heap_allocator@PEBVCRTTIMethod@@@vector_allocators@ttl@@$00@ttl@@XZ'), 'pointer', ['pointer']);
  const getFieldName = new NativeFunction(exported('?GetName@CRTTIField@@QEBAPEBDXZ'), 'pointer', ['pointer']);
  const getMethodName = new NativeFunction(exported('?GetName@CRTTIMethod@@QEBAPEBDXZ'), 'pointer', ['pointer']);
  const getClassName = new NativeFunction(exported('?GetClassNameA@CRTTI@@QEBAPEBDXZ'), 'pointer', ['pointer']);
  function elements(v) {
    const n=v.add(7).readU8()?v.add(7).readU8()-1:v.add(8).readU32();
    if(n>4096) throw Error('Invalid vector '+n);
    const p=ptr(v.readU64().and(uint64('0xffffffffffff')).toString());
    return Array.from({length:n},(_,i)=>p.add(i*8).readPointer());
  }
  globalThis.targetObjects = nearbyObjects.filter(p=>/BodyContainer|CollectableObject|PlayerDI_PH/.test(className(p)));
  return targetObjects.map(p=>{
    const base=p.add(16);
    const c=new NativeFunction(base.readPointer().add(16).readPointer(),'pointer',['pointer'])(base);
    const queue=[c],seen=new Set(),classes=[];
    while(queue.length && classes.length<24) {
      const current=queue.shift();
      if(current.isNull() || seen.has(current.toString()))continue;
      seen.add(current.toString());
      classes.push({name:getClassName(current).readCString(),ptr:current.toString(),
        fields:elements(getFields(current)).map(f=>({name:getFieldName(f).readCString(),ptr:f.toString(),type:className(f)})),
        methods:elements(getMethods(current)).map(m=>({name:getMethodName(m).readCString(),ptr:m.toString(),type:className(m)}))});
      queue.push(current.add(0x120).readPointer(),current.add(0x110).readPointer());
    }
    return {object:p.toString(),type:className(p),rtti:c.toString(),classes};
  });
})()
