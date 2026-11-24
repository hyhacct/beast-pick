<div align="center">

<img src="beast_pick/assets/beast-pick.png" alt="Beast Pick (BP) 自动搜刮工具" width="144" height="144">

# Beast Pick — Dying Light 2 & The Beast Auto Loot

**BP ·《消逝的光芒 2》与《消逝的光芒：困兽》自动搜刮 / 自动拾取工具**

简体中文 · [English](README.en.md)

[![Windows](https://img.shields.io/badge/Windows-x64-DDEBF7?style=flat-square)](#运行环境)
[![CI](https://img.shields.io/github/actions/workflow/status/hyhacct/beast-pick/ci.yml?branch=main&style=flat-square)](https://github.com/hyhacct/beast-pick/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/hyhacct/beast-pick?style=flat-square)](https://github.com/hyhacct/beast-pick/releases/latest)
[![MIT](https://img.shields.io/badge/License-MIT-F0EDEA?style=flat-square)](LICENSE)

[下载](https://github.com/hyhacct/beast-pick/releases/latest) · [功能](#功能一览) · [快速开始](#快速开始) · [支持的游戏构建](#支持的游戏构建) · [验证与限制](#验证与已知限制)

</div>

**Beast Pick（BP）** 是 Windows 自动搜刮工具，支持《消逝的光芒 2》和《消逝的光芒：困兽》的指定构建。它查询本地角色附近已加载的目标，按设置搜刮尸体、普通容器并拾取散落物品。当前界面和已解析的物品名称为中文。

> **当前状态：** 两款游戏的尸体、普通容器和散落物均有本机样本验证；《消光 2》的特定武器排除有实机样本。自动开箱默认关闭，锁箱功能另需启用且属于试验功能。《消光 2》的完整自动开箱链路及特殊收集物尚待实机验证。曾出现游戏闪退，根因尚未完全确认；长期稳定性、联机归属与同步仍需验证。

## 功能一览

| 功能 | 行为 |
| --- | --- |
| 游戏选择 | 自动检测或手动选择《消光 2》/《困兽》；连接后标题和状态栏显示当前游戏 |
| 自动搜刮 | 分别控制尸体、普通容器及散落物品；半径可设为 **1–500 米**，默认 8 米 |
| 武器排除 | “拾取武器”总开关，或按名称 / ID 排除具体武器和投掷物；两款游戏的排除列表分别保存 |
| 箱柜开启 | 可选开启已识别箱柜；锁箱需额外启用试验选项，游戏对象须已进入模拟 |
| 操作与日志 | F6 开始 / 暂停，F8 停止；日志显示连接、拾取与错误状态 |
| 更新 | 检查 GitHub Release，用户确认后下载、校验、替换并重启 |

当前界面不提供 DIY 武器页或千刀入口。自动开箱与内容领取是两个步骤：要拾取生成的物品，还需勾选“自动拾取散落物品”。

## 支持的游戏构建

| 游戏 | 当前适配构建 | 配置 |
| --- | --- | --- |
| 消逝的光芒：困兽 | ph-ft patch08（2026-10-30 / 6550878，Steam BuildID `26402545`） | [current.json](beast_pick/profiles/current.json) |
| 消逝的光芒 2 | 本机验证的 `1.30.2.0na` | [dl2.json](beast_pick/profiles/dl2.json) |

连接时校验实际加载的引擎和游戏 DLL 的 SHA-256 与映像大小。版本文字相同也不一定是同一构建；游戏更新或不同发行版本可能需要重新适配。

## 快速开始

### 运行环境

- Windows x64；本机在 Windows 11 上验证。
- 游戏已启动并进入存档，构建与上述配置匹配。
- 打包版无需安装 Python；源码运行使用 Python 3.12，项目依赖 PySide6 和 Frida。

### 下载并运行

1. 前往 [GitHub Releases](https://github.com/hyhacct/beast-pick/releases/latest)，下载 `BP-v版本号-windows-x64.zip` 并解压，运行 `BP.exe`。
2. 在工具栏选择游戏或使用“自动检测”。如果两款游戏同时运行，请明确选择目标。
3. 点击“连接游戏”，设置半径以及尸体、普通容器、散落物选项。
4. 如需排除物品，点击“排除指定武器 / 投掷物”，搜索名称或内部 ID 并勾选；同名条目的所有所列版本会一起排除。
5. 切回游戏，按 **F6** 开始或暂停，按 **F8** 停止。每次启动初始为停止状态。

例如，在《困兽》列表搜索“草叉”可排除其 3 个目录版本。总开关取消“拾取武器”会排除已识别的近战和枪械类别；草叉等投掷类别的具体物品可通过排除列表单独设置。存在排除规则时，可能属于排除范围但身份不明的物品，以及内容不透明的物资包会被跳过。

### 箱柜选项

勾选“自动搜刮普通容器”和“自动开启箱柜”后，工具才尝试开启已识别箱柜。若要尝试锁箱，还需单独勾选“强制开启锁箱柜（试验）”；该选项默认关闭。未知锁型、特殊禁搜刮箱柜和不满足正常交互条件的目标会跳过。

### 更新与设置

程序启动时检查正式版本，也可点击“检查更新”。确认后下载并校验新 EXE，自动停止搜刮、替换并重启；替换失败时恢复旧版。打包版的 `settings.json` 与 `logs/beast-pick.log` 位于 EXE 同目录；源码版位于项目根目录。

## 验证与已知限制

- 《消光 2》实机样本覆盖尸体、普通容器和地面武器；排除“技工锤头”时，该物品留在地面，另一件物品被拾取。
- 一个中等锁箱的单次探针验证了开启判定和状态变化；之后附近有物品被 BP 领取，但未证明每件物品都来自该箱。**BP 完整自动开箱链路与特殊收集物尚未实机验证。**
- 《困兽》已有尸体、普通容器、散落物和武器排除的历史本机样本；草叉具体版本排除通过离线规则测试，尚未在该游戏中复测。
- 搜索为直线距离，可能跨墙或楼层；只覆盖引擎已加载目标。500 米不保证所有目标都已加载或进入模拟。
- 背包已满、死亡 / 过场、读档压力、全部目标类型、联机切换、物品归属与长期运行尚未全面验证。历史闪退与生命周期调查见 [实现记录](docs/implementation.md)。
- CI 不运行游戏，代码和打包检查不能替代实机验收。

## 开发与发布

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
node --test tests\agent.test.cjs tests\dl2_agent.test.cjs tests\filters.test.cjs tests\melee.test.cjs
node --check beast_pick\agent.js
node --check beast_pick\dl2_agent.js
.\build.ps1
```

构建输出为 `dist/BP.exe`。`tools/check_bundle.py` 复核真实 EXE 和内置资源；加 `--check-game` 可额外验证连接，但不会开启搜刮。

推送 `main` 会触发 CI；推送与 `beast_pick/__init__.py` 版本及 `CHANGELOG.md` 对应的 `vX.Y.Z` 标签，会触发 Windows 构建和 GitHub Release。详情见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [发布工作流](.github/workflows/release.yml)。

## 反馈与许可证

请通过 [Issues](https://github.com/hyhacct/beast-pick/issues) 提供游戏名称、构建、目标类型、复现步骤及相关日志。项目代码采用 [MIT License](LICENSE)，本项目为非官方工具。