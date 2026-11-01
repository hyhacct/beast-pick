(() => {
  const find = new NativeFunction(exported('?FindField@CRTTIObject@@QEBAPEBVCRTTIField@@PEBD@Z'),'pointer',['pointer','pointer']);
  const get = new NativeFunction(exported('?GetValueInternal@CRTTIField@@MEBA_NAEBVCRTTIObject@@PEAX@Z'),'bool',['pointer','pointer','pointer']);
  const xform = new NativeFunction(exported('?GetWorldXform@IControlObject@@QEBAAEBVmtx34@@XZ'),'pointer',['pointer']);
  const fields=['m_UsingDistance','m_AutoExecuteDistance','m_EnableState','m_QEnableState','m_State','m_StateBool','m_TakeUsingInterval','m_OpenUsingInterval','m_TakeMode','m_IsCollected','m_ShouldDisplayLootTrigger'];
  return targetObjects.filter(p=>!/Player/.test(className(p))).map(p=>{
    const object=p.add(16),full=p.sub(16),mat=xform(p);
    return {object:p.toString(),type:className(p),position:[mat.add(12).readFloat(),mat.add(28).readFloat(),mat.add(44).readFloat()],fields:fields.map(name=>{
      const f=find(object,Memory.allocUtf8String(name));
      if(f.isNull())return {name,missing:true};
      const val=Memory.alloc(128),ok=get(f,object,val);
      const offset=/TypedEngineNativeScript/.test(className(f))?f.add(0x50).readU32():null;
      return {name,ok,type:className(f),float:val.readFloat(),int:val.readS32(),byte:val.readU8(),offset,nativeFloat:offset===null?null:full.add(offset).readFloat()};
    })};
  });
})()
