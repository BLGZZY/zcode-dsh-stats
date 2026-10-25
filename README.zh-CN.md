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
请在我的 Mac 上安装 ZCode DSH Stats，并启用官方 ZCode 更新后的自动恢复。
先读取并遵循安装指南：https://raw.githubusercontent.com/BLGZZY/zcode-dsh-stats/main/INSTALL_FOR_AGENTS.md
请直接完成环境检查、获取代码、安装和结果验证；必要时可通过已有 Homebrew 安装 Python。
不要构建 ZCode Dev，不要强退正在运行的 ZCode。若被系统权限或兼容性检查阻止，请说明实际原因和我需要做的一步操作。
最后告诉我是否安装成功、自动恢复是否启用，以及是否还需要重启 ZCode。
```

支持具备本机终端权限的 agent；普通网页聊天或远程沙箱无法直接安装到你的 Mac。[查看 Agent 安装指南](INSTALL_FOR_AGENTS.md)。

### 方式二：手动安装

需要 **macOS**、可通过 `python3` 调用的 **Python 3.11+**、Git，以及安装在 `/Applications/ZCode.app` 的官方 ZCode。不需要安装 pip 依赖。目前针对 **Apple Silicon 上的 ZCode 3.16.3** 做过兼容检查；Windows、Linux 和其他客户端版本尚未验证。

```sh
git clone https://github.com/BLGZZY/zcode-dsh-stats.git
cd zcode-dsh-stats
python3 setup_auto.py enable
python3 setup_auto.py status
```

安装成功会显示 `auto-restore-enabled`。等后台任务结束后，**完全退出并重新打开 ZCode**，进入一个已有的本地会话，输入框下方就会出现统计条。尚未创建会话的新草稿不显示统计。

也可双击下载目录里的 `Install.command`。遇到 macOS 的 `Operation not permitted`，请看[完整指南](docs/guide.zh-CN.md#安装与卸载)。

> [!NOTE]
> 这是非官方、实验性的扩展，会先备份，再向已安装应用的 `app.asar` 添加加载入口。它不依赖官方输入框插件 API，也不会重新编译 ZCode。未来客户端结构变化时可能需要适配。

## ZCode 更新后怎么办

本地插件会在新建或恢复会话时检查加载入口。若官方更新覆盖了入口，它会检查兼容性、备份新版本并补回入口，**下一次正常重启 ZCode 后生效**。不会强退应用或中断后台任务。

权限不足或新版结构不兼容时会暂停恢复，详情见[自动恢复说明](docs/guide.zh-CN.md#官方更新后自动恢复)。它负责恢复本组件，不负责升级 ZCode，也不会联网下载本扩展的新版本。

## 升级或卸载本组件

```sh
# 更新组件及已安装的自动恢复副本
git pull --ff-only
python3 setup_auto.py enable

# 或卸载组件，同时禁用自动恢复
python3 install.py remove
```

修改后完全退出并重开 ZCode。只想关闭自动恢复、保留统计条，可执行 `python3 setup_auto.py disable`。

## 数据与隐私

采集器**只读**本地用量数据库，按当前会话 ID 查询数字统计。不读取提示词、不访问 API key、不上传遥测，也不额外调用模型。只统计已完成的主请求；记录保留期、缺失的计时和历史缓存口径会影响数字，详见[数据与显示](docs/guide.zh-CN.md#数据与显示)。

安装会写入应用加载入口、组件自身文件和备份，并注册用户级本地插件。自动恢复仅在修复成功或失败时向当前会话提供一条简短维护状态。

## 文档与贡献

- [中文完整指南](docs/guide.zh-CN.md) · [English guide](docs/guide.md)
- [开发、测试与贡献](CONTRIBUTING.md)
- [实现约定](spec.json)

## 致谢与许可

接入方式和 ASAR 格式处理参考 [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar)，保留其 [MIT 许可声明](vendor/LICENSE)。界面参考 DeepSeek Harness，未打包其产品运行时。本项目与 ZCode 官方无隶属关系。

[MIT](LICENSE) © 2026 ZCode DSH Stats contributors.
