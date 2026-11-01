"""UI groups for the game's CategoryType enum (inventorystuff.scr)."""

ITEM_TYPES = {
    "weapons": ("武器（含临场武器）", [0, 1]),
    "ammo": ("弹药", [4]),
    "materials": ("制作 / 维修材料", [8, 11, 18]),
    "money": ("金钱 / 代币", [5, 21, 25]),
    "valuables": ("贵重物品", [20]),
    "consumables": ("治疗 / 消耗品", [3, 7, 15, 23, 24]),
    "throwables": ("投掷物", [2, 13, 14]),
    "gear": ("服装 / 装备", [22, 26]),
    "other": ("其他已识别物品", [6, 9, 10, 12, 16, 17, 19, 27, 28]),
}


def checked_item_types(value=None) -> dict[str, bool]:
    if value is None:
        return dict.fromkeys(ITEM_TYPES, True)
    if not isinstance(value, dict) or set(value) - ITEM_TYPES.keys():
        raise ValueError("物品类型筛选格式不正确")
    if any(type(v) is not bool for v in value.values()):
        raise ValueError("物品类型筛选必须为勾选状态")
    return {key: value.get(key, True) for key in ITEM_TYPES}
