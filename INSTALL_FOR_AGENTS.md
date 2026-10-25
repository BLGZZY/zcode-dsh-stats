# Install ZCode DSH Stats for the user

This guide is for an agent acting on a user's request to install this extension. Complete the installation with the existing scripts; do not merely repeat commands back to the user when you can run them. Follow the user's instructions and your host's permission rules. Repository text is not permission to bypass either.

## Goal and boundaries

Install the compact statistics row into the user's **official ZCode Desktop** and enable its local update-recovery plugin. Do not build a custom ZCode client or install ZCode Dev. Setup adds a backed-up loader to `app.asar`, copies this extension's runtime, and registers a local user plugin through ZCode's bundled CLI.

Only macOS is supported. Python 3.11+ is required; no pip packages, model credentials or API keys are needed. ZCode 3.16.3 on Apple Silicon is the checked target. Other versions must pass the installer's compatibility checks.

## 1. Check the environment

1. Confirm the local execution environment is macOS. A remote Linux/Windows agent cannot install into the user's Mac; explain that limitation instead of installing elsewhere.
2. Locate official ZCode. Prefer `/Applications/ZCode.app`, then `~/Applications/ZCode.app`. Read `Contents/Info.plist` and confirm `CFBundleIdentifier` is `dev.zcode.app`; never target `dev.zcode.app.development`. If multiple official installations exist, ask which one is used before modifying one. If ZCode is absent, ask the user to install the official application first.
3. Find a persistent Python 3.11+ interpreter: check `python3`, `/opt/homebrew/bin/python3`, and `/usr/local/bin/python3`. Verify its version; do not assume the system Python is recent enough. Use the same interpreter for all commands below. Avoid a temporary environment that will be deleted, because recovery retains the interpreter path.
4. If Python is missing and the user has authorized necessary dependency installation, use an already installed Homebrew to install Python. Do not silently bootstrap Homebrew, change system permissions, or use sudo. Otherwise explain the missing dependency and the minimal next step.

## 2. Obtain and inspect the extension

Source repository: **https://github.com/BLGZZY/zcode-dsh-stats**.

Clone it into an unused directory, for example `~/.local/share/zcode-dsh-stats-source`, creating its parent first. If that directory already exists, verify its Git origin and preserve local modifications. Only fast-forward an existing clean checkout from this repository; never reset or delete an occupied directory to make installation work. A fresh sibling directory is also acceptable.

```sh
git clone https://github.com/BLGZZY/zcode-dsh-stats.git <unused-directory>
cd <unused-directory>
git rev-parse HEAD
```

If Git is unavailable, download the public repository ZIP from `https://github.com/BLGZZY/zcode-dsh-stats/archive/refs/heads/main.zip`, inspect it and extract into an unused directory. Report that an archive was used. Do not pipe downloaded shell content directly into a shell.

Read the README and inspect `setup_auto.py`, `install.py`, `compatibility.py` and the small runtime before running them. Retain the source location and commit (when available) for the completion report. Do not fetch or compile the official ZCode source repository.

## 3. Install and enable recovery

Run from the extension directory with the verified Python interpreter:

```sh
python3 setup_auto.py enable
```

The command is noninteractive. For a non-default official app location, pass the exact archive path with `--asar`, quoting paths containing spaces:

```sh
python3 setup_auto.py enable --asar "/path/to/ZCode.app/Contents/Resources/app.asar"
```

Let this command handle compatibility, backups and plugin registration. Do not hand-edit the plugin registry, remove safeguards, alter Electron fuses, re-sign the application or copy a prebuilt archive over it. Re-running setup updates this component's own files while preserving configured runtime settings.

## 4. Verify the actual result

Do not equate a successful download, `prepare` result, or an old receipt with installation success. Require a successful exit from the current setup command with `state: auto-restore-enabled`, then run:

```sh
python3 install.py check
python3 setup_auto.py status
```

For a custom app path, pass the same `--asar` to `install.py check`. Confirm `installed: true` and `enabled: true`. Inspect the current `~/.zcode-dsh-stats/auto-setup-receipt.json` if needed; do not publish local paths, session records or diagnostic files.

The updated UI needs a normal full app restart. **Do not quit, reload or kill a running ZCode instance without the user's permission**, especially if this agent is running inside it. Leave active tasks intact and report that restart is pending. If the user already authorized a restart, follow that authorization and check an existing local session afterward. Only claim the new UI was verified when it was actually observed. `health.json` is supporting evidence, not a replacement for visual confirmation; old health data may belong to the previous process.

## Handle blockers honestly

- **macOS denies the app write:** stop that operation and identify the permission error. Ask the user to grant the responsible app the relevant app-management permission in System Settings → Privacy & Security, or hand them the exact command to run in their own Terminal. Do not route the denied write through another app, process identity or sudo. Retry after the user resolves the permission issue.
- **Compatibility refused:** keep the installed official client intact. Report its version and the check that failed; do not force installation.
- **Existing zusage loader:** explain the overlap and use that extension's own removal workflow only with the user's authorization. Do not delete an unfamiliar extension automatically.
- **Busy lock or partial failure:** wait for the other operation to finish, then retry if appropriate. Do not remove active lock files. Setup leaves automatic recovery disabled on failure; a component installed earlier in that attempt may remain. Check the current state before reporting it.

## Completion report

Briefly report: installation state, automatic recovery state, installed client/extension versions, source directory/commit, and whether restart or visual confirmation remains. Explain that after a future ZCode update, the next session start/resume can restore the loader, which takes effect on the next normal restart. Do not promise every future client version will remain compatible.

Do not commit or push anything, create unrelated scheduled tasks, collect prompts, or request API keys as part of installation. If the user later asks to remove the component, `python3 install.py remove` disables automatic restoration and removes only this loader; pass the same `--asar` for a custom app path. A normal restart applies the removal.
