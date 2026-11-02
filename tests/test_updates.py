import copy

import pytest

from beast_pick.updates import Release, executable_checksum, release_from_api, release_from_redirect, version_tuple


def metadata(tag="v0.3.0"):
    release = Release(tag)
    return dict(tag_name=tag, draft=False, prerelease=False, body="更新说明",
                html_url=release.page_url, assets=[dict(name=name, state="uploaded", size=123,
                    browser_download_url=release.asset_url(name)) for name in (release.executable_name, "SHA256SUMS.txt")])


def test_versions_are_compared_numerically_and_only_newer_versions_notify():
    assert Release("v0.10.0").newer_than("0.9.9")
    assert not Release("v0.3.0").newer_than("0.3.0")
    assert not Release("v0.2.1").newer_than("0.3.0")


@pytest.mark.parametrize("value", [None, 3, "latest", "v0.3.0-beta", "v0.03.0", "1.2", "v1.2.3/evil", "1.2.3\n"])
def test_reject_unsafe_or_nonstable_tags(value):
    with pytest.raises(ValueError):
        version_tuple(value)


def test_parse_stable_release_and_verified_asset_routes():
    release = release_from_api(metadata())
    assert release.tag == "v0.3.0"
    assert release.notes == "更新说明"
    assert release.size == 123


@pytest.mark.parametrize("change", [
    {"draft": True}, {"prerelease": True}, {"html_url": "https://example.com"},
    {"assets": []}, {"assets": "broken"},
])
def test_reject_nonrelease_or_incomplete_metadata(change):
    with pytest.raises(ValueError):
        release_from_api({**metadata(), **change})


@pytest.mark.parametrize("change", [
    {"state": "new"}, {"size": 0}, {"size": None}, {"size": True},
    {"browser_download_url": "https://example.com/BP.exe"},
])
def test_reject_unready_or_redirected_assets(change):
    payload = copy.deepcopy(metadata())
    payload["assets"][0].update(change)
    with pytest.raises(ValueError):
        release_from_api(payload)


def test_fallback_only_accepts_our_stable_release_page():
    release = release_from_redirect("https://github.com/hyhacct/beast-pick/releases/tag/v0.3.0")
    assert release.tag == "v0.3.0"
    for url in ("http://github.com/hyhacct/beast-pick/releases/tag/v0.3.0",
                "https://github.com/other/beast-pick/releases/tag/v0.3.0",
                "https://github.com.evil.test/hyhacct/beast-pick/releases/tag/v0.3.0",
                "https://github.com/hyhacct/beast-pick/releases/latest",
                release.page_url + "?download=evil"):
        with pytest.raises(ValueError):
            release_from_redirect(url)


def test_checksum_selects_only_the_exe_and_rejects_missing_or_ambiguous_values():
    digest = "a1" * 32
    assert executable_checksum(digest.upper() + "  BP.exe\n" + "b" * 64 + "  archive.zip\n") == digest
    for value in ("", "a" * 63 + "  BP.exe\n", digest + "  other.exe\n",
                  (digest + "  BP.exe\n") * 2):
        with pytest.raises(ValueError):
            executable_checksum(value)


def test_release_download_names_preserve_legacy_compatibility():
    for tag, filename in (("v0.2.1", "beast-pick.exe"), ("v0.3.0", "BP.exe"), ("v1.0.0", "BP.exe")):
        release = release_from_api(metadata(tag))
        assert release.executable_name == filename
        assert release.asset_url(filename).endswith('/' + filename)
        digest = "a1" * 32
        assert executable_checksum(digest + '  ' + filename + '\n', release.executable_name) == digest
