import json
import re

import pytest

from beast_pick import diy


def sample_weapon():
    return next(key for key, entry in diy.weapons().items()
                if entry['kind'] == 'melee' and diy.damage_table(key))


def sample_weapon_with_all_slots():
    return next(key for key in diy.weapons()
                if diy.damage_table(key) and diy.weapon_slots(key) == diy.slots())


def test_catalogue_is_complete():
    catalogue = diy.catalogue()
    assert catalogue['version'] >= 1
    assert len(diy.weapons()) > 2000
    assert {entry['kind'] for entry in diy.weapons().values()} == {'melee', 'firearm'}
    assert len(diy.mods()) > 50
    assert len(diy.affixes()) > 50
    assert [slot['key'] for slot in diy.slots()] == ['MOD_SLOT_TIP', 'MOD_SLOT_SHAFT',
                                                    'MOD_SLOT_GRIP', 'MOD_SLOT_CHARM']


def test_families_collapse_level_variants():
    families = diy.families()
    assert 100 < len(families) < len(diy.weapons())
    assert {family['id'] for family in families.values()} <= set(diy.weapons())
    covered = [variant for family in families.values() for variant in family['variants']]
    assert len(covered) == len(diy.weapons()) == len(set(covered))
    assert all(len(family['variants']) >= 1 for family in families.values())
    assert all(diy.weapon_slots(variant) == diy.weapon_slots(family['id'])
               for family in families.values() for variant in family['variants'])


def test_find_weapon_resolves_any_variant():
    family = next(value for value in diy.families().values() if len(value['variants']) > 1)
    for variant in family['variants']:
        assert diy.find_weapon(variant)['id'] == family['id']
    assert diy.find_weapon('not_a_weapon') is None


def test_families_keep_distinct_definitions_apart():
    """A repeated name is only merged when the damage table, quality and slots match."""
    by_name: dict[tuple, list[dict]] = {}
    for family in diy.families().values():
        by_name.setdefault((family['n'], family['kind'], family['sub']), []).append(family)
    duplicates = [group for group in by_name.values() if len(group) > 1]
    assert len(duplicates) <= 10
    for group in duplicates:
        signatures = {(family.get('tbl'), family.get('q'),
                       tuple(slot['key'] for slot in diy.weapon_slots(family['id'])))
                      for family in group}
        assert len(signatures) == len(group)


def test_catalogue_has_no_leftover_markup():
    """Labels come from the game's localisation file and can embed renderer tags."""
    labels = [entry['n'] for entry in diy.weapons().values()]
    labels += [entry['n'] for entry in diy.mods().values()]
    labels += [entry['n'] for entry in diy.affixes().values()]
    leftovers = [label for label in labels if '%' in label and re.search(r'%[A-Za-z_]', label)]
    assert not leftovers
    assert not [label for label in labels if '&' in label or '\\n' in label]
    assert not [label for label in labels if not label.strip()]


def test_every_affix_and_mod_round_trips_through_a_plan():
    weapon = sample_weapon_with_all_slots()
    plan = diy.validate_plan({'weapon': weapon, 'quality': 0, 'level': 0, 'stats': {},
                              'mods': {}, 'affixes': list(diy.affixes())[:diy.MAX_AFFIXES]})
    assert len(plan['affixes']) == diy.MAX_AFFIXES
    for mod_id, entry in diy.mods().items():
        for slot in entry['slots']:
            plan = diy.validate_plan({'weapon': weapon, 'mods': {slot: mod_id}})
            assert plan['mods'] == {slot: mod_id}


def test_unknown_weapon_rejected():
    with pytest.raises(ValueError, match='未知武器'):
        diy.validate_plan({'weapon': 'not_a_weapon', 'quality': 0, 'level': 0})


@pytest.mark.parametrize('quality', [-1, 7, 2.5, True, 'red'])
def test_quality_must_be_a_known_index(quality):
    with pytest.raises(ValueError, match='品质'):
        diy.validate_plan({'weapon': sample_weapon(), 'quality': quality, 'level': 0})


def test_level_must_fit_the_damage_table():
    weapon = sample_weapon()
    table = diy.damage_table(weapon)
    diy.validate_plan({'weapon': weapon, 'level': len(table) - 1})
    with pytest.raises(ValueError, match='档位'):
        diy.validate_plan({'weapon': weapon, 'level': len(table)})
    with pytest.raises(ValueError, match='档位'):
        diy.validate_plan({'weapon': weapon, 'level': -1})


def test_stats_are_range_checked_and_normalised():
    weapon = sample_weapon()
    plan = diy.validate_plan({'weapon': weapon, 'level': 0, 'stats': {'CriticalProb': 0.5, 'DamageSize': 3}})
    assert plan['stats'] == {'CriticalProb': 0.5, 'DamageSize': 3.0}
    with pytest.raises(ValueError, match='暴击率'):
        diy.validate_plan({'weapon': weapon, 'level': 0, 'stats': {'CriticalProb': 2}})
    with pytest.raises(ValueError, match='不支持'):
        diy.validate_plan({'weapon': weapon, 'level': 0, 'stats': {'Damage': 999}})
    with pytest.raises(ValueError, match='数字'):
        diy.validate_plan({'weapon': weapon, 'level': 0, 'stats': {'CriticalProb': 'high'}})


def test_mod_must_fit_its_slot():
    weapon = sample_weapon_with_all_slots()
    grip_only = next((key for key, entry in diy.mods().items()
                      if entry['slots'] == ['MOD_SLOT_GRIP']), None)
    if grip_only is None:
        pytest.skip('no grip-only attachment in this catalogue')
    with pytest.raises(ValueError, match='不能安装到「刀尖」'):
        diy.validate_plan({'weapon': weapon, 'level': 0, 'mods': {'MOD_SLOT_TIP': grip_only}})


def test_affix_limit_and_duplicates():
    weapon = sample_weapon()
    keys = list(diy.affixes())
    plan = diy.validate_plan({'weapon': weapon, 'level': 0, 'affixes': keys[:3] + keys[:3]})
    assert plan['affixes'] == keys[:3]
    with pytest.raises(ValueError, match='最多选择'):
        diy.validate_plan({'weapon': weapon, 'level': 0, 'affixes': keys[:diy.MAX_AFFIXES + 1]})
    with pytest.raises(ValueError, match='未知词条'):
        diy.validate_plan({'weapon': weapon, 'level': 0, 'affixes': ['Nope']})


def test_preview_computes_damage_with_attachment_bonus():
    weapon = sample_weapon_with_all_slots()
    plain = diy.preview({'weapon': weapon, 'level': 0})
    assert plain['damage'] is not None
    assert plain['damage_total'] == pytest.approx(plain['damage'])
    boosted_mod = next((key for key, entry in diy.mods().items()
                        if any(effect['key'] == 'CraftingEffect_IncreasedDamageMul' and effect['value']
                               for effect in entry['effects'])), None)
    if boosted_mod is None:
        pytest.skip('no damage attachment in this catalogue')
    slot = diy.mods()[boosted_mod]['slots'][0]
    boosted = diy.preview({'weapon': weapon, 'level': 0, 'mods': {slot: boosted_mod}})
    assert boosted['damage_bonus'] > 0
    assert boosted['damage_total'] > plain['damage_total']


def test_export_plan_is_json_round_trip():
    weapon = sample_weapon()
    text = diy.export_plan({'weapon': weapon, 'quality': 3, 'level': 1,
                            'stats': {'CriticalProb': 0.25}, 'affixes': []})
    payload = json.loads(text)
    assert payload['weapon'] == weapon
    assert payload['stats'] == {'CriticalProb': 0.25}
    assert payload['tool']


def test_damage_tables_hold_real_numbers():
    """Every stored table entry must be a positive number, not a leftover string."""
    for name, table in diy.tiers().items():
        assert table, name
        for value in table:
            assert isinstance(value, (int, float)) and not isinstance(value, bool), name
            assert value >= 0, name


def test_health_scaling_weapons_are_not_flattened_to_a_number():
    """`Cut("1%-101% of MaxHealth")` used to be parsed as 1 damage.

    Those tables belong to scripted enemies and quest props, so no player weapon
    may point at one; if that ever changes the preview must say so instead of
    showing a fake damage number.
    """
    formulas = diy.special()
    assert formulas
    for table, text in formulas.items():
        assert '%' in text or 'MaxHealth' in text, (table, text)
        assert table not in diy.tiers(), table
    referenced = {entry.get('tbl') for entry in diy.weapons().values()} & set(formulas)
    assert not referenced, sorted(referenced)
    assert diy.damage_formula(sample_weapon()) is None
    assert diy.preview({'weapon': sample_weapon(), 'level': 0})['damage'] is not None


def test_calibrated_profile_lists_writable_stats():
    """The profile must stay in sync with the stats the page can offer."""
    writable = diy.writable_stats()
    assert writable, 'profile/current.json lost the calibrated diy block'
    assert set(writable) <= set(diy.STAT_LABELS)
    for key, field in writable.items():
        assert field['kind'] == 'float', key
        # Stat blocks sit deep inside the item object but well below one block stride.
        assert 0 < field['offset'] < 0x498, key
    assert {'DamageRange', 'CriticalCondition', 'StaminaUsage'} <= set(writable)


def test_unwritable_stats_are_still_previewable():
    """Read-only stats (quality-side fields) must not block a plan or its preview."""
    weapon = sample_weapon()
    unsupported = sorted(set(diy.STAT_LABELS) - set(diy.writable_stats()))
    assert unsupported, 'expected some stats to be read-only on this build'
    plan = diy.validate_plan({'weapon': weapon, 'level': 0,
                              'stats': {unsupported[0]: diy.STAT_LIMITS[unsupported[0]][0]}})
    assert plan['stats']
    assert diy.preview(plan)['damage'] is not None


def test_writable_layout_names_its_description_class():
    """The measured offsets only fit one description class; say which one."""
    assert diy.diy_layout().get('desc_type') == '.?AVItemDescMelee@@'
    assert diy.writable_kind() == 'melee'


def test_only_the_calibrated_kind_is_writable():
    assert diy.writable_for({'kind': 'melee'}) is True
    assert diy.writable_for({'kind': 'firearm'}) is False
    assert diy.writable_for(None) is True


def test_firearm_page_offers_no_writes_and_says_why(qapp):
    """Selecting a firearm must not promise melee offsets, and must answer a click."""
    from beast_pick.diy_page import DiyPage

    page = DiyPage()
    firearm = next(entry['id'] for entry in diy.families().values() if entry['kind'] == 'firearm')
    assert page.select_weapon(firearm)
    assert all(not check.isEnabled() for check, _ in page.stat_boxes.values())
    assert all(not box.isEnabled() for _, box in page.stat_boxes.values())
    assert '近战' in page.stats_hint.text()

    blocked = []
    page.blocked.connect(blocked.append)
    page.apply()
    assert blocked, 'a click that writes nothing must report back'
    assert '未标定' in blocked[0]


def test_melee_page_offers_the_calibrated_stats(qapp):
    from beast_pick.diy_page import DiyPage

    page = DiyPage()
    melee = next(entry['id'] for entry in diy.families().values() if entry['kind'] == 'melee')
    assert page.select_weapon(melee)
    writable = diy.writable_stats()
    for key, (check, box) in page.stat_boxes.items():
        assert check.isEnabled() is (key in writable), key
        assert box.isEnabled() is (key in writable), key
    assert '不写入' in page.stats_hint.text()


def test_empty_selection_reports_instead_of_silence(qapp):
    from beast_pick.diy_page import DiyPage

    page = DiyPage()
    melee = next(entry['id'] for entry in diy.families().values() if entry['kind'] == 'melee')
    page.select_weapon(melee)
    blocked = []
    page.blocked.connect(blocked.append)
    page.apply()
    assert blocked and '勾选' in blocked[0]


def test_prepare_generation_resolves_selected_melee_tier():
    weapon = 'dlc_ft_wpn_1hs_mach_b_baron_r1'
    plan = diy.prepare_generation({
        'weapon': weapon,
        'quality': diy.weapons()[weapon].get('q') or 0,
        'level': 7,
        'stats': {'DamageRange': 2.5},
    })
    assert plan['kind'] == 'melee'
    assert plan['item_id'] == 'dlc_ft_wpn_1hs_mach_b_baron_r8'
    assert plan['stats'] == {'DamageRange': 2.5}


def test_prepare_generation_rejects_unmeasured_fields_and_non_melee():
    melee = 'dlc_ft_wpn_1hs_mach_b_baron_r1'
    base = {'weapon': melee, 'stats': {'DamageRange': 2.5}}
    with pytest.raises(ValueError, match='未标定这些属性'):
        diy.prepare_generation({**base, 'stats': {'CriticalProb': 0.5}})
    with pytest.raises(ValueError, match='配件与词条'):
        diy.prepare_generation({**base, 'mods': {'MOD_SLOT_CHARM': 'charm_Final_Boss_ft'}})
    firearm = next(key for key, entry in diy.weapons().items() if entry['kind'] == 'firearm')
    with pytest.raises(ValueError, match='只支持已标定的近战'):
        diy.prepare_generation({'weapon': firearm, 'stats': {'DamageRange': 2.5}})
