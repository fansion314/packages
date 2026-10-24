# Arch Linux 和 CachyOS

[English](README.md) | 中文

## 概要

`dsh-electron` 从源码构建 DeepSeek Harness；`dsh-electron-bin` 安装预构建应用。两者均面向 x86_64，依赖 Arch 的 `electron` 软件包，不捆绑 Electron。这些是 [fansion314/packages](https://github.com/fansion314/packages) 提供的社区软件包，独立于上游桌面版发行。

## 目录

- [安装](#installation)
- [发行构建](#release-builds)
- [系统软件包](#system-packages)
- [运行环境](#runtime)

## 安装 {#installation}

GitHub 发行版仅保存一份可用 `sudo pacman -U` 直接安装的 `.pkg.tar.zst` 包。`dsh-electron-bin` PKGBUILD 下载并校验该包，随后由 makepkg 重新打包供 AUR 安装。源码与二进制配方及其 `.SRCINFO` 位于此目录。工作流不会向 aur.archlinux.org 上传配方。

桌面启动命令为 `dsh-desktop`；侧栏、窗口标题和应用菜单名称为 DeepSeek Harness。两个软件包相互冲突。应用通过 pacman 或 AUR 助手更新；上游应用内更新器处于停用状态。系统 Electron 优先读取对应版本的参数文件，再回退到 `~/.config/electron-flags.conf` 读取显示和 Chromium 选项。

软件包同时安装 `dsh`，使用同版本上游 CLI，并通过 Electron Node 运行内置 pnpm。`dsh web --host 127.0.0.1 --port 0 --no-open` 启动 Web 界面但不自动打开浏览器。CLI 保留 `headless`、`sdk`、`sdk-minimal` 和 `acp` profile、配置导出，以及 `dsh plugin --profile <name> ...` 包管理功能。模型请求仍需要模型提供方凭据。CLI profile 与保留的 Desktop profile 各自使用配置和插件安装目录；窗口与托盘集成由 `dsh-desktop` 提供。

## 发行构建 {#release-builds}

[工作流](https://github.com/fansion314/packages/blob/main/.github/workflows/release.yml) 在 Arch 容器内以非特权用户构建。它使用固定的 AUR 配方构建官方仓库中缺失的 `python-pptx`；本地安装需要该 AUR 依赖，或由已配置仓库提供的等效软件包。推送 `deepseek-harness-v<upstream-version>-<pkgrel>` 标签后，运行检查和打包成功才会发布 pacman 包。手动运行仅生成 Actions 构建产物，不发布发行版。打标签前，两个配方的版本和发行编号必须一致。

构建使用仓库固定的 pnpm，编译桌面端和 Web 前端，并部署生产 JavaScript 依赖。运行时解释器和 Python 库由 pacman 提供。发布前执行原生模块、PTY、搜索、Host、前端、Office 转换和 Electron 窗口检查。发行配方写入实际软件包校验和并生成 `.SRCINFO`；提交到 AUR 前，仓库内二进制配方必须与发布包一致。

## 系统软件包 {#system-packages}

| 能力 | 运行时使用的 Arch 软件包 |
|---|---|
| 桌面界面 | `electron` |
| Host 和 JavaScript 执行 | `electron` 提供的 Node |
| 插件包操作 | 随包提供的 pnpm，由 Electron Node 运行 |
| Python 解释器 | `python` |
| 数据分析 | `python-numpy`, `python-pandas` |
| Word 和 PowerPoint 创作 | `python-docx`, `python-pptx` |
| Excel 创作 | `python-openpyxl`, `python-xlsxwriter` |
| 图像和 XML | `libvips`, `python-pillow`, `python-lxml` |
| Python 配套库 | `python-dateutil`, `python-six`, `python-tzdata`, `python-typing_extensions`, `python-et-xmlfile` |
| 文件搜索 | `ripgrep` |
| 原生库和桌面集成 | `glibc`, `gcc-libs`, `xdg-utils` |

两个配方均声明这些依赖。已安装的软件包可共享使用；发行包缩小并不免除缺失系统依赖所需的磁盘空间。仅构建时需要的工具包括 Git、Rust、Clang、CMake、Node.js、pnpm、node-gyp 和 pkgconf。

DSH 专用的 `libreoffice-kit-wasm` 引擎仍随包提供：文档预览和转换使用其 JavaScript/worker API，而非系统 `libreoffice` 命令。已验证的 npm 依赖图、原生 Node 绑定和语音引擎仍由应用软件包管理。Sharp 编译时链接系统 libvips，不附带其预编译 libvips 二进制。通过现有桌面文件策略排除其他平台的 PTY 二进制、源码映射和 TypeScript 声明。

## 运行环境 {#runtime}

资源位于 `/usr/lib/dsh-electron`。启动器使用 Desktop 可配置的资源路径，并关闭开发者工具。用户配置仍保存在常规 DSH 主目录。Arch 的 `electron` 软件包跟随最新稳定版；主版本升级后，应先验证桌面端和原生模块，再继续依赖现有二进制包。

启动器使用 Electron Node 运行 Host、包操作和主 JavaScript 运行时。它读取当前系统 Python 分发包版本，仅在 `${XDG_CACHE_HOME:-~/.cache}/dsh-electron/runtimes` 下创建元数据、链接和 Python 启动脚本。Python 别名直接指向版本化启动脚本，由它执行 `/usr/bin/python`；库路径链接到 `/usr/lib`。Host 就地使用这些依赖，不将 `/usr` 或解释器复制到 `~/.dsh`。系统版本变化后更新元数据。缺少依赖时启动会报错。系统 Python 遵循 Arch 的外部管理环境策略；额外的系统库通过 pacman 安装，也可使用工作区虚拟环境。

Linux 常驻应用托盘图标。激活图标可恢复窗口；右键菜单提供打开、关于、检查更新、刷新页面、重启应用与 Host 以及退出。关闭工作区或欢迎窗口会隐藏窗口，任务继续运行。桌面环境需支持系统托盘。如果托盘创建失败，关闭窗口则退出。Linux 托盘激活动作由桌面环境决定，可能需要双击。

Arch 构建对部署后的内部模块辅助包应用一个小型[兼容补丁](require-builtin.patch)：显式传入 `--expose-internals` 时使用 Node 内置加载器，无需探测 Electron 的 V8 内存布局。工作区和上游依赖源码保持不变。运行时冒烟检查使用已安装的 Electron 版本验证该辅助包和重编译的 sharp 扩展。

应用 JavaScript、前端资源和 dsh 依赖树存放在 `app.asar` 中。相邻的 `app.asar.unpacked` 按上游 Desktop 的排除规则保留原生库、可执行辅助程序和完整的 Office 包依赖。pnpm、其 Node 启动器和 Office 技能资源保留在 `runtime/`，因为外部进程需要真实路径。ASAR 只做归档，不负责压缩；用户配置、插件安装目录和工作区仍在归档外可写。打包流程会在发布前验证归档中的 Host、原生模块、前端、插件加载、PTY、搜索、包脚本和 Office 转换。
