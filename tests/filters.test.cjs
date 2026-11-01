const {test} = require('node:test');
const assert = require('node:assert/strict');
require('../beast_pick/filters.js');
const groups = JSON.parse(require('node:child_process').execFileSync(
    require('node:path').resolve(__dirname, '../.venv/Scripts/python.exe'),
    ['-c', 'import json; from beast_pick.categories import ITEM_TYPES; print(json.dumps({k:v[1] for k,v in ITEM_TYPES.items()}))'],
    {cwd: require('node:path').resolve(__dirname, '..'), encoding:'utf8'}));
const all = Object.fromEntries(Object.keys(groups).map(k => [k, true]));

test('known categories cover the game enum exactly once', () => {
    assert.deepEqual(Object.values(groups).flat().sort((a,b)=>a-b), Array.from({length:29},(_,i)=>i));
    for(let c=0;c<29;c++) assert.equal(LootPolicy.accepts(c,all,groups),true);
});
test('weapon exclusion blocks both melee/improvised and firearm categories', () => {
    const selection = {...all, weapons:false};
    assert.equal(LootPolicy.accepts(0,selection,groups),false);
    assert.equal(LootPolicy.accepts(1,selection,groups),false);
    for(const c of [4,5,7,18,20]) assert.equal(LootPolicy.accepts(c,selection,groups),true);
});
test('unknown metadata never falls through into other', () => {
    for(const c of [null,undefined,-1,29,100,NaN,'0']) assert.equal(LootPolicy.accepts(c,all,groups),false);
});
test('opaque bundles cannot indirectly grant excluded items', () => {
    for(const c of [17,19,27,28]) {
        assert.equal(LootPolicy.accepts(c,{...all,weapons:false},groups),false);
        assert.equal(LootPolicy.accepts(c,all,groups),true);
    }
});
test('single type selection and disabled all stay closed', () => {
    const none = Object.fromEntries(Object.keys(groups).map(k=>[k,false]));
    for(let c=0;c<29;c++) {
        assert.equal(LootPolicy.accepts(c,none,groups),false);
        assert.equal(LootPolicy.accepts(c,{...none,money:true},groups),groups.money.includes(c));
    }
});

const grenade = {id:'Grenade_A', subtype:'throwables:ItemType_Grenade'};
test('exact item overrides subtype which overrides broad group', () => {
    const rules={items:{Grenade_A:true},subtypes:{'throwables:ItemType_Grenade':false}};
    assert.equal(LootPolicy.accepts(2,{...all,throwables:false},groups,grenade,rules),true);
    assert.equal(LootPolicy.accepts(2,all,groups,{...grenade,id:'Grenade_B'},rules),false);
    assert.equal(LootPolicy.accepts(2,{...all,throwables:false},groups,grenade,{items:{},subtypes:{[grenade.subtype]:true}}),true);
});
test('a specific exclusion remains active when broad groups are all selected', () => {
    const rules={items:{Grenade_A:false},subtypes:{}};
    assert.equal(LootPolicy.accepts(2,all,groups,grenade,rules),false);
    assert.equal(LootPolicy.accepts(2,all,groups,{...grenade,id:'Grenade_B'},rules),true);
    assert.equal(LootPolicy.accepts(2,all,groups,null,rules),false);
    assert.equal(LootPolicy.accepts(2,all,groups,{id:null,subtype:null},rules),false);
    for(const c of [17,19,27,28]) assert.equal(LootPolicy.accepts(c,all,groups,grenade,rules),false);
});

test('opening is limited to exact ordinary container types and verified state', () => {
    const config={containers:true,open_containers:true,locked_containers:true};
    const info={verified:true,simulating:true,noLoot:false,lock:'hard',linked:false};
    for(const name of ['.?AVDoor@@','.?AVDoorDI@@','.?AVLock@@','.?AVQuestTrigger@@','.?AVContainerItem@@',null])
        assert.equal(LootPolicy.canOpenContainer(name,2,info,config),false);
    for(const state of [0,1,3,4,5]) assert.equal(LootPolicy.canOpenContainer('.?AVComplexContainer@@',state,info,config),false);
    assert.equal(LootPolicy.canOpenContainer('.?AVComplexContainer@@',2,info,config),true);
    for(const override of [{verified:false},{simulating:false},{simulating:undefined},{noLoot:true},{noLoot:undefined},{lock:'cube1'},{lock:undefined}])
        assert.equal(LootPolicy.canOpenContainer('.?AVComplexContainer@@',2,{...info,...override},config),false);
    assert.equal(LootPolicy.canOpenContainer('.?AVContainer@@',2,info,config),true);
    assert.equal(LootPolicy.canOpenContainer('.?AVContainer@@',2,{...info,linked:true},config),false);
});
test('lock bypass and ordinary opening have separate stop-by-default switches', () => {
    const config={containers:true,open_containers:true,locked_containers:false};
    const info={verified:true,simulating:true,noLoot:false,lock:''};
    assert.equal(LootPolicy.canOpenContainer('.?AVComplexContainer@@',2,info,config),true);
    assert.equal(LootPolicy.canOpenContainer('.?AVComplexContainer@@',2,{...info,lock:'easy'},config),false);
    for(const override of [{open_containers:false},{containers:false}])
        assert.equal(LootPolicy.canOpenContainer('.?AVComplexContainer@@',2,info,{...config,...override}),false);
});

test('state changes alone cannot claim that a complex cabinet has generated contents', () => {
    assert.equal(LootPolicy.openConfirmed('.?AVComplexContainer@@',1,0,3),false);
    assert.equal(LootPolicy.openConfirmed('.?AVComplexContainer@@',5,0,3),false);
    assert.equal(LootPolicy.openConfirmed('.?AVComplexContainer@@',1,2,1),true);
    // MarkTakenOnOpen can set state5 even when a weapon remains inside.
    assert.equal(LootPolicy.openConfirmed('.?AVComplexContainer@@',5,3,2),true);
    assert.equal(LootPolicy.openConfirmed('.?AVComplexContainer@@',5,0,0),true);
    assert.equal(LootPolicy.openConfirmed('.?AVComplexContainer@@',2,2,1),false);
    assert.equal(LootPolicy.openConfirmed('.?AVDoor@@',1,2,1),false);
});
