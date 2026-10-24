# 2026-10-24：统一维护入口与旧仓库收尾

维护入口为 `fansion314/packages`（本机 `~/Codebase/fansionia-packages`）。
DNR/Pi/Etcher 保留独立源码与发布仓库；四个内部应用的配方、补丁和 CI 发布已迁入本仓库。

## 远端归档

以下 GitHub 仓库已确认 `archived = true`，描述和主页指向统一入口。
归档保留提交、标签和历史 Release，不删除或替换下载资产。

- https://github.com/fansion314/homebrew-dnr
- https://github.com/fansion314/aur
- https://github.com/fansion314/Motrix
- https://github.com/fansion314/deepseek-harness
- https://github.com/fansion314/bitwarden
- https://github.com/fansion314/obsidian

Gitea 账号的对应旧 DSH 仓库是 https://git.fansionia.world/fansion/dsh ，
已在设置页确认“仓库已成功归档”。账号仓库列表未列出其他五个对应旧仓库；
未创建空镜像或修改无关仓库。DNR、Pi、Etcher 保持可维护状态。

## 本机清理与恢复

六个旧检出删除前，均核实无工作区修改、无额外 worktree，并为所有 refs 创建、
验证 Git bundle。本地历史分支以及旧 Homebrew 中未推送的维护文档提交均保留在：

```text
~/.local/share/fansionia-packages/retired-repositories/20261024/
  homebrew-dnr.bundle
  aur.bundle
  Motrix.bundle
  deepseek-harness.bundle
  bitwarden.bundle
  obsidian.bundle
  bitwarden-upstream-clients.bundle
  bitwarden-upstream-sdk-internal.bundle
  cleanup-local.json
  cloudflare-rule-before-packages.json
```

目录权限受限，bundle 文件为 0600。需要恢复时，在不覆盖现有目录的路径克隆：

```sh
git clone ~/.local/share/fansionia-packages/retired-repositories/20261024/Motrix.bundle /path/to/restored-Motrix
```

本机移除了六个旧检出、已不用于成品打包的两个干净 Bitwarden 上游检出、
仍维护项目中的忽略依赖/构建输出，以及此次迁移的专用
临时检出、npm/pnpm 缓存和临时凭据副本。精确清单在 `cleanup-local.json`；
共 65 个删除入口，删除前分配量合计 13,493,105,177 bytes（约 12.6 GiB）。
此统计不是对磁盘空闲量变化的承诺，硬链接、克隆和文件系统统计可能影响回收量。

`../dnr`、`../pi`、`../etcher`、本仓库源码保留；DNR 用户的
`docs/PERFORMANCE.md` 修改和 `docs/PI-STARTUP-PROFILE.md` 保留。
签名离线备份仍在 `~/.local/share/fansionia-packages/signing/`。

## xjtuse 清理

仅处理 `~/xjtuse-arch-dev/workspaces/` 中核实带 `.codex-rsync-owned` 的
本批项目工作区。过滤 Git 跟踪文件和活动进程后删除构建依赖、缓存及输出；
builder UID 所有文件通过现有 rootless Arch 容器删除，没有使用 sudo 或改变宿主权限。

精确清单：`/home/fansion/packages-cleanup-20261024/cleanup-remote.json`。
共 801 个删除入口，删除前分配量合计 21,145,424,078 bytes（约 19.7 GiB）。
已复查清单路径均不存在。远端源码副本及其独有修改保留。

共享 pnpm store、Cargo/rustup/sccache、系统依赖、GPU 桌面容器、无关项目及用户
数据未清理。后续如需清理共享存储，须另行明确范围，不能按本记录 blanket prune。

## 验证与尚未完成的上线条件

- 六个 GitHub 归档状态、Gitea 归档成功提示、六份 bundle 与删除路径均已核实。
- 文档代码块、相对链接和 `git diff --check` 通过。
- `fac0847` 对应完整 CI（[40080528122](https://github.com/fansion314/packages/actions/runs/40080528122)）通过：静态检查、原生签名数据库集成和四应用构建/烟雾测试。
- 六项目新版本已公开；Homebrew/paru 的迁移后同步成功。签名 pacman 输入完整。
- 最初上线被免费 Bot Fight Mode 质询阻塞。随后用户明确授权关闭该 zone 的此项功能，
  已核对其他机器人设置和既有自定义 WAF 规则保持原值。
- 修复 Python 直接执行 pnpm shell shim 的 Exec format error，改用 Node 启动已锁定的
  项目 Wrangler。重试复用完整已签名快照，没有覆盖应用 Release 或数据库字节。
- 首个正式快照 `140d9b39410eaf2091e8dc7a1e243de5` 已激活。
  [发布流水线 40107812988](https://github.com/fansion314/packages/actions/runs/40107812988)
  全部通过：输入探测、签名快照、Pages、候选 pacman 安装、Worker 两阶段部署、
  **正式域名 pacman 安装**。最终部署代码提交为 `4f490dc`。
- 独立检查确认 `/status.json` 为 active、数据库与签名指向同一不可变 Pages 快照、
  包与签名跳转到准确 Release、公钥与 Git 跟踪字节一致、未知路径 404、POST 405。
