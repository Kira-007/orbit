"""Application entry point: single instance, actions and the Win+Y summon socket."""
import json
import os
import socket
import sys
import time
from pathlib import Path

import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from .paths import ROOT  # noqa: E402
from .tray import Tray  # noqa: E402
from .window import PetWindow  # noqa: E402


def control_path():
    base = os.environ.get('XDG_RUNTIME_DIR') or os.environ.get('XDG_STATE_HOME') or str(Path.home() / '.local/state')
    return Path(base) / 'orbit-agent-pet-control.sock'


class OrbitApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='foundation.orbit.AgentPet', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        for name, callback in (('hide', lambda *_: self.toggle(False)), ('show', lambda *_: self.toggle(True)),
                               ('reset-position', lambda *_: self.window.reset_position()),
                               ('settings', lambda *_: self.window.show_settings()), ('quit', lambda *_: self.quit())):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.add_action(action)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css = Gtk.CssProvider()
        css.load_from_path(str(ROOT / 'src/orbit/style.css'))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self.hold()
        self._listen()

    def do_activate(self):
        # A second launch toggles visibility, replacing the Electron tray icon.
        if self.window:
            self.toggle(not self.window.get_visible())
            return
        self.window = PetWindow(self)
        self.window.present()
        try:
            self.tray = Tray(self.window.settings['petName'] + ' · your agent companion', [
                ('Show companion', lambda: self.toggle(True)), ('Hide companion', lambda: self.toggle(False)),
                ('Settings', self.window.show_settings), None, ('Quit Orbit', self.quit)],
                lambda: self.toggle(not self.window.get_visible()))
        except GLib.Error:
            self.tray = None

    def do_shutdown(self):
        if self.window:
            self.window.save_position()
            self.window.feed.save()
        try:
            os.unlink(control_path())
        except OSError:
            pass
        Gtk.Application.do_shutdown(self)

    def toggle(self, visible):
        if not visible:
            self.window.clear_fleas()
        self.window.set_visible(visible)

    def _listen(self):
        path = control_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_socket():
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        os.chmod(path, 0o600)
        server.listen(4)
        server.setblocking(False)
        self._server = server
        GLib.io_add_watch(server.fileno(), GLib.IO_IN, self._accept)

    def _accept(self, *_):
        try:
            client, _ = self._server.accept()
        except OSError:
            return True
        with client:
            client.settimeout(1)
            try:
                value = json.loads(client.recv(1024).split(b'\n')[0])
                if value.get('type') != 'summon' or abs(time.time() * 1000 - value['time']) > 5000:
                    raise ValueError
                ok = self.window and self.window.summon(float(value['x']), float(value['y']))
                client.sendall(b'ok\n' if ok else b'error: could not summon pet\n')
            except (OSError, ValueError, KeyError, TypeError):
                try:
                    client.sendall(b'error: could not summon pet\n')
                except OSError:
                    pass
        return True


def main():
    return OrbitApp().run(sys.argv)
