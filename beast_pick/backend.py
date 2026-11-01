"""Local process connection with strict build validation and stopped detach."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import frida

from .categories import ITEM_TYPES, checked_item_types
from .catalog import checked_rules, has_allowed, load_catalog

PROCESS = "DyingLightGame_TheBeast_x64_rwdi.exe"
MAX_RADIUS = 500.0
ROOT = Path(__file__).resolve().parent


def load_profile() -> dict:
    return json.loads((ROOT / "profiles" / "current.json").read_text(encoding="utf-8"))


def validate_modules(profile: dict, modules: list[dict]) -> None:
    """A matching version string is insufficient: validate the actual loaded DLL files."""
    found = {m["name"].lower(): m for m in modules}
    for name, expected in profile["modules"].items():
        actual = found.get(name)
        if actual is None:
            raise RuntimeError(f"游戏模块尚未加载：{name}。请先进入存档。")
        if actual["size"] != expected["size"]:
            raise RuntimeError(f"游戏构建不匹配：{name}。需要重新适配此版本。")
        with Path(actual["path"]).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected["sha256"]:
            raise RuntimeError(f"游戏文件校验不匹配：{name}。已阻止启动，需要重新适配。")


def checked_settings(radius: float, corpses: bool, items: bool, enabled: bool, item_types=None,
                     *, containers: bool = False, item_rules=None, open_containers: bool = False,
                     locked_containers: bool = False) -> dict:
    if not 1 <= radius <= MAX_RADIUS:
        raise ValueError(f"搜刮半径应在 1–{MAX_RADIUS:g} 米之间")
    if enabled and not (corpses or items or containers):
        raise ValueError("请至少选择一种搜刮功能")
    selection = checked_item_types(item_types)
    rules = checked_rules(item_rules)
    if enabled and not has_allowed(selection, rules):
        raise ValueError("请至少选择一种允许拾取的物品类型")
    return dict(radius=float(radius), corpses=bool(corpses), items=bool(items), containers=bool(containers), enabled=bool(enabled),
                item_types=selection, item_rules=rules, open_containers=bool(open_containers),
                locked_containers=bool(locked_containers))


class Client:
    def __init__(self, on_event: Callable[[dict], None] | None = None):
        self.on_event = on_event or (lambda event: None)
        self.session = None
        self.script = None
        self.pid = None
        self.closing = False

    @property
    def connected(self) -> bool:
        return self.script is not None and self.session is not None

    def _message(self, message, data):
        if message["type"] == "send":
            self.on_event(message["payload"])
        elif message["type"] == "error":
            self.on_event({"event": "error", "error": message.get("stack", message.get("description", "脚本错误"))})

    def _detached(self, reason, crash=None):
        self.script = None
        self.session = None
        self.pid = None
        if not self.closing:
            self.on_event({"event": "detached", "reason": str(reason)})

    def connect(self) -> dict:
        if self.connected:
            return {"pid": self.pid, "profile": load_profile()["label"]}
        if frida.__version__ != "17.24.0":
            raise RuntimeError("此工具需要 Frida 17.24.0；当前版本为 " + frida.__version__)
        device = frida.get_local_device()
        matches = [p for p in device.enumerate_processes() if p.name.lower() == PROCESS.lower()]
        if len(matches) != 1:
            raise RuntimeError("未找到唯一的《消逝的光芒：困兽》进程，请先启动游戏并进入存档。")
        self.closing = False
        try:
            self.session = device.attach(matches[0].pid)
            self.session.on("detached", self._detached)
            source = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("filters.js", "agent.js"))
            self.script = self.session.create_script(source)
            self.script.on("message", self._message)
            self.script.load()
            profile = load_profile()
            validate_modules(profile, self.script.exports_sync.modules())
            profile["item_categories"] = {key: ids for key, (_, ids) in ITEM_TYPES.items()}
            profile["item_catalog"] = load_catalog()
            self.script.exports_sync.init(profile)
            self.pid = matches[0].pid
            return {"pid": self.pid, "profile": profile["label"]}
        except BaseException:
            self.close()
            raise

    def configure(self, **settings) -> dict:
        if not self.connected:
            raise RuntimeError("请先连接游戏")
        return self.script.exports_sync.configure(checked_settings(**settings))

    def heartbeat(self) -> dict:
        if not self.connected:
            raise RuntimeError("游戏已断开")
        return self.script.exports_sync.heartbeat()

    def stop(self):
        if self.script is not None:
            self.script.exports_sync.stop()

    def close(self):
        self.closing = True
        script, session = self.script, self.session
        self.script = self.session = self.pid = None
        try:
            if script is not None:
                try:
                    script.exports_sync.shutdown()
                except BaseException:
                    script.unload()
                    raise
                else:
                    # Keep the idle Frida runtime resident until game exit. Rapid
                    # unload after a connect-only check preceded an execute AV at
                    # an unmapped address on this host. All our engine listeners
                    # have already been detached and looting is disabled above.
                    script.eternalize()
        finally:
            if session is not None:
                try:
                    session.detach()
                except frida.InvalidOperationError:
                    pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
