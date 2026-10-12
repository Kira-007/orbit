#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${ORBIT_ELECTRON:-}" ]; then runtime=$ORBIT_ELECTRON
elif command -v electron44 >/dev/null 2>&1; then runtime=electron44
elif command -v electron >/dev/null 2>&1; then runtime=electron
else echo 'Orbit requires Electron. Install electron44 or electron, or set ORBIT_ELECTRON.' >&2; exit 1
fi
if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || [ -z "${DISPLAY:-}" ]; then
 echo 'Start Orbit inside a Hyprland session with XWayland enabled.' >&2; exit 1
fi
exec "$runtime" "$here" --class=agent-pet --ozone-platform=x11 "$@"
