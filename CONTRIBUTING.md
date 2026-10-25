# Contributing

Issues and pull requests are welcome in English or Chinese. Include macOS architecture, ZCode version, extension version, expected behavior and reproduction steps. Use synthetic examples and redact private data before sharing logs or screenshots.

## Run checks

Python 3.11+ and Node.js 18+ are enough for unit tests. Tests use temporary fixtures; they do not install into your actual ZCode app.

```sh
python3 -m unittest discover -s tests -v
node --test tests/loader.test.cjs
node --check runtime/overlay.js
node --check runtime/loader.cjs
```

## Preview and browser acceptance

```sh
python3 -m http.server 8766 --bind 127.0.0.1
# In another terminal, with Playwright CLI installed:
playwright-cli open http://127.0.0.1:8766/preview.html
playwright-cli run-code "$(cat tests/browser-acceptance.js)"
playwright-cli close
```

`preview.html` and `docs/showcase.html` use labeled demo values. Browser screenshots and logs belong in ignored `output/`. Browser acceptance checks positioning, bottom spacing, narrow panes, themes, details, session isolation and cleanup. A preview passing does not substitute for validation in the official app.

## Scope

- Keep collection read-only and session-specific. Do not add prompt collection, credentials or telemetry.
- Update `spec.json` before changing behavior. Add regression coverage for data correctness or installation lifecycle changes.
- Preserve original payload bytes, backups, compatibility guards and opt-out behavior. Do not disable Electron security features or force restarts.
- Keep English and Chinese Quick Start instructions aligned.
- Do not commit app archives, databases, local settings, logs, private screenshots or installation receipts.

The root [MIT license](LICENSE) covers this project; retain the upstream attribution in [vendor/LICENSE](vendor/LICENSE).
