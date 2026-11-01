(() => {
 const p=nearbyObjects.find(p=>className(p)==='.?AVDroppedItem@@');
 if(!p)throw Error('No dropped item');
 const f=p.sub(16),vt=f.readPointer();
 globalThis.pickupTrace=[]; globalThis.pickupHooks=[];
 for(const i of [196,197])pickupHooks.push(Interceptor.attach(vt.add(i*8).readPointer(),{
  onEnter(a){
   this.match=a[0].equals(f);
   if(!this.match)return;
   this.row={i,tid:Process.getCurrentThreadId(),self:a[0].toString(),arg1:a[1].toString(),arg2:a[2].toString(),context:Array.from(new Uint8Array(a[2].readByteArray(64))),stack:Thread.backtrace(this.context,Backtracer.ACCURATE).slice(0,6).map(describe)};
  },
  onLeave(r){if(this.row&&(this.row.i===197||pickupTrace.filter(t=>t.i===196).length<3)){this.row.result=r.toString();pickupTrace.push(this.row);if(this.row.i===197)send({pickup:this.row});}}
 }));
 return {hooked:p.toString()};
})()
