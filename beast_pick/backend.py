"""Local process connection with strict build validation and stopped detach."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import frida

from .categories import ITEM_TYPES, checked_item_types
from .catalog import checked_rules, has_allowed, load_catalog
from .diy import prepare_generation, validate_plan
from .weapon_catalog import checked_exclusions

PROCESS = "DyingLightGame_TheBeast_x64_rwdi.exe"
DL2_PROCESS = "DyingLightGame_x64_rwdi.exe"
MAX_RADIUS = 500.0
ROOT = Path(__file__).resolve().parent


def load_profile(name: str = "current") -> dict:
    return json.loads((ROOT / "profiles" / f"{name}.json").read_text(encoding="utf-8"))


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
                     locked_containers: bool = False, rapid_melee: bool = False, melee_speed: float = 12) -> dict:
    if not 1 <= radius <= MAX_RADIUS:
        raise ValueError(f"搜刮半径应在 1–{MAX_RADIUS:g} 米之间")
    if enabled and not (corpses or items or containers):
        raise ValueError("请至少选择一种搜刮功能")
    selection = checked_item_types(item_types)
    rules = checked_rules(item_rules)
    if enabled and not has_allowed(selection, rules):
        raise ValueError("请至少选择一种允许拾取的物品类型")
    if isinstance(melee_speed, bool) or not isinstance(melee_speed, (int, float)) or not 2 <= melee_speed <= 20:
        raise ValueError("千刀攻速倍率应在 2–20 之间")
    return dict(radius=float(radius), corpses=bool(corpses), items=bool(items), containers=bool(containers), enabled=bool(enabled),
                item_types=selection, item_rules=rules, open_containers=bool(open_containers),
                locked_containers=bool(locked_containers), rapid_melee=bool(rapid_melee), melee_speed=float(melee_speed))


def select_game_process(processes, game='auto'):
    supported = {PROCESS.lower(): 'beast', DL2_PROCESS.lower(): 'dl2'}
    if game not in ('auto', 'beast', 'dl2'):
        raise ValueError('请选择有效的游戏。')
    matches = [p for p in processes if p.name.lower() in supported and
               (game == 'auto' or supported[p.name.lower()] == game)]
    if len(matches) != 1:
        raise RuntimeError('未找到唯一的目标游戏进程；如果两款游戏同时运行，请在工具栏选择游戏。')
    return matches[0], supported[matches[0].name.lower()]


class Client:
    def __init__(self, on_event: Callable[[dict], None] | None = None):
        self.on_event = on_event or (lambda event: None)
        self.session = None
        self.script = None
        self.pid = None
        self.game_key = None
        self.profile_label = None
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
        self.game_key = self.profile_label = None
        if not self.closing:
            self.on_event({"event": "detached", "reason": str(reason)})

    def connect(self, game: str = "auto") -> dict:
        if self.connected:
            if game not in ("auto", self.game_key):
                raise RuntimeError("请先断开当前游戏。")
            return {"pid": self.pid, "profile": self.profile_label, "game": self.game_key}
        if frida.__version__ != "17.24.0":
            raise RuntimeError("此工具需要 Frida 17.24.0；当前版本为 " + frida.__version__)
        device = frida.get_local_device()
        target, game = select_game_process(device.enumerate_processes(), game)
        self.closing = False
        try:
            self.session = device.attach(target.pid)
            self.session.on("detached", self._detached)
            names = ("dl2_agent.js",) if game == "dl2" else ("filters.js", "melee.js", "agent.js")
            source = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in names)
            self.script = self.session.create_script(source)
            self.script.on("message", self._message)
            self.script.load()
            profile = load_profile("dl2" if game == "dl2" else "current")
            validate_modules(profile, self.script.exports_sync.modules())
            profile["item_categories"] = {key: ids for key, (_, ids) in ITEM_TYPES.items()}
            profile["item_catalog"] = load_catalog()
            self.script.exports_sync.init(profile)
            self.pid = target.pid
            self.game_key = game
            self.profile_label = profile["label"]
            return {"pid": self.pid, "profile": profile["label"], "game": game}
        except BaseException:
            self.close()
            raise

    def configure(self, **settings) -> dict:
        if not self.connected:
            raise RuntimeError("请先连接游戏")
        excluded = checked_exclusions(self.game_key, settings.pop('excluded_ids', []))
        config = checked_settings(**settings)
        if self.game_key == "dl2":
            if config["rapid_melee"]:
                raise RuntimeError("消光 2 尚未适配千刀。")
            config['excluded_ids'] = excluded
        elif self.game_key == "beast":
            config['item_rules']['items'].update({identity: False for identity in excluded})
        return self.script.exports_sync.configure(config)

    def heartbeat(self) -> dict:
        if not self.connected:
            raise RuntimeError("游戏已断开")
        return self.script.exports_sync.heartbeat()

    def diy_apply(self, plan: dict) -> dict:
        """Validate locally, then hand the plan to the agent.

        The agent refuses writes until this build's descriptor layout has been
        calibrated, so an unsupported build surfaces a clear message rather than
        corrupting an inventory item.
        """
        if not self.connected:
            raise RuntimeError("请先连接游戏")
        if self.game_key == "dl2":
            raise RuntimeError("消光 2 尚未适配 DIY 武器写入。")
        return self.script.exports_sync.diyApply(validate_plan(plan)) or {}

    def diy_generate(self, plan: dict) -> dict:
        """Create one calibrated melee weapon in inventory on the game thread."""
        if not self.connected:
            raise RuntimeError("请先连接游戏")
        if self.game_key == "dl2":
            raise RuntimeError("消光 2 尚未适配 DIY 武器生成。")
        prepared = prepare_generation(plan)
        return self.script.exports_sync.diyGenerate(prepared) or {}

    def stop(self):
        if self.script is not None:
            self.script.exports_sync.stop()

    def close(self):
        self.closing = True
        script, session = self.script, self.session
        self.script = self.session = self.pid = None
        self.game_key = self.profile_label = None
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
