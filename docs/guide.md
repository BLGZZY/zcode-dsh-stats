# User guide

[Quick Start](../README.md#quick-start) · [中文指南](guide.zh-CN.md)

## Install and inspect

Checked targets are **macOS / Apple Silicon with ZCode 3.16.3** and **Windows 11 x64 with official ZCode 3.14.4**. Windows was validated with an existing Anaconda base Python 3.11.4. Linux is not supported. Python 3.11+ is required on both target platforms; no pip dependencies.

On macOS, use `python3` or double-click `Install.command`. On Windows, open PowerShell in the downloaded directory and run:

```powershell
.\Install.ps1
# For an installation outside the discovered locations:
.\Install.ps1 -Asar 'C:\path\to\ZCode\resources\app.asar'
# Reuse an existing Python outside PATH (replace this example path):
.\Install.ps1 -PythonPath 'C:\path\to\python.exe'
```

The launcher resolves `py -3`, `python`, or `python3` to a persistent, non-virtual Python 3.11+ executable. That absolute path can be used by recovery after this terminal closes. If execution policy blocks the launcher, check `py -3 --version` and run `py -3 setup_auto.py enable` directly; no policy change is needed. If the launcher is absent but Python is installed, use its verified absolute path with PowerShell's call operator: `& 'C:\path\to\python.exe' setup_auto.py enable`.

On macOS, the default is `/Applications/ZCode.app/Contents/Resources/app.asar`; use `--asar` for other locations. On Windows, the installer discovers standard official ZCode locations. Multiple Windows candidates require an explicit `--asar` path; discovery does not choose an arbitrary copy. Pass the same target for later `check`, `prepare`, update, or removal commands. The PowerShell launchers spell this option `-Asar`. Do not target a development build.

Before installing Python, check for an existing installation outside PATH, including Python registry entries and Anaconda/Miniconda base installations. `-PythonPath` works with both launchers and can be combined with `-Asar`; it does not require environment activation. If no suitable Python exists, install an official Python 3.11+ package. With an existing winget, first inspect `winget show --id Python.Python.3.13 --exact --source winget`, then use `winget install --id Python.Python.3.13 --exact --source winget --scope user --interactive`. On macOS, an existing Homebrew can install Python with `brew install python`. Neither launcher installs a package manager, elevates privileges, changes execution policy, or stops ZCode.

The commands below use macOS `python3`; **on Windows use `py -3` after verifying its version, or the discovered absolute executable**. User data paths beginning with `~` refer to your home directory; on Windows this is `$HOME` in PowerShell (normally `%USERPROFILE%`).

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

On Windows, `.\Remove.ps1` removes the component and disables automatic recovery. Pass the same `-Asar` for a custom app location. To update the installed component and recovery copy, run `git pull --ff-only` followed by `.\Install.ps1` from the source directory.

If initial Windows setup reports a locked archive, wait for active tasks, fully quit ZCode normally with the user's authorization, then rerun setup; initial installation is not queued by the recovery helper. If setup fails midway, recovery remains disabled. A component already installed by that attempt is retained. Re-run setup after addressing the error. Existing zusage loaders are rejected to avoid overlapping bars; remove that overlay through its own installer first.

## Verified configurations

Windows verification used extension **0.4.0** in the installed official ZCode 3.14.4 client, with a custom app location and an existing Python outside PATH. Public examples use placeholder paths.

| Windows 11 x64 check | Result |
| --- | --- |
| `Install.ps1` with `-Asar` and `-PythonPath` | Installed successfully; automatic recovery enabled. |
| Existing local session and collector | Live statistics visible; health reports data available. |
| Activity, token and context cards | Real values, independent button anchors and viewport bounds verified. |
| Footer spacing | 24px row and 2px dock bottom padding verified. |
| Same-version simulated loader overwrite | Passed: deferred while the official app ran; repaired after normal exit; helper exited; live UI restored after relaunch. |
| Windows automated tests | 124-test Python suite passed with one POSIX-only skip; 6 Node tests passed. |

The recovery drill removed only this component's loader entry on the same official ZCode 3.14.4 version. It verified `deferred-until-exit`, helper survival after the calling terminal ended, reuse on repeated checks, repair after all matching app processes exited, helper termination and the restored 0.4.0 UI after relaunch. It was not an actual official version upgrade and does not establish future-version compatibility. The macOS 124-test Python suite also passed, with one Windows-native-API skip.

ZCode 3.14.4 predates `data-composer-layout`. Its verified legacy profile requires that exact version plus the scoped editor, surface, card and dock markers. Unknown legacy versions/layouts remain rejected; other versions still need the normal compatibility checks.

## Update recovery

The local plugin handles SessionStart events for startup/resume/clear/compact. This is a session event; macOS restoration runs in that hook without a persistent background helper. When a stable official archive lacks the loader, the hook checks the package, composer selectors and Electron integrity mode before reinstalling.

Installation uses locks, verified content-addressed backups, validation of unchanged payload bytes and atomic replacement. Unsupported versions or permission errors stop restoration. The same unchanged archive backs off for 30 minutes after failure. Status is recorded in `~/.zcode-dsh-stats/auto-status.json`; a short maintenance notice is supplied to the current session on repair, failure or deferral.

On Windows, the running app may lock `app.asar`. Automatic recovery then reports `deferred-until-exit` and starts or reuses one detached Python helper. It waits up to **24 hours** for all processes belonging to the configured official executable to exit normally. The helper survives the calling terminal's exit; after the app exits it rechecks compatibility, file state and opt-out before repairing. It then exits, and the restored component loads on the next app start. `worker-status.json` records its progress. If it times out, a later SessionStart can queue a new attempt. Disabling recovery or removing the component cancels the pending repair.

No forced restart, scheduled task, service, network download or extra model call is used. macOS keeps the direct hook-based restoration path. Install new extension versions using `git pull --ff-only` and `python3 setup_auto.py enable` from your clone.

Removal records an opt-out first. The plugin registration may remain, but the hook cannot reinstall the row while disabled. To remove the registration too, uninstall **ZCode DSH Stats** in ZCode's plugin manager. Backups and receipts are retained.

## Metrics

| Metric | Definition |
| --- | --- |
| Turns / steps | Distinct turns and completed main_turn requests in locally retained records. Failed, cancelled and background requests are excluded. |
| Model time | Sum of client-recorded completed main-request durations, including preparation, retries and completion handling. Not pure server inference time. |
| Tool time | Sum of dispatch-to-terminal intervals associated with retained main turns, including queue/approval waits and failed/cancelled calls. Parallel calls overlap; this is not wall-clock waiting time. |
| Mean TTFT | Arithmetic mean of valid first-token delays; missing timing samples are excluded and marked. |
| Decode tok/s | Sum of output tokens divided by sum of completion-minus-first-token durations, over paired valid samples. Updated after completion. |
| Tokens | Cumulative completed main-request tokens, with legacy cached-input storage normalized to avoid double counting. |
| Cache hit | Input-weighted cache-hit ratio where stored usage provides sufficient evidence. |
| Context | Native usage/limit from the active pane; no model-window guessing. |

ZCode normally retains about 30 days of usage, so these are not permanent lifetime totals. Missing values show as unknown; `*` means partial sample coverage. Tool-only output may lack a first-token timestamp because ZCode records it for text/reasoning. Details show sample coverage.

Token details use independent sample counts. If cache writes are not fully reported, the input row is labeled non-cache-read input and includes any unreported writes. Partial rows carry an asterisk; they must not be treated as a complete reconciled partition.

Context details use only native total usage and capacity. System/tool/message token breakdown is unavailable; character proportions are not converted into token counts.

Each pane uses its exact session ID. A new draft hides the row; a remote session without local records shows unavailable instead of borrowing another session's values. Collector data older than 10 seconds is hidden.

## Troubleshooting

- **Python error:** check `python3 --version` (macOS) or `py -3 --version` (Windows); Python 3.11+ is required. No pip packages are needed.
- **Operation not permitted:** run setup in your own Terminal. If macOS still denies app modification, grant the responsible app the relevant app-management permission under System Settings → Privacy & Security, then retry. Setup never changes system permissions or uses sudo.
- **Windows script execution blocked:** run the verified Python CLI directly instead of changing PowerShell execution policy.
- **Windows access denied / file in use:** keep tasks intact and report the target path. Retry after a normal user-authorized app exit if the file is in use; do not elevate, change ACLs or disable security controls.
- **Compatibility refused:** keep the official app intact and report its version. The installer does not disable integrity validation or re-sign the app.
- **Installed but invisible:** wait for active tasks, fully quit/reopen ZCode, and enter an existing local session. Check `install.py check` and `health.json`. Drafts and inline editors hide the row.
- **Update still missing the row:** start/resume a session and inspect `auto-status.json`. On Windows, `deferred-until-exit` means the helper is waiting for a normal app exit; inspect `worker-status.json`, finish your tasks and exit normally, then reopen after repair. An expired helper can be queued again by the next session start/resume.
- **Busy operation:** wait for the existing operation to finish, then retry; do not delete its locks while it runs.

Archive backups stay in `~/.zcode-dsh-stats/backups/`. Normal removal edits only this extension's marked entry, preserving newer app contents. Avoid restoring old archives over a newer official version.
