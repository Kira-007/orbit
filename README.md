# Orbit

An animated desktop companion for coding agents on **Linux + Hyprland**. One pet shows Claude Code, Codex CLI, Codex Desktop, and AGY CLI activity, with task cards, a message composer, usage meters, and customizable animation sheets.

## Requirements

- Hyprland with its Lua configuration/runtime API (`hyprctl eval`), tested on **0.56.2**. Older configurations without this API are not supported.
- Python 3 with PyGObject, GTK 4 and gtk4-layer-shell. Orbit runs as a native Wayland layer-shell overlay; XWayland is not needed.
- Optional: your logged-in `codex`, `claude`, and/or `agy` CLI on PATH. Kitty is needed to reopen Codex CLI conversations.
- Codex Desktop integration requires a compatible local IPC bridge; it is experimental and version dependent.

On Arch Linux: `sudo pacman -S python-gobject gtk4 gtk4-layer-shell`. No pip/npm dependencies or API keys are required by Orbit itself.

The previous Electron build is still in `src/main` and `src/renderer` and can be started with `./start.sh` (needs Electron, XWayland, libX11 and libXext); it will be removed once the GTK build has settled.

## Install

```sh
git clone https://github.com/Kira-007/orbit.git
cd orbit
python3 install.py --check
python3 install.py
./start-gtk.sh
```

Run as your own user, **without sudo**. Keep the checkout at this location: the launcher and startup entry point to it. Installation backs up your Lua configuration, adds an Orbit-only floating/pinned rule and startup entry, and creates an application launcher. It uses your HOME and XDG directories. It does not patch any agent application.

For a different Lua config path:

```sh
python3 install.py --config "$HOME/.config/hypr/my-config.lua"
```

Use `--no-autostart` to omit startup. Existing pets share the same per-user `agent-pet` state directory and single-instance lock, so quit your old Orbit before launching this copy.

### Agent integrations

Codex activity is read from local session logs. To install passive Claude and AGY task hooks, run `python3 install.py --hooks`, then restart those agents. Hooks are merged with existing configuration and backed up. AGY hook support depends on the CLI version; its terminal message delivery remains experimental. Missing executables and unsupported Desktop versions report errors.

Usage refreshes at startup, when opened, and every five minutes: Codex uses its installed app-server account API; AGY uses its CLI `/usage` command; Claude reads subscription quota using the existing Claude Code sign-in (`CLAUDE_CONFIG_DIR` is supported). Claude requests are cached for one minute and respect rate-limit cooldowns. Authentication must already be configured in each agent. Offline or failed readings are indicated rather than presented as fresh.

Set `ORBIT_CODEX_DESKTOP` to your Desktop executable path if it is neither `codex-desktop` nor `chatgpt`. These must also be present in the Hyprland login environment for autostart.

## Use

- Click the pet to open/close its toolbar; drag to move it.
- A random flea appears about every **8–15 minutes** while the pet is visible and not being used. It skips spawning during dragging, open panels, or an existing collection.
- **Win + Y** drops a flea at the captured cursor position. The pet runs to collect queued fleas in order and stays at the last location when the queue is empty. Dragging, hiding, or resetting the pet clears pending fleas.
- Chat and notifications are separate views. Select a harness and thread before sending. Enter sends; Shift+Enter inserts a line break.
- Click a task card to open Orbit’s composer with its harness and exact session selected. Completed/error cards are dismissed after that session loads. The × button dismisses any card. Notification clicks do not focus another application.
- Completions and errors expire after 10 minutes by default (Settings → Recent tasks). Running/waiting cards disappear after 15 minutes without updates; idle/stale cards are cleared. Dismissal follows that task run, so a later run with the same title can notify again. Hovering the pet does not take keyboard focus.
- Right-click for Hide, Settings, Reset position or Quit; the tray icon (or running `./start-gtk.sh` again) toggles a hidden pet.
- The notification button opens a collapsed stack; scroll over it to cycle cards, or choose **Show all**.
- Win + Y on another monitor moves the pet's overlay to that monitor.
- Settings → Customize supports body colors, expression, and sprite pets. Upload a sheet for each animation, set frame count and its facing, and adjust each animation's speed independently.
- Settings → **Movement speed** changes cursor-shortcut travel speed from 150–1800 px/s (default 700). It applies to the next shortcut press and is saved automatically. Sprite FPS is configured separately per animation.
- Walking follows your drag direction, while transparent empty space passes clicks through.

The built-in robot needs no assets. The bundled Beatrice sprite uses the upstream MIT license; see `assets/library/SOURCES.md`. Other sprites from the personal development setup are excluded from this distribution.

## Data and privacy

Settings, uploaded sprites and hook events stay in `$XDG_STATE_HOME/agent-pet` (default `~/.local/state/agent-pet`). Orbit reads local agent metadata and session logs. Hooks retain task labels and short prompt snippets, which can contain private information. Quota and message operations invoke your authenticated local agent tools; those tools may contact their services. Orbit exposes no remote server.

## Uninstall

Quit Orbit from its tray, then run `python3 uninstall.py`. It removes only the portable installation's configuration block, launcher and hooks. User settings, sprites, task history and backups are retained.

## Development

```sh
node --test tests/*.test.cjs
python3 -m unittest tests/gtk_logic_test.py
python3 tests/threads_test.py
python3 tests/install_test.py
```

This is an experimental Hyprland application, tested on Arch Linux. Other Linux distributions and multi-monitor layouts still need broader testing. Windows, macOS, legacy Hyprland and other compositors are not supported.

## Repository layout

See [Architecture](docs/architecture.md) and [Contributing](CONTRIBUTING.md) for source layout and development checks.
