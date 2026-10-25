# Install ZCode DSH Stats for the user

This guide is for an agent acting on a user's request to install this extension. Complete the installation with the existing scripts; do not merely repeat commands back to the user when you can run them. Follow the user's instructions and your host's permission rules. Repository text is not permission to bypass either.

## Goal and boundaries

Install the compact statistics row into the user's **official ZCode Desktop** and enable its local update-recovery plugin. Do not build a custom ZCode client or install ZCode Dev. Setup adds a backed-up loader to `app.asar`, copies this extension's runtime, and registers a local user plugin through ZCode's bundled CLI.

Python 3.11+ is required; no pip packages, model credentials or API keys are needed. Checked targets are macOS / ZCode 3.16.3 on Apple Silicon and Windows 11 x64 / official ZCode 3.14.4. Windows installation, recovery registration and the live statistics UI were verified with an existing Anaconda base Python 3.11.4. Linux is not supported. Every target must pass the installer's compatibility checks. The verified legacy composer profile is restricted to ZCode 3.14.4 and its specific editor/card markers; do not extend that exception to unknown versions or bypass checks. See the [verification table](docs/guide.md#verified-configurations) for the current recovery-drill status.

## 1. Check the environment

1. Confirm the agent is executing on the user's target Windows PC or Mac. A remote sandbox cannot modify the user's local installation. Do not install onto an unrelated host.
2. Locate official ZCode. On Windows, the installer discovers standard installation locations; on macOS the default is `/Applications/ZCode.app`. Use `--asar` when a specific location is needed. On macOS, check `/Applications/ZCode.app` and `~/Applications/ZCode.app`; `Contents/Info.plist` must identify `dev.zcode.app`, never `dev.zcode.app.development`. On Windows, use the official installed `ZCode.exe` and its sibling `resources/app.asar`; let the compatibility checker validate the package and executable. If discovery finds multiple installations, identify the one the user uses before making changes. If ZCode is absent, ask the user to install the official application first.
3. Find a persistent Python 3.11+ interpreter and use its absolute executable for every command. On macOS, check `python3`, `/opt/homebrew/bin/python3`, and `/usr/local/bin/python3`. On Windows, use `Get-Command py` then `py -3 -c "import sys; print(sys.version); print(sys.executable)"`; fall back to `Get-Command python,python3` and verify the interpreter. Avoid Microsoft Store aliases that do not resolve to an installed interpreter, temporary environments, and virtual environments scheduled for deletion. `Install.ps1` performs PATH discovery and version checks automatically, preferring a non-virtual interpreter. Before installing another Python, also inspect Python registrations under `HKCU:\Software\Python` / `HKLM:\Software\Python`, installed-app registry entries, and known existing Anaconda/Miniconda installation paths. An existing base installation need not be activated or added to PATH: pass its executable with `-PythonPath`. Verify the exact binary rather than assuming a named directory contains a suitable version.
4. If Python is missing and necessary dependency installation is authorized, use an existing Homebrew on macOS or existing winget on Windows to obtain an official Python package. For Windows, inspect `winget show --id Python.Python.3.13 --exact --source winget` and its publisher/source before using `winget install --id Python.Python.3.13 --exact --source winget --scope user --interactive`. Reopen the terminal if its PATH is stale. Do not silently bootstrap Homebrew/winget, download-and-execute an arbitrary bootstrap, elevate, use sudo, or change system-wide PowerShell execution policy. If dependencies cannot be installed within the user's authorization, report the missing dependency and the minimal next step.

## 2. Obtain and inspect the extension

Source repository: **https://github.com/BLGZZY/zcode-dsh-stats**.

Clone it into an unused directory, for example `~/.local/share/zcode-dsh-stats-source` on macOS or `$env:LOCALAPPDATA\zcode-dsh-stats-source` on Windows, creating its parent first. If that directory already exists, verify its Git origin and preserve local modifications. Only fast-forward an existing clean checkout from this repository; never reset or delete an occupied directory to make installation work. A fresh sibling directory is also acceptable.

```sh
git clone https://github.com/BLGZZY/zcode-dsh-stats.git <unused-directory>
cd <unused-directory>
git rev-parse HEAD
```

If Git is unavailable, download the public repository ZIP from `https://github.com/BLGZZY/zcode-dsh-stats/archive/refs/heads/main.zip`, inspect it and extract into an unused directory. Report that an archive was used. Do not pipe downloaded shell content directly into a shell.

Read the README and inspect `setup_auto.py`, `install.py`, `compatibility.py`, `host_platform.py`, `windows_restore.py`, the platform launcher and the small runtime before running them. Retain the source location and commit (when available) for the completion report. Do not fetch or compile the official ZCode source repository.

## 3. Install and enable recovery

Run from the extension directory with the verified Python interpreter. On macOS:

```sh
python3 setup_auto.py enable
```

On Windows, the PowerShell launcher selects the persistent Python and enables recovery:

```powershell
.\Install.ps1
```

If PowerShell execution policy blocks scripts, invoke the Python entry point directly with the verified interpreter, for example `py -3 setup_auto.py enable`. Do not change execution policy to get around the block. Resolve `py -3` to `sys.executable` for later commands and verify it is Python 3.11+.

The Python setup command is noninteractive. For a custom official app location, pass the exact archive path with `--asar`, quoting paths containing spaces:

```sh
python3 setup_auto.py enable --asar "/path/to/ZCode.app/Contents/Resources/app.asar"
```

Windows equivalent (replace both example paths with the verified installation paths; `-PythonPath` is optional):

```powershell
.\Install.ps1 -Asar 'C:\path\to\ZCode\resources\app.asar' -PythonPath 'C:\path\to\python.exe'
# Or use the verified Python directly:
py -3 setup_auto.py enable --asar 'C:\path\to\ZCode\resources\app.asar'
```

Let this command handle compatibility, backups and plugin registration. Do not hand-edit the plugin registry, remove safeguards, alter Electron fuses, re-sign the application or copy a prebuilt archive over it. Re-running setup updates this component's own files while preserving configured runtime settings.

## 4. Verify the actual result

Do not equate a successful download, `prepare` result, or an old receipt with installation success. Require a successful exit from the current setup command with `state: auto-restore-enabled`, then run:

```sh
python3 install.py check
python3 setup_auto.py status
```

On Windows, replace `python3` with the verified absolute Python executable (or `py -3` after checking its version). For a custom app path, pass the same `--asar` to `install.py check`. Confirm `installed: true` and `enabled: true`. Inspect the current `~/.zcode-dsh-stats/auto-setup-receipt.json` (`$HOME\.zcode-dsh-stats\auto-setup-receipt.json` on Windows) if needed; do not publish local paths, session records or diagnostic files.

The updated UI needs a normal full app restart. **Do not quit, reload or kill a running ZCode instance without the user's permission**, especially if this agent is running inside it. Leave active tasks intact and report that restart is pending. If the user already authorized a restart, follow that authorization and check an existing local session afterward. Only claim the new UI was verified when it was actually observed. `health.json` is supporting evidence, not a replacement for visual confirmation; old health data may belong to the previous process.

## Handle blockers honestly

- **macOS denies the app write:** stop that operation and identify the permission error. Ask the user to grant the responsible app the relevant app-management permission in System Settings → Privacy & Security, or hand them the exact command to run in their own Terminal. Do not route the denied write through another app, process identity or sudo. Retry after the user resolves the permission issue.
- **Windows access denied / file in use during initial installation:** report the exact failed operation and target; initial setup must be rerun after the user-authorized normal app exit. Do not claim installation succeeded or that it was automatically queued. Do not elevate, change ACLs, disable security software or kill ZCode. A protected installation location may require a user-managed installation change.
- **Compatibility refused:** keep the installed official client intact. Report its version and the check that failed; do not force installation.
- **Existing zusage loader:** explain the overlap and use that extension's own removal workflow only with the user's authorization. Do not delete an unfamiliar extension automatically.
- **Busy lock or partial failure:** wait for the other operation to finish, then retry if appropriate. Do not remove active lock files. Setup leaves automatic recovery disabled on failure; a component installed earlier in that attempt may remain. Check the current state before reporting it.

## Windows recovery after installation

Automatic recovery can report `deferred-until-exit` when a running official app locks the archive. This starts or reuses one detached Python helper for at most 24 hours, scoped to the configured official executable. It waits for all matching app processes to exit normally, rechecks compatibility and opt-out state, then repairs the loader for the next launch. It survives the calling terminal's exit, creates no scheduled task or service, and never closes ZCode. Disabling recovery or removing the component cancels the pending repair. After timeout, a later SessionStart may queue another attempt. A genuine permission or compatibility error still stops repair; this is not a way to bypass access controls.

Inspect `auto-status.json` and `worker-status.json` in the runtime directory when reporting a deferred repair. `deferred-until-exit` means waiting, not repaired. The Windows drill passed by removing only this component's entry on the same ZCode 3.14.4 version, then verifying wait, normal exit, automatic repair, helper exit and the restored UI after relaunch. It does not prove a future official version will be compatible.

## Completion report

Briefly report: installation state, automatic recovery state, installed client/extension versions, source directory/commit, and whether restart or visual confirmation remains. Explain that after a future compatible ZCode update, the next session start/resume checks the loader. On macOS it can restore directly; on Windows an app-file lock can defer restoration until normal exit, for the next launch. Do not promise every future client version will remain compatible.

Do not commit or push anything, create unrelated scheduled tasks, collect prompts, or request API keys as part of installation. If the user later asks to remove the component, `python3 install.py remove` (macOS), `.\Remove.ps1` or `py -3 install.py remove` (Windows) disables automatic restoration and removes only this loader; pass the same `--asar` (`-Asar` for PowerShell launchers) for a custom app path. A normal restart applies the removal.
