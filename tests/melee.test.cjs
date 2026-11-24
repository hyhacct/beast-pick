const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../beast_pick/melee.js', 'utf8');
const layout = JSON.parse(fs.readFileSync(__dirname + '/../beast_pick/profiles/current.json', 'utf8')).melee;
function fixture() {
    const state = {now: 1000, down: false, ready: true, melee: true, lease: true, baseSpeed: 1,
        memory: new Map(), hooks: new Map(), original: [], replacement: null, replacing: false, reports: []};
    const BASE = 0x10000000, PLAYER = 0x20000000, ITEM = 0x30000000, CTRL = 0x40000000;
    class P {
        constructor(v) { this.v = Number(v); }
        add(n) { return new P(this.v + n); }
        isNull() { return !this.v; }
        equals(p) { return this.v === p.v; }
        toString() { return '0x' + this.v.toString(16); }
        readPointer() { return new P(state.memory.get(this.v) ?? 0); }
        readFloat() { return state.memory.get(this.v) ?? 0; }
        readS32() { return state.memory.get(this.v) ?? 0; }
        writeFloat(v) { state.memory.set(this.v, v); }
    }
    const p = v => new P(v);
    state.memory.set(CTRL + layout.controller_owner_offset, PLAYER);
    layout.controller_speed_offsets.forEach(o => state.memory.set(CTRL + o, state.baseSpeed));
    function input(target, action, value, analog) {
        if (state.replacement && !state.replacing) {
            state.replacing = true;
            try { return state.replacement(target, action, value, analog); }
            finally { state.replacing = false; }
        }
        state.original.push({action, value, analog});
        if (action === layout.attack_action && value === 1 &&
            state.memory.get(CTRL + layout.attack_phase_offset) === 0)
            state.memory.set(CTRL + layout.attack_phase_offset, 1);
        if (action === layout.attack_action && value === 0 &&
            state.memory.get(CTRL + layout.attack_phase_offset) === 1) {
            // Captured normal quick release: light attack is queued while
            // phase returns to 0, then the animation consumes that queue.
            state.memory.set(CTRL + layout.attack_phase_offset, 0);
            state.memory.set(CTRL + layout.attack_pending_offset, 1);
        }
    }
    function speed(control = p(CTRL)) {
        const hook = state.hooks.get(BASE + layout.speed_update_rva), call = {};
        hook?.onEnter.call(call, [control]);
        layout.controller_speed_offsets.forEach(o => control.add(o).writeFloat(state.baseSpeed));
        hook?.onLeave.call(call);
    }
    const sandbox = {Date: {now: () => state.now},
        Process: {getModuleByName: () => ({getExportByName: () => p(99)})},
        type: x => x.v === CTRL ? '.?AVWeaponMeleeController@@' : null,
        NativeCallback: function(f) { return f; },
        NativeFunction: function(a) {
            if (a.v === 99) return () => state.down ? -32768 : 0;
            if (a.v === BASE + layout.input_rva) return (...args) => {
                assert.equal(typeof args[3], 'number', 'Frida bool arguments require integer 0/1');
                return input(...args);
            };
            if (a.v === BASE + layout.speed_update_rva) return control => {
                // Native calls inside an interceptor bypass our own listeners.
                layout.controller_speed_offsets.forEach(o => control.add(o).writeFloat(state.baseSpeed));
            };
            throw Error('Unexpected native');
        },
        Interceptor: {
            replace(_a, f) { state.replacement = f; },
            revert() { state.replacement = null; },
            attach(a, h) { state.hooks.set(a.v, h); return {detach() { state.hooks.delete(a.v); }}; }
        },
        options: {layout, engine: {}, gameDll: {base: p(BASE)},
            context: () => ({player: p(PLAYER), item: p(ITEM), controller: p(CTRL), ready: state.ready, melee: state.melee,
                reason: !state.ready ? 'paused' : !state.melee ? 'melee_required' : 'idle'}),
            lease: () => state.lease, report: e => state.reports.push(e)}
    };
    vm.createContext(sandbox);
    vm.runInContext(source + '\nglobalThis.api = RapidMelee.create(options);', sandbox);
    const api = sandbox.api;
    function frame() { state.hooks.get(BASE + layout.frame_site_rva)?.onEnter.call({context: {rsi: p(55)}}); }
    function press() {
        state.down = true;
            for (const action of [210, 208, 162]) input(p(PLAYER + layout.input_target_offset), action, 1, 0);
    }
    function start() { api.configure(true, 12); frame(); }
    state.memory.set(CTRL + layout.attack_phase_offset, 0);
    state.memory.set(CTRL + layout.attack_pending_offset, -1);
    state.memory.set(CTRL + layout.attack_running_offset, -1);
    return {state, api, frame, press, start, speed,
        playAttack: () => {
            state.memory.set(CTRL + layout.attack_running_offset,
                state.memory.get(CTRL + layout.attack_pending_offset));
            state.memory.set(CTRL + layout.attack_pending_offset, -1);
        },
        finishAttack: () => {
            state.memory.set(CTRL + layout.attack_phase_offset, 0);
            state.memory.set(CTRL + layout.attack_pending_offset, -1);
            state.memory.set(CTRL + layout.attack_running_offset, -1);
        },
        boosted: () => p(CTRL).add(layout.controller_speed_offsets[0]).readFloat()};
}
test('held melee emits a quick click, scales controller rate and restores on release', () => {
    const h = fixture(); h.start(); h.press(); h.frame();
    assert.equal(h.api.snapshot().pulses, 1);
    assert.equal(h.boosted(), 12);
    assert.ok(h.state.original.some(e => e.action === 210 && e.value === 1), 'synthetic input must reach the game');
    h.state.now += 20; h.frame(); h.state.now += 40; h.frame();
    assert.equal(h.api.snapshot().pulses, 1, 'do not restart an unfinished attack');
    h.finishAttack(); h.frame();
    assert.equal(h.api.snapshot().pulses, 2);
    h.state.down = false; h.frame(); assert.equal(h.boosted(), 1);
    h.state.now += 100; h.frame(); assert.equal(h.api.snapshot().pulses, 2);
});

test('light attack queues on the same frame and preserves pending and running swings at phase zero', () => {
    const h = fixture(); h.start(); h.press(); h.frame();
    assert.equal(h.api.snapshot().attacks, 1);
    assert.equal(h.api.snapshot().phase, 0);
    for (let i = 0; i < 10; i++) { h.state.now += 20; h.frame(); }
    assert.equal(h.api.snapshot().attacks, 1, 'queued animation is not idle');
    h.playAttack();
    for (let i = 0; i < 10; i++) { h.state.now += 20; h.frame(); }
    assert.equal(h.api.snapshot().attacks, 1, 'preserve the animation and damage event until native completion');
    h.finishAttack(); h.frame();
    assert.equal(h.api.snapshot().attacks, 2);
});
test('speed is recomputed from game values and never compounds', () => {
    const h = fixture(); h.start(); h.press(); h.frame();
    h.state.now += 60; h.frame(); assert.equal(h.boosted(), 12);
    h.state.baseSpeed = 1.5; h.speed(); assert.equal(h.boosted(), 18);
    h.api.stop(); h.frame(); assert.equal(h.boosted(), 1.5);
});
test('ranged weapons, paused gameplay and an expired lease do not auto attack', () => {
    for (const mode of ['ranged', 'paused', 'expired']) {
        const h = fixture(); h.start();
        if (mode === 'ranged') h.state.melee = false;
        if (mode === 'paused') h.state.ready = false;
        if (mode === 'expired') h.state.lease = false;
        h.frame(); h.press(); h.frame();
        assert.equal(h.api.snapshot().pulses, 0, mode);
        assert.equal(h.boosted(), 1, mode);
    }
});
test('F8 stop and shutdown release synthetic input and restore native speed', () => {
    for (const closing of [false, true]) {
        const h = fixture(); h.start(); h.press(); h.frame();
        closing ? h.api.shutdown() : h.api.stop(); h.frame();
        assert.equal(h.boosted(), 1);
        assert.equal(h.state.original.at(-1).value, 0);
        assert.equal(h.api.snapshot().enabled, false);
        if (closing) assert.equal(h.state.hooks.size, 0);
    }
});
test('invalid native speed stops before emitting an attack', () => {
    const h = fixture(); h.start(); h.press(); h.state.baseSpeed = NaN; h.frame();
    assert.equal(h.api.snapshot().enabled, false);
    assert.equal(h.api.snapshot().pulses, 0);
    assert.equal(h.state.reports.at(-1).event, 'melee_error');
});
