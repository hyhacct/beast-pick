<div align="center">

# beast-pick

**Beast Pick · 困兽自动搜刮**

把时间留给探索，让附近的战利品自动入袋。

[![Windows](https://img.shields.io/badge/Windows-x64-0078D4)](#运行环境)
[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](#从源码运行)
[![CI](https://github.com/hyhacct/beast-pick/actions/workflows/ci.yml/badge.svg)](https://github.com/hyhacct/beast-pick/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/hyhacct/beast-pick)](https://github.com/hyhacct/beast-pick/releases/latest)
[![MIT](https://img.shields.io/badge/License-MIT-2EA44F)](LICENSE)

[下载](https://github.com/hyhacct/beast-pick/releases/latest) · [功能](#功能一览) · [快速开始](#快速开始) · [物品筛选](#物品筛选) · [开发与发布](#开发与发布) · [常见问题](#常见问题)

</div>

面向《消逝的光芒：困兽》单人游戏的 Windows 桌面工具。开启后持续检测附近已加载的尸体、容器和散落物品，按你的规则搜刮和拾取。

采用 PySide6 原生 Windows 风格界面，提供快捷键、实时统计、中文物品记录和分层筛选。当前适配 **1.7.1.0na 的指定游戏构建**，连接时以实际 DLL 的 SHA-256 校验；版本文字相同也不代表构建相同。

> **当前状态：** 尸体、普通容器及独立物品领取已有本机实测。箱柜自动开启默认关闭，跳过撬锁为试验功能。曾出现游戏闪退，根因尚未完全确认，尚未完成长期稳定性验证。

## 功能一览

| 功能 | 行为 |
| --- | --- |
| 尸体搜刮 | 检测附近可搜刮尸体，按规则逐项领取 |
| 散落物品 | 拾取地面物品，以及箱柜内生成的独立物品 |
| 普通容器 | 搜刮已识别的背包等普通容器 |
| 箱柜开启 | 可选完成普通箱柜的长按 / 连按 F 开启流程 |
| 锁箱柜 | 可选跳过已确认箱柜的撬锁流程，**试验功能** |
| 物品筛选 | **9 个大类 · 71 个子类 · 4,077 个物品定义** |
| 搜索范围 | **1–500 米**，默认 8 米，保留已有设置 |
| 运行控制 | F6 开始 / 暂停，F8 停止；暂停、加载和切出游戏时等候 |
| 运行记录 | 显示中文物品名、领取距离、统计和连接状态 |

只处理确认的容器类型；**门、未知锁型、特殊禁搜刮容器及关联机关会跳过**。搜索距离按空间直线计算，可能覆盖隔墙、隔层目标；未加载的目标无法检测。

## 快速开始

### 运行环境

- Windows x64；当前在 Windows 11 上验证。
- 游戏已启动并进入单人存档，构建须与[适配配置](beast_pick/profiles/current.json)匹配。
- 下载打包版无需安装 Python。源码运行需要 Python 3.12 或更高版本；当前验证环境为 Python 3.12、PySide6 6.12 和 Frida 17.24.0。
- Node.js 仅在运行 JavaScript 开发检查时需要。

### 下载 Windows 版

前往 [Releases](https://github.com/hyhacct/beast-pick/releases/latest)，下载最新的 **beast-pick-v版本号-windows-x64.zip**，解压后运行 **beast-pick.exe**。

每个版本同时提供独立 EXE 和 SHA256SUMS.txt。发布包包含使用说明和 MIT 许可证；无需将文件放进游戏安装目录。

### 从源码运行

在 PowerShell 中执行：

~~~powershell
git clone https://github.com/hyhacct/beast-pick.git
cd beast-pick

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m beast_pick
~~~

安装后也可运行 .\.venv\Scripts\beast-pick.exe，或双击 [start-beast-pick.bat](start-beast-pick.bat)。

### 连接与使用

1. 进入单人存档，关闭旧版工具，再启动 Beast Pick。
2. 点击 **连接游戏**，设置半径和允许拾取的物品类型。
3. 切回游戏，按 **F6** 开始；再次按 F6 暂停，按 **F8** 停止。

每次启动初始为停止状态。切回游戏并满足场景条件后才执行搜刮。

| 选项 | 使用方式 |
| --- | --- |
| 自动搜刮尸体 | 独立控制尸体搜刮 |
| 自动搜刮普通容器 | 控制普通容器领取，也是箱柜开启的前置开关 |
| 自动拾取散落物品 | 控制地面及箱柜生成的独立物品领取 |
| 自动开启箱柜 | 默认关闭；需要时手动勾选 |
| 强制开启锁箱柜（试验） | 默认关闭；需同时启用普通容器和自动开启箱柜 |

**自动开箱与内容领取是两个步骤。** 要领取 ComplexContainer 箱柜生成的独立物品，也需启用“自动拾取散落物品”。远处箱柜必须先进入引擎模拟；未激活时工具会等待，500 米搜索半径不代表能立即打开范围内所有箱柜。

## 物品筛选

先在主界面选择大类，再通过 **详细筛选…** 调整子类和具体物品。

~~~text
具体物品规则  >  子类规则  >  大类选择
~~~

每条详细规则都有三种状态：**跟随上级 / 拾取 / 跳过**。

| 想要的效果 | 设置方法 |
| --- | --- |
| 不捡近战、枪械和临场武器 | 点击主界面的“排除武器” |
| 拾取投掷物，但跳过手雷 | 勾选“投掷物”，在“按子类”中将手雷设为“跳过” |
| 只拾取某一种物品 | 大类全不选，再把该具体物品设为“拾取” |
| 排除同名物品中的某个版本 | 在“按物品名称”中根据名称和内部 ID 定位对应行 |

详细筛选支持名称 / ID 搜索、大类与子类过滤，以及多行批量设置。双击规则单元格即可编辑；**Ctrl+A** 可选中当前过滤后的全部结果。取消对话框不会保存本次编辑。

目录来自当前游戏安装资源。有中文名称的显示中文，无法解析的名称保留真实内部 ID。同名物品可能对应不同等级或版本，应结合 ID 设置规则。

为使排除规则生效，容器始终逐项领取。存在详细规则时，身份无法确认的物品会跳过；存在任何排除项时，也会跳过内容不透明的物资包，避免间接获得被排除物品。

## 实现方式

工具通过 Frida 连接本地游戏进程，使用引擎空间查询取得附近目标，经类型、状态和规则检查后调用游戏已有交互路径。

~~~mermaid
flowchart LR
    A[连接并校验构建] --> B[等待场景就绪]
    B --> C[查询范围内目标]
    C --> D[检查类型与拾取规则]
    D --> E[调用游戏交互路径]
    E --> F[确认结果并更新记录]
    F --> C
~~~

- 查询和原生调用统一运行在已验证的游戏模拟回调中，不在 RPC 线程直接调用。
- 不跨扫描保存待执行的原生对象指针；每轮重新查询，开箱后结束当前候选处理。
- 每秒最多开启一个箱柜，检查实际内容生成结果；仅状态变化不会计为 ComplexContainer 开启成功。
- 心跳中断超过 5 秒时停止；关闭时先停止领取、移除回调，再断开连接。

## 开发与发布

### 本地检查与打包

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
node --test tests\filters.test.cjs
node --check beast_pick\agent.js
.\build.ps1
~~~

输出为 **dist/beast-pick.exe**。构建使用 [packaging/beast-pick.spec](packaging/beast-pick.spec)，随后对真实 EXE 进行干净环境启动检查，并核对内置代理、规则、适配配置和物品目录。

~~~powershell
# 单独复核打包结果
.\.venv\Scripts\python.exe tools\check_bundle.py

# 可选：额外检查游戏连接，不开启搜刮；需先进入存档。
.\.venv\Scripts\python.exe tools\check_bundle.py --check-game
~~~

### 自动构建与版本发布

| 触发条件 | GitHub Actions 行为 |
| --- | --- |
| 提交到 main / 创建 Pull Request | 运行检查、构建 Windows EXE，保存构建产物 |
| 推送 vX.Y.Z 标签 | 校验版本与更新日志，构建并自动发布 GitHub Release |
| 手动运行 CI | 重跑检查与构建，不发布新版本 |

版本号唯一来源为 **beast_pick/__init__.py**，Python 发行包、窗口、EXE 版本信息与发布文件名均由此取得。采用语义化版本：补丁号用于兼容修复，次版本号用于功能增加，主版本号用于不兼容变化。

~~~powershell
# 示例：准备下一个补丁版本
.\.venv\Scripts\python.exe tools\release.py bump 0.2.1
# 编辑 CHANGELOG.md，填写本版本实际变更
.\.venv\Scripts\python.exe tools\release.py check
git add .
git commit -m "Release v0.2.1"
.\.venv\Scripts\python.exe tools\release.py tag
git push origin main v0.2.1
~~~

已发布标签保持不变，修复通过新版本发布。**首次开源日期：2026-11-01（Asia/Shanghai）**。版本变更与发布日期见 [CHANGELOG.md](CHANGELOG.md)。

### 项目结构

~~~text
beast-pick/
├── .github/workflows/      # 检查、构建与自动发布
├── beast_pick/             # Python 包、原生界面与连接管理
│   ├── agent.js            # 游戏内查询与交互代理
│   ├── filters.js          # 共享筛选策略
│   ├── filter_dialog.py    # 子类和具体物品规则编辑器
│   ├── data/items.json     # 物品元数据目录
│   └── profiles/           # 游戏构建校验与适配配置
├── tests/                  # Python 与 JavaScript 检查
├── tools/                  # 版本管理、打包检查与诊断
├── packaging/              # PyInstaller 配置与玩家使用说明
├── docs/implementation.md  # 实现细节、验证记录与历史调查
├── build.ps1               # 构建与自检入口
└── start-beast-pick.bat     # 本地源码启动入口
~~~

tools 中包含针对本机安装的实验诊断脚本，部分会调用游戏交互；它们不属于日常启动步骤。适配新构建前请阅读[贡献指南](CONTRIBUTING.md)和[实现记录](docs/implementation.md)。

## 验证与已知限制

本地检查覆盖构建校验、配置与筛选、连接清理，以及纯 JavaScript 决策策略；打包检查覆盖原生窗口、配置持久化、详细筛选、500 米边界、版本和包内资源一致性。

已记录的游戏样本包括尸体搜刮、散落物品领取、普通容器逐项领取及武器排除。最近一次普通柜子测试中，约 4.5 米外的柜子生成 3 个道具目标，罐头食品和手枪弹药被领取，排除的冲锋枪保留；10 秒内完成 33 轮扫描，无脚本错误。

这些结果仅覆盖已测试样本。**跳过撬锁仍为试验功能**，最近一次完整自动开箱验证使用的是无锁柜子。尚未完整验证所有箱柜、背包满、死亡 / 过场、读档压力、联机切换和长时间运行。历史闪退与生命周期调整见[实现记录](docs/implementation.md)。

CI 中没有游戏进程，只能验证代码、界面和打包结果，不能代替实际游戏验证。运行日志、设置、诊断输出、虚拟环境和打包产物不提交到仓库；实现记录中的 artifacts 路径指开发时的本地证据。

## 常见问题

<details>
<summary><strong>连接时提示游戏构建不匹配？</strong></summary>

当前配置只接受已验证 DLL 的 SHA-256 和映像大小。游戏更新或不同构建都可能无法连接，需要重新适配。请勿只修改版本名或关闭校验来强行运行。

</details>

<details>
<summary><strong>设为 500 米，为什么仍有目标没有处理？</strong></summary>

查询只能找到已加载的目标，箱柜开启还要求对象进入引擎模拟。拾取规则、目标类型、状态、游戏暂停或后台等待也会影响处理结果，可查看运行记录。

</details>

<details>
<summary><strong>设置和日志保存在哪里？</strong></summary>

源码运行时保存在项目根目录；打包运行时保存在 EXE 所在目录。设置文件为 settings.json，日志为 logs/beast-pick.log。更新 EXE 时保留同目录设置即可。

</details>

<details>
<summary><strong>EXE 提示 QtCore DLL 无法加载？</strong></summary>

已知原因之一是构建环境将不兼容的 ICU DLL 打入程序。请使用仓库提供的 build.ps1 和打包配置重新构建，并确认 check_bundle.py 通过。报告时请附 Windows 版本和完整错误信息。

</details>

## 参与贡献

欢迎通过 [Issues](https://github.com/hyhacct/beast-pick/issues) 报告问题，或提交 Pull Request。请提供游戏构建、系统版本、目标类型、复现步骤和相关日志；提交前移除个人信息。

命名统一为：仓库 / Python 发行包 / 启动命令 **beast-pick**，Python 导入包 **beast_pick**，Windows 程序 **beast-pick.exe**。具体流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

项目代码采用 [MIT License](LICENSE)。游戏名称、物品名称和相关内容的权利归其各自权利人；本项目是非官方工具。

<div align="center">

<sub>Beast 来自 The Beast；pick 既是 pick up，也呼应 pick a lock。</sub>

</div>
