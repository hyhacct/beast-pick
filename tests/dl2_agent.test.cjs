const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../beast_pick/dl2_agent.js'), 'utf8');
function adapter() {
  const pointer = {add(){return this}, sub(){return this}, isNull(){return false}};
  const s=vm.createContext({Memory:{alloc:()=>pointer},rpc:{},send(){},ptr:()=>pointer});
  vm.runInContext(source + `\nprofile={item_categories:{weapons:[0],ammo:[4]}};publish=()=>{};`,s);
  return s.rpc.exports;
}
function settings(){return {radius:8,enabled:true,items:true,item_types:{weapons:true,ammo:true},item_rules:{items:{},subtypes:{}}}}
test('DL2 permits unfiltered ground pickup',()=>{const a=adapter(); assert.equal(a.configure(settings()).enabled,true);assert.equal(a.stop(),true)});
test('DL2 permits excluding weapons but rejects other category exclusions',()=>{const a=adapter(),c=settings();c.item_types.weapons=false;assert.equal(a.configure(c).enabled,true);c.item_types.ammo=false;assert.throws(()=>a.configure(c),/筛选/)});
test('DL2 refuses specific item and subtype rules',()=>{for(const kind of ['items','subtypes']){const a=adapter(),c=settings();c.item_rules[kind].foo=false;assert.throws(()=>a.configure(c),/筛选/)}});
test('DL2 requires at least one target and valid radius',()=>{const a=adapter(),c=settings();c.items=false;assert.throws(()=>a.configure(c));c.corpses=true;assert.equal(a.configure(c).enabled,true);c.radius=501;assert.throws(()=>a.configure(c))});
function acceptsCategory(n, weapons) {
  const pointer={add(){return this},sub(){return this},isNull(){return false}};
  const s=vm.createContext({Memory:{alloc:()=>pointer},rpc:{},send(){},ptr:()=>pointer,scenario:{category:n,weapons}});
  vm.runInContext(source+`\ncfg.weapons=scenario.weapons; category=()=>scenario.category; scenario.result=accepts({});`,s);
  return s.scenario.result;
}
test('weapon filter accepts known cash but blocks melee, firearms, unknowns and opaque bundles',()=>{
  for(const n of [0,1,17,19,27,28,null])assert.equal(acceptsCategory(n,false),false);
  assert.equal(acceptsCategory(5,false),true);
  assert.equal(acceptsCategory(0,true),true);
});

test('chests require a known lock and explicit locked opt-in',()=>{
 const pointer={add(){return this},sub(){return this},isNull(){return false}};
 const s=vm.createContext({Memory:{alloc:()=>pointer},rpc:{},send(){},ptr:()=>pointer,scenario:{}});
 vm.runInContext(source+`\nscenario.result=[mayOpen(null,true),mayOpen('',false),mayOpen('medium',false),mayOpen('medium',true)];`,s);
 assert.deepEqual(Array.from(s.scenario.result),[false,true,false,true]);
});
test('empty bodies never occupy the limited target queue',()=>{
 const pointer={add(){return this},sub(){return this},isNull(){return false}};
 const s=vm.createContext({Memory:{alloc:()=>pointer},rpc:{},send(){},ptr:()=>pointer,scenario:{}});
 vm.runInContext(source+`\nprofile={body_state_offset:1};cfg.weapons=true;bodyCounts=()=>[0,0];const item={add(){return {readS32(){return 1}}}};scenario.empty=bodyEligible(item);bodyCounts=()=>[1,1];scenario.nonempty=bodyEligible(item);`,s);
 assert.equal(s.scenario.empty,false);assert.equal(s.scenario.nonempty,true);
});

test('locked chest calls game actions only with the separate opt-in',()=>{
 const pointer={add(){return this},sub(){return this},isNull(){return false},equals(){return true},readPointer(){return this},readS32(){return 1}};
 for (const enabled of [false,true]) {
  const s=vm.createContext({Memory:{alloc:()=>pointer},rpc:{},send(){},ptr:()=>pointer,scenario:{enabled,calls:[]}});
  vm.runInContext(source+`\nprofile={can_slot:203,execute_slot:204,complex_can_rva:1,complex_execute_rva:2,body_state_offset:1};gameDll={base:scenario.ptr};cfg.locked_containers=scenario.enabled;safeComplexLock=()=>"medium";actionContext=()=>{};native=()=>function(self,action){scenario.calls.push(action);return 1};const target={obj:scenario.ptr,id:'test',distance:1};openComplex(target,scenario.ptr,2000);scenario.opened=stats.opened;`,Object.assign(s,{scenario:{enabled,calls:[],ptr:pointer}}));
  assert.equal(s.scenario.opened,enabled?1:0);assert.deepEqual(Array.from(s.scenario.calls),enabled?[7,7]:[]);
 }
});

test('exact exclusions cover throwable weapons and fail closed on unknown identities',()=>{
 const pointer={add(){return this},sub(){return this},isNull(){return false}};
 function check(category,id,includeWeapons,excluded){
  const scenario={category,id,includeWeapons,excluded};
  const s=vm.createContext({Memory:{alloc:()=>pointer},rpc:{},send(){},ptr:()=>pointer,scenario});
  vm.runInContext(source+`\ncfg.weapons=scenario.includeWeapons;cfg.excluded_ids=new Set(scenario.excluded);category=()=>scenario.category;itemId=()=>scenario.id;scenario.result=accepts({});`,s);
  return scenario.result;
 }
 assert.equal(check(2,'pitchfork',true,['pitchfork']),false);
 assert.equal(check(2,'other',true,['pitchfork']),true);
 assert.equal(check(2,null,true,['pitchfork']),false);
 assert.equal(check(18,null,true,['pitchfork']),true);
 assert.equal(check(17,'bundle',true,['pitchfork']),false);
 assert.equal(check(0,'hammer',false,[]),false);
});
