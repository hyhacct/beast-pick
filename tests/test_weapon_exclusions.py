from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt

from beast_pick.backend import Client, PROCESS, DL2_PROCESS, select_game_process
from beast_pick.weapon_catalog import checked_exclusions, weapon_groups, weapon_items
from beast_pick.weapon_exclusions_dialog import WeaponExclusionsDialog


def client_for(game):
    calls = []
    c = Client()
    c.game_key = game
    c.session = object()
    c.script = SimpleNamespace(exports_sync=SimpleNamespace(configure=lambda value: calls.append(value) or value))
    return c, calls


def test_game_selection_is_explicit_when_both_are_running():
    processes = [SimpleNamespace(name=PROCESS, pid=1), SimpleNamespace(name=DL2_PROCESS, pid=2)]
    with pytest.raises(RuntimeError, match='选择游戏'):
        select_game_process(processes, 'auto')
    assert select_game_process(processes, 'beast')[0].pid == 1
    assert select_game_process(processes, 'dl2')[0].pid == 2


def test_beast_pitchfork_group_includes_throwable_variants():
    rows = [(group, ids) for name, group, ids in weapon_groups('beast') if name == '草叉']
    assert rows and all(group == 'throwables' for group, _ in rows)
    ids = [identity for _, group in rows for identity in group]
    assert len(ids) == 3 and all('pitchfork' in identity.lower() for identity in ids)
    client, calls = client_for('beast')
    client.configure(radius=8, corpses=True, items=True, enabled=True, excluded_ids=ids)
    assert all(calls[0]['item_rules']['items'][identity] is False for identity in ids)
    assert calls[0]['item_types']['weapons'] is True


def test_dl2_selection_is_separate_and_covers_all_hammer_variants():
    items = weapon_items('dl2')
    identity = 'wpn_1hb_ham_a_fpp_r17_renegades'
    assert items[identity]['name'] == '技工锤头'
    groups = [ids for name, _, ids in weapon_groups('dl2') if name == '技工锤头']
    assert groups and identity in groups[0] and len(groups[0]) > 1
    client, calls = client_for('dl2')
    client.configure(radius=8, corpses=False, items=True, enabled=True, excluded_ids=groups[0])
    assert identity in calls[0]['excluded_ids']
    with pytest.raises(ValueError, match='当前游戏'):
        checked_exclusions('dl2', ['dlc_ft_Thrown_Pitchfork_wt1'])


def test_dialog_filters_by_name_and_selection_includes_group(qapp):
    dialog = WeaponExclusionsDialog('beast', [])
    dialog.filter_items('草叉')
    visible = [dialog.items.item(i) for i in range(dialog.items.count()) if not dialog.items.item(i).isHidden()]
    assert visible
    target = next(item for item in visible if item.text().startswith('草叉 '))
    ids = target.data(Qt.ItemDataRole.UserRole)
    target.setCheckState(Qt.CheckState.Checked)
    assert len(ids) == 3 and set(ids).issubset(dialog.exclusions)
    target.setCheckState(Qt.CheckState.Unchecked)
    assert not set(ids).intersection(dialog.exclusions)
    dialog.close()

def test_window_game_specific_exclusions_are_persisted(qapp, tmp_path, monkeypatch):
    import json
    from PySide6.QtCore import QEventLoop, QTimer
    from shiboken6 import delete
    from beast_pick import app as ui
    monkeypatch.setattr(ui, 'BASE', tmp_path)
    window = ui.Window(check_updates=False, update_prompts=False)
    loop = QEventLoop()
    try:
        grass = next(ids for name, _, ids in weapon_groups('beast') if name == '草叉')
        hammer = next(ids for name, _, ids in weapon_groups('dl2') if name == '技工锤头')
        window.excluded_by_game = {'beast': grass, 'dl2': hammer}
        window.game_choice.setCurrentIndex(window.game_choice.findData('beast'))
        assert window.settings()['excluded_ids'] == grass
        window.game_choice.setCurrentIndex(window.game_choice.findData('dl2'))
        assert window.settings()['excluded_ids'] == hammer
        window.flush_settings()
        saved = json.loads((tmp_path / 'settings.json').read_text(encoding='utf8'))
        assert saved['game_preference'] == 'dl2'
        assert saved['excluded_weapons'] == {'beast': grass, 'dl2': hammer}
    finally:
        window.thread.finished.connect(loop.quit)
        QTimer.singleShot(0, window.close)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        assert window.thread.wait(5000)
        delete(window)
