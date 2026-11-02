# 贡献指南

提交问题或改动前，请先阅读 [README](README.md) 中的构建适配要求与已知限制。

## 开发环境

使用 Windows x64 与 Python 3.12，安装开发依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m beast_pick
```

Node.js 用于运行 JavaScript 策略检查。普通单元测试不要求游戏正在运行。

## 提交改动

1. Fork 仓库并为改动创建分支。
2. 让改动集中解决一个具体问题，更新受影响的使用文档。
3. 运行与改动相关的检查；涉及行为时补充能验证实际结果的测试。
4. 提交 Pull Request，说明触发条件、改动后行为、验证方式和未覆盖范围。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests\agent.test.cjs tests\filters.test.cjs
node --check beast_pick\agent.js
```

修改构建、界面或包内资源后，还需运行 `build.ps1`，验证真实 `dist/BP.exe`。`--check-game` 会连接游戏但不启用搜刮，不能代替实际领取验证。

更新功能的默认测试使用本地模拟响应，不访问网络。需要验证 GitHub 连接时运行 `.\.venv\Scripts\python.exe tools\verify_updates.py`，可加 `--download artifacts\updater-live\BP.exe` 验证真实下载与校验，但不会执行下载的程序。打包后运行 `.\.venv\Scripts\python.exe tools\check_bundle.py --check-updates` 可检查发行 EXE 的实际网络运行时；网络检查不属于离线 CI 的必需项。

## 游戏适配

- 记录游戏构建、模块 SHA-256、映像大小以及可复现样本，不根据版本文字猜测偏移。
- 游戏查询与交互留在已验证的模拟回调中；不从 RPC 线程直接调用游戏逻辑，不跨扫描保存待执行的原生对象指针。
- 新目标需核对真实类型、状态和交互入口；门、关联机关和未知目标不能混入箱柜处理。
- 筛选规则须同时作用于尸体、容器和独立物品，避免通过全部领取绕过排除项。
- 区分“请求已执行”“状态变化”“内容生成”和“领取确认”，不要仅凭状态值宣称完整成功。
- 关闭流程保留停止领取、移除回调、驻留空闲运行时和断开连接的顺序；历史调查见 [docs/implementation.md](docs/implementation.md)。

`tools/` 保留研究与诊断脚本，部分包含本机安装路径或会执行游戏操作。先阅读对应源码，仅运行与当前调查有关的脚本。

## 命名约定

| 用途 | 名称 |
| --- | --- |
| 仓库、发行包、命令 | `beast-pick` |
| Python 导入包 | `beast_pick` |
| 窗口标题 | `BP · 困兽自动搜刮` |
| Windows 构建 | `dist/BP.exe` |
| 打包配置 | `packaging/beast-pick.spec` |
| 日志 | `logs/beast-pick.log` |

旧版本实例锁的名称仅用于迁移兼容，不作为新命名使用。

## 问题报告

请提供系统版本、游戏构建、启用的功能与规则、复现步骤和相关日志。崩溃时说明退出的是工具还是游戏。发布前移除用户名、存档信息和其他个人信息，不提交游戏二进制、内存转储、虚拟环境或构建产物。

提交的项目代码使用与本仓库一致的 [MIT License](LICENSE)。
