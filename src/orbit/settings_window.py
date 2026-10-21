"""Settings window: general preferences and pet customization (port of settings.html)."""
import shutil
import uuid
from pathlib import Path

import gi

gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
from gi.repository import GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from . import settings as prefs  # noqa: E402
from .paths import STATE_DIR  # noqa: E402
from .sprite import SpriteView  # noqa: E402

ANIMATIONS = [('idle', 'Idle'), ('walking', 'Running (shortcut)'), ('dragging', 'Dragging (cursor)'), ('working', 'Working'),
              ('waiting', 'Waiting'), ('done', 'Done'), ('error', 'Error'), ('unknown', 'Stale')]
HARNESSES = [('codex-cli', 'Codex CLI'), ('codex-desktop', 'Codex Desktop'), ('claude', 'Claude Code'), ('antigravity', 'AGY CLI')]


def _row(label, widget):
    row = Gtk.Box(spacing=12, margin_top=4, margin_bottom=4)
    row.append(Gtk.Label(label=label, xalign=0, hexpand=True))
    row.append(widget)
    return row


def _choice(options, current, on_change):
    dropdown = Gtk.DropDown.new_from_strings([name for _, name in options])
    values = [value for value, _ in options]
    dropdown.set_selected(values.index(current) if current in values else 0)
    dropdown.connect('notify::selected', lambda d, _p: on_change(values[d.get_selected()]))
    return dropdown


class SettingsWindow(Gtk.Window):
    def __init__(self, pet):
        super().__init__(title='Orbit Settings', default_width=500, default_height=610)
        self.pet = pet
        self.settings = pet.settings
        self.save_timer = None
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.add_named(self._scrolled(self._general()), 'general')
        self.stack.add_named(self._scrolled(self._customize()), 'customize')
        header = Gtk.HeaderBar()
        self.back = Gtk.Button(label='← Settings', visible=False)
        self.back.connect('clicked', lambda *_: self._show('general'))
        header.pack_start(self.back)
        done = Gtk.Button(label='Done')
        done.connect('clicked', lambda *_: self.close())
        header.pack_end(done)
        self.set_titlebar(header)
        self.set_child(self.stack)
        self.connect('close-request', lambda *_: self._flush() or False)

    def _scrolled(self, child):
        child.set_margin_start(18)
        child.set_margin_end(18)
        child.set_margin_top(12)
        child.set_margin_bottom(12)
        return Gtk.ScrolledWindow(child=child, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _show(self, name):
        self.stack.set_visible_child_name(name)
        self.back.set_visible(name != 'general')
        self.set_title('Customize' if name != 'general' else 'Orbit Settings')

    # ---- persistence -----------------------------------------------------
    def changed(self, key=None, value=None, immediate=False):
        if key:
            self.settings[key] = value
        self.pet.apply_settings(self.settings)
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        self.save_timer = GLib.timeout_add(0 if immediate else 180, self._flush)

    def _flush(self):
        if self.save_timer:
            GLib.source_remove(self.save_timer)
            self.save_timer = None
        self.settings = prefs.normalize(self.settings)
        prefs.save(self.settings)
        self.pet.apply_settings(self.settings)
        return False

    # ---- general -------------------------------------------------------
    def _general(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 60, 240, 5)
        scale.set_value(self.settings['petScale'] * 100)
        scale.set_size_request(200, -1)
        scale.set_format_value_func(lambda _s, v: f'{round(v)}%')
        scale.set_draw_value(True)
        scale.connect('value-changed', lambda s: self.changed('petScale', round(s.get_value()) / 100))
        box.append(_row('Pet size', scale))
        speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 150, 1800, 50)
        speed.set_value(self.settings['movementSpeed'])
        speed.set_size_request(200, -1)
        speed.set_format_value_func(lambda _s, v: f'{round(v)} px/s')
        speed.set_draw_value(True)
        speed.set_tooltip_text('Travel speed when collecting fleas placed with Win + Y.')
        speed.connect('value-changed', lambda s: self.changed('movementSpeed', round(s.get_value())))
        box.append(_row('Movement speed', speed))
        for key, label in (('animations', 'Animations'), ('controls', 'Always show controls')):
            switch = Gtk.Switch(active=self.settings[key], valign=Gtk.Align.CENTER)
            switch.connect('notify::active', lambda s, _p, k=key: self.changed(k, s.get_active(), True))
            box.append(_row(label, switch))
        box.append(_row('Hover delay', _choice([(400, 'Short'), (750, 'Medium'), (1200, 'Long')], self.settings['hoverDelay'],
                                               lambda v: self.changed('hoverDelay', v, True))))
        box.append(_row('Recent tasks', _choice([(5, '5 minutes'), (10, '10 minutes'), (30, '30 minutes'), (60, '1 hour')],
                                                self.settings['completionMinutes'], lambda v: self.changed('completionMinutes', v, True))))
        flea = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        spins = [Gtk.SpinButton.new_with_range(1, 240, 1) for _ in range(2)]
        for spin, value in zip(spins, self.settings['fleaMinutes']):
            spin.set_value(value)
            spin.connect('value-changed', lambda *_: self.changed('fleaMinutes', sorted(round(s.get_value()) for s in spins)))
        flea.append(spins[0])
        flea.append(Gtk.Label(label='to'))
        flea.append(spins[1])
        flea.append(Gtk.Label(label='min'))
        flea.set_tooltip_text('A flea appears at a random time within this range.')
        box.append(_row('Random flea every', flea))
        box.append(_row('Default harness', _choice(HARNESSES, self.settings['harness'], lambda v: self.changed('harness', v, True))))
        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=12)
        reset = Gtk.Button(label='Reset position')
        reset.connect('clicked', lambda *_: self.pet.reset_position())
        customize = Gtk.Button(label='Customize', css_classes=['suggested-action'])
        customize.connect('clicked', lambda *_: self._show('customize'))
        actions.append(reset)
        actions.append(customize)
        box.append(actions)
        return box

    # ---- customization -------------------------------------------------
    def _customize(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(_row('Pet style', _choice([('custom', 'Custom'), ('sprite', 'Sprite sheet')], self.settings['petMode'], self._mode)))
        self.custom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        name = Gtk.Entry(text=self.settings['petName'], max_length=30, placeholder_text='Orbit')
        name.connect('changed', lambda e: self.changed('petName', e.get_text()))
        self.custom_box.append(_row('Name', name))
        for key, label in (('bodyColor', 'Body color'), ('accentColor', 'Accent color')):
            color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False))
            rgba = color.get_rgba().copy()
            rgba.parse(self.settings[key])
            color.set_rgba(rgba)
            color.connect('notify::rgba', lambda b, _p, k=key: self.changed(k, '#%02x%02x%02x' % tuple(round(c * 255) for c in (b.get_rgba().red, b.get_rgba().green, b.get_rgba().blue))))
            self.custom_box.append(_row(label, color))
        self.custom_box.append(_row('Expression', _choice([('friendly', 'Friendly'), ('focused', 'Focused'), ('sleepy', 'Sleepy')],
                                                          self.settings['face'], lambda v: self.changed('face', v, True))))
        box.append(self.custom_box)

        self.sprite_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pets = Gtk.Box(spacing=8)
        self.pet_list = Gtk.StringList()
        self.pet_choice = Gtk.DropDown(model=self.pet_list, hexpand=True)
        self.pet_choice.connect('notify::selected', self._choose_pet)
        add = Gtk.Button(label='+ Add pet')
        add.connect('clicked', self._add_pet)
        pets.append(self.pet_choice)
        pets.append(add)
        self.sprite_box.append(pets)
        self.pet_name = Gtk.Entry(max_length=60)
        self.pet_name.connect('changed', self._rename_pet)
        self.sprite_box.append(_row('Name', self.pet_name))
        self.offsets = {}
        for key, label in (('offsetX', 'Global X offset'), ('offsetY', 'Sprite–bar gap')):
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 1)
            scale.set_size_request(200, -1)
            scale.set_draw_value(True)
            scale.connect('value-changed', lambda s, k=key: self._pet_field(k, round(s.get_value())))
            self.offsets[key] = scale
            self.sprite_box.append(_row(label, scale))
        self.animation = Gtk.DropDown.new_from_strings([name for _, name in ANIMATIONS])
        self.animation.connect('notify::selected', lambda *_: self._render_animation())
        self.sprite_box.append(_row('Animation', self.animation))
        self.facing = Gtk.DropDown.new_from_strings(['Right', 'Left'])
        self.facing.connect('notify::selected', self._set_facing)
        self.sprite_box.append(_row('Sheet faces', self.facing))
        self.preview = SpriteView()
        self.preview.resize(1.6)
        self.preview.set_halign(Gtk.Align.CENTER)
        self.sprite_box.append(self.preview)
        upload = Gtk.Box(spacing=8)
        self.sheet_name = Gtk.Label(label='No sheet selected', xalign=0, hexpand=True, ellipsize=3)
        pick = Gtk.Button(label='Upload')
        pick.connect('clicked', self._pick_sheet)
        upload.append(self.sheet_name)
        upload.append(pick)
        self.sprite_box.append(upload)
        self.frames = Gtk.SpinButton.new_with_range(1, 256, 1)
        self.frames.connect('value-changed', lambda s: self._sheet_field('frames', int(s.get_value())))
        self.sprite_box.append(_row('Cut count', self.frames))
        self.fps = Gtk.SpinButton.new_with_range(1, 60, 1)
        self.fps.connect('value-changed', lambda s: self._sheet_field('fps', int(s.get_value())))
        self.sprite_box.append(_row('Speed (FPS)', self.fps))
        self.error = Gtk.Label(xalign=0, css_classes=['error'])
        self.sprite_box.append(self.error)
        box.append(self.sprite_box)
        self._refresh_pets()
        self._mode(self.settings['petMode'], save=False)
        return box

    def _mode(self, mode, save=True):
        self.custom_box.set_visible(mode != 'sprite')
        self.sprite_box.set_visible(mode == 'sprite')
        if save:
            self.changed('petMode', mode, True)

    def _selected_pet(self):
        return next((p for p in self.settings['spritePets'] if p['id'] == self.settings['activeSpritePet']), None)

    def _refresh_pets(self):
        self._refreshing = True
        names = [p['name'] for p in self.settings['spritePets']] or ['Add your first pet']
        self.pet_list.splice(0, self.pet_list.get_n_items(), names)
        ids = [p['id'] for p in self.settings['spritePets']]
        if self.settings['activeSpritePet'] in ids:
            self.pet_choice.set_selected(ids.index(self.settings['activeSpritePet']))
        pet = self._selected_pet()
        self.pet_name.set_text(pet['name'] if pet else '')
        self.pet_name.set_sensitive(bool(pet))
        for key, scale in self.offsets.items():
            scale.set_value((pet or {}).get(key) or 0)
            scale.set_sensitive(bool(pet))
        self._refreshing = False
        self._render_animation()

    def _state(self):
        return ANIMATIONS[self.animation.get_selected()][0]

    def _render_animation(self):
        pet = self._selected_pet()
        config = (pet or {}).get('spriteSheets', {}).get(self._state())
        self._refreshing, was = True, getattr(self, '_refreshing', False)
        self.sheet_name.set_label(config['name'] if config else 'No sheet selected')
        self.frames.set_value(config['frames'] if config else 1)
        self.fps.set_value(config['fps'] if config else 10)
        self.frames.set_sensitive(bool(config))
        self.fps.set_sensitive(bool(config))
        self.facing.set_selected(1 if ((config or {}).get('facing') or (pet or {}).get('facing')) == 'left' else 0)
        self._refreshing = was
        self.preview.set_sprite({**config, 'offsetX': pet.get('offsetX', 0)} if config else None, self.settings['animations'])

    def _choose_pet(self, *_):
        if getattr(self, '_refreshing', False):
            return
        index = self.pet_choice.get_selected()
        if 0 <= index < len(self.settings['spritePets']):
            self.settings['activeSpritePet'] = self.settings['spritePets'][index]['id']
            self._refresh_pets()
            self.changed(immediate=True)

    def _add_pet(self, *_):
        pet = {'id': str(uuid.uuid4()), 'name': 'My pet %d' % (len(self.settings['spritePets']) + 1), 'facing': 'right',
               'offsetX': 0, 'offsetY': 0, 'spriteSheets': {}}
        self.settings['spritePets'].append(pet)
        self.settings['activeSpritePet'] = pet['id']
        self._refresh_pets()
        self.changed(immediate=True)
        self.pet_name.grab_focus()

    def _rename_pet(self, entry):
        pet = self._selected_pet()
        if pet and not getattr(self, '_refreshing', False):
            pet['name'] = entry.get_text().strip() or 'My pet'
            self._refreshing = True
            self.pet_list.splice(self.pet_choice.get_selected(), 1, [pet['name']])
            self._refreshing = False
            self.changed()

    def _pet_field(self, key, value):
        pet = self._selected_pet()
        if pet and not getattr(self, '_refreshing', False):
            pet[key] = value
            self._render_animation()
            self.changed()

    def _sheet_field(self, key, value):
        pet = self._selected_pet()
        config = (pet or {}).get('spriteSheets', {}).get(self._state())
        if config and not getattr(self, '_refreshing', False):
            config[key] = value
            if key == 'frames':
                config['columns'] = value
            self._render_animation()
            self.changed()

    def _set_facing(self, dropdown, _param):
        if getattr(self, '_refreshing', False):
            return
        pet = self._selected_pet()
        if not pet:
            return
        facing = 'left' if dropdown.get_selected() else 'right'
        config = pet['spriteSheets'].get(self._state())
        if config:
            config['facing'] = facing
        else:
            pet['facing'] = facing
        self.changed(immediate=True)

    def _pick_sheet(self, *_):
        if not self._selected_pet():
            self._add_pet()
        images = Gtk.FileFilter(name='Images')
        for suffix in ('png', 'webp', 'jpg', 'jpeg'):
            images.add_suffix(suffix)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(images)
        dialog = Gtk.FileDialog(title='Choose a sprite sheet', filters=filters)
        pet_id, state = self.settings['activeSpritePet'], self._state()
        dialog.open(self, None, lambda d, result: self._sheet_chosen(d, result, pet_id, state))

    def _sheet_chosen(self, dialog, result, pet_id, state):
        try:
            source = Path(dialog.open_finish(result).get_path())
        except GLib.Error:
            return
        self.error.set_label('')
        try:
            if source.stat().st_size > 20 * 1024 * 1024:
                raise ValueError('Choose an image smaller than 20 MB')
            if GdkPixbuf.Pixbuf.get_file_info(str(source))[0] is None:
                raise ValueError('Could not read this image')
            folder = STATE_DIR / 'sprites'
            folder.mkdir(parents=True, exist_ok=True)
            destination = folder / (str(uuid.uuid4()) + source.suffix)
            shutil.copyfile(source, destination)
        except (OSError, ValueError) as error:
            self.error.set_label(str(error) or 'Could not read image')
            return
        pet = next((p for p in self.settings['spritePets'] if p['id'] == pet_id), None)
        if not pet:
            return
        old = pet['spriteSheets'].get(state) or {}
        pet['spriteSheets'][state] = {'sheet': destination.as_uri(), 'name': source.name, 'frames': 1, 'columns': 1,
                                      'fps': old.get('fps', 10), 'facing': old.get('facing') or pet.get('facing') or 'right'}
        self._render_animation()
        self.changed(immediate=True)
