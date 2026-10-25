# ZCode DSH Stats

A compact token usage bar for official ZCode Desktop, with automatic restoration after updates.

**English** · [简体中文](README.zh-CN.md)

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

Requires **macOS**, **Python 3.11+** as `python3`, Git, and official ZCode at `/Applications/ZCode.app`. No pip dependencies. The current target was checked against **ZCode 3.16.3 on Apple Silicon**; Windows/Linux and other client versions are not verified.

```sh
git clone https://github.com/BLGZZY/zcode-dsh-stats.git
cd zcode-dsh-stats
python3 setup_auto.py enable
python3 setup_auto.py status
```

Successful setup reports `auto-restore-enabled`. After background tasks finish, **fully quit and reopen ZCode**, then open an existing local conversation. The row appears beneath the input card. A new draft has no statistics row yet.

You can also double-click `Install.command` in the downloaded folder. If macOS reports `Operation not permitted`, see [troubleshooting](docs/guide.md#troubleshooting).

> [!NOTE]
> This is an unofficial, experimental extension. It adds a loader to the installed application's `app.asar`, with a verified backup. It does not use an official composer extension API or rebuild ZCode. Future client changes may need an adaptation.

## After ZCode updates

The installed local plugin checks its loader when a session starts or resumes. If an update replaced it, the plugin checks compatibility, backs up the new archive and restores the loader. **The restored component takes effect on the next normal app restart.** It never forces a restart or interrupts your tasks.

Permission errors or incompatible client changes pause restoration. See [update recovery](docs/guide.md#update-recovery). This restores the component; it does not update ZCode or download new extension versions.

## Update or remove this extension

```sh
# Update the component and its installed recovery copy
git pull --ff-only
python3 setup_auto.py enable

# Or remove the component and disable automatic restoration
python3 install.py remove
```

Fully quit and reopen ZCode after either change. To stop restoration while keeping the row, use `python3 setup_auto.py disable`.

## Data and privacy

The collector opens the local usage database **read-only** and selects numeric usage for the exact current session. It does not read prompts, access API keys, send telemetry or make model requests. Only completed main requests are counted. Local retention, missing timing samples and legacy cache accounting affect totals; see [metric definitions](docs/guide.md#metrics).

Installation writes the app loader, the extension's own files/backups and a user-level local plugin registration. Recovery contributes a short maintenance notice to the current session only when a repair succeeds or fails.

## Documentation and contributing

- [User guide and troubleshooting](docs/guide.md) · [中文完整指南](docs/guide.zh-CN.md)
- [Development, tests and contributions](CONTRIBUTING.md)
- [Implementation contract](spec.json)

## Credits and license

The loading approach and ASAR format handling are based on [xhwxt/zcode-token-usage-statusbar](https://github.com/xhwxt/zcode-token-usage-statusbar). Its [MIT notice](vendor/LICENSE) is retained. The interface is inspired by DeepSeek Harness; its product runtime is not bundled. This project is not affiliated with ZCode.

[MIT](LICENSE) © 2026 ZCode DSH Stats contributors.
