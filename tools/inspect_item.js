(() => {
 const p=nearbyObjects.find(p=>className(p)==='.?AVContainerItem@@');
 if(!p)return {missing:true};
 const f=p.sub(16),vf=f.readPointer();
 const xf=new NativeFunction(exported('?GetWorldXform@IControlObject@@QEBAAEBVmtx34@@XZ'),'pointer',['pointer'])(p);
 return {p:p.toString(),full:f.toString(),position:[xf.add(12).readFloat(),xf.add(28).readFloat(),xf.add(44).readFloat()],
  primary:Array.from({length:245},(_,i)=>({i,...describe(vf.add(i*8).readPointer())})),
  data:hexdump(f,{length:0x600})};
})()
