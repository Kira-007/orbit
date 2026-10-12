# Architecture

```text
orbit/
├── src/
│   ├── main/          Electron lifecycle, preload bridges, agent adapters and state
│   └── renderer/      Pet and settings UI, styles, animation playback
├── scripts/           Python hooks, agent discovery, X11 input shape and installation
├── assets/            Sprite library, original sources, attribution and icons
├── tests/             Node unit tests and isolated Python installation tests
├── docs/              Architecture notes
├── start.sh           Launch using system Electron
├── install.py         Stable installer entry point
└── uninstall.py       Stable uninstaller entry point
```

Electron loads `src/main/main.cjs` through the root `package.json`. Main-process modules own desktop windows, geometry, state persistence, and local agent communication. Sandboxed preloads expose narrow IPC methods to the renderers in `src/renderer`.

Python helpers in `scripts` read agent metadata, receive passive hook events, and constrain X11 input to visible controls. Hyprland's Lua policy handles compositor focus eligibility. Dragging uses absolute compositor coordinates rather than accumulating browser motion events.

Bundled sprite metadata contains paths relative to the repository root. `bundled-pets.cjs` resolves them at runtime, so moving the checkout does not break the bundled library. Uploaded sheets and settings live in the user's state directory, outside source control.

Installation implementation lives in `scripts`; root wrappers preserve the documented commands. Integration records and backups are local to the user. Source paths are computed from file locations, rather than the current working directory.
