# GitHub 搜索展示配置

仓库：<https://github.com/hyhacct/beast-pick>。仓库名保留 `beast-pick`，Windows 程序名保留 `BP.exe`。

## About

Description：

```text
Dying Light: The Beast Auto Loot & Auto Pickup Tool | 消逝的光芒：困兽自动搜刮工具 | Auto-loot corpses, containers and items with customizable filters.
```

Website 使用现有下载入口：

```text
https://github.com/hyhacct/beast-pick/releases/latest
```

Topics（12 个）：

```text
dying-light, dying-light-the-beast, dyinglight, the-beast, auto-loot, autoloot, auto-pickup, auto-looter, game-mod, game-tools, frida, windows
```

登录仓库所有者账号后，在仓库首页 **About → 齿轮** 中设置以上内容。Topics 逐个添加；无需修改仓库名。

## 使用 GitHub CLI 应用配置

需要已安装 GitHub CLI，并通过 `gh auth login` 登录具有该仓库管理权限的账号。Git SSH 推送权限与 GitHub API 登录是两套独立凭据；能推送代码不代表能修改 About。

在 PowerShell 中执行：

```powershell
$repo = 'hyhacct/beast-pick'
$description = 'Dying Light: The Beast Auto Loot & Auto Pickup Tool | 消逝的光芒：困兽自动搜刮工具 | Auto-loot corpses, containers and items with customizable filters.'
$topics = 'dying-light,dying-light-the-beast,dyinglight,the-beast,auto-loot,autoloot,auto-pickup,auto-looter,game-mod,game-tools,frida,windows'
gh repo edit $repo --description $description --homepage 'https://github.com/hyhacct/beast-pick/releases/latest' --add-topic $topics
gh repo view $repo --json description,homepageUrl,repositoryTopics
```

`--add-topic` 会补充标签，保留其他已有标签。GitHub 每个仓库最多允许 20 个 Topics，添加前应检查现有数量。

## Release 标题

后续标签发布会通过 [.github/workflows/release.yml](../.github/workflows/release.yml) 自动使用：

```text
Beast Pick (BP) vX.Y.Z — Dying Light: The Beast Auto Loot
```

现有 v0.3.8 可单独修改展示标题：

```powershell
gh release edit v0.3.8 --repo hyhacct/beast-pick --title 'Beast Pick (BP) v0.3.8 — Dying Light: The Beast Auto Loot'
gh release view v0.3.8 --repo hyhacct/beast-pick --json name,tagName,url
```

该命令修改展示标题，保留版本标签、二进制资产与版本说明。

## 后续展示素材

- README 的中文与英文入口分别为 [README.md](../README.md) 和 [README.en.md](../README.en.md)。更新功能、适配版本或已知限制时同步维护。
- 后续可补充真实界面截图或实机 GIF；发布前核对截图对应版本，避免把本地未发布功能展示为已发布功能。
- 如需在 Nexus Mods 等平台发布介绍，使用真实功能与兼容性说明，并链接到此仓库及下载页。
- 标题、简介与标签能让项目用途更明确，但不保证 GitHub 排名、Google 收录时间或下载增长；效果需通过后续访问与下载数据观察。
