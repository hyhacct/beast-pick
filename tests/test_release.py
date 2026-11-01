import pytest

from tools import release


@pytest.mark.parametrize('value', ['v1.2.3', '01.2.3', '1.2', '1.2.3-rc.1', '1.2.65536'])
def test_reject_versions_that_cannot_be_released_as_windows_versions(value):
    with pytest.raises(ValueError):
        release.parse_version(value)


def test_release_notes_require_exactly_one_completed_section():
    text = '## [1.2.3] - 2026-11-01\n\n- Fixed pickup.\n\n## [1.2.2] - 2026-10-31\n- Previous.\n'
    assert release.release_notes('1.2.3', text) == '- Fixed pickup.\n'
    for invalid in (text + text, text.replace('Fixed pickup.', '待补充'), text.replace('2026-11-01', '2026-13-01')):
        with pytest.raises(ValueError):
            release.release_notes('1.2.3', invalid)


def test_tag_mismatch_is_rejected_before_publication():
    current = release.current_version()
    assert release.check(f'v{current}') == current
    with pytest.raises(ValueError, match='不一致'):
        release.check('v999.0.0')


def test_bump_preserves_history_and_requires_completed_notes(tmp_path, monkeypatch):
    source = tmp_path / '__init__.py'
    source.write_text("__version__ = '1.2.3'\n", encoding='utf-8')
    changelog = tmp_path / 'CHANGELOG.md'
    original = '# History\n\n## [1.2.3] - 2026-11-01\n\n- Existing change.\n'
    changelog.write_text(original, encoding='utf-8')
    monkeypatch.setattr(release, 'VERSION_FILE', source)
    monkeypatch.setattr(release, 'CHANGELOG', changelog)
    release.bump('1.2.4')
    assert release.current_version() == '1.2.4'
    updated = changelog.read_text(encoding='utf-8')
    assert '## [1.2.3] - 2026-11-01\n\n- Existing change.' in updated
    with pytest.raises(ValueError, match='填写'):
        release.check('v1.2.4')
    with pytest.raises(ValueError, match='高于'):
        release.bump('1.2.3')
    assert source.read_text(encoding='utf-8') == "__version__ = '1.2.4'\n"
