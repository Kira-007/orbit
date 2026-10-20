"""Sprite-sheet pet widget drawn with Cairo."""
import math
import time

import cairo
import gi

gi.require_version('Gdk', '4.0')
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
        self.robot = None
        self.started = time.monotonic()
        self.loaded = None
        self._tick = None
        self.set_draw_func(self._draw)
        self.resize(1.0)

    def resize(self, scale):
        self.scale = scale
        self.set_size_request(round(BOX_W * scale), round(BOX_H * scale))

    def set_robot(self, robot, animate=True):
        """Draw the built-in robot; robot is {'body', 'accent', 'face', 'state'}."""
        self.robot = robot
        self.set_sprite(None, animate)

    def set_sprite(self, config, animate=True, flip=False):
        if config:
            self.robot = None
        if config != self.config:
            self.config, self.started = config, time.monotonic()
            try:
                self.loaded = _frames(config) if config else None
            except GLib.Error:
                self.loaded = None
        self.animate, self.flip = animate, flip
        if self.animate and (self.loaded or self.robot) and not self._tick:
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
        if self.robot and not self.loaded:
            ctx.scale(width / BOX_W, height / BOX_H)
            return draw_robot(ctx, self.robot, time.monotonic() - self.started if self.animate else 0)
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


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _rounded(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    for cx, cy, a in ((x + w - r, y + r, -math.pi / 2), (x + w - r, y + h - r, 0), (x + r, y + h - r, math.pi / 2), (x + r, y + r, math.pi)):
        ctx.arc(cx, cy, r, a, a + math.pi / 2)
    ctx.close_path()


def draw_robot(ctx, robot, t):
    """Cairo port of the SVG robot, with simplified state animations."""
    state, body, accent = robot['state'], _rgb(robot['body']), _rgb(robot['accent'])
    light = tuple(c * .4 + .6 for c in body)
    core = {'waiting': (.94, .64, .42), 'done': (.49, .89, .73), 'error': (.95, .55, .58)}.get(state, (.96, .74, .42))
    ctx.set_source_rgba(.02, .12, .16, .2)
    ctx.save(); ctx.translate(75, 133); ctx.scale(30, 5); ctx.arc(0, 0, 1, 0, 2 * math.pi); ctx.restore(); ctx.fill()
    bob = {'working': math.sin(t * 9.7) * 2, 'done': -abs(math.sin(t * 5.2)) * 8, 'unknown': math.sin(t * 1.3) * 3}.get(state, math.sin(t * 1.6) * 2)
    ctx.translate(75, 105 + bob)
    if state == 'waiting':
        ctx.rotate(math.sin(t * 2.6) * .12)
    elif state == 'error':
        ctx.translate(math.sin(t * 40) * 4 if t % 1.6 < .55 else 0, 0)
    ctx.translate(-75, -105)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_source_rgb(.42, .69, .67); ctx.set_line_width(5); ctx.move_to(74, 34); ctx.line_to(74, 21); ctx.stroke()
    ctx.arc(74, 17, 7, 0, 2 * math.pi); ctx.set_source_rgb(*(core if state != 'idle' else (.96, .74, .42)))
    ctx.fill_preserve(); ctx.set_source_rgb(.07, .22, .28); ctx.set_line_width(3); ctx.stroke()
    lift = -abs(math.sin(t * 10)) * 7 if state == 'done' else (math.sin(t * 19) * 3 if state == 'working' else 0)
    ctx.set_source_rgb(.65, .80, .77); ctx.set_line_width(9)
    ctx.move_to(32, 76); ctx.line_to(20, 91 + lift); ctx.move_to(118, 76); ctx.line_to(130, 91 + lift); ctx.stroke()
    ctx.set_source_rgb(.96, .74, .42)
    for x in (19, 131):
        ctx.arc(x, 94 + lift, 6, 0, 2 * math.pi); ctx.fill()
    gradient = cairo.LinearGradient(32, 34, 100, 103)
    gradient.add_color_stop_rgb(0, *light); gradient.add_color_stop_rgb(1, *body)
    _rounded(ctx, 32, 34, 86, 69, 26); ctx.set_source(gradient); ctx.fill_preserve()
    ctx.set_source_rgb(.09, .25, .29); ctx.set_line_width(3); ctx.stroke()
    _rounded(ctx, 42, 46, 66, 44, 17); ctx.set_source_rgb(.06, .17, .21); ctx.fill()
    ctx.set_source_rgb(*accent)
    eye_h = 13 * (.13 if t % 7 > 6.85 or state == 'unknown' else 1)
    shift = math.sin(t * 2.6) * 4 if state == 'waiting' else 0
    for x in (56, 85):
        _rounded(ctx, x + shift, 64.5 - eye_h / 2, 9, eye_h, min(4, eye_h / 2)); ctx.fill()
    ctx.set_line_width(2.5)
    face = robot.get('face')
    if face == 'focused':
        ctx.move_to(68, 79); ctx.line_to(82, 79)
    elif face == 'sleepy':
        ctx.move_to(71, 79); ctx.line_to(79, 79)
    else:
        ctx.move_to(67, 77); ctx.curve_to(72, 81, 78, 81, 83, 77)
    ctx.stroke()
    ctx.move_to(56, 103); ctx.line_to(53, 116); ctx.curve_to(68, 126, 82, 126, 97, 116); ctx.line_to(94, 103)
    ctx.set_source_rgb(.89, .93, .88); ctx.fill_preserve(); ctx.set_source_rgb(.09, .25, .29); ctx.set_line_width(3); ctx.stroke()
    ctx.arc(75, 112, 5, 0, 2 * math.pi); ctx.set_source_rgb(*core); ctx.fill()
    ctx.set_source_rgb(.09, .25, .29); ctx.set_line_width(6)
    ctx.move_to(55, 122); ctx.line_to(49, 128); ctx.move_to(95, 122); ctx.line_to(101, 128); ctx.stroke()
    if state in ('working', 'done'):
        ctx.set_source_rgba(.96, .74, .42, .65 + .35 * math.sin(t * 6))
        ctx.move_to(123, 24)
        for px, py in ((125, 29), (130, 31), (125, 33), (123, 38), (121, 33), (116, 31), (121, 29)):
            ctx.line_to(px, py)
        ctx.close_path(); ctx.fill()
        ctx.arc(28, 35, 3, 0, 2 * math.pi); ctx.fill()


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
