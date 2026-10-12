# Contributing

Use Linux with a running Hyprland Lua session and the dependencies listed in README.md. No npm installation is needed.

## Checks

From the repository root:

```sh
node --test tests/*.test.cjs
python3 tests/install_test.py
python3 install.py --check
```

The Python integration test uses an isolated home and mocked compositor calls; it does not edit your live configuration. `install.py --check` reads dependency and compositor availability without installing anything.

Run `./start.sh` for manual UI checks. Quit any existing Orbit instance first. Verify click-through transparency, dragging, toolbar panels and settings after changing UI or window behavior. Automated tests do not replace those checks.

Keep user data, credentials, logs and installation manifests out of the repository. Retain upstream asset licenses and source attribution when adding sprites. Describe the change and its verification in your pull request.
