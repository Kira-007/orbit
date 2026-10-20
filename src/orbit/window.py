"""The pet overlay: one transparent gtk4-layer-shell surface covering a monitor.

Only the visible controls accept input; the rest of the surface has an empty
input region, so clicks fall through to the windows underneath.
"""
import json
import os
import math
import random
import re
import threading
import time

import cairo
import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell as LayerShell, Pango  # noqa: E402

from . import settings as prefs  # noqa: E402
from .activity import Activity  # noqa: E402
from .notifications import NotificationFeed, task_key  # noqa: E402
from .paths import POSITION_FILE, ROOT, STATE_DIR  # noqa: E402
from .sprite import BOX_H, BOX_W, DragDirection, SpriteView, pet_state  # noqa: E402
from .store import Store, now_ms  # noqa: E402
from .tasks import open_threads, start_task  # noqa: E402
from .usage import agy_usage, claude_usage, codex_usage  # noqa: E402

NAMES = {'claude': 'Claude Code', 'codex-cli': 'Codex CLI', 'codex-desktop': 'Codex Desktop', 'antigravity': 'AGY CLI'}
PANEL_W, PANEL_H, TOOLBAR_W, TOOLBAR_H, GAP = 358, 430, 132, 40, 8
ICONS = ROOT / 'assets/icons/ui'
MINI_W, MINI_H = 32, 6
USAGE_COLORS = {'codex': '#eeeeee', 'claude': '#ee9877', 'antigravity': '#8bdba4'}


def _usage_label(label):
    """Shorten provider quota names the same way the Electron build did."""
    label = re.sub(r'^(gemini|3p)-(5h|weekly)$', lambda m: ('Gemini' if m[1] == 'gemini' else 'Claude / GPT') + ' · ' + ('Week' if m[2] == 'weekly' else '5h'), label)
    for old, new in (('Gemini Models', 'Gemini'), ('Claude and GPT models', 'Claude / GPT'), ('Five Hour Limit Remaining', '5h'), ('Weekly Limit Remaining', 'Week')):
        label = label.replace(old, new)
    return {'Session': '5h', 'Weekly': 'Week'}.get(label, label)


def _age(t):
    sec = max(0, (now_ms() - t) // 1000)
    return 'just now' if sec < 60 else f'{sec // 60}m ago' if sec < 3600 else f'{sec // 3600}h ago'


def _card_css(task):
    return {'claude': 'claude', 'antigravity': 'agy', 'codex-desktop': 'codex-desktop'}.get(task['provider'], 'codex-cli')


class PetWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Orbit Agent Pet')
        self.add_css_class('orbit')
        self.remove_css_class('background')
        self.settings = prefs.load()
        self.store, self.feed = Store(), NotificationFeed()
        self.activity = Activity(self.store, STATE_DIR)
        self.pet_x = self.pet_y = 0.0
        self.direction, self.walking, self.dragging = 1, False, False
        self.toolbar_pinned = self.settings['controls']
        self.panel_view = None
        self.fleas, self.current_flea, self.run = [], None, None
        self.selected_thread, self.threads = '', []

        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, 'orbit')
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self, edge, True)
        LayerShell.set_exclusive_zone(self, -1)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
        self._restore_position()

        self.fixed = Gtk.Fixed()
        self.set_child(self.fixed)
        self._build_pet()
        self._build_toolbar()
        self._build_panel()

        controller = Gtk.EventControllerKey()
        controller.connect('key-pressed', lambda _c, key, *_: key == Gdk.KEY_Escape and self.open_panel(None))
        self.add_controller(controller)

        self._region_key = None
        self.connect('realize', self._realized)
        self.activity.poll()
        self.refresh_state()
        GLib.timeout_add(1000, self._poll)
        self.refresh_usage()
        GLib.timeout_add_seconds(300, lambda: self.refresh_usage() or True)
        self._arm_random_flea()
        self.update_controls()

    # ---- construction -------------------------------------------------
    def _build_pet(self):
        self.sprite = SpriteView()
        self.sprite.resize(self.settings['petScale'])
        self.fixed.put(self.sprite, 0, 0)
        # Track the drag on the fixed surface, whose coordinates don't move with the pet.
        drag = Gtk.GestureDrag(button=1)
        drag.connect('drag-begin', self._drag_begin)
        drag.connect('drag-update', self._drag_update)
        drag.connect('drag-end', self._drag_end)
        self.fixed.add_controller(drag)
        self.drag_origin = None
        menu = Gtk.GestureClick(button=3)
        menu.connect('pressed', self._context_menu)
        self.sprite.add_controller(menu)

    def _build_toolbar(self):
        self.toolbar = Gtk.Box(css_classes=['toolbar'], halign=Gtk.Align.CENTER, homogeneous=True)
        self.toolbar.set_size_request(TOOLBAR_W, TOOLBAR_H)
        for icon, tip, view in (('chat', 'Message a conversation', 'chat'), ('usage', 'Usage remaining', 'usage'),
                                ('inbox', 'Task notifications', 'cards')):
            button = Gtk.Button(child=Gtk.Image.new_from_file(str(ICONS / f'{icon}.svg')), tooltip_text=tip)
            button.connect('clicked', lambda _b, v=view: self._toggle_view(v))
            if view == 'cards':
                overlay = Gtk.Overlay(child=button)
                self.badge = Gtk.Label(css_classes=['badge'], halign=Gtk.Align.END, valign=Gtk.Align.START, visible=False, can_target=False)
                overlay.add_overlay(self.badge)
                self.toolbar.append(overlay)
            else:
                self.toolbar.append(button)
        self.fixed.put(self.toolbar, 0, 0)
        # The toolbar rests as a small bar that shows the selected quota; it opens on click.
        self.mini_usage = Gtk.Box(css_classes=['mini-usage'], can_target=False)
        self.mini_usage.set_size_request(MINI_W, MINI_H)
        self.mini_fill = Gtk.Box(css_classes=['usage-strip'], halign=Gtk.Align.START)
        self.mini_usage.append(self.mini_fill)
        self.fixed.put(self.mini_usage, 0, 0)

    def _build_panel(self):
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['panel'], visible=False)
        self.panel.set_size_request(PANEL_W, -1)
        self.panel.set_overflow(Gtk.Overflow.HIDDEN)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)
        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack_expanded, self.front_key, self.last_cycle = False, None, 0
        wheel = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        wheel.connect('scroll', self._cycle_cards)
        self.cards.add_controller(wheel)
        self.cards_scroll = Gtk.ScrolledWindow(child=self.cards, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.stack.add_named(self.cards_scroll, 'cards')
        self.usage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.usage_scroll = Gtk.ScrolledWindow(child=self.usage_box, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.stack.add_named(self.usage_scroll, 'usage')
        self.stack.add_named(self._build_composer(), 'chat')
        self.toast = Gtk.Label(css_classes=['toast'], wrap=True, visible=False, margin_top=6)
        self.panel.append(self.stack)
        self.panel.append(self.toast)
        self.fixed.put(self.panel, 0, 0)

    def _build_composer(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=['composer'])
        self.prompt = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._prompt_key)
        self.prompt.add_controller(keys)
        placeholder = Gtk.Label(label='Write a message…', css_classes=['placeholder'], xalign=0, yalign=0,
                                halign=Gtk.Align.START, valign=Gtk.Align.START, can_target=False)
        self.prompt.get_buffer().connect('changed', lambda b: placeholder.set_visible(b.get_char_count() == 0))
        scroll = Gtk.ScrolledWindow(child=self.prompt, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=86, max_content_height=120)
        field = Gtk.Overlay(child=scroll)
        field.add_overlay(placeholder)
        box.append(field)
        row = Gtk.Box(spacing=6)
        self.harness_ids = list(NAMES)
        self.harness_index = self.harness_ids.index(self.settings['harness'])
        self.harness = self._pill(False)
        self.thread = self._pill(True)
        self.send = Gtk.Button(child=Gtk.Image.new_from_file(str(ICONS / 'send.svg')), css_classes=['send'],
                               tooltip_text='Send message (Enter; Shift+Enter for a new line)', valign=Gtk.Align.CENTER)
        self.send.connect('clicked', lambda *_: self.submit())
        for widget in (self.harness, self.thread, self.send):
            row.append(widget)
        box.append(row)
        self._set_harness_label()
        return box

    def _pill(self, expand):
        """A rounded picker: a button whose popover lists choices, like the Electron composer."""
        label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, hexpand=True, max_width_chars=1 if expand else -1)
        button = Gtk.MenuButton(css_classes=['pill'], hexpand=expand, always_show_arrow=False)
        inner = Gtk.Box(spacing=4)
        inner.append(label)
        inner.append(Gtk.Label(label='▾'))
        button.set_child(inner)
        button.label = label
        button.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['pill-menu'])
        popover = Gtk.Popover(child=Gtk.ScrolledWindow(child=button.list, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                                       propagate_natural_height=True, max_content_height=170),
                              has_arrow=False, css_classes=['pill-popover'])
        popover.set_size_request(300 if expand else 170, -1)
        button.set_popover(popover)
        return button

    def _fill_pill(self, pill, names, on_pick, selected=None, css=None):
        while child := pill.list.get_first_child():
            pill.list.remove(child)
        for index, name in enumerate(names):
            item = Gtk.Button(label=name, css_classes=['pill-item'] + (['selected'] if index == selected else []) + ([css[index]] if css else []))
            item.get_child().set_xalign(0)
            item.get_child().set_ellipsize(Pango.EllipsizeMode.END)
            item.connect('clicked', lambda _b, i=index: (pill.popdown(), on_pick(i)))
            pill.list.append(item)

    def _set_harness_label(self):
        provider = self._provider()
        self.harness.label.set_label(NAMES[provider])
        self._fill_pill(self.harness, [NAMES[h] for h in self.harness_ids], self._pick_harness, self.harness_index,
                        css=['h-' + h for h in self.harness_ids])

    def _pick_harness(self, index):
        self.harness_index = index
        self._set_harness_label()
        self.load_threads()

    # ---- geometry ------------------------------------------------------
    def _monitor(self):
        if getattr(self, '_pinned_monitor', None):
            return self._pinned_monitor
        surface = self.get_surface()
        monitor = surface and self.get_display().get_monitor_at_surface(surface)
        return monitor or self.get_display().get_monitors().get_item(0)

    def _area(self):
        width, height = self.get_width(), self.get_height()
        if not width:
            geometry = self._monitor().get_geometry()
            width, height = geometry.width, geometry.height
        return width, height

    def _restore_position(self):
        try:
            saved = json.loads(POSITION_FILE.with_name('position-gtk.json').read_text())
        except (OSError, ValueError):
            saved = {}
        monitors = self.get_display().get_monitors()
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            if monitor.get_connector() == saved.get('monitor'):
                LayerShell.set_monitor(self, monitor)
                self._pinned_monitor = monitor
        self.pet_x, self.pet_y = saved.get('x', -1), saved.get('y', -1)

    def save_position(self):
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            POSITION_FILE.with_name('position-gtk.json').write_text(json.dumps(
                {'monitor': self._monitor().get_connector(), 'x': round(self.pet_x), 'y': round(self.pet_y)}))
        except OSError:
            pass

    def pet_size(self):
        scale = self.settings['petScale']
        return BOX_W * scale, BOX_H * scale

    def move_pet(self, x, y):
        width, height = self._area()
        pw, ph = self.pet_size()
        self.pet_x, self.pet_y = max(0, min(x, width - pw)), max(0, min(y, height - ph))
        self.layout()

    def layout(self):
        width, height = self._area()
        pw, ph = self.pet_size()
        if self.pet_x < 0:
            self.pet_x, self.pet_y = width - pw - 60, height - ph - 120
        self.pet_x, self.pet_y = max(0, min(self.pet_x, width - pw)), max(0, min(self.pet_y, height - ph))
        self.fixed.move(self.sprite, self.pet_x, self.pet_y)
        top, bottom = self.sprite.visible_bounds()
        above = self.pet_y > height - self.pet_y - ph
        offset = float(self._active_pet().get('offsetY') or 0)
        bar_y = self.pet_y + top - offset - TOOLBAR_H if above else self.pet_y + bottom + offset
        center = self.pet_x + pw / 2
        self.fixed.move(self.toolbar, center - TOOLBAR_W / 2, bar_y)
        self.fixed.move(self.mini_usage, center - MINI_W / 2, bar_y + (TOOLBAR_H - MINI_H if above else 4))
        if self.panel.get_visible():
            # Size the scrolled views to their content, capped at the room on that side of the pet.
            room = (bar_y - GAP - 8) if above else (height - bar_y - TOOLBAR_H - GAP - 8)
            for scroll in (self.cards_scroll, self.usage_scroll):
                content = scroll.get_child().measure(Gtk.Orientation.VERTICAL, PANEL_W)[1]
                scroll.set_min_content_height(max(40, min(content, PANEL_H, room - 40)))
            panel_h = self.panel.measure(Gtk.Orientation.VERTICAL, PANEL_W)[1]
            panel_x = max(8, min(center - PANEL_W / 2, width - PANEL_W - 8))
            panel_y = bar_y - GAP - panel_h if above else bar_y + TOOLBAR_H + GAP
            self.fixed.move(self.panel, panel_x, max(0, panel_y))
        for flea in self.fleas:
            self.fixed.move(flea['widget'], flea['x'] - 22, flea['y'] - 32)
        GLib.idle_add(self.update_input_region)

    def _realized(self, *_):
        # GTK may reset the input region on resize, so reapply it after every frame.
        self.get_surface().set_input_region(cairo.Region())
        self.get_frame_clock().connect('after-paint', lambda *_: self.update_input_region(force=True))
        GLib.idle_add(self.layout)

    def update_input_region(self, force=False):
        surface = self.get_surface()
        if not surface:
            return False
        region = cairo.Region()
        for widget in (self.sprite, self.toolbar, self.panel):
            if not widget.get_visible() or not widget.get_mapped() or widget.get_opacity() == 0:
                continue
            ok, bounds = widget.compute_bounds(self)
            if ok:
                region.union(cairo.RectangleInt(int(bounds.get_x()), int(bounds.get_y()),
                                                math.ceil(bounds.get_width()), math.ceil(bounds.get_height())))
        key = [(r.x, r.y, r.width, r.height) for r in map(region.get_rectangle, range(region.num_rectangles()))]
        if os.environ.get('ORBIT_DEBUG') and key != self._region_key:
            print('input region', key, flush=True)
        if force or key != self._region_key:
            self._region_key = key
            surface.set_input_region(region)
        return False

    # ---- pet interaction ------------------------------------------------
    def _drag_begin(self, gesture, x, y):
        # Only start on the sprite itself; the toolbar can overlap the sprite's transparent margin.
        if self.fixed.pick(x, y, Gtk.PickFlags.DEFAULT) is not self.sprite:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            self.drag_origin = None
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.clear_fleas()
        self.drag_origin, self.drag_moved = (self.pet_x, self.pet_y), False
        self.drag_direction = DragDirection(0, self.direction)

    def _drag_update(self, _gesture, dx, dy):
        if self.drag_origin is None:
            return
        if not self.drag_moved and math.hypot(dx, dy) <= 4:
            return
        if not self.drag_moved:
            self.drag_moved, self.walking, self.dragging = True, True, True
            self.open_panel(None)
        direction = self.drag_direction.update(dx, time.monotonic(), dy)
        self.direction = direction
        self.move_pet(self.drag_origin[0] + dx, self.drag_origin[1] + dy)
        self.update_sprite()

    def _drag_end(self, _gesture, _dx, _dy):
        if self.drag_origin is None:
            return
        self.drag_origin = None
        if self.drag_moved:
            self.walking = self.dragging = False
            self.save_position()
            self.update_sprite()
        else:
            self.toolbar_pinned = not self.toolbar_pinned
            if not self.toolbar_pinned:
                self.open_panel(None)
            self.update_controls()

    def _context_menu(self, gesture, _n, x, y):
        menu = Gio.Menu()
        for label, action in (('Hide', 'app.hide'), ('Settings', 'app.settings'), ('Reset position', 'app.reset-position'), ('Quit Orbit', 'app.quit')):
            menu.append(label, action)
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self.sprite)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.popup()

    def update_controls(self):
        self.toolbar.set_visible(bool(self.toolbar_pinned or self.panel_view) and not self.dragging)
        self.mini_usage.set_visible(not self.toolbar.get_visible() and not self.dragging)
        self.layout()

    def apply_settings(self, value):
        """Apply settings edited elsewhere, keeping the pet's centre fixed when it is resized."""
        old_w, old_h = self.pet_size()
        self.settings = value
        new_w, new_h = self.pet_size()
        self.sprite.resize(value['petScale'])
        self.pet_x += (old_w - new_w) / 2
        self.pet_y += (old_h - new_h) / 2
        self.toolbar_pinned = value['controls'] or bool(self.panel_view)
        self._usage_signature = None
        self.update_sprite()
        self.update_controls()
        self.paint()

    def show_settings(self):
        from .settings_window import SettingsWindow
        if not getattr(self, 'settings_window', None):
            self.settings_window = SettingsWindow(self)
            self.settings_window.connect('destroy', lambda *_: setattr(self, 'settings_window', None))
        self.settings_window.present()

    def _active_pet(self):
        return next((p for p in self.settings['spritePets'] if p['id'] == self.settings['activeSpritePet']), {})

    def update_sprite(self):
        if self.settings['petMode'] != 'sprite':
            self.sprite.set_robot({'body': self.settings['bodyColor'], 'accent': self.settings['accentColor'],
                                   'face': self.settings['face'], 'state': self.state}, self.settings['animations'] and not self.dragging)
            return
        pet = self._active_pet()
        sheets = pet.get('spriteSheets') or {}
        state = self.state
        if self.walking:
            config = (sheets.get('dragging') if self.dragging else None) or sheets.get('walking')
        else:
            config = None
        config = config or sheets.get(state) or sheets.get('idle')
        original = -1 if (config or {}).get('facing', pet.get('facing')) == 'left' else 1
        self.sprite.set_sprite(config, self.settings['animations'], self.direction * original < 0)

    # ---- panels ------------------------------------------------------------
    def _toggle_view(self, view):
        # The notification button opens a collapsed stack; other entry points expand it.
        self.stack_expanded = view != 'cards'
        self._cards_signature = None
        self.open_panel(None if self.panel_view == view else view)

    def _cycle_cards(self, _controller, _dx, dy):
        if self.stack_expanded or not dy or time.monotonic() - self.last_cycle < .18:
            return not self.stack_expanded
        tasks = self.feed.update(self.sessions, self.settings['completionMinutes'])
        if len(tasks) < 2:
            return True
        self.last_cycle = time.monotonic()
        keys = [task_key(t) for t in tasks]
        index = keys.index(self.front_key) if self.front_key in keys else 0
        self.front_key = keys[(index + (1 if dy > 0 else -1)) % len(keys)]
        self._force_paint()
        return True

    def open_panel(self, view):
        self.panel_view = view
        self.panel.set_visible(bool(view))
        if view:
            self.stack.set_visible_child_name(view)
            self.toolbar_pinned = True
            if view == 'chat':
                self.load_threads()
                LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
                self.prompt.grab_focus()
            elif view == 'usage':
                self.refresh_usage()
            self.paint()
        self.update_controls()
        return bool(view)

    def show_toast(self, message):
        self.toast.set_label(message)
        self.toast.set_visible(True)
        GLib.timeout_add(3500, lambda: self.toast.set_visible(False) or self.layout() or False)
        self.layout()

    def _poll(self):
        self.activity.poll()
        self.refresh_state()
        return True

    def refresh_state(self):
        snapshot = self.store.snapshot()
        self.sessions = snapshot['sessions']
        self.state = pet_state(self.sessions, snapshot['time'])
        if not self.dragging:
            self.update_sprite()
        self.paint()

    def paint(self):
        tasks = self.feed.update(self.sessions, self.settings['completionMinutes'])
        self.badge.set_label(str(len(tasks)))
        self.badge.set_visible(bool(tasks))
        self._paint_usage_strip()
        keys = [task_key(t) for t in tasks]
        if self.front_key in keys:
            front = keys.index(self.front_key)
            tasks = tasks[front:] + tasks[:front]
        signature = json.dumps([[t['session'], t['status'], t['title'], t['activity'], _age(t['time'])] for t in tasks] + [self.stack_expanded])
        if self.panel_view == 'cards' and signature != getattr(self, '_cards_signature', None):
            self._cards_signature = signature
            self.feed.save()
            self._paint_cards(tasks)
        if self.panel_view == 'usage':
            self._paint_usage()
        if self.panel.get_visible():
            self.layout()

    def _paint_cards(self, tasks):
        while child := self.cards.get_first_child():
            self.cards.remove(child)
        if not tasks:
            self.cards.append(Gtk.Label(label='No tasks yet', css_classes=['empty']))
            return
        shown = tasks if self.stack_expanded else tasks[:1]
        for task in shown:
            self.cards.append(self._card(task))
        if not self.stack_expanded:
            # Cards behind the front one peek out underneath it, in their provider colours.
            for depth, task in enumerate(tasks[1:3], 1):
                self.cards.append(Gtk.Box(css_classes=['peek', f'peek{depth}', _card_css(task)], can_target=False))

    def _card(self, task):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['card', _card_css(task)], spacing=2)
        top = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        top.append(Gtk.Label(label='STATUS STALE' if task['status'] == 'unknown' else task['status'].upper(), css_classes=['state']))
        dismiss = Gtk.Button(label='×', css_classes=['dismiss'], tooltip_text='Dismiss ' + task['title'])
        dismiss.connect('clicked', lambda _b, t=task: (self.feed.dismiss(t), self._force_paint()))
        top.append(dismiss)
        card.append(top)
        card.append(Gtk.Label(label=task['title'], css_classes=['card-title'], wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0))
        card.append(Gtk.Label(label=task['activity'] or 'Working on task', css_classes=['task-activity'], wrap=True,
                              wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0, lines=4, ellipsize=Pango.EllipsizeMode.END))
        card.set_tooltip_text(task['workspace'] or None)
        click = Gtk.GestureClick()
        click.connect('released', lambda *_a, t=task: self.open_task_chat(t))
        card.add_controller(click)
        return card

    def _force_paint(self):
        self._cards_signature = None
        self.paint()

    def _paint_usage_strip(self):
        bar = self.settings['usageBar']
        quota = bar and next((w for w in (self.store.usage.get(bar['provider']) or {}).get('windows', []) if w['label'] == bar['label']), None)
        valid = quota and (not quota.get('reset') or quota['reset'] > now_ms())
        value = max(0, min(100, quota['remaining'])) if valid else 0
        self.mini_fill.set_visible(bool(bar))
        self.mini_fill.set_size_request(round(MINI_W * value / 100), MINI_H)
        for provider in USAGE_COLORS:
            (self.mini_fill.add_css_class if bar and provider == bar['provider'] else self.mini_fill.remove_css_class)(provider)

    def _paint_usage(self):
        signature = json.dumps([self.store.usage, self.store.usage_status, self.settings['usageBar']])
        if signature == getattr(self, '_usage_signature', None):
            return
        self._usage_signature = signature
        while child := self.usage_box.get_first_child():
            self.usage_box.remove(child)
        for key, name, css in (('claude', 'Claude', 'claude'), ('codex', 'Codex', 'codex'), ('antigravity', 'AGY', 'agy')):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['usage-card', css])
            status = self.store.usage_status.get(key)
            heading = Gtk.Box()
            heading.append(Gtk.Label(label=name, xalign=0, hexpand=True, css_classes=['usage-name']))
            if status in ('refreshing', 'failed'):
                heading.append(Gtk.Label(label='↻' if status == 'refreshing' else '!', css_classes=['usage-indicator'],
                                         tooltip_text='Refreshing quota' if status == 'refreshing' else 'Refresh failed; showing previous values'))
            card.append(heading)
            snapshot = self.store.usage.get(key)
            if not snapshot:
                card.append(Gtk.Label(label='Loading…' if status == 'refreshing' else 'Unavailable', xalign=0, css_classes=['usage-note']))
            for window in (snapshot or {}).get('windows', []):
                expired = window.get('reset') and window['reset'] <= now_ms()
                selected = self.settings['usageBar'] == {'provider': key, 'label': window['label']}
                row = Gtk.Box(spacing=4, css_classes=['usage-row'])
                row.append(Gtk.Label(label=_usage_label(window['label']), xalign=0, hexpand=True))
                eye = Gtk.Button(child=Gtk.Image.new_from_file(str(ICONS / ('eye-on.svg' if selected else 'eye.svg'))),
                                 css_classes=['usage-eye'] + (['selected'] if selected else []),
                                 tooltip_text='Remove from collapsed bar' if selected else 'Show on collapsed bar')
                eye.set_opacity(1 if selected else 0)
                eye.connect('clicked', lambda _b, k=key, l=window['label'], on=selected: self.select_usage_bar(k, l, not on))
                hover = Gtk.EventControllerMotion()
                hover.connect('enter', lambda *_a, e=eye: e.set_opacity(1))
                hover.connect('leave', lambda *_a, e=eye, on=selected: e.set_opacity(1 if on else 0))
                row.add_controller(hover)
                row.append(eye)
                row.append(Gtk.Label(label='—' if expired else f"{window['remaining']}%", css_classes=['usage-value'], xalign=1))
                if window.get('reset'):
                    row.set_tooltip_text('Resets ' + time.strftime('%a %H:%M', time.localtime(window['reset'] / 1000)))
                card.append(row)
                card.append(Gtk.ProgressBar(fraction=0 if expired else window['remaining'] / 100))
            self.usage_box.append(card)

    def select_usage_bar(self, provider, label, active):
        self.settings['usageBar'] = {'provider': provider, 'label': label} if active else None
        prefs.save(self.settings)
        self._usage_signature = None
        self.paint()

    def refresh_usage(self):
        if getattr(self, '_usage_refreshing', False):
            return
        self._usage_refreshing = True
        readers = {'codex': codex_usage, 'antigravity': agy_usage, 'claude': claude_usage}
        self.store.usage_status = {k: 'refreshing' for k in readers}
        remaining = [len(readers)]

        def done(provider, usage):
            if usage:
                self.store.usage[provider] = usage
            self.store.usage_status[provider] = 'live' if usage else 'failed'
            remaining[0] -= 1
            if not remaining[0]:
                self._usage_refreshing = False
            self.paint()
            return False

        def work(provider, read):
            try:
                usage = read()
            except Exception:
                usage = None
            GLib.idle_add(done, provider, usage)
        for provider, read in readers.items():
            threading.Thread(target=work, args=(provider, read), daemon=True).start()

    # ---- composer ------------------------------------------------------------
    def _provider(self):
        return self.harness_ids[self.harness_index]

    def load_threads(self, preferred=None):
        provider = self._provider()
        self.thread_request = request = object()
        self.send.set_sensitive(False)
        self.thread.label.set_label('Loading…')
        self.thread.set_sensitive(False)

        def work():
            threads = open_threads(provider, self.store)
            GLib.idle_add(apply, threads)

        def apply(threads):
            if request is not self.thread_request:
                return False
            self.threads = threads
            index = next((i for i, t in enumerate(threads) if t['id'] == preferred), 0 if not preferred else -1)
            if preferred and index < 0:
                self.show_toast('This session is no longer available. Choose another conversation.')
                index = 0
            self.thread.set_sensitive(bool(threads))
            self._thread_selected(index if threads else -1)
            return False
        threading.Thread(target=work, daemon=True).start()

    def _thread_selected(self, index):
        valid = 0 <= index < len(self.threads)
        self.selected_thread = self.threads[index]['id'] if valid else ''
        self.thread.label.set_label(self.threads[index]['name'] if valid else 'No conversations detected for ' + NAMES[self._provider()])
        self.thread.set_tooltip_text(self.threads[index]['name'] if valid else None)
        self._fill_pill(self.thread, [t['name'] for t in self.threads], self._thread_selected, index)
        self.send.set_sensitive(bool(self.selected_thread))

    def _prompt_key(self, _controller, key, _code, state):
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not state & Gdk.ModifierType.SHIFT_MASK:
            self.submit()
            return True
        return False

    def submit(self):
        buffer = self.prompt.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
        if not text or not self.selected_thread or not self.send.get_sensitive():
            return
        provider, thread = self._provider(), self.selected_thread
        self.send.set_sensitive(False)

        def finished(event):
            GLib.idle_add(lambda: self.store.update(event) and self.refresh_state() and False)

        def work():
            try:
                ok, message = start_task(provider, text, thread, self.store, finished)
            except Exception:
                ok, message = False, 'Could not send message'
            GLib.idle_add(after, ok, message)

        def after(ok, message):
            if ok:
                buffer.set_text('')
            self.send.set_sensitive(bool(self.selected_thread))
            self.show_toast(message)
            self.refresh_state()
            return False
        threading.Thread(target=work, daemon=True).start()

    def open_task_chat(self, task):
        self.harness_index = self.harness_ids.index(task['provider'])
        self._set_harness_label()
        self.open_panel('chat')
        self.load_threads(task['session'])
        if task['status'] in ('done', 'error'):
            self.feed.dismiss(task)

    # ---- fleas -----------------------------------------------------------
    def add_flea(self, x, y):
        """Queue a flea at surface coordinates; the pet runs to collect them in order."""
        if len(self.fleas) >= 32 or self.dragging:
            return False
        flea_file = next((f for f in (STATE_DIR / 'sprites/flea/flea-animated.webp', STATE_DIR / 'sprites/flea/Flea.png') if f.exists()), None)
        widget = Gtk.Picture.new_for_filename(str(flea_file)) if flea_file else Gtk.Label(label='🪳')
        widget.set_size_request(44, 64)
        widget.set_can_target(False)
        self.fixed.put(widget, x - 22, y - 32)
        self.fleas.append({'x': x, 'y': y, 'widget': widget})
        self.set_visible(True)
        if not self.run:
            self._next_flea()
        return True

    def _next_flea(self):
        if not self.fleas:
            return
        flea = self.fleas[0]
        pw, ph = self.pet_size()
        self.run_to(flea['x'] - pw / 2, flea['y'] - ph / 2)

    def _collect_flea(self):
        if self.fleas:
            self.fixed.remove(self.fleas.pop(0)['widget'])
        self._next_flea()

    def clear_fleas(self):
        for flea in self.fleas:
            self.fixed.remove(flea['widget'])
        self.fleas.clear()
        self.stop_run()

    def run_to(self, x, y):
        self.stop_run()
        start = (self.pet_x, self.pet_y)
        dx, dy = x - start[0], y - start[1]
        distance = math.hypot(dx, dy)
        if distance < 1:
            return self._collect_flea()
        if abs(dx) > max(1, abs(dy) * .1):
            self.direction = 1 if dx > 0 else -1
        duration = max(.18, min(15, distance / self.settings['movementSpeed']))
        began = time.monotonic()
        self.walking = True
        self.open_panel(None)
        self.update_sprite()

        def frame():
            progress = min(1, (time.monotonic() - began) / duration)
            eased = progress * progress * (3 - 2 * progress)
            self.move_pet(start[0] + dx * eased, start[1] + dy * eased)
            if progress < 1:
                return True
            self.run, self.walking = None, False
            self.update_sprite()
            self.save_position()
            self._collect_flea()
            return False
        self.run = GLib.timeout_add(16, frame)

    def stop_run(self):
        if self.run:
            GLib.source_remove(self.run)
            self.run, self.walking = None, False
            self.update_sprite()

    def _arm_random_flea(self):
        GLib.timeout_add_seconds(random.randint(8 * 60, 15 * 60), self._random_flea)

    def _random_flea(self):
        if self.get_visible() and not self.dragging and not self.panel_view and not self.fleas:
            width, height = self._area()
            pw, ph = self.pet_size()
            mx, my = min(max(40, pw / 2), width / 2), min(max(40, ph / 2), height / 2)
            self.add_flea(mx + random.random() * max(0, width - 2 * mx), my + random.random() * max(0, height - 2 * my))
        self._arm_random_flea()
        return False

    def summon(self, x, y):
        """Drop a flea at global logical coordinates (from hyprctl cursorpos)."""
        monitors = self.get_display().get_monitors()
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            g = monitor.get_geometry()
            if g.x <= x < g.x + g.width and g.y <= y < g.y + g.height and monitor != self._monitor():
                # The overlay covers one monitor; move it (and the pet) to the cursor's monitor.
                self.clear_fleas()
                LayerShell.set_monitor(self, monitor)
                self._pinned_monitor = monitor
                pw, ph = self.pet_size()
                self.pet_x, self.pet_y = min(x - g.x, g.width - pw), min(y - g.y, g.height - ph)
                self.save_position()
                GLib.timeout_add(100, lambda: self.layout() or False)
                return True
        geometry = self._monitor().get_geometry()
        return self.add_flea(x - geometry.x, y - geometry.y)

    def reset_position(self):
        self.clear_fleas()
        width, height = self._area()
        self.move_pet(width - 210, height - 250)
        self.save_position()

