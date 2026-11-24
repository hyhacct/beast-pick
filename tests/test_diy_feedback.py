from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from beast_pick.app import Window
from beast_pick import diy
from beast_pick.diy_page import DiyPage


def test_diy_page_states_that_writes_do_not_add_items(qapp):
    page = DiyPage()

    assert not page.write_scope.isHidden()
    assert "不会新增背包物品" in page.write_scope.text()
    assert "不会新增背包物品" in page.apply_button.toolTip()
    assert page.generate_button.text() == "生成到背包"


def test_generate_button_emits_prepared_plan_without_equipping(qapp):
    page = DiyPage()
    weapon = "dlc_ft_wpn_1hs_mach_b_baron_r1"
    assert page.select_weapon(weapon)
    page.stat_boxes["DamageRange"][0].setChecked(True)
    generated = []
    page.generate_requested.connect(generated.append)

    page.generate()

    assert len(generated) == 1
    assert generated[0]["kind"] == "melee"
    assert generated[0]["item_id"].endswith("_r8")
    assert generated[0]["stats"]["DamageRange"] == page.stat_boxes["DamageRange"][1].value()


@pytest.mark.parametrize(
    ("result", "ok", "message"),
    [
        ({}, False, "没有手持武器属性被更新。"),
        ({"applied": []}, False, "没有手持武器属性被更新。"),
        ({"applied": ["damage_range"]}, True, "手持武器属性已更新。"),
        ({"applied": [], "message": "方案没有可写入的字段"}, False, "方案没有可写入的字段"),
    ],
)
def test_diy_apply_feedback_without_game(result, ok, message):
    ui = SimpleNamespace(diy_ready=True, diy_page=Mock(), on_diy_notice=Mock())

    Window.on_diy_applied(ui, result)

    ui.on_diy_notice.assert_called_once_with(message)
    ui.diy_page.show_result.assert_called_once_with(message, ok=ok)


@pytest.mark.parametrize(('weapon', 'slots'), [
    ('dlc_ft_wpn_1hs_mach_16_r1', ['刀尖', '刀柄', '握把', '挂饰']),
    ('dlc_ft_wpn_1hs_mach_b_military_r1', ['刀尖', '刀柄', '挂饰']),
    ('dlc_ft_wpn_1hs_knife_n_r1', ['握把', '挂饰']),
    ('dlc_ft_wpn_1hs_mach_b_baron_r1', ['挂饰']),
    ('dlc_ft_wpn_1hb_mace_m_r1', []),
    ('dlc_ft_wpn_lbow_c_r1', []),
])
def test_source_weapon_slot_layouts(weapon, slots):
    assert [slot['name'] for slot in diy.weapon_slots(weapon)] == slots


def test_matching_attachment_is_rejected_when_weapon_lacks_its_slot():
    weapon = 'dlc_ft_wpn_1hb_mace_m_r1'
    with pytest.raises(ValueError, match='该武器不支持「挂饰」'):
        diy.validate_plan({'weapon': weapon, 'mods': {'MOD_SLOT_CHARM': 'charm_Final_Boss_ft'}})


def test_charm_details_use_player_facing_quality_and_stats():
    charm_ids = [key for key, mod in diy.mods().items() if 'MOD_SLOT_CHARM' in mod['slots']]
    assert charm_ids
    assert all(diy.mods()[key]['color'] and diy.mods()[key]['uistats'] for key in charm_ids)
    assert diy.mod_details('charm_Final_Boss_ft').splitlines() == [
        '品质：紫色', '击杀后体力值恢复：+5%',
    ]


def test_diy_page_switches_slots_and_clears_stale_attachments(qapp):
    page = DiyPage()
    slots = page.mods_form
    charm = 'MOD_SLOT_CHARM'
    assert not hasattr(page, 'read_button')
    assert page.select_weapon('dlc_ft_wpn_1hs_mach_b_baron_r1')
    assert {key for key, row in page.mod_rows.items() if slots.isRowVisible(row)} == {charm}
    assert not slots.isRowVisible(page.no_mod_slots)

    combo = page.mod_boxes[charm]
    choice = combo.findData('charm_Final_Boss_ft')
    assert choice > 0 and '紫色' in combo.itemText(choice)
    combo.setCurrentIndex(choice)
    assert not page.mod_descriptions[charm].isHidden()
    assert '+5%' in page.mod_descriptions[charm].text()
    assert page.plan()['mods'] == {charm: 'charm_Final_Boss_ft'}

    assert page.select_weapon('dlc_ft_wpn_1hb_mace_m_r1')
    assert all(not slots.isRowVisible(row) for row in page.mod_rows.values())
    assert slots.isRowVisible(page.no_mod_slots)
    assert page.mod_descriptions[charm].isHidden()
    assert not page.plan()['mods']

    assert page.select_weapon('dlc_ft_wpn_1hs_knife_n_r1')
    assert {key for key, row in page.mod_rows.items() if slots.isRowVisible(row)} == {charm, 'MOD_SLOT_GRIP'}
    assert combo.currentIndex() == 0
