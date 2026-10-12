# Orbit

An animated desktop companion for coding agents on **Linux + Hyprland**. One pet shows Claude Code, Codex CLI, Codex Desktop, and AGY CLI activity, with task cards, a message composer, usage meters, and customizable animation sheets.

## Requirements

- Hyprland with its Lua configuration/runtime API (`hyprctl eval`), tested on **0.56.2**. Older configurations without this API are not supported.
- XWayland enabled, Electron (tested with 44), Node.js, Python 3, libX11 and libXext.
- Optional: your logged-in `codex`, `claude`, and/or `agy` CLI on PATH. Kitty is needed to reopen Codex CLI conversations.
- Codex Desktop integration requires a compatible local IPC bridge; it is experimental and version dependent.

On Arch Linux, install Node.js, Python, Electron, XWayland, libx11 and libxext using your package manager. Package names and Electron versions vary by distribution. No npm dependencies or API keys are required by Orbit itself.

## Install

```sh
git clone https://github.com/Kira-007/orbit.git
cd orbit
python3 install.py --check
python3 install.py
./start.sh
```

Run as your own user, **without sudo**. Keep the checkout at this location: the launcher and startup entry point to it. Installation backs up your Lua configuration, adds an Orbit-only floating/pinned rule and startup entry, and creates an application launcher. It uses your HOME and XDG directories. It does not patch any agent application.

For a different Lua config path:

```sh
python3 install.py --config "$HOME/.config/hypr/my-config.lua"
```

Use `--no-autostart` to omit startup. Existing pets share the same per-user `agent-pet` state directory and single-instance lock, so quit your old Orbit before launching this copy.

### Agent integrations

Codex activity is read from local session logs. To install passive Claude and AGY task hooks, run `python3 install.py --hooks`, then restart those agents. Hooks are merged with existing configuration and backed up. AGY hook support depends on the CLI version; its terminal message delivery remains experimental. Missing executables and unsupported Desktop versions report errors.

Usage refreshes at startup and when opened: Codex uses its installed app-server account API; AGY uses its CLI `/usage` command. Authentication must already be configured in each agent. Claude quota retrieval is not implemented. Offline or failed readings are indicated rather than presented as fresh.

Set `ORBIT_ELECTRON` to an alternative Electron executable. Set `ORBIT_CODEX_DESKTOP` to your Desktop executable path if it is neither `codex-desktop` nor `chatgpt`. These must also be present in the Hyprland login environment for autostart.

## Use

- Click the pet to open/close its toolbar; drag to move it.
- Chat and notifications are separate views. Select a harness and thread before sending. Enter sends; Shift+Enter inserts a line break.
- Scroll notification cards; dismiss them with their small close control.
- Right-click for Hide or Settings; the tray restores a hidden pet.
- Settings → Customize supports body colors, expression, and sprite pets. Upload a sheet for each animation, set frame count and its facing, and adjust each animation's speed independently.
- Walking follows your drag direction, while transparent empty space passes clicks through.

The built-in robot needs no assets. The bundled Beatrice sprite uses the upstream MIT license; see `assets/library/SOURCES.md`. Other sprites from the personal development setup are excluded from this distribution.

## Data and privacy

Settings, uploaded sprites and hook events stay in `$XDG_STATE_HOME/agent-pet` (default `~/.local/state/agent-pet`). Orbit reads local agent metadata and session logs. Hooks retain task labels and short prompt snippets, which can contain private information. Quota and message operations invoke your authenticated local agent tools; those tools may contact their services. Orbit exposes no remote server.

## Uninstall

Quit Orbit from its tray, then run `python3 uninstall.py`. It removes only the portable installation's configuration block, launcher and hooks. User settings, sprites, task history and backups are retained.

## Development

```sh
node --test test/*.test.cjs
```

This is an experimental Hyprland application, tested on Arch Linux. Other Linux distributions and multi-monitor layouts still need broader testing. Windows, macOS, legacy Hyprland and other compositors are not supported.
