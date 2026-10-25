# User guide

[Quick Start](../README.md#quick-start) · [中文指南](guide.zh-CN.md)

## Install and inspect

`python3 setup_auto.py enable` installs the row and registers its local recovery plugin through ZCode's bundled manager. Required files are copied into `~/.zcode-dsh-stats/auto-marketplace/`; after setup the plugin does not depend on the original clone.

```sh
python3 setup_auto.py status
python3 install.py check
```

`enabled: true` means recovery is configured, not that a running window has loaded the row. `installed: true` confirms the archive marker. After restarting ZCode, `~/.zcode-dsh-stats/health.json` records window/update counts and data availability.

```sh
python3 install.py install     # Component only, without enabling recovery
python3 install.py prepare     # Validate a prepared archive; do not replace the app
python3 setup_auto.py disable  # Keep the component; turn off recovery
python3 install.py remove      # Remove this loader and disable recovery
```

If setup fails midway, recovery remains disabled. A component already installed by that attempt is retained. Re-run setup after addressing the error. Existing zusage loaders are rejected to avoid overlapping bars; remove that overlay through its own installer first.

## Update recovery

The local plugin handles SessionStart events for startup/resume/clear/compact. This is a session event, not an app-launch daemon. When a stable official archive lacks the loader, the hook checks the package, composer selectors and Electron integrity mode before reinstalling.

Installation uses locks, verified content-addressed backups, validation of unchanged payload bytes and atomic replacement. Unsupported versions or permission errors stop restoration. The same unchanged archive backs off for 30 minutes after failure. Status is recorded in `~/.zcode-dsh-stats/auto-status.json`; a short maintenance notice is supplied to the current session on repair/failure.

Restoration takes effect on the next normal restart. No forced restart, timer service, network download or extra model call. Install new extension versions using `git pull --ff-only` and `python3 setup_auto.py enable` from your clone.

Removal records an opt-out first. The plugin registration may remain, but the hook cannot reinstall the row while disabled. To remove the registration too, uninstall **ZCode DSH Stats** in ZCode's plugin manager. Backups and receipts are retained.

## Metrics

| Metric | Definition |
| --- | --- |
| Turns / steps | Distinct turns and completed main_turn requests in locally retained records. Failed, cancelled and background requests are excluded. |
| Decode tok/s | Sum of output tokens divided by sum of completion-minus-first-token durations, over paired valid samples. Updated after completion. |
| Tokens | Cumulative completed main-request tokens, with legacy cached-input storage normalized to avoid double counting. |
| Cache hit | Input-weighted cache-hit ratio where stored usage provides sufficient evidence. |
| Context | Native usage/limit from the active pane; no model-window guessing. |

ZCode normally retains about 30 days of usage, so these are not permanent lifetime totals. Missing values show as unknown; `*` means partial sample coverage. Tool-only output may lack a first-token timestamp because ZCode records it for text/reasoning. Details show sample coverage.

Each pane uses its exact session ID. A new draft hides the row; a remote session without local records shows unavailable instead of borrowing another session's values. Collector data older than 10 seconds is hidden.

## Troubleshooting

- **Python error:** check `python3 --version`; Python 3.11+ is required. No pip packages are needed.
- **Operation not permitted:** run setup in your own Terminal. If macOS still denies app modification, grant the responsible app the relevant app-management permission under System Settings → Privacy & Security, then retry. Setup never changes system permissions or uses sudo.
- **Compatibility refused:** keep the official app intact and report its version. The installer does not disable integrity validation or re-sign the app.
- **Installed but invisible:** wait for active tasks, fully quit/reopen ZCode, and enter an existing local session. Check `install.py check` and `health.json`. Drafts and inline editors hide the row.
- **Update still missing the row:** start/resume a session, inspect `auto-status.json`, and restart normally after repair.
- **Busy operation:** wait for the existing operation to finish, then retry; do not delete its locks while it runs.

Archive backups stay in `~/.zcode-dsh-stats/backups/`. Normal removal edits only this extension's marked entry, preserving newer app contents. Avoid restoring old archives over a newer official version.
