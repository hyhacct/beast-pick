'use strict';

// All engine queries and mutations run at a verified simulation-thread call site.
// There is no asynchronous queue of native pointers or loot actions.
let profile = null, engine = null, gameDll = null, level = null;
let levelSeen = 0, levelStable = 0, enabled = false, busy = false;
let leaseUntil = 0, lastTick = 0, lastPublish = 0, lastOpen = 0;
let config = {radius: 8, corpses: true, items: true, containers: true, item_types: {}, item_rules: {items: {}, subtypes: {}}};
let stats = {status: 'waiting', corpses: 0, items: 0, containers: 0, opened: 0, scans: 0, nearbyCorpses: 0, nearbyContainers: 0,
    nearbyItems: 0, filtered: 0, unknown: 0, objects: 0, attempts: 0, blocked: 0, scanMs: 0, error: null};
const listeners = [], retries = new Map(), pending = new Map(), nativeCache = new Map();
const typeCache = new Map(), itemCache = new Map(), containerLayouts = new Set(), lootedBodies = new Set(), knownBodies = new Set();
// Keep all native loot calls on the simulation thread, but drain a current
// target in one callback.  A separate worker would race the game's vectors.
const bodyBatchLimit = 16;
const capacity = 65536;
const vector = Memory.alloc(16), storage = Memory.alloc(capacity * 8);
const center = Memory.alloc(12), context = Memory.alloc(128), pidOut = Memory.alloc(4);
let query, frozen, loading, worldTransform, getControl, foreground, windowPid;

function native(address, result, args) {
    const key = address.toString() + result + args.join(',');
    if (!nativeCache.has(key)) nativeCache.set(key, new NativeFunction(address, result, args));
    return nativeCache.get(key);
}
function exp(name) { return engine.getExportByName(name); }
function vf(p, slot, result, args) { return native(p.readPointer().add(slot * 8).readPointer(), result, args); }
function type(p) {
    if (!p || p.isNull()) return null;
    const table = p.readPointer(), key = table.toString();
    if (typeCache.has(key)) return typeCache.get(key);
    const mod = Process.getModuleByAddress(table);
    const col = table.sub(8).readPointer();
    const name = mod.base.add(col.add(12).readU32()).add(16).readCString();
    typeCache.set(key, name);
    return name;
}
function size(v) {
    const code = v.add(7).readU8();
    const n = code ? code - 1 : v.add(8).readU32();
    if (n > capacity) throw Error('Invalid vector length: ' + n);
    return n;
}
function data(v) { return ptr(v.readU64().and(uint64('0xffffffffffff')).toString()); }
function xyz(matrix) { return [12, 28, 44].map(i => matrix.add(i).readFloat()); }
function publish(force = false) {
    const now = Date.now();
    if (force || now - lastPublish >= 1000) {
        lastPublish = now;
        send({event: 'stats', ...stats, enabled, radius: config.radius, pending: pending.size});
    }
}
function pause(reason) {
    stats.status = reason;
    stats.nearbyCorpses = stats.nearbyItems = stats.nearbyContainers = 0;
    stats.filtered = stats.unknown = 0;
    pending.clear();
    publish();
}
function foregroundGame() {
    const hwnd = foreground();
    if (hwnd.isNull()) return false;
    windowPid(hwnd, pidOut);
    return pidOut.readU32() === Process.id;
}
function allowed(full) { return profile.trigger_enabled_offsets.every(o => full.add(o).readU8() === 1); }
function identity(control, position) {
    return control + ':' + control.readPointer() + ':' + position.map(x => x.toFixed(2)).join(',');
}
function retry(key, now) {
    const old = retries.get(key);
    const failures = (old?.failures || 0) + 1;
    // A failed can-interact check is usually a transient simulation-frame
    // condition.  The old 2/4/8/16/30 second backoff made a nearby corpse look
    // permanently missed after it became interactable.
    retries.set(key, {failures, next: now + Math.min(5000, 250 * 2 ** Math.min(failures - 1, 4)), seen: now});
}
function targetSnapshot(full) {
    return {state: full.add(profile.body_state_offset).readS32(),
        counts: profile.body_items_offsets.map(o => size(full.add(o)))};
}
function category(desc) {
    try {
        const iface = desc.add(profile.description_context_offset);
        if (type(iface) !== '.?AVItemDescWithContext@@' || iface.add(8).readPointer().isNull()) return null;
        const getter = iface.readPointer().add(profile.description_category_slot * 8).readPointer();
        if (!getter.equals(gameDll.base.add(profile.description_category_rva))) return null;
        const value = native(getter, 'int', ['pointer'])(iface);
        return LootPolicy.group(value, profile.item_categories) ? value : null;
    } catch (_) { return null; }
}
function gameString(value, limit = 256) {
    const code = value.add(7).readU8();
    const length = code <= 7 ? 7 - code : limit;
    const chars = code <= 7 ? value : data(value);
    if (chars.isNull()) return null;
    let result = '';
    for (let i = 0; i < length; i++) {
        const c = chars.add(i).readU8();
        if (!c) return result;
        if (c < 33 || c > 126) return null;
        result += String.fromCharCode(c);
    }
    return code <= 7 ? result : null;
}
function itemIdentity(desc) {
    const value = category(desc), unknown = {category: value, id: null, name: null, subtype: null};
    if (value === null) return unknown;
    try {
        const definition = desc.add(profile.description_context_offset + 8).readPointer();
        const layout = profile.item_identity;
        if (!layout || definition.isNull()) return unknown;
        const table = definition.readPointer();
        const getter = table.add(layout.name_slot * 8).readPointer();
        if (!getter.equals(gameDll.base.add(layout.name_rva))) return unknown;
        const packed = definition.add(layout.name_offset).readU64();
        const cacheKey = `${definition}:${table}:${packed}:${value}`;
        if (itemCache.has(cacheKey)) return itemCache.get(cacheKey);
        const id = gameString(definition.add(layout.name_offset));
        const entry = profile.item_catalog?.items[id];
        if (!id || !entry || entry.category !== value || entry.group !== LootPolicy.group(value, profile.item_categories)) return unknown;
        const result = {category: value, id, name: entry.name, subtype: entry.subtype};
        if (itemCache.size > 10000) itemCache.clear();
        itemCache.set(cacheKey, result);
        return result;
    } catch (_) {}
    return unknown;
}
function accepts(item) {
    if (typeof item !== 'object' || item === null) item = {category: item};
    return LootPolicy.accepts(item.category, config.item_types, profile.item_categories, item, config.item_rules);
}
function bodySelection(full) {
    const v = full.add(profile.body_items_offsets[0]), count = size(v), base = data(v);
    if (count > 256) throw Error('Invalid corpse item count');
    const selected = [], categories = [], identities = [];
    for (let i = 0; i < count; i++) {
        const item = itemIdentity(base.add(i * profile.body_item_stride));
        categories.push(item.category); identities.push(item);
        if (accepts(item)) selected.push(i);
    }
    return {count, selected, categories, identities};
}
function interactionContext(player, distance) {
    const source = player.add(profile.player_context_offset);
    if (!source.readPointer().equals(player.add(0x1b0))) throw Error('Local player interaction context is unavailable');
    Memory.copy(context, source, 128);
    context.add(20).writeFloat(distance);
    context.add(24).writeU8(0x43);
    return context;
}
function containerInterface(full, complex = false) {
    const expected = complex ? profile.complex_container : profile.container;
    const table = full.readPointer();
    for (const [slot, rva] of [[196, expected.can_rva], [197, expected.execute_rva]]) {
        if (!table.add(slot * 8).readPointer().equals(gameDll.base.add(rva)))
            throw Error('Container interface does not match the supported build');
    }
}
function ordinaryEligible(full) {
    const state = full.add(profile.body_state_offset).readS32();
    // Linked sub-triggers can run scripted interactions; leave these to the player.
    return state === 1 && full.add(profile.container.linked_trigger_offset).readPointer().isNull();
}
function containerInfo(full, complex) {
    const control = full.add(16), getter = control.readPointer().add(67 * 8).readPointer();
    if (!getter.equals(gameDll.base.add(profile.control_simulating_rva))) return {verified: false};
    const simulating = !!native(getter, 'bool', ['pointer'])(control);
    if (!complex) return {verified: true, simulating, linked: !full.add(profile.container.linked_trigger_offset).readPointer().isNull()};
    const layout = profile.complex_container, obj = full.add(32);
    const base = vf(obj, 6, 'pointer', ['pointer'])(obj);
    if (!base.equals(obj)) return {verified: false};
    const key = obj.readPointer().toString();
    if (!containerLayouts.has(key)) {
        const rtti = vf(obj, 2, 'pointer', ['pointer'])(obj);
        const fields = native(exp('?GetFields@CRTTI@@QEBAAEBV?$vector@PEBVCRTTIField@@V?$heap_allocator@PEBVCRTTIField@@@vector_allocators@ttl@@$00@ttl@@XZ'), 'pointer', ['pointer'])(rtti);
        const getName = native(exp('?GetName@CRTTIField@@QEBAPEBDXZ'), 'pointer', ['pointer']);
        const wanted = new Map([['m_LockpickDifficulty', layout.lock_property_offset], ['m_ForceNoLoot', layout.no_loot_property_offset]]);
        if (size(fields) > 256) return {verified: false};
        for (let i = 0; i < size(fields); i++) {
            const field = data(fields).add(i * 8).readPointer(), name = getName(field).readCString();
            if (!wanted.has(name)) continue;
            if (field.add(0x50).readU32() !== wanted.get(name) || !field.add(0x60).readPointer().isNull()) return {verified: false};
            const stringField = name === 'm_LockpickDifficulty';
            const fieldType = stringField ? '.?AVCRTTIFieldStringNativeScript@@' : '.?AV?$CRTTIFieldTypedEngineNativeScript@_NV?$CRTTIFieldTyped@_N@@@@';
            if (type(field) !== fieldType) return {verified: false};
            wanted.delete(name);
        }
        if (wanted.size) return {verified: false};
        containerLayouts.add(key);
    }
    const lock = gameString(base.add(layout.lock_property_offset), 32);
    if (lock === null) return {verified: false};
    const noLoot = base.add(layout.no_loot_property_offset).readU8();
    return {verified: noLoot === 0 || noLoot === 1, simulating, noLoot: noLoot !== 0, lock: lock.toLowerCase()};
}
function openContainer(target, player, now) {
    if (now - lastOpen < 1000) return;
    const full = target.control.sub(16), name = type(target.control);
    if (name !== target.type || !allowed(full)) return;
    const info = containerInfo(full, target.isComplex), before = full.add(profile.body_state_offset).readS32();
    if (!LootPolicy.canOpenContainer(name, before, info, config)) return;
    containerInterface(full, target.isComplex);
    interactionContext(player, target.distance);
    if (!vf(full, 196, 'bool', ['pointer', 'int', 'pointer'])(full, 7, context)) { retry(target.key, now); return; }
    lastOpen = now; stats.attempts++;
    const ok = vf(full, 197, 'bool', ['pointer', 'int', 'pointer'])(full, 7, context);
    const after = full.add(profile.body_state_offset).readS32();
    const children = target.isComplex ? full.add(profile.complex_container.child_count_offset).readU32() : null;
    if (children !== null && children > 256) throw Error('Invalid container child count');
    const remaining = target.isComplex ? full.add(profile.complex_container.metadata_count_offset).readU32() : null;
    const contentReady = LootPolicy.openConfirmed(name, after, children, remaining);
    if (ok && (after === 1 || after === 5) && contentReady) {
        stats.opened++;
        retries.set(target.key, {failures: 0, next: now + 1500, seen: now});
        send({event: 'loot', kind: 'container_open', distance: target.distance, locked: !!info.lock, before, after, children, remaining});
    } else {
        stats.blocked++; retry(target.key, now);
        if (ok && !contentReady) send({event: 'container_wait', distance: target.distance,
            message: '箱柜内容生成尚未确认，未计为开启成功'});
    }
}
function corpse(target, player, now) {
    const full = target.control.sub(16), before = targetSnapshot(full);
    if (before.state !== 1 || !before.counts.some(n => n > 0) || !allowed(full)) return;
    const ordinary = target.isContainer;
    if (ordinary) {
        if (!ordinaryEligible(full)) return;
        containerInterface(full);
        interactionContext(player, target.distance);
        if (!vf(full, 196, 'bool', ['pointer', 'int', 'pointer'])(full, 1, context)) {
            stats.blocked++; retry(target.key, now); return;
        }
    }
    const init = full.readPointer().add(profile.body_init_slot * 8).readPointer();
    const iface = full.add(profile.body_loot_offset), take = iface.readPointer().add(32).readPointer();
    if (!init.equals(gameDll.base.add(ordinary ? profile.container.init_rva : profile.body_init_rva)) || !take.equals(gameDll.base.add(profile.body_take_rva)))
        throw Error('Loot interface does not match the supported build');
    native(init, 'void', ['pointer'])(full);
    const takeOne = native(gameDll.base.add(profile.body_take_one_rva), 'bool', ['pointer', 'uint', 'pointer', 'bool']);
    let drained = 0, blocked = false;
    // Re-read the selection after every successful call.  The game compacts
    // the vector immediately, so retaining an index across calls can skip an
    // item or address the wrong entry.
    for (; drained < bodyBatchLimit; drained++) {
        const current = targetSnapshot(full);
        const selection = bodySelection(full);
        if (!selection.selected.length) break;
        const index = selection.selected[selection.selected.length - 1];
        const item = selection.identities[index];
        stats.attempts++;
        const ok = takeOne(full, index, player, 0);
        const after = targetSnapshot(full);
        const changed = ok && after.counts.some((n, i) => n < current.counts[i]);
        if (!changed) { blocked = true; break; }
        if (!lootedBodies.has(target.key)) { stats[ordinary ? 'containers' : 'corpses']++; lootedBodies.add(target.key); }
        send({event: 'loot', kind: ordinary ? 'container' : 'corpse', distance: target.distance, ...item,
            group: LootPolicy.group(item.category, profile.item_categories), before: current, after});
    }
    if (drained) {
        retries.set(target.key, {failures: 0, next: now + 250, seen: now});
    } else if (blocked) {
        stats.blocked++;
        retry(target.key, now);
    }
}
function pickup(target, player, now) {
    const full = target.control.sub(16);
    if (!allowed(full)) return;
    const item = itemIdentity(full.add(target.type === '.?AVDroppedItem@@'
        ? profile.dropped_description_offset : profile.item_description_offset));
    if (!accepts(item)) return;
    const expected = target.type === '.?AVDroppedItem@@' ? profile.dropped_execute_rva : profile.item_execute_rva;
    const execute = full.readPointer().add(profile.item_execute_slot * 8).readPointer();
    if (!execute.equals(gameDll.base.add(expected))) throw Error('Pickup interface does not match the supported build');
    // Reuse the local player's live interaction context, never a context from an old scene.
    interactionContext(player, target.distance); // Ordinary pickup; swap/replace flag stays clear.
    const can = vf(full, 196, 'bool', ['pointer', 'int', 'pointer'])(full, 1, context);
    if (!can) { stats.blocked++; retry(target.key, now); return; }
    stats.attempts++;
    const ok = native(execute, 'bool', ['pointer', 'int', 'pointer'])(full, 1, context);
    // Confirm disappearance on a later fresh radius query, not merely a true return value.
    if (ok) {
        pending.set(target.key, {at: now, position: target.position, type: target.type, distance: target.distance,
            ...item, group: LootPolicy.group(item.category, profile.item_categories)});
        retries.set(target.key, {failures: 0, next: now + 3000, seen: now});
    } else { stats.blocked++; retry(target.key, now); }
}
function tick(game) {
    const now = Date.now();
    if (!enabled) { pause('disabled'); return; }
    if (now > leaseUntil) { enabled = false; pause('lease_expired'); return; }
    if (!foregroundGame()) { pause('background'); return; }
    if (!level || now - levelSeen > 1000 || now - levelStable < 1200) { pause('waiting_level'); return; }
    if (type(level) !== '.?AVLevelDI@@' || loading(level) || frozen(level)) { pause('paused'); return; }
    // Co-op uses this machine's local player, regardless of the session's player count.
    const entity = vf(game, profile.local_entity_slot, 'pointer', ['pointer'])(game);
    if (entity.isNull()) { pause('waiting_player'); return; }
    const control = getControl(entity);
    if (control.isNull() || type(control) !== '.?AVPlayerDI_PH@@') { pause('waiting_player'); return; }
    const player = control.sub(16);
    const position = xyz(vf(game, profile.player_transform_slot, 'pointer', ['pointer'])(game));
    if (!position.every(Number.isFinite)) throw Error('Invalid player position');
    position.forEach((v, i) => center.add(i * 4).writeFloat(v));
    vector.writePointer(storage); vector.add(8).writeU32(0); vector.add(12).writeU32(capacity);
    if (!query(level, vector, center, config.radius, ptr(0), 0, ptr(0))) throw Error('Radius query failed');
    const n = size(vector), objects = data(vector), candidates = [], present = new Set();
    stats.nearbyCorpses = stats.nearbyItems = stats.nearbyContainers = stats.filtered = stats.unknown = 0;
    stats.objects = n;
    for (let i = 0; i < n; i++) {
        const p = objects.add(i * 8).readPointer(), name = type(p);
        const isBody = name === '.?AVBodyContainer@@';
        const isComplex = name === '.?AVComplexContainer@@';
        const isContainer = name === '.?AVContainer@@' || isComplex;
        const isItem = name === '.?AVDroppedItem@@' || name === '.?AVContainerItem@@';
        if (!isBody && !isItem && !isContainer) continue;
        const pos = xyz(worldTransform(p));
        const distance = Math.hypot(...pos.map((v, j) => v - position[j]));
        const key = identity(p, pos);
        const freshBody = isBody && !knownBodies.has(key);
        if (isBody) knownBodies.add(key);
        present.add(key);
        if (!Number.isFinite(distance) || distance > config.radius || !allowed(p.sub(16))) continue;
        let wantOpen = false;
        if (isContainer) {
            const full = p.sub(16);
            const state = full.add(profile.body_state_offset).readS32();
            if (state === 2) {
                if (!config.open_containers || !config.containers || now - lastOpen < 1000) continue;
                if (!LootPolicy.canOpenContainer(name, state, containerInfo(full, isComplex), config)) continue;
                wantOpen = true;
            } else {
                if (isComplex || !ordinaryEligible(full) || !targetSnapshot(full).counts.some(x => x > 0)) continue;
            }
            stats.nearbyContainers++;
            if (!config.containers) continue;
            if (!wantOpen) {
                const selection = bodySelection(full);
                if (!selection.selected.length) {
                    stats.filtered++;
                    if (selection.identities.some(v => v.category === null || !v.id)) stats.unknown++;
                    continue;
                }
            }
        } else if (isBody) {
            const state = targetSnapshot(p.sub(16));
            if (state.state !== 1 || !state.counts.some(x => x > 0)) continue;
            stats.nearbyCorpses++;
            if (!config.corpses) continue;
            const selection = bodySelection(p.sub(16));
            if (!selection.selected.length) {
                stats.filtered++;
                if (selection.identities.some(v => v.category === null || !v.id)) stats.unknown++;
                continue;
            }
        } else {
            stats.nearbyItems++;
            if (!config.items) continue;
            const item = itemIdentity(p.sub(16).add(isItem && name === '.?AVDroppedItem@@'
                ? profile.dropped_description_offset : profile.item_description_offset));
            if (!accepts(item)) { stats.filtered++; if (item.category === null || !item.id) stats.unknown++; continue; }
        }
        const old = retries.get(key);
        if (old) old.seen = now;
        if (pending.has(key) || (old && now < old.next)) continue;
        candidates.push({control: p, position: pos, distance, key, type: name, isBody, isContainer, isComplex, wantOpen, freshBody});
    }
    for (const key of knownBodies) if (!present.has(key)) knownBodies.delete(key);
    for (const [key, entry] of pending) {
        if (!present.has(key)) {
            // Moving away cannot turn an unconfirmed attempt into a success.
            const stillInRange = Math.hypot(...entry.position.map((v, j) => v - position[j])) < config.radius - 0.1;
            if (stillInRange && now - entry.at < 2000 && accepts(entry)) {
                stats.items++;
                send({event: 'loot', kind: 'item', type: entry.type, distance: entry.distance,
                    category: entry.category, group: entry.group, id: entry.id, name: entry.name, subtype: entry.subtype});
            }
            pending.delete(key);
        } else if (now - entry.at > 2000) {
            pending.delete(key); stats.blocked++; retry(key, now);
        }
    }
    // Newly created corpses are usually the target the player is waiting for.
    // Keep nearest-first ordering within the fresh/old groups.
    candidates.sort((a, b) => Number(b.freshBody) - Number(a.freshBody) || a.distance - b.distance);
    // Bound work per simulation update; refresh the entire query on the next tick.
    for (const target of candidates.slice(0, 3)) {
        if (!enabled || Date.now() > leaseUntil) break;
        if (target.wantOpen) { openContainer(target, player, now); break; }
        else if (target.isBody || target.isContainer) corpse(target, player, now);
        else pickup(target, player, now);
    }
    for (const [key, entry] of retries) if (now - entry.seen > 60000) retries.delete(key);
    stats.scans++; stats.status = 'running'; stats.scanMs = Date.now() - now; publish();
}
rpc.exports = {
    modules() { return Process.enumerateModules().filter(m => ['engine_x64_rwdi.dll', 'gamedll_ph_x64_rwdi.dll'].includes(m.name.toLowerCase())).map(m => ({name: m.name, path: m.path, size: m.size})); },
    init(p) {
        if (profile) throw Error('Already initialized');
        profile = p;
        if (!p.item_categories || !Object.keys(p.item_categories).length) throw Error('Item category map is missing');
        config.item_types = Object.fromEntries(Object.keys(p.item_categories).map(k => [k, true]));
        engine = Process.getModuleByName('engine_x64_rwdi.dll');
        gameDll = Process.getModuleByName('gamedll_ph_x64_rwdi.dll');
        for (const m of [engine, gameDll]) if (m.size !== p.modules[m.name.toLowerCase()].size) throw Error('Module size mismatch');
        query = native(exp('?FindObjectsInRadius@ILevel@@QEAA_NPEAV?$vector@PEAVIControlObject@@V?$heap_allocator@PEAVIControlObject@@@vector_allocators@ttl@@$00@ttl@@AEBVvec3@@MPEBVCRTTI@@_NPEAH@Z'), 'bool', ['pointer', 'pointer', 'pointer', 'float', 'pointer', 'bool', 'pointer']);
        frozen = native(exp('?IsTimerFrozen@ILevel@@QEBA_NXZ'), 'bool', ['pointer']);
        loading = native(exp('?IsLoading@ILevel@@QEBA_NXZ'), 'bool', ['pointer']);
        worldTransform = native(exp('?GetWorldXform@IControlObject@@QEBAAEBVmtx34@@XZ'), 'pointer', ['pointer']);
        getControl = native(exp('?GetControlObject@IControlObject@@SAPEAV1@PEBVCEntity@cbs@@@Z'), 'pointer', ['pointer']);
        const user32 = Process.getModuleByName('user32.dll');
        foreground = native(user32.getExportByName('GetForegroundWindow'), 'pointer', []);
        windowPid = native(user32.getExportByName('GetWindowThreadProcessId'), 'uint', ['pointer', 'pointer']);
        listeners.push(Interceptor.attach(exp('?GetTimeWeatherSystem@ILevel@@QEBAPEAVCSystem@TimeWeather@@XZ'), {
            onEnter(a) {
                const now = Date.now();
                if (!level || !level.equals(a[0])) { level = a[0]; levelStable = now; pending.clear(); retries.clear(); lootedBodies.clear(); knownBodies.clear(); itemCache.clear(); }
                levelSeen = now;
            }
        }));
        const site = engine.base.add(profile.scheduler_return_rva);
        listeners.push(Interceptor.attach(exp('?GetGameTimeDelta@IGame@@QEBAMXZ'), {
            onEnter(a) { this.game = a[0]; this.run = this.returnAddress.equals(site); },
            onLeave() {
                if (!this.run || busy || Date.now() - lastTick < Math.max(300, Math.min(1500, stats.scanMs * 5))) return;
                lastTick = Date.now(); busy = true;
                try { tick(this.game); }
                catch (e) { enabled = false; pending.clear(); stats.status = 'error'; stats.error = String(e); publish(true); }
                finally { busy = false; }
            }
        }));
        stats.status = 'disabled'; publish(true); return true;
    },
    configure(c) {
        if (!profile) throw Error('Not initialized');
        if (!Number.isFinite(c.radius) || c.radius < 1 || c.radius > 500) throw Error('Radius must be 1–500 m');
        const keys = Object.keys(profile.item_categories);
        if (!c.item_types || keys.some(k => typeof c.item_types[k] !== 'boolean') || Object.keys(c.item_types).length !== keys.length)
            throw Error('Invalid item filters');
        const rules = c.item_rules || {items: {}, subtypes: {}};
        if (Object.keys(rules).some(k => !['items', 'subtypes'].includes(k))) throw Error('Invalid detailed filters');
        for (const kind of ['items', 'subtypes']) {
            if (!rules[kind] || typeof rules[kind] !== 'object' || Array.isArray(rules[kind]) ||
                Object.entries(rules[kind]).some(([k,v]) => typeof v !== 'boolean' || !Object.hasOwn(profile.item_catalog?.[kind] || {}, k)))
                throw Error('Unknown item or invalid detailed filter');
        }
        const anyAllowed = keys.some(k => c.item_types[k]) || Object.values(rules.items).includes(true) || Object.values(rules.subtypes).includes(true);
        if (c.enabled && (!(c.corpses || c.items || c.containers) || !anyAllowed)) throw Error('No allowed loot types selected');
        config = {radius: c.radius, corpses: !!c.corpses, items: !!c.items, containers: !!c.containers,
            open_containers: !!c.open_containers, locked_containers: !!c.locked_containers,
            item_types: {...c.item_types}, item_rules: {items: {...rules.items}, subtypes: {...rules.subtypes}}};
        retries.clear();
        enabled = !!c.enabled; leaseUntil = Date.now() + 5000;
        pending.clear(); knownBodies.clear(); stats.error = null; stats.status = enabled ? 'waiting' : 'disabled';
        publish(true); return {...stats, enabled};
    },
    heartbeat() { leaseUntil = Date.now() + 5000; return {...stats, enabled, pending: pending.size}; },
    stop() { enabled = false; pending.clear(); stats.status = 'disabled'; publish(true); return true; },
    shutdown() { enabled = false; pending.clear(); listeners.splice(0).forEach(h => h.detach()); return true; }
};
