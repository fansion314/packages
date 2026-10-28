# 统一软件发布仓库维护指南

本仓库是 **`fansion314/packages`**，维护分支为 `main`；本机目录为
`/Users/peilin/Codebase/fansionia-packages`。目录名不是 GitHub 仓库名。
它是 Homebrew、paru 配方和签名 pacman 仓库的唯一维护入口。

## 任务含义与基本约束

- 用户给出“项目 + 版本”默认授权核实上游、更新源码/成品配方、解决兼容问题、提交推送、CI 发布、同步适用下游并验证完成。跟进时从最早未完成步骤继续；不要重复递增版本、移动标签或重复发布。
- **本机不编译、不重建原生模块、不运行 makepkg、不安装应用验收。** 应用构建、打包和安装测试均交 GitHub Actions。允许 Git、元数据生成、lint、无产物类型检查和不触发构建的针对性测试；先读脚本，不能把 bundle、cargo check/test 或安装生命周期当静态检查。
- 补充远端验证前读 `/Users/peilin/.codex/CROSS_PLATFORM.md`，使用 xjtuse 原生 Arch 与增量同步。Rust 默认保留 sccache；权限问题申请提权，不清空 wrapper。不要自动创建本地 ExecPlan。
- 本机命令遵守 `/Users/peilin/.codex/RTK.md`。外部信息优先网页搜索；标签、提交、Actions、Release 优先 Git/GitHub API。依赖选兼容的最新稳定版，指定的 beta/rc 应用沿指定通道发布。
- 保留用户修改、既有应用身份、配置目录、数据与 fork 功能。不自动 stash/reset、不重写公开历史、不 force-push main。提交只包含本任务路径，使用英文 Conventional Commits。
- 新建前端默认 Node + pnpm + Vite+；既有项目保留工具链、锁文件。Pi 用 npm，不为统一工具迁移。新应用 ID 默认为 `world.fansionia.xxx`，既有应用不改 ID。

## 项目归属与唯一发布入口

| 项目 | 实际维护位置 | 发布标签 / 工作流 | 下游 |
| --- | --- | --- | --- |
| dnr / dnc | `../dnr`，`fansion314/dnr` | `v<V>`；`release-arch.yml`、`release-macos.yml` | 三种渠道 |
| Pi / Pi-dnr | `../pi`，`fansion314/pi` | `pi-dnr-v<V>-<R>`；`release-dnr.yml`、`release-dnr-macos.yml` | 三种渠道 |
| Etcher | `../etcher`，`fansion314/etcher` | `v<V>-dnr.<R>`；`release-dnr-arch.yml`、`release-dnr-macos.yml` | 三种渠道 |
| MyGo 云音乐 | `packages/mygo-cloudmusic/` | `mygo-cloudmusic-v<V>-<R>`；`release.yml` | paru + pacman |
| Motrix | `packages/motrix/` | `motrix-v<V>-<R>`；`release.yml` | paru + pacman |
| DeepSeek Harness / DSH | `packages/deepseek-harness/` | `deepseek-harness-v<V>-<R>`；`release.yml` | paru + pacman |
| Bitwarden | `packages/bitwarden/` | `bitwarden-v<V>-<R>`；`release.yml` | paru + pacman |
| Obsidian | `packages/obsidian/` | `obsidian-v<V>-<R>`；`release.yml` | paru + pacman |
| python-pptx、fansionia-keyring | `arch/support/<id>/PKGBUILD` | `<id>-v<V>-<R>`；`release-support.yml` | pacman |
| Clash Momo | `../clash/clash-momo`，`fansion314/momo` 的 `clash-momo` 分支 | `clash-momo-v<V>-<R>`；`release-arch.yml` | paru + pacman |
| Mihomomo | `../clash/mihomomo`，`fansion314/momo` 的 `mihomomo` 分支 | `mihomomo-v<V>-<R>`；`release-arch.yml` | paru + pacman |

- Clash Momo 与 Mihomomo 共用仓库，按各自标签族选择版本；先发布内核，再发布依赖该签名内核的客户端。上游来源记录在各分支 `UPSTREAM.json`，后续以补丁同步并追加提交。
- 版本、打包号和准确上游提交以 `packages/<id>/manifest.json`、支持包 PKGBUILD 或外部源码仓库为准，不能依赖本文件中的历史版本。
- 内部项目的源码与 bin 配方共用一个 Release。Bitwarden/Obsidian 使用官方 Linux 成品和系统 Electron，不合并官方源码、不重复携带 Electron；必须验证原生模块、bootstrap、应用布局及 ABI。
- Motrix/DSH/MyGo 云音乐从 manifest 固定的准确上游提交构建。fork 修改存为有序 `patches/series`；`overlay/` 仅放新增文件，不能覆盖现有上游文件。补丁冲突必须审阅并修复，禁止失败后静默跳过。
- DNR/Pi/Etcher 进入后读各自 AGENTS.md 和发布文档。DNR 上游同步依 `docs/UPSTREAM.md`，保留可重放补丁和严格 CEF ABI/hash 检查；不要修改用户上游 mirror。CEF 默认跟随已验证稳定 API，显式新 API 需独立 CI 验证。
- Pi 保留 DeepSeek/Azure 适配、DNR ESM 启动器、原生 groups、资源、worker；生成文件从生成器更新。Pi 维护提交和 DNR 标签同步 GitHub `github` 与 Gitea `origin`；DNR/Etcher 按其现有镜像政策，不把 `origin` 假设成 GitHub。
- Pi 仅保留 `release-dnr.yml`、`release-dnr-macos.yml`、`backfill-signatures.yml`；合并上游后不得恢复其 npm/Nix/环境守护等工作流。其他项目也不启动上游 npm、PyPI、Snap 或官方多平台发布。
- 旧的 `homebrew-dnr`、`aur`、`Motrix`、`deepseek-harness`、`bitwarden`、`obsidian` 用户仓库是迁移历史，只读归档。`imports.json` 记录原始导入点，不是后续版本来源；不要恢复其自动发布。旧 Release 链接须保持可读。Songjian 等私有/本地应用不进入此仓库。

## 目录与生成边界

- `packages/<id>/manifest.json`：应用版本、pkgrel、固定源与迁移来源；`recipes/`：配方模板；`patches/`、`overlay/`：最小兼容修改。
- `scripts/package.py`：固定源准备、补丁与配方生成、发布输入整理；`scripts/build.sh`：CI 普通用户构建与应用质量/烟雾检查；`scripts/publish.py`：不可变资产发布。
- `homebrew/`：Homebrew 生成器、模板、测试与 release 记录；`aur/`：paru 同步/验证逻辑、来源清单和生成结果；`arch/`：签名、二进制仓库、Worker、支持包。
- **生成结果**：`Formula/`、`Casks/`、`homebrew/releases/`、`aur/packages/`、`aur/state/`。优先修源配方、模板或生成器，由验证通过的 CI 自动提交；不能在生成结果中制造独立分叉。
- `.cache/`、`.work/`、`dist/`、`arch/generated/` 和 `node_modules/` 是可重建产物；不提交它们、私钥、token、密码或临时日志。`pacman-pages` 分支是已发布数据库状态，不是可随意删除的缓存。

## 更新与发布顺序

1. 检查工作区、暂存区、分支、远端及真实 HEAD；保留用户修改。核实准确上游标签、提交和迁移说明，不混入该标签以后的 main 提交。不要覆盖同名本地/公开标签。
2. 更新 manifest 或外部源仓库、必要补丁/锁文件/配方/资源与版本。新应用版本通常 pkgrel=1，同版本变更递增 pkgrel；macOS package_revision 与 pkgrel 分开。
3. 源码/生成文件从真实源更新。依赖安装先禁生命周期，避免本地编译。Pi 可用 `PI_SKIP_BUILD_CHECKS=1 npm run check`，远端发布仍须完整检查。检查钩子，不静默禁钩子或伪造通过。
4. 完成本地适用检查，提交推送 main，等待对应 SHA 的 `ci.yml` 门禁。CI 失败读具体 job 日志；产品相关失败须修复，不能忽略或弱化测试。无关平台失败也须说明影响。
5. CI 通过后创建并推送准确发布标签。内部项目亦可 `gh workflow run release.yml -R fansion314/packages --ref main -f release_tag=<tag>`；支持包用 `release-support.yml`。一次 push 超过 3 个标签可能不触发 GitHub 工作流，需逐个推送或用准确既有标签 dispatch，不能重新打标签。
6. 等待构建、烟雾测试、签名、公开 publish 全部完成；核对 tag SHA、实际资产 SHA-256、`.sha256` 和存在的 GitHub asset digest。公开同版本资产不得覆盖；重试已完成的资产必须复用准确原字节。
7. 触发并跟进下游：`gh workflow run downstream.yml -R fansion314/packages --ref main`；可用 `-f project=<id> -f platform=arch`（或 macos）缩小同步。主动发布不以“等定时任务”为收尾。
8. 检查公开 Release、远端配方版本、pacman `/status.json` 和正式域名安装 CI。工作区干净时再快进同步 CI 自动提交，避免与生成器抢提交。只报告完成证据，触发/运行中不是发布成功；GUI/物理设备未验收须明确。

## Homebrew 与 paru

- Homebrew 只允许 dnr、pi-dnr、etcher-dnr；tap 为 `fansion314/packages`，必须显式 URL `https://github.com/fansion314/packages.git`。Apple Silicon/macOS 15+；Pi/Etcher 共享 dnr。Etcher 维持 ad-hoc 签名，不宣称 Apple notarization；隔离属性只从安装的 Etcher app 删除。
- `homebrew/scripts/sync.py` 生成 formula/cask/release 记录；版本比较为数字 key `[major, minor, patch, packaging_release, macos_revision]`，拒绝降级、同 key 更换 URL/哈希。
- paru 配方仓库名 `fansionia`，URL 同上，`Path = aur/packages`。源码/bin 是互斥选择；普通使用 `paru -S dnr-bin` 等短名称。pacman 二进制仓库没有额外 `-bin` 变体。
- `aur/sources.json` 是项目、配方与排除项的权威清单。外部 Release 完整且 bin 配方回写后同步；Motrix 配方取正式 Release 的 recipe bundle，避免默认分支回写时序造成旧内容。
- bin 校验和来自公开 CI 真字节，保留 provides/conflicts、许可证与 runtime 依赖。原生 Arch 普通用户验证 `makepkg --printsrcinfo` 和 bin 打包；源码配方元数据通过不等于全量源码构建通过。
- `sync-homebrew.yml` 每小时 17/47 分，`sync-aur.yml` 每小时 23 分；调度可能延迟。默认让验证后的 workflow 自动提交生成结果。

## pacman、签名和 Cloudflare

- 公共入口 `https://packages.fansionia.world`；仓库名 `fansionia`，x86_64（同时接收 any）。15 个包由 `arch/sources.json` 显式列出；直接索引准确 GitHub Release `.pkg.tar.zst`，不重新打包、不复制应用到 Pages。
- 主公钥指纹 `338AEAB64ECF2EF69AAF3EEFDF31748072E5B972`，`arch/keys/` 仅公开材料。每个发布仓库各有签名子密钥；校验实际 `.PKGINFO`、摘要、签名和预期来源子密钥，不得只检查文件存在。
- Actions secrets：`ARCH_SIGNING_PRIVATE_KEY`、`ARCH_SIGNING_PASSPHRASE`、`ARCH_SIGNING_KEY_ID`；只上传所属签名子密钥，主认证私钥绝不上传。`backfill-signatures.yml` 只为验证过的旧公开原字节补 `.sig`，不改包。
- 离线恢复资料在维护机 `~/.local/share/fansionia-packages/signing/`，恢复密码位于登录 Keychain 的 service `world.fansionia.packages.signing` / account `primary-key-recovery`。不读出到日志，不在清理时删除。子密钥到期前 45 天拒绝发布；续期/吊销/轮换按 `arch/README.md`。
- `publish-pacman.yml`：固定维护 SHA → 签名输入验证 → 完整数据库快照 → 持久化 `pacman-pages` → Pages → 候选真实 pacman 安装 → Worker 两阶段部署 → 正式域名真实安装。
- Pages 地址 `https://fansion314.github.io/packages/`。数据库/签名采用不可变快照，最多保留 32 个（包含 staged candidate，active 不淘汰）；别删除 generated branch 或重写快照。最新匹配 Release 不完整时失败，不默默退回旧版。
- Worker `fansionia-packages` 只将精确路径 302 到嵌入的 Pages/Release URL；不使用 KV、不运行时拉 JSON、不代理包体。prepare 同时含新旧映射且仍选旧 DB；确认部署后 active 切新 DB。HTTP 检查是操作门禁，不宣称跨独立 HTTP 请求的全球原子事务。
- 回滚要选择保留的旧数据库、同时保留新包映射，不能直接恢复缺新映射的历史 Worker。激活后公开安装失败可重跑 failed job；新手动 publication 也会重新验收已 active 的快照，定时无变化时不重复安装/部署。
- Cloudflare account `86191ab109215f74781aef56cee40263`；现有 Custom Domain/TLS 已配置。`CLOUDFLARE_API_TOKEN` 只授已有 fansionia-packages Worker 的 Editor；日常 versions upload/deploy 不改域名。Wrangler 由 `arch/package.json` 和锁文件固定，不升级到未验证版本。Python 部署器直接用 Node 启动项目内的 `wrangler/bin/wrangler.js`，避免 pnpm shell shim 在直接 subprocess 调用中出现 Exec format error。
- 非浏览器客户端必须可访问包域名：国家质询规则排除该 hostname，并仅对此 hostname 跳过 Browser Integrity Check。免费 Bot Fight Mode 没有主机名例外；如它拦截，关闭会影响整 zone，须有用户明确授权，不能擅自关闭全站防护或升级付费计划。
- 2026-10-24 已获用户授权关闭该 zone 的免费 Bot Fight Mode；其余机器人设置和自定义 WAF 保留。首个正式域名仓库发布及真实 pacman 安装通过；不要为恢复默认设置而重新开启会拦截仓库客户端的挑战功能。当前 active 以线上 `/status.json` 为准，不把初始快照 ID 当永久配置。
- 外部源用 GitHub App 通知本仓库：App `fansionia-package-distribution`，仅安装到 packages，Actions write/Metadata read；源仓库变量 `DISTRIBUTION_APP_ID` 与 secret `DISTRIBUTION_APP_PRIVATE_KEY`。勿把普通 GITHUB_TOKEN 当跨仓库 dispatch 凭据。
- `downstream.yml` 每小时 4/19/34/49 分兜底；`arch/dispatch.py` 只恢复 `disabled_inactivity`，尊重 `disabled_manually`。GitHub 对 fork 的整仓 Actions 禁用可能仍需人在网页确认，不能声称 API enable 永远足够。

## 本地检查与收尾

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s homebrew/scripts -p 'test_*.py' -v
python3 -m unittest discover -s aur/tests -v
python3 -m unittest discover -s arch/tests -v
node --test arch/tests/*.test.mjs
git diff --check
```

原生 repo-add 集成、完整应用构建、`arch/test-install.sh`、Homebrew 安装脚本只在可丢弃 CI 环境运行。按改动选择检查；已通过且没有新问题时不无意义重复全量测试。gh 日志缓存权限不足可指定 `XDG_CACHE_HOME=/private/tmp/fansionia-gh-cache`，不要借此禁签名或更改 Git 全局配置。

删除旧检出前核实 remote archive、未推送分支、untracked 和 worktree；独有历史先保留 Git bundle。清理用审核过的精确路径白名单；仅删项目可重建依赖/产物，不对共享 pnpm/Cargo/sccache/容器存储做 blanket prune，不删仍在用的源码、运行环境、密钥或用户数据。远端副本须核对同步 ownership 和活动进程；有独有修改先保留。
