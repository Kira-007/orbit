"""Tray icon via StatusNotifierItem + com.canonical.dbusmenu (replaces Electron's Tray)."""
import os

from gi.repository import Gio, GLib

from .paths import ROOT

SNI_XML = '''<node><interface name="org.kde.StatusNotifierItem">
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/><property name="IconThemePath" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
<property name="Menu" type="o" access="read"/>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<signal name="NewToolTip"/></interface></node>'''

MENU_XML = '''<node><interface name="com.canonical.dbusmenu">
<property name="Version" type="u" access="read"/><property name="Status" type="s" access="read"/>
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
<arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal></interface></node>'''


class Tray:
    """items: list of (label, callback); None for a separator. on_activate: left click."""

    def __init__(self, title, items, on_activate):
        self.title, self.items, self.on_activate = title, items, on_activate
        self.name = 'org.kde.StatusNotifierItem-%d-1' % os.getpid()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        sni = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.bus.register_object('/StatusNotifierItem', sni, self._sni_call, self._sni_prop)
        self.bus.register_object('/MenuBar', menu, self._menu_call, self._menu_prop)
        Gio.bus_own_name_on_connection(self.bus, self.name, Gio.BusNameOwnerFlags.NONE, self._register, None)

    def _register(self, *_):
        self.bus.call('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher', 'org.kde.StatusNotifierWatcher',
                      'RegisterStatusNotifierItem', GLib.Variant('(s)', (self.name,)), None, Gio.DBusCallFlags.NONE, -1, None, None)

    def set_title(self, title):
        self.title = title
        self.bus.emit_signal(None, '/StatusNotifierItem', 'org.kde.StatusNotifierItem', 'NewToolTip', None)

    def _sni_prop(self, _bus, _sender, _path, _iface, name):
        values = {
            'Category': GLib.Variant('s', 'ApplicationStatus'), 'Id': GLib.Variant('s', 'orbit'),
            'Title': GLib.Variant('s', self.title), 'Status': GLib.Variant('s', 'Active'),
            'IconName': GLib.Variant('s', 'tray'), 'IconThemePath': GLib.Variant('s', str(ROOT / 'assets/icons')),
            'ToolTip': GLib.Variant('(sa(iiay)ss)', ('tray', [], self.title, '')),
            'ItemIsMenu': GLib.Variant('b', False), 'Menu': GLib.Variant('o', '/MenuBar'),
        }
        return values.get(name)

    def _sni_call(self, _bus, _sender, _path, _iface, method, _params, invocation):
        if method == 'Activate':
            GLib.idle_add(lambda: self.on_activate() or False)
        invocation.return_value(None)

    def _menu_prop(self, _bus, _sender, _path, _iface, name):
        return {'Version': GLib.Variant('u', 3), 'Status': GLib.Variant('s', 'normal')}.get(name)

    def _item_props(self, index):
        item = self.items[index - 1]
        if item is None:
            return {'type': GLib.Variant('s', 'separator')}
        return {'label': GLib.Variant('s', item[0]), 'enabled': GLib.Variant('b', True), 'visible': GLib.Variant('b', True)}

    def _menu_call(self, _bus, _sender, _path, _iface, method, params, invocation):
        ids = range(1, len(self.items) + 1)
        if method == 'GetLayout':
            children = [GLib.Variant('(ia{sv}av)', (i, self._item_props(i), [])) for i in ids]
            invocation.return_value(GLib.Variant('(u(ia{sv}av))', (1, (0, {'children-display': GLib.Variant('s', 'submenu')}, children))))
        elif method == 'GetGroupProperties':
            wanted = params.unpack()[0] or list(ids)
            invocation.return_value(GLib.Variant('(a(ia{sv}))', ([(i, self._item_props(i)) for i in wanted if i in ids],)))
        elif method == 'GetProperty':
            i, key = params.unpack()
            invocation.return_value(GLib.Variant('(v)', (self._item_props(i).get(key, GLib.Variant('s', '')),)))
        elif method in ('Event', 'EventGroup'):
            events = [params.unpack()[:2]] if method == 'Event' else [(e[0], e[1]) for e in params.unpack()[0]]
            for i, kind in events:
                if kind == 'clicked' and i in ids and self.items[i - 1]:
                    GLib.idle_add(lambda cb=self.items[i - 1][1]: cb() or False)
            invocation.return_value(None if method == 'Event' else GLib.Variant('(ai)', ([],)))
        elif method == 'AboutToShow':
            invocation.return_value(GLib.Variant('(b)', (False,)))
        elif method == 'AboutToShowGroup':
            invocation.return_value(GLib.Variant('(aiai)', ([], [])))
        else:
            invocation.return_value(None)
