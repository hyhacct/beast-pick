(() => {
  const body=targetObjects.find(p=>/BodyContainer/.test(className(p))).sub(16);
  const collect=targetObjects.find(p=>/CollectableObject/.test(className(p))).sub(16);
  globalThis.triggerTrace={};
  globalThis.triggerHooks=[];
  const bases=targetObjects.filter(p=>!/Player/.test(className(p))).map(p=>p.sub(16));
  const functions=new Map();
  const tables=[];
  for(const [label,base,offset] of [['body.trigger',body,432],['body.lootcontainer',body,944],['body.lootable',body,984],['item.trigger',collect,432]]) {
    const iface=base.add(offset),vf=iface.readPointer(),entries=[];
    for(let i=0;i<100;i++) {
      const p=vf.add(i*8).readPointer(),range=Process.findRangeByAddress(p);
      if(!range || !range.protection.includes('x'))break;
      const key=p.toString();
      if(!functions.has(key))functions.set(key,{p,names:[]});
      functions.get(key).names.push(label+'['+i+']');
      entries.push({i,...describe(p)});
    }
    tables.push({label,iface:iface.toString(),vf:describe(vf),entries});
  }
  for(const [key,info] of functions) {
    try {triggerHooks.push(Interceptor.attach(info.p,{onEnter(args){
      const self=args[0];
      if(!bases.some(b=>self.compare(b)>=0&&self.compare(b.add(1600))<0))return;
      if(!triggerTrace[key])triggerTrace[key]={names:info.names,count:0,samples:[]};
      const entry=triggerTrace[key];entry.count++;
      if(entry.samples.length<2)entry.samples.push({self:self.toString(),args:[args[1].toString(),args[2].toString(),args[3].toString()],stack:Thread.backtrace(this.context,Backtracer.ACCURATE).slice(0,8).map(describe)});
    }}));}catch(e){}
  }
  return {tables,hooked:triggerHooks.length};
})()
