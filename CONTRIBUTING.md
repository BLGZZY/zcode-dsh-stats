# Contributing

Issues and pull requests are welcome in English or Chinese. Include operating system/version, architecture, ZCode version, extension version, expected behavior and reproduction steps. Use synthetic examples and redact private data before sharing logs or screenshots.

Checked targets are macOS / Apple Silicon with ZCode 3.16.3 and Windows 11 x64 with official ZCode 3.14.4 and 3.16.3. Windows installation, recovery registration, live official-client statistics on both versions and a same-version simulated loader-overwrite recovery drill were verified with an existing Anaconda base Python 3.11.4. Distinguish fixture tests, preview tests, installed-client verification and recovery drills in reports; see the [verification table](docs/guide.md#verified-configurations) for the current evidence.

## Run checks

Python 3.11+ and Node.js 18+ are enough for unit tests. Tests use temporary fixtures; they do not install into your actual ZCode app.

```sh
python3 -m unittest discover -s tests -v
node --test tests/loader.test.cjs
node --check runtime/overlay.js
node --check runtime/loader.cjs
```

On Windows use `py -3` in place of `python3`, after checking it is 3.11+. `Install.ps1` and `Remove.ps1` are intended for Windows PowerShell 5.1+ / PowerShell 7. They discover a persistent Python executable and accept `-Asar` plus an optional `-PythonPath` for an existing interpreter outside PATH; they must not alter execution policy, request elevation, or stop the app.

## Preview and browser acceptance

```sh
python3 -m http.server 8766 --bind 127.0.0.1
# In another terminal, with Playwright CLI installed:
playwright-cli open http://127.0.0.1:8766/preview.html
playwright-cli run-code "$(cat tests/browser-acceptance.js)"
playwright-cli close
```

Windows PowerShell equivalent:

```powershell
py -3 -m http.server 8766 --bind 127.0.0.1
# In another terminal, with Playwright CLI installed:
playwright-cli open http://127.0.0.1:8766/preview.html
playwright-cli run-code (Get-Content -Raw tests/browser-acceptance.js)
playwright-cli close
```

`preview.html` and `docs/showcase.html` use labeled demo values. Browser screenshots and logs belong in ignored `output/`. Browser acceptance checks positioning, bottom spacing, narrow panes, themes, details, session isolation and cleanup. A preview passing does not substitute for validation in the official app.

## Windows acceptance evidence

For every additional Windows target, record the Windows version/architecture, official ZCode version, Python executable/version, discovered archive path and source commit. Exercise installation, status, per-session statistics, a normal restart, automatic repair after a representative update, and opt-out/removal. Confirm paths containing spaces and multiple discovered installations behave correctly. Preserve current backups and never replace the user's app with a synthetic fixture. Record UI verification separately from installer success; redact local paths and session content in public evidence.

The Windows deferred-recovery helper is a single temporary Python process with a 24-hour bound. Preserve executable-specific process detection, worker reuse, opt-out cancellation and fresh compatibility checks after normal app exit. Do not replace it with a scheduled task/service or force the app to close. Initial installation with a locked archive still requires a normal app exit and rerun.

The earlier simulated Windows drill removed only the loader entry on the same official ZCode 3.14.4 version, then verified the helper survived its caller, waited for normal exit, repaired the entry, exited, and restored the real UI after relaunch. Separately, on 2026-10-25 the native updater completed a real official stable-channel upgrade from 3.14.4 to 3.16.3. The native SessionStart hook queued recovery without manual setup or restoration commands; normal exit let the helper restore the loader and terminate. The post-relaunch 3.16.3 UI also passed live verification of the three cards, positioning, viewport bounds and footer spacing, recorded separately in the verification table. Neither result guarantees future-version compatibility.

ZCode 3.14.4 uses a verified legacy composer profile without `data-composer-layout`. Its compatibility exception requires the exact version and scoped editor, surface, card and dock markers. Add evidence and regression coverage before introducing another profile; unknown legacy layouts must remain rejected.

## Scope

- Keep collection read-only and session-specific. Do not add prompt collection, credentials or telemetry.
- Update `spec.json` before changing behavior. Add regression coverage for data correctness or installation lifecycle changes.
- Preserve original payload bytes, backups, compatibility guards and opt-out behavior. Do not disable Electron security features or force restarts.
- Keep English and Chinese Quick Start instructions aligned.
- Do not commit app archives, databases, local settings, logs, private screenshots or installation receipts.

The root [MIT license](LICENSE) covers this project; retain the upstream attribution in [vendor/LICENSE](vendor/LICENSE).
