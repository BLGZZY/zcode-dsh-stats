# ZCode DSH Stats

给官方 ZCode Desktop 添加紧凑的 token 统计条，并在客户端更新后自动恢复。

[English](README.md) · **简体中文**

**目录：** [功能](#一眼看清什么) · [Quick Start](#quick-start) · [客户端更新](#zcode-更新后怎么办) · [升级与卸载](#升级或卸载本组件) · [隐私](#数据与隐私) · [文档](#文档与贡献) · [许可](#致谢与许可)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/showcase-dark.png">
  <img src="docs/assets/showcase-light.png" alt="ZCode 输入框下方的 DSH 统计条：轮数、步数、速度、token、缓存命中率和上下文占用。图中使用演示数据。">
</picture>

**不用离开输入框，就能看清这段对话用了多少 token。** 参考 DeepSeek Harness 的紧凑统计体验，在官方 ZCode 输入框外侧下方加一行统计，无需自行编译 ZCode。

## 一眼看清什么

| 展示 | 含义 |
| --- | --- |
| **6 轮 · 58 步 · 204 tok/s** | 已完成的对话轮数、主请求数和平均解码速度。 |
| **5.2M tok · 缓存命中 83%** | 当前保留记录的累计 token，以及输入的缓存命中比例。 |
| **16% 上下文** | 当前会话的原生上下文占用。 |
| **点开任意统计项** | 分别展开会话性能、Token 明细和上下文容量卡片。 |

统计行只有 **24px 高**，窄窗口自动精简，适配明暗主题，分屏会话各自统计。展示图使用**演示数据**；安装后读取你当前会话的本地记录。速度在请求完成后更新，并非逐 token 的流式瞬时速度。

<details>
<summary><strong>展开看看三张详情卡片</strong></summary>

**会话性能**：模型/工具用时、平均首 token 延迟和输出速度。

![会话统计卡片，演示数据](docs/assets/card-activity.png)

**Token 用量**：缓存命中、未缓存输入、缓存读取和输出。

![Token 用量明细卡片，演示数据](docs/assets/card-tokens.png)

**上下文容量**：原生已用量、剩余空间和进度条。ZCode 暂未提供系统/工具/消息的分项 token。

![上下文占用卡片，演示数据](docs/assets/card-context.png)

</details>

## Quick Start

### 方式一：交给 Agent 安装（推荐）

把下面这段话复制给能操作你本机终端的 agent：

```text
请在我这台 Windows 或 Mac 电脑上安装 ZCode DSH Stats，并启用官方 ZCode 更新后的自动恢复。
先读取并遵循安装指南：https://raw.githubusercontent.com/BLGZZY/zcode-dsh-stats/main/INSTALL_FOR_AGENTS.md
请直接完成环境检查、获取代码、安装和结果验证；必要时可通过已有 Homebrew（macOS）或 winget（Windows）安装官方 Python 包，不要静默安装包管理器。
不要构建 ZCode Dev，不要强退正在运行的 ZCode。若被系统权限或兼容性检查阻止，请说明实际原因和我需要做的一步操作。
最后告诉我是否安装成功、自动恢复是否启用，以及是否还需要重启 ZCode。
```

支持具备本机终端权限的 agent；普通网页聊天或远程沙箱无法直接安装到你的本机。[查看 Agent 安装指南](INSTALL_FOR_AGENTS.md)。

### 方式二：手动安装

需要 **Python 3.11+**、Git 和已安装的官方 ZCode Desktop，无 pip 依赖。**已检查的目标：Apple Silicon 上的 macOS / ZCode 3.16.3，以及 Windows 11 x64 上的官方 ZCode 3.14.4。** Windows 已使用现有 Anaconda 基础安装中的 Python 3.11.4 验证安装与真实会话统计界面。暂不支持 Linux；其他客户端版本必须通过兼容检查。

两种平台均先下载源码：

```sh
git clone https://github.com/BLGZZY/zcode-dsh-stats.git
cd zcode-dsh-stats
```

**macOS**：在终端执行：

```sh
python3 setup_auto.py enable
python3 setup_auto.py status
```

**Windows**：在 PowerShell 执行：

```powershell
.\Install.ps1
```

Windows 脚本会寻找已安装的 Python 3.11+，保留其绝对路径供后续自动恢复使用。已有 Python 不在 PATH 时，可传 `-PythonPath 'C:\path\to\python.exe'`（替换成实际路径），无需激活环境或重复安装。安装器自动发现官方 ZCode；自定义路径可用 `.\Install.ps1 -Asar 'C:\path\to\ZCode\resources\app.asar'`。如果 PowerShell 阻止脚本运行，确认 `py -3 --version` 为 3.11+ 后，直接运行 `py -3 setup_auto.py enable`，无需修改执行策略。详见[平台安装说明](docs/guide.zh-CN.md#安装与卸载)。

Windows 首次安装若提示应用文件被占用，先完成当前任务，正常完全退出 ZCode，再重跑安装。安装器不会替你关闭应用。

安装成功会显示 `auto-restore-enabled`。等后台任务结束后，**完全退出并重新打开 ZCode**，进入一个已有的本地会话，输入框下方就会出现统计条。尚未创建会话的新草稿不显示统计。

macOS 也可双击下载目录里的 `Install.command`。遇到 macOS 的 `Operation not permitted`，请看[完整指南](docs/guide.zh-CN.md#安装与卸载)。

> [!NOTE]
> 这是非官方、实验性的扩展，会先备份，再向已安装应用的 `app.asar` 添加加载入口。它不依赖官方输入框插件 API，也不会重新编译 ZCode。未来客户端结构变化时可能需要适配。

## ZCode 更新后怎么办

本地插件会在新建或恢复会话时检查加载入口。若官方更新覆盖了入口，它会检查兼容性、备份新版本并补回入口。Windows 运行中的应用可能锁定文件，此时会启动一个临时后台助手，最多等待 24 小时，等对应官方应用正常退出后重新检查并修复，**下次启动 ZCode 后生效**。禁用恢复或卸载组件会取消待执行修复；不会强退应用，也不创建计划任务或服务。

权限不足或新版结构不兼容时会暂停恢复，详情见[自动恢复说明](docs/guide.zh-CN.md#官方更新后自动恢复)。它负责恢复本组件，不负责升级 ZCode，也不会联网下载本扩展的新版本。

## 升级或卸载本组件

**macOS：**

```sh
# 更新组件及已安装的自动恢复副本
git pull --ff-only
python3 setup_auto.py enable

# 或卸载组件，同时禁用自动恢复
python3 install.py remove
```

**Windows：**更新时运行 `git pull --ff-only`，然后 `.\Install.ps1`；卸载运行 `.\Remove.ps1`。自定义安装继续传同一个 `-Asar`。对应 Python 命令为 `py -3 setup_auto.py enable` 和 `py -3 install.py remove`。

修改后完全退出并重开 ZCode。只想关闭自动恢复、保留统计条，macOS 可执行 `python3 setup_auto.py disable`，Windows 执行 `py -3 setup_auto.py disable`。

## 数据与隐私

采集器**只读**本地用量数据库，按当前会话 ID 查询数字统计。不读取提示词、不访问 API key、不上传遥测，也不额外调用模型。只统计已完成的主请求；记录保留期、缺失的计时和历史缓存口径会影响数字，详见[数据与显示](docs/guide.zh-CN.md#数据与显示)。

安装会写入应用加载入口、组件自身文件和备份，并注册用户级本地插件。自动恢复在修复成功、失败或延后至应用退出时向当前会话提供一条简短维护状态。

## 文档与贡献

- [中文完整指南](docs/guide.zh-CN.md) · [English guide](docs/guide.md)
- [开发、测试与贡献](CONTRIBUTING.md)
- [实现约定](spec.json)

## 致谢与许可

接入方式和 ASAR 格式处理参考 [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar)，保留其 [MIT 许可声明](vendor/LICENSE)。界面参考 DeepSeek Harness，未打包其产品运行时。本项目与 ZCode 官方无隶属关系。

[MIT](LICENSE) © 2026 ZCode DSH Stats contributors.
