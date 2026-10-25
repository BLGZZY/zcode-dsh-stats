# ZCode DSH Stats

给官方 ZCode Desktop 的输入框卡片外侧下方添加 DSH 风格统计行：轮数、请求步数、解码均速、累计 token、缓存命中率和原生上下文占用。无需编译 ZCode 源码。统计条存在时，将桌面输入区原有 16px 底部留白收至 2px，使整块输入区更贴近窗口下界；移除组件后恢复原生留白。

采用 [zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar) 的接入思路：在 `app.asar` 主入口追加一个动态加载入口，由 Electron 注入独立 Shadow DOM 组件。它属于成品应用扩展，不是官方提供的 composer 插件 API。

## 安装与卸载

已检查的目标为 **Apple Silicon 上的 macOS / ZCode 3.16.3** 和 **Windows 11 x64 上的官方 ZCode 3.14.4 和 3.16.3**。Windows 已使用现有 Anaconda 基础安装中的 Python 3.11.4 完成验证。暂不支持 Linux；两种目标平台均需 Python 3.11+，不需要 pip 依赖。

Windows 在下载目录中打开 PowerShell：

```powershell
.\Install.ps1
# 自定义官方应用安装位置：
.\Install.ps1 -Asar 'C:\path\to\ZCode\resources\app.asar'
# 复用 PATH 外已有的 Python（替换为实际路径）：
.\Install.ps1 -PythonPath 'C:\path\to\python.exe'
```

脚本依次发现 `py -3`、`python`、`python3`，验证版本并选取非虚拟环境的 Python 绝对路径，后续自动恢复可继续使用。如果执行策略阻止脚本，确认 `py -3 --version` 为 3.11+ 后，直接运行 `py -3 setup_auto.py enable`；无需修改执行策略。没有 `py` 但已经装好 Python 时，可通过 `& 'C:\path\to\python.exe' setup_auto.py enable` 使用验证过的绝对路径。

macOS 默认使用 `/Applications/ZCode.app/Contents/Resources/app.asar`，其他位置通过 `--asar` 指定。Windows 自动发现官方 ZCode 的常见安装位置；多个候选不会随意选择，应通过 `--asar` 明确指定。后续检查、准备、更新和卸载均传相同路径；PowerShell 入口对应参数为 `-Asar`。不要指向开发版。

安装 Python 前，先检查 PATH 外已有安装，包括 Python 注册表记录和 Anaconda/Miniconda 基础安装。两个 PowerShell 入口均支持 `-PythonPath`，可与 `-Asar` 同时传入，无需激活环境。确认没有合适的 Python 后，再安装官方 Python 3.11+ 包。已有 winget 可先执行 `winget show --id Python.Python.3.13 --exact --source winget` 核对来源，再执行 `winget install --id Python.Python.3.13 --exact --source winget --scope user --interactive`。macOS 已有 Homebrew 可用 `brew install python`。脚本不会自动安装包管理器、提权、修改执行策略或结束 ZCode 进程。

下文命令使用 macOS 的 `python3`；**Windows 请替换成已确认版本的 `py -3` 或 Python 绝对路径**。`~` 代表当前用户主目录，Windows PowerShell 中对应 `$HOME`（通常为 `%USERPROFILE%`）。

macOS 首次安装并开启更新后自动恢复（推荐）：

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

安装和卸载后都需要完全退出并重新打开官方 ZCode。安装器不会结束进程。自动发现官方应用位置，也可用 `--asar` 指定完整 `app.asar` 路径。macOS 常见路径为 `/Applications/ZCode.app/Contents/Resources/app.asar`，Windows 为安装目录下的 `resources\app.asar`。运行时位于 `~/.zcode-dsh-stats/`，每次修改前保存独立备份及 SHA-256 收据。卸载只去掉本工具的标记，不回滚官方升级或其他扩展。检测到旧 zusage 加载入口时拒绝叠加安装。

Windows 首次安装遇到应用文件锁定时，需要完成任务并获得用户授权后正常完全退出 ZCode，再重跑安装；首次安装不会由自动恢复助手排队代办。

Windows 卸载用 `.\Remove.ps1`；自定义安装继续传同一个 `-Asar`。更新源码后，执行 `git pull --ff-only` 和 `.\Install.ps1` 同步组件与自动恢复副本。若提示拒绝访问或文件占用，先报告具体路径和操作，不提权、不修改 ACL、不关闭安全软件；需要退出应用时，等任务结束并获得用户授权后正常退出再重试。

macOS 若返回 `Operation not permitted`，可在自己的终端执行安装命令，或先在系统设置中授权执行安装的应用管理其他应用。也可双击 `Install.command`；`Remove.command` 用于卸载。安装脚本不会更改系统权限、申请 sudo 或终止后台任务。`prepare` 成功不代表已经安装。

## 官方更新后自动恢复

一次启用后，本地插件通过官方 `SessionStart` hook 在新建或恢复会话时检查加载入口。官方更新覆盖入口后，它验证新版兼容性，备份并补回入口，无需每次手动执行命令。macOS 在会话 hook 内直接执行恢复，不常驻后台。Windows 在文件被运行中的应用锁定时，会启动下面说明的一次性后台助手；两端均不创建计划任务或服务，不额外调用模型，也不访问网络。脚本不读取会话输入；在修复、失败或延后时，通过官方 hook 向当前会话提供一条本地维护状态，正常检查保持静默。

会话 hook 不等同于应用启动事件：一般要到首次会话操作才检查，而恢复的加载入口要在**下一次正常完全退出并重开 ZCode**后生效。不会强制退出或打断后台任务。权限不足、新版输入框结构不兼容、Electron ASAR 完整性校验开启时停止修复并记录 `~/.zcode-dsh-stats/auto-status.json`；同一应用文件失败后退避 30 分钟。不会修改 Electron fuse、禁用安全检查或自动重签名。

Windows 遇到应用文件锁定时返回 `deferred-until-exit`，启动或复用一个独立 Python 后台助手，最多等待 **24 小时**。它只等待所配置官方可执行文件对应的全部进程正常退出，调用它的终端关闭后仍可继续等待；退出后重新检查兼容性、文件状态和禁用标记，再补回入口并结束自身，组件在下次启动时加载。进度记录在 `worker-status.json`。等待超时后，下次 SessionStart 可以再次排队；禁用恢复或卸载组件会取消待执行修复。真正的权限错误不会被绕过。

卸载组件会先写入禁用标记，即使卸载失败或插件仍在注册列表中，也不会自动把组件装回来。`setup_auto.py disable` 只关闭恢复；再次运行 `setup_auto.py enable` 可重新开启。手动升级组件源码后应再次运行此命令更新本地插件副本。

## 数据与显示

三个入口分别打开会话性能、Token 用量、上下文容量卡片，数值随当前会话更新。模型用时是客户端完整请求耗时，含准备、重试与收尾；工具用时是关联主回合工具从调度至终态的耗时总和，含排队、审批等待及失败/取消，并行调用会累加。TTFT 按有效样本取算术平均。

**0.4.1** 修复了回答生成期间点卡片后立即消失的问题：对话自动滚动或卡片内容滚动时保持打开，父容器滚动及窗口缩放时跟随按钮定位，按钮滚出窗口时关闭。旧版会在任意滚动事件中关闭卡片；更新组件后，正常完全退出并重开 ZCode 即可加载修复。

Token 各分项独立标记有效样本；缓存写入缺失时，输入项改为“非缓存读取输入”，不把缺失写入假定为零。上下文卡仅显示原生已用/上限/剩余，暂不展示系统、工具、消息的分项 token，也不按字符数推算。

- 只读 `~/.zcode/cli/db/db.sqlite`，使用当前输入框所属会话 ID，不猜最近活跃会话，不发送网络请求、不访问凭据、不调用模型。
- 统计当前本地保留记录中的已完成 `main_turn` 请求；官方通常清理 30 天前的用量记录，因此不是永久历史总量。错误、重试失败及子代理不混入主请求统计。
- 速度为配对有效样本的 `Σoutput_tokens / Σ(completed_at − first_token_at)`。每次请求结束后更新；不是流式过程中逐 token 跳动的速度。
- ZCode 首 token 计时来自文本/思考片段，纯工具参数可能没有计时；星号表示部分样本，详情显示有效样本数。思考速度取决于提供方上报口径。
- 累计输入兼容历史缓存存储格式，不重复加缓存；缺失值显示未知，显式零才显示零。
- 上下文来自官方 UI 的当前读数，不假设模型窗口大小。远程会话没有本地记录时显示不可用，不读其他会话充数。
- 不写项目、会话、数据库、模型配置或原有源码仓库。组件安装仅修改自己的运行时、备份、安装收据和官方应用入口；启用自动恢复还会通过官方管理器注册用户级本地插件。

## 验证

Windows 真机验证使用组件 **0.4.0** 与官方 ZCode 3.14.4，并于 **2026-10-25** 通过官方稳定通道真实升级至 3.16.3；应用位于自定义目录，复用了 PATH 外已有的 Python。公开命令中的路径均为占位示例。

| Windows 11 x64 验收项 | 结果 |
| --- | --- |
| `Install.ps1` 同时传 `-Asar` 和 `-PythonPath` | 安装成功，自动恢复已启用。 |
| ZCode 3.14.4 已有本地会话与采集器 | 真实统计已显示，health 确认数据可用。 |
| ZCode 3.14.4 会话性能、Token 用量、上下文三卡 | 已验证真实数值、独立按钮定位及窗口边界。 |
| ZCode 3.14.4 底栏间距 | 已验证 24px 统计行与 2px 底部留白。 |
| 同版本模拟加载入口覆盖 | 通过：运行时延后，正常退出后自动修复，助手退出，重启后真实界面恢复。 |
| 官方稳定版 3.14.4 → 3.16.3（2026-10-25） | 通过：原生更新替换应用归档，原生 SessionStart 自行排队，正常退出后自动补回入口并结束助手，无需手动重装。 |
| ZCode 3.16.3 恢复后重启界面 | 通过：0.4.0 组件恢复，三卡真实数据、独立定位与窗口边界正常，底栏 24px、底部留白 2px；修复完成，助手已退出。 |
| Windows 自动化测试 | 124 项 Python 测试套件通过（其中跳过 1 项 POSIX 专用测试）；Node 6 项通过。 |

早期模拟演练在同一官方 ZCode 3.14.4 版本上去掉本组件入口，验证了 `deferred-until-exit`、调用终端结束后助手存活、重复检查复用、全部匹配进程正常退出后的修复、助手结束，以及重启后的 0.4.0 真实界面恢复。

随后于 2026-10-25 使用客户端原生更新器和签名有效的官方稳定版安装包，完成了独立的真实版本升级验证。新版替换应用归档后，只需打开已有会话，原生 SessionStart 即自动触发恢复；期间没有手动运行安装或恢复命令。正常退出后助手自行补回入口并结束，下次启动生效。重启后的官方 ZCode 3.16.3 界面复验也已通过：0.4.0 组件的三张卡片、定位与间距正常，恢复助手已退出。未来版本仍须通过兼容检查。

macOS 的 124 项 Python 测试套件同样通过（其中跳过 1 项 Windows 原生 API 测试）。

ZCode 3.14.4 尚无 `data-composer-layout`；其已验证旧版兼容分支要求版本精确匹配，且同时具备限定的编辑器、外层、卡片和底部区域标记。未验证的旧版或未知结构仍拒绝安装；其他版本也必须通过正常兼容检查。

```sh
python3 -m unittest discover -s tests -v
node --test tests/loader.test.cjs
node --check runtime/overlay.js
node --check runtime/loader.cjs
python3 -m http.server 8766 --bind 127.0.0.1
```

`preview.html` 使用明确标注的演示数据；`tests/browser-acceptance.js` 通过 Playwright CLI `run-code` 验证输入框卡片外侧挂载、24px 单行与 3px 间隔、居中及 Highspeed 模式、详情顶层、连续流式滚动与数据刷新、卡片内部滚动、父容器滚动与窗口缩放定位、键盘关闭、明暗主题、窄窗口、切会话、分屏、过期数据及卸载清理。截图与结果保存在 `output/`。

独立预览通过不等于官方应用已生效；须在重启后的官方客户端中确认底栏与真实会话数据，并检查 `~/.zcode-dsh-stats/health.json`。

## 参考与许可

接入机制与 ASAR 格式参考 xhwxt 的 MIT 项目，原许可保留于 `../vendor/LICENSE`。组件、采集器、加载器及测试在此目录独立实现；ASAR 安装器保留原 payload 字节，仅替换入口记录。视觉参考本地 DeepSeek Harness `StatsPills`，未复制其产品运行时。
