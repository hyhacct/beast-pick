'use strict';
// Build-specific DL2 adapter for verified pickup paths and guarded world interactions.
let profile=null, engine=null, gameDll=null, level=null, levelSeen=0, levelStable=0;
let enabled=false, lease=0, lastTick=0, lastPublish=0, lastOpen=0, busy=false;
let cfg={radius:8,items:false,corpses:false,containers:false,weapons:true,open_containers:false,locked_containers:false,excluded_ids:new Set()}, query, frozen, loading, worldTransform, getControl, foreground, windowPid, getEntity, isSimulating, findField;
const hooks=[], pending=new Map(), retry=new Map(), looted=new Set(), verifiedLayouts=new Set(), cap=8192;
const vector=Memory.alloc(16), storage=Memory.alloc(cap*8), center=Memory.alloc(12), context=Memory.alloc(128), pid=Memory.alloc(4);
let stats={status:'disabled',corpses:0,containers:0,items:0,opened:0,scans:0,nearbyCorpses:0,nearbyContainers:0,nearbyItems:0,filtered:0,unknown:0,objects:0,attempts:0,blocked:0,scanMs:0,error:null};
function native(p,r,a){return new NativeFunction(p,r,a)}
function exp(n){return engine.getExportByName(n)}
function typ(p){try{const v=p.readPointer(),m=Process.findModuleByAddress(v),c=v.sub(8).readPointer();return m.base.add(c.add(12).readU32()).add(16).readCString()}catch(_){return null}}
function vcall(p,i,r,a){return native(p.readPointer().add(i*8).readPointer(),r,a)}
function xyz(p){return [12,28,44].map(i=>p.add(i).readFloat())}
function length(v){const x=v.add(7).readU8(),n=x?x-1:v.add(8).readU32();if(n>cap)throw Error('范围查询结果超出容量');return n}
function publish(force=false){const now=Date.now();if(force||now-lastPublish>=1000){lastPublish=now;send({event:'stats',...stats,enabled,pending:pending.size})}}
function pause(s){stats.status=s;stats.nearbyItems=0;stats.nearbyCorpses=0;stats.nearbyContainers=0;pending.clear();publish()}
function activeWindow(){const h=foreground();if(h.isNull())return false;windowPid(h,pid);return pid.readU32()===Process.id}
function key(p,pos){return p.toString()+':'+p.readPointer().toString()+':'+pos.map(x=>x.toFixed(2)).join(',')}
function category(desc){
 try{const p=desc.add(profile.description_context_offset);if(typ(p)!=='.?AVItemDescWithContext@@'||p.add(8).readPointer().isNull())return null;
  const f=p.readPointer().add(profile.description_category_slot*8).readPointer();if(!f.equals(gameDll.base.add(profile.description_category_rva)))return null;
  const n=native(f,'int',['pointer'])(p);return n>=0&&n<=28?n:null;
 }catch(_){return null}
}
function itemId(desc){
 try{
  const iface=desc.add(profile.description_context_offset);if(typ(iface)!=='.?AVItemDescWithContext@@')return null;
  const definition=iface.add(8).readPointer();if(definition.isNull())return null;
  const getter=definition.readPointer().add(profile.identity_getter_slot*8).readPointer();if(!getter.equals(gameDll.base.add(profile.identity_getter_rva)))return null;
  const value=definition.add(8),tag=value.add(7).readU8();let chars,length=128;
  if(tag<=7){chars=value;length=7-tag}else{chars=ptr(value.readU64().and(uint64('0xffffffffffff')).toString());if(chars.isNull()||!Process.findRangeByAddress(chars))return null}
  let id='';for(let i=0;i<length;i++){const x=chars.add(i).readU8();if(x===0)return id||null;if(x<33||x>126)return null;id+=String.fromCharCode(x)}
  return tag<=7&&id?id:null;
 }catch(_){return null}
}
function accepts(desc){
 const hasExclusions=cfg.excluded_ids.size>0;if(cfg.weapons&&!hasExclusions)return true;
 const c=category(desc);if(c===null)return false;
 if(!cfg.weapons&&[0,1].includes(c))return false;
 if((!cfg.weapons||hasExclusions)&&[17,19,27,28].includes(c))return false;
 if(hasExclusions&&[0,1,2,13,14].includes(c)){const id=itemId(desc);return id!==null&&!cfg.excluded_ids.has(id)}
 return true;
}
function bodyCounts(o){return profile.body_items_offsets.map(x=>length(o.add(x)))}
function takeBody(t,player,now){
 const o=t.obj,ordinary=t.type==='. ?AVContainer@@'.replace(' ','');if(o.add(profile.body_state_offset).readS32()!==1)return;
 let counts=bodyCounts(o);if(!counts[0]||counts[0]>256||counts[1]>256)return;
 const vt=o.readPointer(),init=vt.add(profile.body_init_slot*8).readPointer(),take=o.add(profile.body_iface_offset).readPointer().add(4*8).readPointer();
 if(!init.equals(gameDll.base.add(ordinary?profile.container_init_rva:profile.body_init_rva))||!take.equals(gameDll.base.add(profile.body_take_rva)))throw Error('尸体或容器接口校验失败');
 if(ordinary){const check=vt.add(profile.can_slot*8).readPointer(),exec=vt.add(profile.execute_slot*8).readPointer();
  if(!check.equals(gameDll.base.add(profile.container_can_rva))||!exec.equals(gameDll.base.add(profile.container_execute_rva)))return;
  const src=player.add(profile.player_context_offset);if(!src.readPointer().equals(player.add(0x1b0)))throw Error('玩家交互上下文不匹配');
  Memory.copy(context,src,128);context.add(20).writeFloat(t.distance);context.add(24).writeU8(0x43);
  if(!native(check,'bool',['pointer','int','pointer'])(o,1,context)){stats.blocked++;retry.set(t.id,now+1000);return}
 }
 native(init,'void',['pointer'])(o);
 for(let batch=0;batch<16;batch++){
  counts=bodyCounts(o);if(!counts[0]||counts[0]>256)break;
  const v=o.add(profile.body_items_offsets[0]),data=ptr(v.readU64().and(uint64('0xffffffffffff')).toString());let index=-1;
  for(let i=counts[0]-1;i>=0;i--)if(accepts(data.add(i*profile.body_item_stride))){index=i;break}
  if(index<0){stats.filtered++;break}
  stats.attempts++;const ok=native(gameDll.base.add(profile.body_take_one_rva),'bool',['pointer','uint','pointer','bool'])(o,index,player,0),after=bodyCounts(o);
  if(!ok||!after.some((x,i)=>x<counts[i])){stats.blocked++;retry.set(t.id,now+1000);break}
  if(!looted.has(t.id)){stats[ordinary?'containers':'corpses']++;looted.add(t.id)}
  send({event:'loot',kind:ordinary?'container':'corpse',distance:t.distance,name:ordinary?'普通容器战利品':'尸体战利品'});
 }
 retry.set(t.id,now+500);
}
function simulated(full){const entity=getEntity(full.add(48));return !entity.isNull()&&!!isSimulating(entity)}
function bodyEligible(full){
 if(full.add(profile.body_state_offset).readS32()!==1)return false;
 const counts=bodyCounts(full);if(!counts[0]||counts[0]>256||counts[1]>256)return false;
 if(cfg.weapons&&cfg.excluded_ids.size===0)return true;
 const vec=full.add(profile.body_items_offsets[0]),base=ptr(vec.readU64().and(uint64('0xffffffffffff')).toString());
 for(let i=0;i<counts[0];i++)if(accepts(base.add(i*profile.body_item_stride)))return true;
 stats.filtered++;return false;
}
function mayOpen(lock,allowLocked){return lock!==null&&(lock===''||allowLocked===true)}
function safeComplexLock(full){
 if(!simulated(full))return null;
 const obj=full.add(32),base=vcall(obj,6,'pointer',['pointer'])(obj);if(!base.equals(obj))return null;
 const identity=obj.readPointer().toString();
 if(!verifiedLayouts.has(identity)){
  for(const [name,offset,expected] of [['m_LockpickDifficulty',profile.complex_lock_offset,'.?AVCRTTIFieldStringNativeScript@@'],['m_ForceNoLoot',profile.complex_no_loot_offset,'.?AV?$CRTTIFieldTypedEngineNativeScript@_NV?$CRTTIFieldTyped@_N@@@@']]){
   const field=findField(obj,Memory.allocUtf8String(name));
   if(field.isNull()||typ(field)!==expected||field.add(0x50).readU32()!==offset||!field.add(0x60).readPointer().isNull())return null;
  }
  verifiedLayouts.add(identity);
 }
 if(base.add(profile.complex_no_loot_offset).readU8()!==0)return null;
 const field=base.add(profile.complex_lock_offset),bytes=new Uint8Array(field.readByteArray(8));
 if(![0x20,0].includes(bytes[7]))return null;
 if(Array.from(bytes.slice(0,7)).every(x=>x===0))return '';
 try{const p=ptr(field.readU64().and(uint64('0xffffffffffff')).toString());if(p.isNull()||!Process.findRangeByAddress(p))return null;let value='';
  for(let i=0;i<32;i++){const x=p.add(i).readU8();if(x===0)return ['easy','medium','hard','impossible'].includes(value.toLowerCase())?value.toLowerCase():null;if(x<33||x>126)return null;value+=String.fromCharCode(x)}
 }catch(_){}return null;
}
function actionContext(player,distance){
 const src=player.add(profile.player_context_offset);if(!src.readPointer().equals(player.add(0x1b0)))throw Error('玩家交互上下文不匹配');
 Memory.copy(context,src,128);context.add(20).writeFloat(distance);context.add(24).writeU8(0x43);
}
function openComplex(t,player,now){
 if(now-lastOpen<1000)return;const lock=safeComplexLock(t.obj);if(!mayOpen(lock,cfg.locked_containers)){retry.set(t.id,now+1000);return;}
 const vt=t.obj.readPointer(),can=vt.add(profile.can_slot*8).readPointer(),execute=vt.add(profile.execute_slot*8).readPointer();
 if(!can.equals(gameDll.base.add(profile.complex_can_rva))||!execute.equals(gameDll.base.add(profile.complex_execute_rva)))return;
 actionContext(player,t.distance);
 if(!native(can,'bool',['pointer','int','pointer'])(t.obj,7,context)){retry.set(t.id,now+1000);stats.blocked++;return}
 lastOpen=now;stats.attempts++;const ok=native(execute,'bool',['pointer','int','pointer'])(t.obj,7,context),after=t.obj.add(profile.body_state_offset).readS32();
 if(ok&&(after===1||after===5)){stats.opened++;retry.set(t.id,now+1500);send({event:'loot',kind:'container_open',distance:t.distance,after,locked:lock!==''})}
 else{stats.blocked++;retry.set(t.id,now+1000)}
}
function tick(game){
 const now=Date.now();
 if(!enabled)return pause('disabled');
 if(now>lease){enabled=false;return pause('lease_expired')}
 if(!activeWindow())return pause('background');
 if(!level||now-levelSeen>1000||now-levelStable<1200)return pause('waiting_level');
 if(typ(level)!=='.?AVLevelDI@@'||loading(level)||frozen(level))return pause('paused');
 if(typ(game)!=='.?AVGameDI_PH@@')return pause('waiting_player');
 const entity=vcall(game,profile.local_entity_slot,'pointer',['pointer'])(game);
 if(entity.isNull())return pause('waiting_player');
 const control=getControl(entity);if(control.isNull()||typ(control)!=='.?AVPlayerDI_PH@@')return pause('waiting_player');
 const player=control.sub(16),m=vcall(game,profile.player_transform_slot,'pointer',['pointer'])(game);
 if(m.isNull())return pause('waiting_player');const pos=xyz(m);if(!pos.every(Number.isFinite))throw Error('玩家坐标无效');
 pos.forEach((x,i)=>center.add(i*4).writeFloat(x));vector.writePointer(storage);vector.add(8).writeU32(0);vector.add(12).writeU32(cap);
 if(!query(level,vector,center,cfg.radius,ptr(0),0,ptr(0)))throw Error('范围查询失败');
 const n=length(vector),data=ptr(vector.readU64().and(uint64('0xffffffffffff')).toString()),found=new Set(),active=new Map(),targets=[];
 stats.objects=n;stats.nearbyItems=0;stats.nearbyCorpses=0;stats.nearbyContainers=0;stats.filtered=0;
 for(let i=0;i<n;i++){
  const p=data.add(i*8).readPointer(),type=typ(p),isBody=type==='. ?AVBodyContainer@@'.replace(' ',''),isContainer=type==='. ?AVContainer@@'.replace(' ',''),isDrop=type==='. ?AVDroppedItem@@'.replace(' ',''),isItem=type==='. ?AVContainerItem@@'.replace(' ',''),isComplex=type==='. ?AVComplexContainer@@'.replace(' ',''),isCollectable=type==='. ?AVCollectableObject@@'.replace(' ','');
  if(!isBody&&!isContainer&&!isDrop&&!isItem&&!isComplex&&!isCollectable)continue;
  const obj=p.sub(16),transform=worldTransform(p);if(transform.isNull())continue;const where=xyz(transform);
  const distance=Math.hypot(...where.map((x,j)=>x-pos[j]));if(!Number.isFinite(distance)||distance>cfg.radius)continue;
  const id=key(p,where);found.add(id);if(isBody)stats.nearbyCorpses++;else if(isContainer||isComplex)stats.nearbyContainers++;else stats.nearbyItems++;
  if(isCollectable)active.set(id,obj.add(456).readU8()===1&&obj.add(457).readU8()===1);
  if((isBody&&!cfg.corpses)||(isContainer&&!cfg.containers)||(isComplex&&(!cfg.containers||!cfg.items||!cfg.open_containers||obj.add(profile.body_state_offset).readS32()!==2))||((isDrop||isItem||isCollectable)&&!cfg.items)||obj.add(456).readU8()!==1||obj.add(457).readU8()!==1||pending.has(id)||(retry.get(id)||0)>now)continue;
  if((isBody||isContainer)&&!bodyEligible(obj))continue;
  if(isComplex){if(now-lastOpen<1000)continue;const lock=safeComplexLock(obj);if(!mayOpen(lock,cfg.locked_containers)){retry.set(id,now+1000);continue}}
  if((isDrop||isItem)&&!accepts(obj.add(isDrop?profile.dropped_description_offset:profile.container_item_description_offset))){stats.filtered++;continue}
  targets.push({obj,id,where,distance,type,isBody,isContainer,isItem,isComplex,isCollectable});
 }
 for(const [id,p] of pending){
  if(!found.has(id)||(p.collectable&&active.get(id)===false)){
   if(now-p.at<2000&&Math.hypot(...p.where.map((x,j)=>x-pos[j]))<cfg.radius-0.1){stats.items++;send({event:'loot',kind:'item',distance:p.distance,name:p.collectable?'特殊收集物':'散落物品（消光 2）'})}
   pending.delete(id);
  }else if(now-p.at>2000){pending.delete(id);stats.blocked++;retry.set(id,now+1000)}
 }
 targets.sort((a,b)=>a.distance-b.distance);
 for(const t of targets.slice(0,3)){
  if(t.isBody||t.isContainer){takeBody(t,player,now);continue}
  if(t.isComplex){openComplex(t,player,now);continue}
  if(t.isCollectable&&!simulated(t.obj)){retry.set(t.id,now+1000);continue;}
  const table=t.obj.readPointer(),canPtr=table.add(profile.can_slot*8).readPointer(),executePtr=table.add(profile.execute_slot*8).readPointer();
  if(!canPtr.equals(gameDll.base.add(t.isItem?profile.container_item_can_rva:(t.isCollectable?profile.collectable_can_rva:profile.can_rva)))||!executePtr.equals(gameDll.base.add(t.isItem?profile.container_item_execute_rva:(t.isCollectable?profile.collectable_execute_rva:profile.execute_rva))))continue;
  const source=player.add(profile.player_context_offset);if(!source.readPointer().equals(player.add(0x1b0)))throw Error('玩家交互上下文不匹配');
  Memory.copy(context,source,128);context.add(20).writeFloat(t.distance);context.add(24).writeU8(0x43);
  if(!native(canPtr,'bool',['pointer','int','pointer'])(t.obj,1,context)){stats.blocked++;retry.set(t.id,now+1000);continue}
  stats.attempts++;const ok=native(executePtr,'bool',['pointer','int','pointer'])(t.obj,1,context);
  if(ok)pending.set(t.id,{at:now,where:t.where,distance:t.distance,collectable:t.isCollectable});else{stats.blocked++;retry.set(t.id,now+1000)}
 }
 if(retry.size>1000)retry.clear();if(looted.size>1000)looted.clear();stats.scans++;stats.scanMs=Date.now()-now;stats.status='running';publish();
}
rpc.exports={
 modules(){return Process.enumerateModules().filter(m=>['engine_x64_rwdi.dll','gamedll_ph_x64_rwdi.dll'].includes(m.name.toLowerCase())).map(m=>({name:m.name,path:m.path,size:m.size}))},
 init(p){
  if(profile)throw Error('Already initialized');profile=p;engine=Process.getModuleByName('engine_x64_rwdi.dll');gameDll=Process.getModuleByName('gamedll_ph_x64_rwdi.dll');
  for(const m of [engine,gameDll])if(m.size!==p.modules[m.name.toLowerCase()].size)throw Error('Module size mismatch');
  query=native(exp('?FindObjectsInRadius@ILevel@@QEAA_NPEAV?$vector@PEAVIControlObject@@V?$heap_allocator@PEAVIControlObject@@@vector_allocators@ttl@@$00@ttl@@AEBVvec3@@MPEBVCRTTI@@_NPEAH@Z'),'bool',['pointer','pointer','pointer','float','pointer','bool','pointer']);
  frozen=native(exp('?IsTimerFrozen@ILevel@@QEBA_NXZ'),'bool',['pointer']);loading=native(exp('?IsLoading@ILevel@@QEBA_NXZ'),'bool',['pointer']);
  worldTransform=native(exp('?GetWorldXform@IControlObject@@QEBAAEBVmtx34@@XZ'),'pointer',['pointer']);getControl=native(exp('?GetControlObject@IControlObject@@SAPEAV1@PEBVCEntity@cbs@@@Z'),'pointer',['pointer']);
  getEntity=native(exp('?GetEntity@ComponentAdapter@cbs@@QEBAPEBVCEntity@2@XZ'),'pointer',['pointer']);isSimulating=native(exp('?IsSimulating@CEntity@cbs@@QEBA_NXZ'),'bool',['pointer']);findField=native(exp('?FindField@CRTTIObject@@QEBAPEBVCRTTIField@@PEBD@Z'),'pointer',['pointer','pointer']);
  const u=Process.getModuleByName('user32.dll');foreground=native(u.getExportByName('GetForegroundWindow'),'pointer',[]);windowPid=native(u.getExportByName('GetWindowThreadProcessId'),'uint',['pointer','pointer']);
  hooks.push(Interceptor.attach(exp('?GetTimeWeatherSystem@ILevel@@QEBAPEAVCSystem@TimeWeather@@XZ'),{onEnter(a){const now=Date.now();if(!level||!level.equals(a[0])){level=a[0];levelStable=now;pending.clear();retry.clear();looted.clear();verifiedLayouts.clear()}levelSeen=now}}));
  const site=engine.base.add(p.scheduler_return_rva);hooks.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'),{onEnter(a){this.game=a[0];this.run=this.returnAddress.equals(site)},onLeave(){if(!this.run||busy||Date.now()-lastTick<300)return;lastTick=Date.now();busy=true;try{tick(this.game)}catch(e){enabled=false;pending.clear();stats.status='error';stats.error=String(e);publish(true)}finally{busy=false}}}));
  publish(true);return true;
 },
 configure(c){
  if(!profile)throw Error('Not initialized');if(!Number.isFinite(c.radius)||c.radius<1||c.radius>500)throw Error('Radius must be 1–500 m');
  if(c.enabled&&!(c.items||c.corpses||c.containers))throw Error('请选择至少一项拾取类型');
  if(!c.item_types||typeof c.item_types.weapons!=='boolean')throw Error('武器筛选设置无效');
  if(!Array.isArray(c.excluded_ids||[])||(c.excluded_ids||[]).length>20000||(c.excluded_ids||[]).some(x=>typeof x!=='string'))throw Error('排除列表格式无效');
  if(Object.entries(c.item_types).some(([k,v])=>k!=='weapons'&&v!==true)||Object.keys(c.item_rules?.items||{}).length||Object.keys(c.item_rules?.subtypes||{}).length)throw Error('消光 2 当前只支持武器筛选');
  cfg={radius:c.radius,items:!!c.items,corpses:!!c.corpses,containers:!!c.containers,weapons:!!c.item_types.weapons,open_containers:!!c.open_containers,locked_containers:!!c.locked_containers,excluded_ids:new Set(c.excluded_ids||[])};pending.clear();retry.clear();looted.clear();enabled=!!c.enabled;lease=Date.now()+5000;stats.error=null;stats.status=enabled?'waiting':'disabled';publish(true);return {...stats,enabled};
 },
 heartbeat(){lease=Date.now()+5000;return {...stats,enabled,pending:pending.size}},
 stop(){enabled=false;pending.clear();stats.status='disabled';publish(true);return true},
 shutdown(){enabled=false;pending.clear();hooks.splice(0).forEach(h=>h.detach());return true}
};