const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../beast_pick/agent.js'), 'utf8');

function scan(playerCount, {localReady = true, loading = false} = {}) {
    const calls = [];
    const pointer = {isNull: () => false, add() { return this; }, sub() { return this; },
        writePointer() {}, writeU32() {}, writeFloat() {}};
    const scenario = {playerCount, localReady, loading, pointer, calls};
    const sandbox = vm.createContext({scenario, Memory: {alloc: () => pointer},
        rpc: {}, ptr: () => pointer, send() {}});
    vm.runInContext(source + `
        profile = {players_slot: 152, local_entity_slot: 153, player_transform_slot: 151};
        enabled = true; leaseUntil = Date.now() + 5000;
        level = scenario.pointer; levelSeen = Date.now(); levelStable = Date.now() - 2000;
        foregroundGame = () => true;
        loading = () => scenario.loading;
        frozen = () => false;
        type = p => p === level ? '.?AVLevelDI@@' : '.?AVPlayerDI_PH@@';
        const entity = {isNull: () => !scenario.localReady};
        const control = {isNull: () => false, sub: () => scenario.pointer};
        getControl = p => { if (p !== entity) throw Error('Wrong player entity'); return control; };
        vf = (game, slot) => () => {
            scenario.calls.push(slot);
            if (slot === profile.players_slot) return {isNull: () => false, count: scenario.playerCount};
            if (slot === profile.local_entity_slot) return entity;
            if (slot === profile.player_transform_slot) return scenario.pointer;
            throw Error('Unexpected virtual slot ' + slot);
        };
        xyz = () => [1, 2, 3];
        query = () => { scenario.calls.push('query'); return true; };
        size = v => v.count ?? 0;
        data = () => scenario.pointer;
        tick(scenario.pointer);
        scenario.status = stats.status;
        scenario.scans = stats.scans;
    `, sandbox);
    return scenario;
}

for (const count of [1, 2, 4]) {
    test(`scans with ${count} session players using the local entity`, () => {
        const result = scan(count);
        assert.equal(result.status, 'running');
        assert.equal(result.scans, 1);
        assert.ok(result.calls.includes(153));
        assert.ok(result.calls.includes('query'));
    });
}

test('co-op waits for the local entity before querying loot', () => {
    const result = scan(4, {localReady: false});
    assert.equal(result.status, 'waiting_player');
    assert.equal(result.scans, 0);
    assert.ok(!result.calls.includes('query'));
});

test('co-op does not scan while the level is loading', () => {
    const result = scan(4, {loading: true});
    assert.equal(result.status, 'paused');
    assert.equal(result.scans, 0);
    assert.equal(result.calls.length, 0);
});

test('drains a corpse in one simulation callback while refreshing compacted indices', () => {
    const calls = [], events = [], state = {counts: [3, 3]};
    const pointer = {
        isNull: () => false,
        add() { return this; },
        sub() { return this; },
        equals() { return true; },
        readPointer() { return this; },
        writePointer() {},
        readS32() { return 1; },
    };
    const scenario = {pointer, calls, events, state};
    const sandbox = vm.createContext({
        scenario,
        calls,
        events,
        state,
        Memory: {alloc: () => pointer},
        rpc: {},
        ptr: () => pointer,
        send(event) { events.push(event); },
        Date,
    });
    vm.runInContext(source + `
        profile = {body_state_offset: 0x388, body_items_offsets: [0x4c8, 0x4d8],
            body_init_slot: 220, body_loot_offset: 984, body_init_rva: 1,
            body_take_rva: 2, body_take_one_rva: 3, item_categories: {other: 6}};
        gameDll = {base: scenario.pointer};
        allowed = () => true;
        ordinaryEligible = () => true;
        targetSnapshot = () => ({state: 1, counts: state.counts.slice()});
        bodySelection = () => ({count: state.counts[0],
            selected: Array.from({length: state.counts[0]}, (_, i) => i),
            categories: Array(state.counts[0]).fill(6),
            identities: Array.from({length: state.counts[0]}, (_, i) => ({category: 6, id: 'item-' + i}))});
        globalThis.LootPolicy = {group: () => 'other'};
        native = (address, result, args) => args.length === 1
            ? () => {}
            : () => { calls.push('take-one'); state.counts[0]--; state.counts[1]--; return true; };
        const target = {control: scenario.pointer, key: 'body-1', distance: 1};
        corpse(target, scenario.pointer, 1000);
        scenario.result = {calls: calls.length, events: events.length, counts: state.counts.slice(), attempts: stats.attempts};
    `, sandbox);
    assert.equal(scenario.result.calls, 3);
    assert.equal(scenario.result.events, 3);
    assert.deepEqual(Array.from(scenario.result.counts), [0, 0]);
    assert.equal(scenario.result.attempts, 3);
});

test('transient loot failures retry without multi-second stalls', () => {
    const pointer = {isNull: () => false, add() { return this; }};
    const scenario = {};
    const sandbox = vm.createContext({scenario, Memory: {alloc: () => pointer}, rpc: {}, ptr: () => pointer, Date});
    vm.runInContext(source + `
        retry('body', 1000);
        scenario.first = retries.get('body');
        retry('body', 1250);
        scenario.second = retries.get('body');
    `, sandbox);
    assert.equal(scenario.first.failures, 1);
    assert.equal(scenario.first.next, 1250);
    assert.equal(scenario.second.failures, 2);
    assert.equal(scenario.second.next, 1750);
});
