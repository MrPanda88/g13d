// g13d focus tracker: exports the focused window on the session bus for the g13d daemon.
// Object /org/g13d/Shell on gnome-shell's connection (destination org.gnome.Shell), interface org.g13d.Shell.
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const IFACE = `
<node>
  <interface name="org.g13d.Shell">
    <method name="GetFocus"><arg type="a{sv}" direction="out" name="window"/></method>
    <method name="ListWindows"><arg type="aa{sv}" direction="out" name="windows"/></method>
    <signal name="FocusChanged"><arg type="a{sv}" name="window"/></signal>
    <property name="Version" type="u" access="read"/>
  </interface>
</node>`;

const OBJECT_PATH = '/org/g13d/Shell';

function str(s) {
    return GLib.Variant.new_string(s ?? '');
}

function describe(win) {
    if (!win)
        return {};
    let app = null;
    try {
        app = Shell.WindowTracker.get_default().get_window_app(win);
    } catch (_e) {
        app = null;
    }
    return {
        'wm_class': str(win.get_wm_class()),
        'wm_class_instance': str(win.get_wm_class_instance()),
        'title': str(win.get_title()),
        'pid': GLib.Variant.new_int32(win.get_pid() ?? 0),
        'app_id': str(app ? app.get_id() : ''),
        'app_name': str(app ? app.get_name() : ''),
        'sandboxed_app_id': str(win.get_sandboxed_app_id()),
        'gtk_app_id': str(win.get_gtk_application_id()),
    };
}

export default class G13dFocusExtension extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
        this._focusId = global.display.connect('notify::focus-window', () => this._emit());
    }

    disable() {
        if (this._focusId) {
            global.display.disconnect(this._focusId);
            this._focusId = 0;
        }
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
    }

    get Version() {
        return 1;
    }

    GetFocus() {
        return describe(global.display.focus_window);
    }

    ListWindows() {
        const seen = new Set();
        const out = [];
        for (const actor of global.get_window_actors()) {
            const win = actor.meta_window;
            if (!win || win.is_skip_taskbar())
                continue;
            const d = describe(win);
            const key = `${d.wm_class.unpack()}|${d.pid.unpack()}`;
            if (seen.has(key))
                continue;
            seen.add(key);
            out.push(d);
        }
        return out;
    }

    _emit() {
        if (!this._dbus)
            return;
        this._dbus.emit_signal('FocusChanged', new GLib.Variant('(a{sv})', [describe(global.display.focus_window)]));
    }
}
