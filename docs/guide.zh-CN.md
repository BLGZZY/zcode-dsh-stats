# ZCode DSH Stats

给官方 ZCode Desktop 的输入框卡片外侧下方添加 DSH 风格统计行：轮数、请求步数、解码均速、累计 token、缓存命中率和原生上下文占用。无需编译 ZCode 源码。统计条存在时，将桌面输入区原有 16px 底部留白收至 2px，使整块输入区更贴近窗口下界；移除组件后恢复原生留白。

采用 [zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar) 的接入思路：在 `app.asar` 主入口追加一个动态加载入口，由 Electron 注入独立 Shadow DOM 组件。它属于成品应用扩展，不是官方提供的 composer 插件 API。

## 安装与卸载

首次安装并开启更新后自动恢复（推荐）：

```sh
python3 setup_auto.py enable
python3 setup_auto.py status
```

需 Python 3.11+。也可双击 `Install.command`。它检查当前应用兼容性、安装统计组件，再通过 ZCode 自带的插件管理器注册本地插件 `zcode-dsh-stats@dsh-stats-local`。插件的独立副本保存在 `~/.zcode-dsh-stats/auto-marketplace/`，启用成功后不依赖此源码目录。任一步失败时保持自动恢复关闭；初始组件安装若已经成功则保留。

只安装组件、不启用自动恢复，以及检查和卸载：

```sh
python3 install.py install
python3 install.py check
python3 install.py remove
python3 install.py prepare  # 只生成已验证的待安装文件，不改应用
python3 setup_auto.py disable  # 只关闭自动恢复，保留组件
```

安装和卸载后都需要完全退出并重新打开官方 ZCode。安装器不会结束进程。默认目标 `/Applications/ZCode.app/Contents/Resources/app.asar`，运行时位于 `~/.zcode-dsh-stats/`，每次修改前保存独立备份及 SHA-256 收据。卸载只去掉本工具的标记，不回滚官方升级或其他扩展。检测到旧 zusage 加载入口时拒绝叠加安装。

macOS 若返回 `Operation not permitted`，可在自己的终端执行安装命令，或先在系统设置中授权执行安装的应用管理其他应用。也可双击 `Install.command`；`Remove.command` 用于卸载。安装脚本不会更改系统权限、申请 sudo 或终止后台任务。`prepare` 成功不代表已经安装。

## 官方更新后自动恢复

一次启用后，本地插件通过官方 `SessionStart` hook 在新建或恢复会话时检查加载入口。官方更新覆盖入口后，它验证新版兼容性，备份并补回入口，无需每次手动执行命令。没有定时守护进程，不额外调用模型，也不访问网络。脚本不读取会话输入；仅在修复或失败时，通过官方 hook 向当前会话提供一条本地维护状态，正常检查保持静默。

会话 hook 不等同于应用启动事件：一般要到首次会话操作才检查，而恢复的加载入口要在**下一次正常完全退出并重开 ZCode**后生效。不会强制退出或打断后台任务。权限不足、新版输入框结构不兼容、Electron ASAR 完整性校验开启时停止修复并记录 `~/.zcode-dsh-stats/auto-status.json`；同一应用文件失败后退避 30 分钟。不会修改 Electron fuse、禁用安全检查或自动重签名。

卸载组件会先写入禁用标记，即使卸载失败或插件仍在注册列表中，也不会自动把组件装回来。`setup_auto.py disable` 只关闭恢复；再次运行 `setup_auto.py enable` 可重新开启。手动升级组件源码后应再次运行此命令更新本地插件副本。

## 数据与显示

- 只读 `~/.zcode/cli/db/db.sqlite`，使用当前输入框所属会话 ID，不猜最近活跃会话，不发送网络请求、不访问凭据、不调用模型。
- 统计当前本地保留记录中的已完成 `main_turn` 请求；官方通常清理 30 天前的用量记录，因此不是永久历史总量。错误、重试失败及子代理不混入主请求统计。
- 速度为配对有效样本的 `Σoutput_tokens / Σ(completed_at − first_token_at)`。每次请求结束后更新；不是流式过程中逐 token 跳动的速度。
- ZCode 首 token 计时来自文本/思考片段，纯工具参数可能没有计时；星号表示部分样本，详情显示有效样本数。思考速度取决于提供方上报口径。
- 累计输入兼容历史缓存存储格式，不重复加缓存；缺失值显示未知，显式零才显示零。
- 上下文来自官方 UI 的当前读数，不假设模型窗口大小。远程会话没有本地记录时显示不可用，不读其他会话充数。
- 不写项目、会话、数据库、模型配置或原有源码仓库。组件安装仅修改自己的运行时、备份、安装收据和官方应用入口；启用自动恢复还会通过官方管理器注册用户级本地插件。

## 验证

```sh
python3 -m unittest discover -s tests -v
node --test tests/loader.test.cjs
node --check runtime/overlay.js
node --check runtime/loader.cjs
python3 -m http.server 8766 --bind 127.0.0.1
```

`preview.html` 使用明确标注的演示数据；`tests/browser-acceptance.js` 通过 Playwright CLI `run-code` 验证输入框卡片外侧挂载、24px 单行与 3px 间隔、居中及 Highspeed 模式、详情顶层、键盘关闭、明暗主题、窄窗口、切会话、分屏、过期数据及卸载清理。截图与结果保存在 `output/`。

独立预览通过不等于官方应用已生效；须在重启后的官方客户端中确认底栏与真实会话数据，并检查 `~/.zcode-dsh-stats/health.json`。

## 参考与许可

接入机制与 ASAR 格式参考 xhwxt 的 MIT 项目，原许可保留于 `../vendor/LICENSE`。组件、采集器、加载器及测试在此目录独立实现；ASAR 安装器保留原 payload 字节，仅替换入口记录。视觉参考本地 DeepSeek Harness `StatsPills`，未复制其产品运行时。
