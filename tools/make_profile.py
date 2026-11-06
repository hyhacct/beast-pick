"""Regenerate the checked-in profile for the installed patch08 build.

This script derives module fingerprints from disk. Native entry points are
from the bounded live-process re-adaptation record and must be re-researched
when the game changes again.
"""
import hashlib
import json
from pathlib import Path

import pefile

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(r"D:\App\Steam\steamapps\common\Dying Light The Beast\ph_ft\work\bin\x64")

PROFILE = {
    "id": "beast-ph-ft-patch08-20261030-6550878",
    "label": "困兽 ph-ft patch08（2026-10-30 / 6550878）",
    "game_build": {
        "name": "ph-ft_pc_tech_rel-ph-ft-patch08_202610301710_6550878_b51v__nightly",
        "steam_build_id": "26402545",
    },
    "scheduler_return_rva": 0xBB49E4,
    "player_transform_slot": 151,
    "players_slot": 152,
    "local_entity_slot": 153,
    "body_init_rva": 0x1197680,
    "container": {
        "init_rva": 0x1197780,
        "can_rva": 0x112DC80,
        "execute_rva": 0x11A03F0,
        "linked_trigger_offset": 1392,
    },
    "body_take_rva": 0x1191E40,
    "body_take_one_rva": 0x1192040,
    "body_item_stride": 0x160,
    "body_init_slot": 220,
    "body_loot_offset": 984,
    "body_state_offset": 0x388,
    "body_items_offsets": [0x4C8, 0x4D8],
    "item_execute_rva": 0x11A0620,
    "dropped_execute_rva": 0xDFADB0,
    "player_context_offset": 0x2460,
    "item_execute_slot": 197,
    "dropped_description_offset": 0x5F0,
    "item_description_offset": 0x380,
    "description_context_offset": 0x38,
    "description_category_slot": 102,
    "description_category_rva": 0xA179B0,
    "item_used_offset": 0x4F0,
    "trigger_enabled_offsets": [0x1C8, 0x1C9],
    "item_identity": {
        "name_rva": 0x255170,
        "name_offset": 8,
        "name_slot": 99,
    },
    "complex_container": {
        "can_rva": 0x112DBA0,
        "execute_rva": 0x11A00C0,
        "lock_property_offset": 1008,
        "no_loot_property_offset": 1176,
        "child_count_offset": 1408,
        "metadata_count_offset": 1248,
    },
    "control_simulating_rva": 0x1EC8160,
}


def module_fingerprints() -> dict:
    modules = {}
    for name in ("engine_x64_rwdi.dll", "gamedll_ph_x64_rwdi.dll"):
        path = BINARY / name
        pe = pefile.PE(str(path), fast_load=True)
        modules[name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": pe.OPTIONAL_HEADER.SizeOfImage,
            "timestamp": pe.FILE_HEADER.TimeDateStamp,
        }
    return modules


def main() -> None:
    profile = {**PROFILE, "modules": module_fingerprints()}
    output = ROOT / "beast_pick" / "profiles" / "current.json"
    output.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
