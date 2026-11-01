(() => {
  const find = new NativeFunction(exported('?FindField@CRTTIObject@@QEBAPEBVCRTTIField@@PEBD@Z'),'pointer',['pointer','pointer']);
  const fields=['m_UsingDistance','m_AutoExecuteDistance','m_User','m_EnableState','m_QEnableState','m_State','m_StateBool','m_TakeUsingInterval','m_OpenUsingInterval','m_TakeMode','m_IsCollected','m_ShouldDisplayLootTrigger'];
  return targetObjects.filter(p=>!/Player/.test(className(p))).map(p=>{
    const object=p.add(16);
    return {object:p.toString(),type:className(p),fields:fields.map(name=>{
      const f=find(object,Memory.allocUtf8String(name));
      return {name,field:f.toString(),type:f.isNull()?null:className(f),data:f.isNull()?null:hexdump(f,{length:112,header:false,ansi:false})};
    })};
  });
})()
