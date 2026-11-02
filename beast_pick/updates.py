"""Release metadata and checksums for this project's stable GitHub releases."""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

REPOSITORY = "hyhacct/beast-pick"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_URL = f"{RELEASES_URL}/latest"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_DOWNLOAD = 512 * 1024 * 1024


def version_tuple(version: str) -> tuple[int, int, int]:
    if not isinstance(version, str) or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("无法识别正式版本号")
    return tuple(map(int, version.removeprefix("v").split(".")))


@dataclass(frozen=True)
class Release:
    tag: str
    notes: str = "详细更新内容请查看发行页面。"
    size: int | None = None

    def __post_init__(self):
        version_tuple(self.tag)
        if not self.tag.startswith("v"):
            raise ValueError("发行标签必须以 v 开头")
        if self.size is not None and (type(self.size) is not int or not 0 < self.size <= MAX_DOWNLOAD):
            raise ValueError("更新文件大小无效")

    @property
    def page_url(self) -> str:
        return f"{RELEASES_URL}/tag/{self.tag}"

    @property
    def executable_name(self) -> str:
        # v0.2.x shipped under the original name; the v0.3 series uses BP.exe.
        return "BP.exe" if version_tuple(self.tag) >= (0, 3, 0) else "beast-pick.exe"

    def asset_url(self, name: str) -> str:
        if name not in (self.executable_name, "SHA256SUMS.txt"):
            raise ValueError("不支持的更新文件")
        return f"{RELEASES_URL}/download/{self.tag}/{name}"

    def newer_than(self, version: str) -> bool:
        return version_tuple(self.tag) > version_tuple(version)


def release_from_api(payload: dict) -> Release:
    if not isinstance(payload, dict) or payload.get("draft") is not False or payload.get("prerelease") is not False:
        raise ValueError("没有可用的正式发行版本")
    release = Release(payload.get("tag_name"), str(payload.get("body") or "暂无更新说明。")[:16000])
    if payload.get("html_url") != release.page_url:
        raise ValueError("发行页面与项目不匹配")
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("发行版本缺少下载文件")
    for name in (release.executable_name, "SHA256SUMS.txt"):
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
        if len(matches) != 1 or matches[0].get("state") != "uploaded" or matches[0].get("browser_download_url") != release.asset_url(name):
            raise ValueError("发行版本的下载文件尚未就绪")
        if name == release.executable_name:
            release = Release(release.tag, release.notes, matches[0].get("size"))
            if release.size is None:
                raise ValueError("更新文件缺少大小")
    return release


def release_from_redirect(url: str) -> Release:
    parsed = urlsplit(url)
    prefix = f"/{REPOSITORY}/releases/tag/"
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path.startswith(prefix) or parsed.query or parsed.fragment:
        raise ValueError("未能获取最新正式发行版本")
    return Release(parsed.path[len(prefix):])


def executable_checksum(text: str, filename: str = "BP.exe") -> str:
    if filename not in ("BP.exe", "beast-pick.exe"):
        raise ValueError("不支持的更新文件")
    matches = re.findall(r"^([a-fA-F0-9]{64})[ \t]+\*?" + re.escape(filename) + r"[ \t]*$", text, re.M)
    if len(matches) != 1:
        raise ValueError("发行版本缺少唯一的 EXE 校验值")
    return matches[0].lower()
