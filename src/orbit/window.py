"""The pet overlay: one transparent gtk4-layer-shell surface covering a monitor.

Only the visible controls accept input; the rest of the surface has an empty
input region, so clicks fall through to the windows underneath.
"""
import json
import os
import math
import random
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
from .notifications import NotificationFeed  # noqa: E402
from .paths import POSITION_FILE, ROOT, STATE_DIR  # noqa: E402
from .sprite import BOX_H, BOX_W, DragDirection, SpriteView, pet_state  # noqa: E402
from .store import Store, now_ms  # noqa: E402
from .tasks import open_threads, start_task  # noqa: E402
from .usage import agy_usage, claude_usage, codex_usage  # noqa: E402

NAMES = {'claude': 'Claude Code', 'codex-cli': 'Codex CLI', 'codex-desktop': 'Codex Desktop', 'antigravity': 'AGY CLI'}
PANEL_W, PANEL_H, TOOLBAR_W, TOOLBAR_H, GAP = 358, 360, 124, 40, 6
USAGE_COLORS = {'codex': '#eeeeee', 'claude': '#ee9877', 'antigravity': '#8bdba4'}


def _age(t):
    sec = max(0, (now_ms() - t) // 1000)
    return 'just now' if sec < 60 else f'{sec // 60}m ago' if sec < 3600 else f'{sec // 3600}h ago'


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
        self.hovering, self.hover_timer, self.panel_view = False, None, None
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
        self._hoverable(self.sprite)

    def _build_toolbar(self):
        self.toolbar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['toolbar'], valign=Gtk.Align.CENTER)
        self.toolbar.set_size_request(TOOLBAR_W, TOOLBAR_H)
        row = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, vexpand=True)
        for icon, tip, view in (('document-edit-symbolic', 'Message a conversation', 'chat'),
                                ('power-profile-performance-symbolic', 'Usage remaining', 'usage'),
                                ('mail-unread-symbolic', 'Task notifications', 'cards')):
            button = Gtk.Button(icon_name=icon, tooltip_text=tip)
            button.connect('clicked', lambda _b, v=view: self.open_panel(None if self.panel_view == v else v))
            if view == 'cards':
                overlay = Gtk.Overlay(child=button)
                self.badge = Gtk.Label(css_classes=['badge'], halign=Gtk.Align.END, valign=Gtk.Align.START, visible=False, can_target=False)
                overlay.add_overlay(self.badge)
                row.append(overlay)
            else:
                row.append(button)
        self.usage_strip = Gtk.Box(css_classes=['usage-strip'], halign=Gtk.Align.START, margin_start=14, margin_bottom=4, visible=False)
        self.toolbar.append(row)
        self.toolbar.append(self.usage_strip)
        self.fixed.put(self.toolbar, 0, 0)
        self._hoverable(self.toolbar)

    def _build_panel(self):
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['panel'], visible=False)
        self.panel.set_size_request(PANEL_W, -1)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vhomogeneous=False)
        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.cards_scroll = Gtk.ScrolledWindow(child=self.cards, hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True, max_content_height=PANEL_H)
        self.stack.add_named(self.cards_scroll, 'cards')
        self.usage_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack.add_named(Gtk.ScrolledWindow(child=self.usage_box, hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True, max_content_height=PANEL_H), 'usage')
        self.stack.add_named(self._build_composer(), 'chat')
        self.toast = Gtk.Label(css_classes=['toast'], wrap=True, visible=False, margin_top=6)
        self.panel.append(self.stack)
        self.panel.append(self.toast)
        self.fixed.put(self.panel, 0, 0)

    def _build_composer(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=['sheet', 'composer'])
        self.prompt = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        self.prompt.set_size_request(-1, 72)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self._prompt_key)
        self.prompt.add_controller(keys)
        box.append(self.prompt)
        row = Gtk.Box(spacing=6)
        self.harness_ids = list(NAMES)
        self.harness = Gtk.DropDown.new_from_strings([NAMES[h] for h in self.harness_ids])
        self.harness.set_selected(self.harness_ids.index(self.settings['harness']))
        self.harness.connect('notify::selected', lambda *_: self.load_threads())
        self.thread_list = Gtk.StringList()
        self.thread = Gtk.DropDown(model=self.thread_list, hexpand=True)
        self.thread.connect('notify::selected', self._thread_selected)
        self.send = Gtk.Button(icon_name='go-up-symbolic', tooltip_text='Send message (Enter; Shift+Enter for a new line)')
        self.send.connect('clicked', lambda *_: self.submit())
        for widget in (self.harness, self.thread, self.send):
            row.append(widget)
        box.append(row)
        return box

    def _hoverable(self, widget):
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda *_: self._hover(True))
        motion.connect('leave', lambda *_: self._hover(False))
        widget.add_controller(motion)

    # ---- geometry ------------------------------------------------------
    def _monitor(self):
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
        if self.panel.get_visible():
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
        pw, ph = self.pet_size()
        if not (self.pet_x <= x < self.pet_x + pw and self.pet_y <= y < self.pet_y + ph):
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
        for label, action in (('Hide', 'app.hide'), ('Reset position', 'app.reset-position'), ('Quit Orbit', 'app.quit')):
            menu.append(label, action)
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self.sprite)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        popover.set_pointing_to(rect)
        popover.popup()

    def _hover(self, inside):
        if self.hover_timer:
            GLib.source_remove(self.hover_timer)
            self.hover_timer = None
        if inside:
            self.hovering = True
            self.update_controls()
        else:
            def leave():
                self.hover_timer, self.hovering = None, False
                self.update_controls()
                return False
            self.hover_timer = GLib.timeout_add(self.settings['hoverDelay'], leave)

    def update_controls(self):
        self.toolbar.set_visible(bool(self.toolbar_pinned or self.hovering or self.panel_view) and not self.dragging)
        self.layout()

    def _active_pet(self):
        return next((p for p in self.settings['spritePets'] if p['id'] == self.settings['activeSpritePet']), {})

    def update_sprite(self):
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
        signature = json.dumps([[t['session'], t['status'], t['title'], t['activity'], _age(t['time'])] for t in tasks])
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
        for task in tasks:
            css = {'claude': 'claude', 'antigravity': 'agy'}.get(task['provider'], 'codex')
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=['card', css], spacing=4)
            top = Gtk.Box(spacing=6)
            title = Gtk.Label(label=task['title'], css_classes=['card-title'], wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0, hexpand=True)
            state = Gtk.Label(label='status stale' if task['status'] == 'unknown' else task['status'], css_classes=['state'], valign=Gtk.Align.START)
            dismiss = Gtk.Button(label='×', css_classes=['dismiss'], valign=Gtk.Align.START, tooltip_text='Dismiss')
            dismiss.connect('clicked', lambda _b, t=task: (self.feed.dismiss(t), self._force_paint()))
            for widget in (title, state, dismiss):
                top.append(widget)
            card.append(top)
            card.append(Gtk.Label(label=f"{NAMES[task['provider']]} · {_age(task['time'])} · {task['activity']}", css_classes=['meta'],
                                  xalign=0, ellipsize=Pango.EllipsizeMode.END, tooltip_text=task['workspace']))
            click = Gtk.GestureClick()
            click.connect('released', lambda *_a, t=task: self.open_task_chat(t))
            card.add_controller(click)
            self.cards.append(card)

    def _force_paint(self):
        self._cards_signature = None
        self.paint()

    def _paint_usage_strip(self):
        bar = self.settings['usageBar']
        quota = bar and next((w for w in (self.store.usage.get(bar['provider']) or {}).get('windows', []) if w['label'] == bar['label']), None)
        valid = quota and (not quota.get('reset') or quota['reset'] > now_ms())
        self.usage_strip.set_visible(bool(bar))
        if bar:
            value = max(0, min(100, quota['remaining'])) if valid else 0
            self.usage_strip.set_size_request(round((TOOLBAR_W - 28) * value / 100), 3)
            for provider in USAGE_COLORS:
                (self.usage_strip.add_css_class if provider == bar['provider'] else self.usage_strip.remove_css_class)(provider)
            self.toolbar.set_tooltip_text(f"{bar['provider']} · {bar['label']} · {value}% remaining" if valid else 'Selected limit unavailable')

    def _paint_usage(self):
        signature = json.dumps([self.store.usage, self.store.usage_status, self.settings['usageBar']])
        if signature == getattr(self, '_usage_signature', None):
            return
        self._usage_signature = signature
        while child := self.usage_box.get_first_child():
            self.usage_box.remove(child)
        for key, name, css in (('claude', 'Claude', 'claude'), ('codex', 'Codex', 'codex'), ('antigravity', 'AGY', 'agy')):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=['usage-card', css])
            status = self.store.usage_status.get(key)
            heading = name + {'refreshing': '  ↻', 'failed': '  !'}.get(status, '')
            card.append(Gtk.Label(label=heading, xalign=0, css_classes=['usage-name']))
            snapshot = self.store.usage.get(key)
            if not snapshot:
                card.append(Gtk.Label(label='Loading…' if status == 'refreshing' else 'Unavailable', xalign=0))
            for window in (snapshot or {}).get('windows', []):
                expired = window.get('reset') and window['reset'] <= now_ms()
                row = Gtk.Box(spacing=6)
                row.append(Gtk.Label(label=window['label'], xalign=0, hexpand=True))
                selected = self.settings['usageBar'] == {'provider': key, 'label': window['label']}
                eye = Gtk.ToggleButton(icon_name='view-reveal-symbolic', active=selected, tooltip_text='Show on collapsed bar')
                eye.connect('toggled', lambda b, k=key, l=window['label']: self.select_usage_bar(k, l, b.get_active()))
                row.append(eye)
                row.append(Gtk.Label(label='—' if expired else f"{window['remaining']}%"))
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
        return self.harness_ids[self.harness.get_selected()]

    def load_threads(self, preferred=None):
        provider = self._provider()
        self.thread_request = request = object()
        self.send.set_sensitive(False)
        self.thread_list.splice(0, self.thread_list.get_n_items(), ['Loading…'])

        def work():
            threads = open_threads(provider, self.store)
            GLib.idle_add(apply, threads)

        def apply(threads):
            if request is not self.thread_request:
                return False
            self.threads = threads
            self.thread_list.splice(0, self.thread_list.get_n_items(), [t['name'] for t in threads] or ['No conversations detected'])
            index = next((i for i, t in enumerate(threads) if t['id'] == preferred), 0 if not preferred else -1)
            if preferred and index < 0:
                self.show_toast('This session is no longer available. Choose another conversation.')
                index = 0
            self.thread.set_selected(max(0, index))
            self._thread_selected()
            return False
        threading.Thread(target=work, daemon=True).start()

    def _thread_selected(self, *_):
        index = self.thread.get_selected()
        self.selected_thread = self.threads[index]['id'] if 0 <= index < len(self.threads) else ''
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
        self.harness.set_selected(self.harness_ids.index(task['provider']))
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
        geometry = self._monitor().get_geometry()
        return self.add_flea(x - geometry.x, y - geometry.y)

    def reset_position(self):
        self.clear_fleas()
        width, height = self._area()
        self.move_pet(width - 210, height - 250)
        self.save_position()

