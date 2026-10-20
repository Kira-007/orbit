"""Sprite-sheet pet widget drawn with Cairo."""
import time

import cairo
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from .settings import sheet_path  # noqa: E402

BOX_W, BOX_H = 150, 129
_frames_cache = {}


def _frames(config):
    """Split a sheet into frames; returns (surfaces, frame width, frame height, alpha top, alpha bottom)."""
    key = (config['sheet'], config['frames'], config['columns'])
    if key in _frames_cache:
        return _frames_cache[key]
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(sheet_path(config['sheet']))
    cols = config['columns']
    rows = -(-config['frames'] // cols)
    fw, fh = pixbuf.get_width() // cols, pixbuf.get_height() // rows
    surfaces, top, bottom = [], fh, 0
    for f in range(config['frames']):
        sub = pixbuf.new_subpixbuf((f % cols) * fw, (f // cols) * fh, fw, fh)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, fw, fh)
        ctx = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(ctx, sub, 0, 0)
        ctx.paint()
        surface.flush()
        data, stride = surface.get_data(), surface.get_stride()
        for y in range(fh):
            if max(bytes(data[y * stride + 3:y * stride + fw * 4:4])) > 8:
                top, bottom = min(top, y), max(bottom, y + 1)
        surfaces.append(surface)
    result = (surfaces, fw, fh, 0 if top == fh else top, bottom or fh)
    _frames_cache[key] = result
    return result


class SpriteView(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.config, self.animate, self.flip, self.scale = None, True, False, 1.0
        self.started = time.monotonic()
        self.loaded = None
        self._tick = None
        self.set_draw_func(self._draw)
        self.resize(1.0)

    def resize(self, scale):
        self.scale = scale
        self.set_size_request(round(BOX_W * scale), round(BOX_H * scale))

    def set_sprite(self, config, animate=True, flip=False):
        if config != self.config:
            self.config, self.started = config, time.monotonic()
            try:
                self.loaded = _frames(config) if config else None
            except GLib.Error:
                self.loaded = None
        self.animate, self.flip = animate, flip
        if self.animate and self.loaded and not self._tick:
            self._tick = self.add_tick_callback(lambda *_: self.queue_draw() or True)
        elif not self.animate and self._tick:
            self.remove_tick_callback(self._tick)
            self._tick = None
        self.queue_draw()

    def visible_bounds(self):
        """Opaque vertical extent of the sprite inside the widget, in widget pixels."""
        h = self.get_height() or BOX_H * self.scale
        if not self.loaded:
            return 0, h
        _, fw, fh, top, bottom = self.loaded
        ratio = min((self.get_width() or BOX_W * self.scale) / fw, h / fh)
        pad = (h - fh * ratio) / 2
        return pad + top * ratio, pad + bottom * ratio

    def _draw(self, _area, ctx, width, height):
        if not self.loaded:
            return
        surfaces, fw, fh, _, _ = self.loaded
        frame = int((time.monotonic() - self.started) * self.config['fps']) % len(surfaces) if self.animate else 0
        ratio = min(width / fw, height / fh)
        dw, dh = fw * ratio, fh * ratio
        ctx.translate((width - dw) / 2 + float(self.config.get('offsetX') or 0) * ratio, (height - dh) / 2)
        if self.flip:
            ctx.translate(dw, 0)
            ctx.scale(-1, 1)
        ctx.scale(ratio, ratio)
        ctx.set_source_surface(surfaces[frame], 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_GOOD)
        ctx.paint()


class DragDirection:
    """Confirm a horizontal turn before mirroring; vertical drags often wobble sideways."""

    def __init__(self, x, direction=1):
        self.extreme, self.extreme_y, self.direction, self.turn = x, 0, direction, None

    def update(self, x, t, y=0):
        advance = (x - self.extreme) * self.direction
        if advance >= 0:
            self.extreme, self.extreme_y, self.turn = x, y, None
            return self.direction
        retreat, vertical = -advance, abs(y - self.extreme_y)
        if vertical >= max(24, retreat * 1.5):
            self.extreme, self.extreme_y, self.turn = x, y, None
            return self.direction
        if retreat < 4:
            self.turn = None
            return self.direction
        if self.turn and (x - self.turn['farthest']) * self.direction >= 4:
            self.turn = None
        if not self.turn:
            self.turn = {'since': t, 'farthest': x}
        if (x - self.turn['farthest']) * self.direction < 0:
            self.turn['farthest'] = x
        if retreat >= 18 and retreat >= vertical * 1.25 and t - self.turn['since'] >= .07:
            self.direction *= -1
            self.extreme, self.extreme_y, self.turn = x, y, None
        return self.direction


def pet_state(sessions, now_ms):
    statuses = {s['status'] for s in sessions}
    for state in ('waiting', 'working'):
        if state in statuses:
            return state
    recent = {s['status'] for s in sessions if 0 <= now_ms - s['time'] < 30000}
    for state in ('error', 'done', 'unknown'):
        if state in recent:
            return state
    return 'idle'
