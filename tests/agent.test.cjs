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
