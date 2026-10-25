# ZCode DSH Stats

A compact token usage bar for official ZCode Desktop, with automatic restoration after updates.

**English** · [简体中文](README.zh-CN.md)

**Contents:** [Features](#at-a-glance) · [Quick Start](#quick-start) · [Client updates](#after-zcode-updates) · [Update/remove](#update-or-remove-this-extension) · [Privacy](#data-and-privacy) · [Docs](#documentation-and-contributing) · [License](#credits-and-license)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/showcase-dark.png">
  <img src="docs/assets/showcase-light.png" alt="DSH Stats beneath the ZCode input card: turns, requests, decode speed, tokens, cache hits and context usage. Demo data.">
</picture>

**Know what each conversation costs in tokens—without leaving the input box.** Inspired by DeepSeek Harness's compact statistics, this extension adds a centered row beneath the official ZCode composer. No ZCode source build required.

## At a glance

| See | Understand |
| --- | --- |
| **6 turns · 58 steps · 204 tok/s** | Completed conversation turns, main requests and average decode speed. |
| **5.2M tok · 83% cache hits** | Cumulative token usage and the input's cache-hit ratio. |
| **16% context** | Native context usage for the active conversation. |
| **Click any metric** | Open separate timing, token breakdown and context-capacity cards. |

The row is **24px high**, adapts to narrow panes, follows light/dark mode and keeps each split pane's statistics separate. Illustrations use **demo data**; installed statistics come from local session records. Speed updates after requests complete, not token by token.

<details>
<summary><strong>See the three detail cards</strong></summary>

**Session performance** — model/tool time, average TTFT and decode speed.

![Session timing card, demo data](docs/assets/card-activity.png)

**Token usage** — cache hits, uncached input, cache reads and output.

![Token breakdown card, demo data](docs/assets/card-tokens.png)

**Context capacity** — native usage, remaining tokens and an accessible progress bar. ZCode does not expose per-category token counts.

![Native context usage card, demo data](docs/assets/card-context.png)

</details>

## Quick Start

### Option 1: Ask your agent to install it

Copy this into an agent that can operate the terminal on your Windows PC or Mac:

```text
Install ZCode DSH Stats on this Windows PC or Mac and enable automatic restoration after official ZCode updates.
First read and follow https://raw.githubusercontent.com/BLGZZY/zcode-dsh-stats/main/INSTALL_FOR_AGENTS.md
Complete the environment checks, source download, installation and verification. You may install an official Python package through an existing Homebrew (macOS) or winget (Windows) if needed; do not silently bootstrap a package manager.
Do not build ZCode Dev or force-quit a running ZCode. If system permissions or compatibility checks block installation, explain the actual blocker and the one step I need to take.
Report whether installation and automatic recovery succeeded, and whether I still need to restart ZCode.
```

Requires an agent with local terminal access. A web-only chat or remote sandbox cannot install into your local computer. [Read the agent installation guide](INSTALL_FOR_AGENTS.md).

### Option 2: Install manually

Requires **Python 3.11+**, Git, and an installed official ZCode Desktop. No pip dependencies. **Checked targets: macOS / Apple Silicon with ZCode 3.16.3, and Windows 11 x64 with official ZCode 3.14.4.** Windows installation and the live statistics UI were verified with Python 3.11.4 from an existing Anaconda base installation. Linux is not supported; other client versions must pass compatibility checks.

Download the source on either platform:

```sh
git clone https://github.com/BLGZZY/zcode-dsh-stats.git
cd zcode-dsh-stats
```

**macOS** — Terminal:

```sh
python3 setup_auto.py enable
python3 setup_auto.py status
```

**Windows** — PowerShell:

```powershell
.\Install.ps1
```

The Windows launcher finds an installed Python 3.11+ and retains its absolute executable path. If Python is already installed outside PATH, pass `-PythonPath 'C:\path\to\python.exe'` (using your actual path); no environment activation or duplicate installation is needed. The installer discovers official ZCode; for a custom location, use `.\Install.ps1 -Asar 'C:\path\to\ZCode\resources\app.asar'`. If PowerShell blocks scripts, use `py -3 setup_auto.py enable` after confirming `py -3 --version` is 3.11+; no execution-policy change is needed. See [platform setup](docs/guide.md#install-and-inspect).

If Windows reports that the app archive is in use during initial installation, let active tasks finish, fully quit ZCode normally, then rerun setup. The installer does not close the app for you.

Successful setup reports `auto-restore-enabled`. After background tasks finish, **fully quit and reopen ZCode**, then open an existing local conversation. The row appears beneath the input card. A new draft has no statistics row yet.

On macOS, you can also double-click `Install.command` in the downloaded folder. If macOS reports `Operation not permitted`, see [troubleshooting](docs/guide.md#troubleshooting).

> [!NOTE]
> This is an unofficial, experimental extension. It adds a loader to the installed application's `app.asar`, with a verified backup. It does not use an official composer extension API or rebuild ZCode. Future client changes may need an adaptation.

## After ZCode updates

The installed local plugin checks its loader when a session starts or resumes. If an update replaced it, the plugin checks compatibility, backs up the new archive and restores the loader. On Windows, a running app can lock the archive: recovery then starts one temporary background helper, which waits up to 24 hours for that official app to exit normally before checking and restoring the loader. Disabling recovery or removing the component cancels the pending repair. **The restored component takes effect on the next app start.** No forced exit, scheduled task or service is used.

Permission errors or incompatible client changes pause restoration. See [update recovery](docs/guide.md#update-recovery). This restores the component; it does not update ZCode or download new extension versions.

## Update or remove this extension

**macOS:**

```sh
# Update the component and its installed recovery copy
git pull --ff-only
python3 setup_auto.py enable

# Or remove the component and disable automatic restoration
python3 install.py remove
```

**Windows** — update with `git pull --ff-only` followed by `.\Install.ps1`; remove with `.\Remove.ps1`. Pass the same `-Asar` for a custom installation. The Python equivalents are `py -3 setup_auto.py enable` and `py -3 install.py remove`.

Fully quit and reopen ZCode after either change. To stop restoration while keeping the row, use `python3 setup_auto.py disable` (macOS) or `py -3 setup_auto.py disable` (Windows).

## Data and privacy

The collector opens the local usage database **read-only** and selects numeric usage for the exact current session. It does not read prompts, access API keys, send telemetry or make model requests. Only completed main requests are counted. Local retention, missing timing samples and legacy cache accounting affect totals; see [metric definitions](docs/guide.md#metrics).

Installation writes the app loader, the extension's own files/backups and a user-level local plugin registration. Recovery contributes a short maintenance notice to the current session when a repair succeeds, fails or is deferred until app exit.

## Documentation and contributing

- [User guide and troubleshooting](docs/guide.md) · [中文完整指南](docs/guide.zh-CN.md)
- [Development, tests and contributions](CONTRIBUTING.md)
- [Implementation contract](spec.json)

## Credits and license

The loading approach and ASAR format handling are based on [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar). Its [MIT notice](vendor/LICENSE) is retained. The interface is inspired by DeepSeek Harness; its product runtime is not bundled. This project is not affiliated with ZCode.

[MIT](LICENSE) © 2026 ZCode DSH Stats contributors.
