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
| Clash Momo | `clash-momo` | `clash-momo-bin` | cask `clash-momo` |
| Mihomomo | `mihomomo` | `mihomomo-bin` | `mihomomo` |

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

中国网络可将上面的 `Server` 改为 CNB 镜像入口：

```ini
Server = https://packages.fansionia.world/mirror/$arch
```

镜像的数据库、包和签名来自 CNB Release 附件，内容和签名身份与主源一致。
公钥也可从 [CNB 镜像公钥入口](https://packages.fansionia.world/mirror/keys/fansionia.asc)
下载，仍须核对上述指纹。两端全部验证成功才更新仓库入口；CNB 故障会阻止新快照发布。
镜像保留最近两个成功快照及其引用的包。长期未更新、缓存了更旧数据库时，先执行
`sudo pacman -Syyu` 完成数据库刷新和系统升级，再安装软件。

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

Clash Momo 需要 macOS 15 及 Apple Silicon；Cask 自动安装独立的 `mihomomo` Formula，不自动安装或启动系统服务。应用采用 ad-hoc 签名，未经 Apple 公证；验证签名后仅移除已安装应用的隔离属性。

支持 Apple Silicon、macOS 15 及以上。两个来源使用同一个 tap 名称
`fansionia/tap`，首次添加时选择其中一个：

```sh
# GitHub 主源
brew tap fansionia/tap https://github.com/fansion314/packages.git

# 或 CNB 镜像
brew tap fansionia/tap https://cnb.cool/fansionia/packages
```

安装命令对两个来源相同：

```sh
brew install fansionia/tap/dnr fansionia/tap/pi-dnr
brew install --cask fansionia/tap/etcher-dnr
brew install --cask fansionia/tap/clash-momo
```

Homebrew 要求 tap 名称为 `用户/仓库` 两段，不能只写 `fansionia`。
显式提供 Git URL 时，名称无需与实际仓库路径一致；同一台机器上的
`fansionia/tap` 一次对应一个来源。首次添加必须提供完整 URL。
`dnr` formula 提供 `dnr` 和 `dnc`；Pi/Etcher 共享该 runtime，Clash Momo
依赖同一 tap 的 Mihomomo。信任配方后也可用短包名安装。

CNB 的 `main` 自动维护 Homebrew 配方、版本记录及使用说明；开发代码与 CI
仍在 GitHub。镜像配方及内部运行时依赖均从 CNB Release 附件下载，归档和
`.sha256` 文件与 GitHub 原件完全一致。首次同步覆盖当前五个受支持项目，
之后自动跟进新版本；使用独立的 `homebrew-…` Release 标签，不参与 pacman
镜像附件清理。

已添加 `fansionia/tap` 后，切换到 CNB：

```sh
brew tap --custom-remote fansionia/tap https://cnb.cool/fansionia/packages
brew update-reset "$(brew --repository fansionia/tap)"
```

切回 GitHub：

```sh
brew tap --custom-remote fansionia/tap https://github.com/fansion314/packages.git
brew update-reset "$(brew --repository fansionia/tap)"
```

两端的 Git 历史不同，切换后需执行上述定向刷新。它会清除该 tap 检出中的
手工提交和未提交修改；先保存需要保留的修改。必须保留命令中的仓库路径，
不要运行不带路径的 `brew update-reset`。此操作不卸载已安装应用，也不删除
应用配置和数据。日常更新：

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
Homebrew 安装验证、原生 Arch 构建/包测试和正式域名 pacman 安装均在 CI 执行。Homebrew 主源同步可按项目指定 `dnr`、`pi`、`etcher`、`mihomomo` 或 `clash-momo`；留空同步全部项目。随后固定验证后的维护提交，上传并匿名校验 CNB 附件、测试完整候选 tap，再快进发布 CNB `main`，最后从公开镜像执行双向切换和完整安装验收。镜像失败不会撤回已验证的 GitHub 更新；失败的镜像步骤须修复或重跑，无版本变化时也会检查镜像是否完成。
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
