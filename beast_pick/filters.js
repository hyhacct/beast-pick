'use strict';

// Pure selection policy; shared by the injected agent and the offline checks.
globalThis.LootPolicy = {
    group(category, groups) {
        if (!Number.isInteger(category) || category < 0) return null;
        return Object.keys(groups).find(key => groups[key].includes(category)) || null;
    },
    allSelected(selection) {
        return Object.values(selection).length > 0 && Object.values(selection).every(v => v === true);
    },
    canOpenContainer(name, state, info, options) {
        if (!options.containers || !options.open_containers || state !== 2 || !info?.verified || info.simulating !== true) return false;
        if (name === '.?AVContainer@@') return info.linked === false;
        if (name !== '.?AVComplexContainer@@' || info.noLoot !== false) return false;
        if (!['', 'easy', 'medium', 'hard', 'impossible'].includes(info.lock)) return false;
        return info.lock === '' || options.locked_containers === true;
    },
    openConfirmed(name, state, children, remaining) {
        if (state !== 1 && state !== 5) return false;
        if (name === '.?AVContainer@@') return true;
        if (name !== '.?AVComplexContainer@@' || !Number.isInteger(children) || children < 0 || children > 256) return false;
        return children > 0 || (state === 5 && remaining === 0);
    },
    accepts(category, selection, groups, metadata = null, rules = {items: {}, subtypes: {}}) {
        const key = this.group(category, groups);
        if (!key) return false;
        const detailed = Object.keys(rules.items).length > 0 || Object.keys(rules.subtypes).length > 0;
        // An unreadable identity must never bypass a per-item exclusion.
        if (detailed && (!metadata?.id || !metadata?.subtype)) return false;
        // Bundles/evolving items may grant hidden contents. With any exclusions,
        // leave them for manual pickup rather than accidentally grant a weapon.
        if ([17, 19, 27, 28].includes(category) && (!this.allSelected(selection) ||
            Object.values(rules.items).includes(false) || Object.values(rules.subtypes).includes(false))) return false;
        if (metadata && Object.hasOwn(rules.items, metadata.id)) return rules.items[metadata.id];
        if (metadata && Object.hasOwn(rules.subtypes, metadata.subtype)) return rules.subtypes[metadata.subtype];
        return selection[key] === true;
    },
};
