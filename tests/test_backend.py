import hashlib
import math

import pytest

from beast_pick.backend import Client, checked_settings, validate_modules


def test_reject_changed_build_even_when_size_matches(tmp_path):
    dll = tmp_path / "game.dll"
    dll.write_bytes(b"original")
    profile = {"modules": {"game.dll": {"size": 123, "sha256": hashlib.sha256(b"original").hexdigest()}}}
    modules = [{"name": "GAME.DLL", "size": 123, "path": str(dll)}]
    validate_modules(profile, modules)
    dll.write_bytes(b"modified")
    with pytest.raises(RuntimeError, match="校验不匹配"):
        validate_modules(profile, modules)


def test_reject_missing_or_wrong_sized_module(tmp_path):
    profile = {"modules": {"game.dll": {"size": 123, "sha256": "unused"}}}
    with pytest.raises(RuntimeError, match="尚未加载"):
        validate_modules(profile, [])
    with pytest.raises(RuntimeError, match="构建不匹配"):
        validate_modules(profile, [{"name": "game.dll", "size": 1, "path": "unreadable"}])


@pytest.mark.parametrize("radius", [-1, 0, 500.1, math.nan, math.inf])
def test_reject_invalid_range(radius):
    with pytest.raises(ValueError):
        checked_settings(radius, True, True, True)


def test_cannot_enable_without_a_target_kind():
    with pytest.raises(ValueError, match="至少选择"):
        checked_settings(8, False, False, True)
    assert checked_settings(8, False, False, False)["enabled"] is False


def test_expanded_radius_supports_500_meters():
    assert checked_settings(500, True, True, True)["radius"] == 500.0


def test_containers_can_run_without_other_target_kinds():
    assert checked_settings(8, False, False, True, containers=True)["containers"] is True
    assert checked_settings(8, True, True, True)["containers"] is False


def test_filters_migrate_old_settings_and_preserve_exclusions():
    assert all(checked_settings(8, True, True, False)["item_types"].values())
    settings = checked_settings(500, True, True, True, {"weapons": False})
    assert settings["item_types"]["weapons"] is False
    assert settings["item_types"]["materials"] is True


def test_empty_selection_can_only_be_saved_while_stopped():
    from beast_pick.categories import ITEM_TYPES
    selection = dict.fromkeys(ITEM_TYPES, False)
    with pytest.raises(ValueError, match="至少选择一种"):
        checked_settings(8, True, True, True, selection)
    assert not any(checked_settings(8, True, True, False, selection)["item_types"].values())


@pytest.mark.parametrize("selection", [{"weapons": "false"}, {"weapon": False}, [], {"weapons": 0}])
def test_reject_malformed_selection(selection):
    with pytest.raises(ValueError, match="筛选"):
        checked_settings(8, True, True, True, selection)


def test_close_detaches_even_if_shutdown_fails():
    calls = []
    class Exports:
        def shutdown(self):
            calls.append("shutdown")
            raise RuntimeError("lost script")
    class Script:
        exports_sync = Exports()
        def unload(self): calls.append("unload")
    class Session:
        def detach(self): calls.append("detach")
    client = Client()
    client.script = Script()
    client.session = Session()
    with pytest.raises(RuntimeError): client.close()
    assert calls == ["shutdown", "unload", "detach"]
    assert not client.connected


def test_close_stops_hooks_and_keeps_idle_runtime_before_detach():
    calls = []
    class Exports:
        def shutdown(self): calls.append("shutdown")
    class Script:
        exports_sync = Exports()
        def eternalize(self): calls.append("eternalize")
        def unload(self): raise AssertionError("Must not unload a stopped runtime")
    class Session:
        def detach(self): calls.append("detach")
    client = Client()
    client.script, client.session = Script(), Session()
    client.close()
    assert calls == ["shutdown", "eternalize", "detach"]
    assert not client.connected


def test_exact_rules_are_validated_and_independent_of_caller():
    from beast_pick.catalog import checked_rules, load_catalog
    source = {"items": {"Water_FT": False}, "subtypes": {"throwables:ItemType_Grenade": True}}
    rules = checked_rules(source)
    source['items']['Water_FT'] = True
    assert rules['items']['Water_FT'] is False
    assert load_catalog()['items']['Water_FT']['name'] == '饮料'
    for value in ({'items': {'made_up': True}}, {'items': {'Water_FT': 1}}, {'weapons': {}}, []):
        with pytest.raises(ValueError, match='筛选'):
            checked_rules(value)


def test_individual_allow_can_override_disabled_broad_groups():
    from beast_pick.categories import ITEM_TYPES
    settings = checked_settings(8, True, True, True, dict.fromkeys(ITEM_TYPES, False),
                                item_rules={'items': {'Water_FT': True}})
    assert settings['enabled']
    assert settings['item_rules']['items']['Water_FT'] is True


def test_catalog_preserves_fields_across_duplicate_item_declarations():
    from beast_pick.catalog import load_catalog
    item = load_catalog()['items']['dlc_ft_firearm_shotgun_b_military_r15']
    assert item['name'] == '军用霰弹枪'
    assert item['subtype'] == 'weapons:ItemType_Shotgun'


def test_opening_and_lock_bypass_are_separate_and_default_off():
    settings = checked_settings(8, True, True, False)
    assert settings['open_containers'] is False and settings['locked_containers'] is False
    settings = checked_settings(8, False, False, True, containers=True, open_containers=True, locked_containers=True)
    assert settings['open_containers'] and settings['locked_containers']
