'use strict';

// Only the game's input handler and verified frame callback invoke native code.
// Attack speed is recomputed in the game's melee controller; player variables
// are never patched, so changing character or scene cannot leave a saved buff.
const RapidMelee = {
    create({layout, engine, gameDll, context, lease, report}) {
        let desired = false, speed = 12, holding = false, pressed = false;
        let injecting = false, busy = false, closing = false, detached = false;
        let current = null, cached = null, nextAttack = 0;
        let status = 'disabled', error = null, pulses = 0;
        let observedSpeed = null, speedUpdates = 0;
        let attacks = 0, phase = null;
        let speedHook = null, frameHook = null, replaced = false;
        let updatingSpeed = false;
        const functions = new Map(), actions = [layout.fire_action, layout.attack_action, layout.charge_action];
        function fn(address, result, args) {
            const key = address + ':' + result + ':' + args;
            if (!functions.has(key)) functions.set(key, new NativeFunction(address, result, args, {scheduling: 'exclusive'}));
            return functions.get(key);
        }
        const user32 = Process.getModuleByName('user32.dll');
        const keyState = fn(user32.getExportByName('GetAsyncKeyState'), 'int16', ['int']);
        const inputAddress = gameDll.base.add(layout.input_rva);
        const originalInput = fn(inputAddress, 'void', ['pointer', 'int', 'float', 'bool']);
        const updateSpeed = fn(gameDll.base.add(layout.speed_update_rva), 'void', ['pointer']);
        function down() { return !!(keyState(1) & 0x8000); }
        function armed() { return desired && lease() && !closing; }
        function eligible() { return armed() && current?.ready && current.melee; }
        function active() { return eligible() && holding && down(); }
        function inject(target, action, value) {
            injecting = true;
            try { originalInput(target, action, value, 0); }
            finally { injecting = false; }
        }
        function validController(entry, ctx) {
            return entry && ctx?.player && entry.owner.equals(ctx.player) && entry.item.equals(ctx.item) &&
                ctx.controller && entry.control.equals(ctx.controller) &&
                type(entry.control) === '.?AVWeaponMeleeController@@' &&
                entry.control.add(layout.controller_owner_offset).readPointer().equals(ctx.player);
        }
        function observeSpeed(control) {
            const values = layout.controller_speed_offsets.map(o => control.add(o).readFloat());
            if (values.some(v => !Number.isFinite(v) || v < 0 || v > 100)) throw Error('Invalid native melee speed');
            cached = {control, owner: current.player, item: current.item, boosted: false};
            if (active()) {
                values.forEach((value, i) => control.add(layout.controller_speed_offsets[i]).writeFloat(value * speed));
                cached.boosted = true;
                observedSpeed = values[0] * speed; speedUpdates++;
            } else observedSpeed = values[0];
        }
        function recomputeSpeed(control) {
            updatingSpeed = true;
            try { updateSpeed(control); }
            finally { updatingSpeed = false; }
            // Frida skips this script's own interceptors during a native call
            // made inside another interceptor. Apply the multiplier explicitly.
            observeSpeed(control);
        }
        function reset(ctx) {
            if (pressed && current?.player && ctx?.player && current.player.equals(ctx.player)) {
                const target = ctx.player.add(layout.input_target_offset);
                for (const action of actions) inject(target, action, 0);
            }
            pressed = false; holding = false; nextAttack = 0;
            if (cached?.boosted && validController(cached, ctx)) {
                // 'holding' is already false, so the observer leaves the game's
                // freshly recomputed speed unchanged.
                recomputeSpeed(cached.control);
                cached.boosted = false;
            }
        }
        function fail(e) {
            desired = false; holding = false; error = String(e); status = 'error';
            report({event: 'melee_error', error, stack: e?.stack || null});
        }
        const replacement = new NativeCallback((target, action, value, analog) => {
            if (injecting) { originalInput(target, action, value, analog); return; }
            let forwarded = value;
            try {
                const local = current?.player && target.equals(current.player.add(layout.input_target_offset));
                if (local && action === layout.fire_action) holding = value > 0 && down() && armed();
                if (local && eligible()) {
                    if (holding && actions.includes(action)) forwarded = 0;
                }
            } catch (e) { fail(e); }
            originalInput(target, action, forwarded, analog);
        }, 'void', ['pointer', 'int', 'float', 'bool']);
        function attach() {
        speedHook = Interceptor.attach(gameDll.base.add(layout.speed_update_rva), {
            onEnter(args) {
                this.rapidControl = args[0];
                this.rapidLocal = false;
                try {
                    this.rapidLocal = !!current?.player && type(args[0]) === '.?AVWeaponMeleeController@@' &&
                        args[0].add(layout.controller_owner_offset).readPointer().equals(current.player);
                } catch (_) {}
            },
            onLeave() {
                if (!this.rapidLocal || updatingSpeed) return;
                try {
                    observeSpeed(this.rapidControl);
                } catch (e) { fail(e); }
            }
        });
        frameHook = Interceptor.attach(gameDll.base.add(layout.frame_site_rva), {
            onEnter() { tick(this.context[layout.game_register]); }
        });
        Interceptor.replace(inputAddress, replacement);
        replaced = true;
        }
        function finish() {
            if (detached) return;
            detached = true;
            speedHook?.detach(); frameHook?.detach();
        }
        function tick(game) {
            if (busy || detached) return;
            busy = true;
            try {
                if (!armed() && !pressed && !cached?.boosted) {
                    holding = false; current = null;
                    status = error ? 'error' : 'disabled';
                    if (closing) finish();
                    return;
                }
                const ctx = context(game);
                if (!current?.player || !ctx.player || !current.player.equals(ctx.player)) {
                    cached = null; pressed = false; holding = false;
                }
                if (!armed() || !ctx.ready || !ctx.melee || !holding || !down()) {
                    reset(ctx); current = ctx;
                    status = error ? 'error' : !armed() ? 'disabled' : ctx.reason || 'idle';
                    if (closing) finish();
                    return;
                }
                current = ctx;
                if (!validController(cached, ctx) && ctx.controller) {
                    cached = {control: ctx.controller, owner: ctx.player, item: ctx.item, boosted: false};
                }
                if (validController(cached, ctx)) recomputeSpeed(cached.control);
                if (!active()) { reset(ctx); status = error ? 'error' : 'idle'; return; }
                const now = Date.now(), target = ctx.player.add(layout.input_target_offset);
                phase = cached.control.add(layout.attack_phase_offset).readS32();
                if (![0, 1, 2].includes(phase)) throw Error('Invalid native attack phase: ' + phase);
                const pending = cached.control.add(layout.attack_pending_offset).readS32();
                const running = cached.control.add(layout.attack_running_offset).readS32();
                // Normal light attacks have phase 0 while the swing is still
                // running. Both the queued and current animation must finish;
                // restarting at phase 0 alone can discard the damage events.
                if (phase === 0 && pending === -1 && running === -1 && now >= nextAttack) {
                    pressed = true;
                    try {
                        for (const action of actions) inject(target, action, 1);
                    } finally {
                        // Reproduce a normal quick click. The native release
                        // chooses commit(false), including its light attack
                        // selection; commit(true) forces the charged branch.
                        for (const action of actions) inject(target, action, 0);
                        pressed = false;
                    }
                    nextAttack = now + 16; pulses++;
                    phase = cached.control.add(layout.attack_phase_offset).readS32();
                    if (cached.control.add(layout.attack_pending_offset).readS32() !== -1 ||
                        cached.control.add(layout.attack_running_offset).readS32() !== -1) attacks++;
                }
                status = 'attacking';
            } catch (e) { fail(e); }
            finally { busy = false; }
        }
        try { attach(); }
        catch (e) {
            if (replaced) Interceptor.revert(inputAddress);
            finish();
            throw e;
        }
        return {
            configure(value, multiplier) { desired = !!value; speed = multiplier; error = null; if (!desired) holding = false; },
            stop() { desired = false; holding = false; },
            snapshot() { return {enabled: armed(), status, speed, pulses, attacks, phase,
                observed_speed: observedSpeed, speed_updates: speedUpdates, error}; },
            shutdown() {
                desired = false; holding = false; closing = true;
                if (replaced) { Interceptor.revert(inputAddress); replaced = false; }
                // A pending release/restoration must finish on the game thread.
                // Client.close eternalizes the runtime while this callback drains.
                if (!pressed && !cached?.boosted) finish();
            },
            // Keep the callback alive through shutdown and an in-flight return.
            replacement
        };
    }
};
