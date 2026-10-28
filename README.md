# fansion314/packages

统一维护 Homebrew、签名 pacman 二进制仓库和 paru PKGBUILD 仓库。
GitHub 源码与发布地址：**https://github.com/fansion314/packages**。
应用保留原名称、配置目录和用户数据；DNR、Pi、Etcher 的源码仍在各自仓库维护。

| 应用 | pacman 包名 | paru 预编译配方 | Homebrew |
| --- | --- | --- | --- |
| DNR / DNC | `dnr`、`dnc` | `dnr-bin`、`dnc-bin` | `dnr`（包含两条命令） |
| DNR CEF / WebView 后端 | `dnr-cef` / `dnr-webview` | `dnr-cef-bin` / `dnr-webview-bin` | — |
| Pi | `pi-dnr` | `pi-dnr-bin` | `pi-dnr` |
| Etcher | `etcher-dnr` | `etcher-dnr-bin` | cask `etcher-dnr` |
| Motrix | `motrix-electron` | `motrix-electron-bin` | — |
| DeepSeek Harness | `dsh-electron` | `dsh-electron-bin` | — |
| Bitwarden | `bitwarden-electron` | `bitwarden-electron-bin` | — |
| MyGo 云音乐 | `mygo-cloudmusic` | `mygo-cloudmusic-bin` | — |
| Obsidian | `obsidian-electron` | `obsidian-electron-bin` | — |
| Clash Momo | `clash-momo` | —（源码配方：`clash-momo`） | — |
| Mihomomo | `mihomomo` | —（源码配方：`mihomomo`） | — |

所有 DNR 后端包是互斥替代品。Arch 仓库还提供 DSH 需要的 `python-pptx`
和签名公钥维护包 `fansionia-keyring`。Bitwarden/Obsidian 使用官方成品应用和
系统 Electron，包内不重复附带 Electron。MyGo 云音乐使用 Go 原生界面，
仅通过可重放补丁增加设置中的界面缩放（75%–200%，立即生效并保存）。

## Arch Linux / CachyOS：直接用 pacman

支持 x86_64，及可在其上安装的 `any` 包。下载源是准确版本的 GitHub Release
资产，不在用户机器上编译或重新打包，也没有额外的 `-bin` 变体。

### 1. 导入并核对签名公钥

```sh
curl -fLO https://packages.fansionia.world/keys/fansionia.asc
gpg --show-keys --with-fingerprint fansionia.asc
```

核对完整主密钥指纹，与本仓库的 [公开密钥](arch/keys/) 交叉确认：

```text
338A EAB6 4ECF 2EF6 9AAF 3EEF DF31 7480 72E5 B972
```

确认后建立本地信任：

```sh
sudo pacman-key --add fansionia.asc
sudo pacman-key --lsign-key 338AEAB64ECF2EF69AAF3EEFDF31748072E5B972
```

### 2. 添加仓库

在 `/etc/pacman.conf` 现有官方仓库之后添加，保留其他配置：

```ini
[fansionia]
SigLevel = Required TrustedOnly
Server = https://packages.fansionia.world/$arch
```

### 3. 更新并选择应用安装

```sh
sudo pacman -Syu fansionia-keyring
sudo pacman -S dnr dnc pi-dnr etcher-dnr
sudo pacman -S motrix-electron dsh-electron bitwarden-electron obsidian-electron
sudo pacman -S mygo-cloudmusic
sudo pacman -S clash-momo  # 自动安装 mihomomo 和系统 Electron
```

按需安装即可，不必安装上面所有应用。依赖由 pacman 自动解析。
日常用 `sudo pacman -Syu` 更新；不要仅刷新数据库后做部分升级。
例如要明确选本仓库，可以使用 `sudo pacman -S fansionia/pi-dnr`。

此前安装了对应 `-bin` 包时，显式安装上表的 pacman 包名，并检查冲突替换提示。
`dnr`、`dnr-cef`、`dnr-webview` 不能同时安装，请按需要选择一个后端。

## Arch Linux / CachyOS：用 paru 配方

如果需要检查或修改构建配方，可以继续使用 paru。此方式与二进制 pacman
仓库是两种安装途径；`-bin` 配方仍会由 makepkg 生成安装包。

在 paru 配置（如 `~/.config/paru/paru.conf`）中添加：

```ini
Include = /etc/paru.conf

[fansionia]
Url = https://github.com/fansion314/packages.git
Path = aur/packages
```

已有配置保留其内容，`Include` 不要重复添加。如果显式设置了 `Mode`，包含
`pkgbuilds`。迁移时用以上条目替换旧仓库条目，不要删除无关仓库。

```sh
paru -Syu
paru -S dnr-bin pi-dnr-bin etcher-dnr-bin
paru -S motrix-electron-bin dsh-electron-bin
paru -S bitwarden-electron-bin obsidian-electron-bin
paru -S mygo-cloudmusic-bin  # 源码构建可选 mygo-cloudmusic
paru -S clash-momo mihomomo
```

可用 `paru -S fansionia/dnr-bin` 明确选择本配方仓库。保留 paru 的正常配方审阅。
应用配方还提供去掉 `-bin` 的变体：Motrix/DSH/MyGo 云音乐从源码构建，
Bitwarden/Obsidian 的配方重打包官方成品。源码与 bin 变体是替代关系。

## macOS：用 Homebrew

支持 Apple Silicon、macOS 15 及以上：

```sh
brew tap fansion314/packages https://github.com/fansion314/packages.git
brew install fansion314/packages/dnr fansion314/packages/pi-dnr
brew install --cask fansion314/packages/etcher-dnr
```

仓库名不带 `homebrew-` 前缀，首次 tap 必须提供完整 URL。
`dnr` formula 提供 `dnr` 和 `dnc`；Pi/Etcher 共享该 runtime。
信任配方后也可用短包名安装。

从旧 tap `fansion314/dnr` 迁移时先添加新 tap，然后可按需重装对应新来源：

```sh
brew reinstall fansion314/packages/dnr fansion314/packages/pi-dnr
brew reinstall --cask fansion314/packages/etcher-dnr
brew untap fansion314/dnr
```

只重装已使用的应用。若 untap 提示仍有旧来源安装，先按提示检查并迁移这些应用，
再移除旧 tap；不要用 `--force` 触发卸载。日常更新：

```sh
brew update
brew upgrade
```

Etcher 采用 ad-hoc 签名，未经过 Apple notarization；cask 验证签名后仅移除
已安装 Etcher app 的隔离属性，不修改全局 Gatekeeper 或用户数据。

## 发布与故障排查

包和数据库均要求受信任签名。GitHub Pages 承载版本化 `.db`/`.files` 和签名；
Cloudflare Worker 把精确文件名跳转到 Pages 或固定 Release 下载链接。
Worker 嵌入映射配置，不使用 KV，不运行时拉 JSON。保留最近最多 32 个完整快照；
先部署兼容新旧包的映射，再切换 active 数据库。应用 Release 资产不被替换。

- [仓库状态](https://packages.fansionia.world/status.json)：显示当前 active 快照与阶段。
- 下载公钥或数据库返回 404 且正文为 `Repository initialization in progress`：首个快照尚未完成，不能按已上线处理。
- 返回 HTML/403 或 JavaScript 质询：这是下载入口防护配置问题。pacman 无法完成浏览器挑战，应由维护者修复，不要关闭客户端签名验证。
- 签名失败：先核对系统时间、公钥指纹和 `fansionia-keyring` 状态；不要用 `SigLevel = Never` 绕过，也不要信任来源不明的替代密钥。
- 网络失败：包会跳转至 GitHub Release，需要能访问相应下载地址；Worker 不代理包体。

发布源主动通知下游，每 15 分钟另有定时兜底；GitHub 调度可能延迟。
本仓库的标签发布会异步调度 `main` 上的 `downstream.yml`，须独立跟进该运行及正式域名安装结果。
Homebrew 安装验证、原生 Arch 构建/包测试和正式域名 pacman 安装均在 CI 执行。
CI 烟雾测试不代表手动 GUI 或物理 USB 设备已经验收。

## 维护入口

后续 agent 和维护者首先阅读 [AGENTS.md](AGENTS.md)，签名、部署、回滚和密钥
续期见 [arch/README.md](arch/README.md)。

- `packages/<id>/manifest.json`：内部项目的版本、打包号与固定源。
- `packages/<id>/recipes/`、`patches/`、`overlay/`：配方与最小兼容改动。
- `homebrew/`、`aur/`：生成器、测试、配方来源及同步记录。
- `Formula/`、`Casks/`、`aur/packages/` 是生成结果，应修源模板后由 CI 更新。
- DNR/Pi/Etcher 仍从各自源码仓库发布；内部项目用
  `<id>-v<version>-<pkgrel>` 标签在本仓库发布。完整历史导入点见 `imports.json`。
- 旧 `homebrew-dnr`、`aur` 及内部项目的用户 fork 退为历史归档；新版维护统一在本仓库，旧 Release 仍用于历史下载。

本地允许的逻辑检查：

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s homebrew/scripts -p 'test_*.py' -v
python3 -m unittest discover -s aur/tests -v
python3 -m unittest discover -s arch/tests -v
node --test arch/tests/*.test.mjs
git diff --check
```

应用编译、makepkg 和安装验证只在 CI。发布后主动触发并跟进同步，不能仅等待定时任务：

```sh
gh workflow run downstream.yml -R fansion314/packages --ref main
```
