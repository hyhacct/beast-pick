from types import SimpleNamespace

import pytest

from beast_pick.backend import Client, load_profile


def make_client():
    calls = []
    exports = SimpleNamespace(configure=lambda cfg: calls.append(cfg) or cfg)
    client = Client()
    client.session = object()
    client.script = SimpleNamespace(exports_sync=exports)
    client.game_key = 'dl2'
    return client, calls


def test_dl2_profile_is_build_specific():
    p = load_profile('dl2')
    assert p['scheduler_return_rva'] == 0xb16cb2
    assert p['execute_rva'] == 0x198f8c0
    assert p['local_entity_slot'] == 154
    assert all(len(module['sha256']) == 64 for module in p['modules'].values())


def test_dl2_routes_corpse_container_and_explicit_box_options():
    client, calls = make_client()
    client.configure(radius=8, corpses=True, items=True, enabled=True, containers=True,
                     open_containers=True, locked_containers=True)
    assert calls[0]['items'] is True
    assert calls[0]['corpses'] is True and calls[0]['containers'] is True
    assert calls[0]['open_containers'] is True and calls[0]['locked_containers'] is True


def test_dl2_rejects_unsupported_melee_but_allows_corpse_only():
    client, calls = make_client()
    with pytest.raises(RuntimeError, match='千刀'):
        client.configure(radius=8, corpses=False, items=True, enabled=True, rapid_melee=True)
    client.configure(radius=8, corpses=True, items=False, enabled=True)
    assert calls[0]['corpses'] is True and calls[0]['items'] is False


def test_dl2_blocks_diy_before_calling_native_agent():
    client, _ = make_client()
    with pytest.raises(RuntimeError, match='DIY'):
        client.diy_apply({})
    with pytest.raises(RuntimeError, match='DIY'):
        client.diy_generate({})