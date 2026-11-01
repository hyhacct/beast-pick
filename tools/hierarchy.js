(() => {
  return targetObjects.map(p=>{
    const vf=p.readPointer(), col=vf.sub(8).readPointer(),mod=Process.getModuleByAddress(vf);
    const chd=mod.base.add(col.add(16).readU32()),n=chd.add(8).readU32(),array=mod.base.add(chd.add(12).readU32());
    return {object:p.toString(),type:className(p),bases:Array.from({length:n},(_,i)=>{
      const desc=mod.base.add(array.add(i*4).readU32()),td=mod.base.add(desc.readU32());
      return {name:td.add(16).readCString(),offset:desc.add(8).readS32(),pdisp:desc.add(12).readS32(),vdisp:desc.add(16).readS32()};
    })};
  });
})()
