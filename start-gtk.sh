#!/bin/sh
# Launch the GTK4 + gtk4-layer-shell build. The layer-shell library must load
# before libwayland-client, hence the preload.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
 echo 'Start Orbit inside a Wayland session (Hyprland).' >&2; exit 1
fi
lib=$(ldconfig -p 2>/dev/null | awk '/libgtk4-layer-shell\.so /{print $NF; exit}')
[ -n "$lib" ] || lib=/usr/lib/libgtk4-layer-shell.so
[ -e "$lib" ] || { echo 'Orbit requires gtk4-layer-shell.' >&2; exit 1; }
LD_PRELOAD="$lib${LD_PRELOAD:+:$LD_PRELOAD}" PYTHONPATH="$here/src${PYTHONPATH:+:$PYTHONPATH}" GDK_BACKEND=wayland exec python3 -m orbit "$@"
