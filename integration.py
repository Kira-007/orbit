"""Per-user integration paths and managed configuration blocks."""
import os,pathlib,re,shlex
ROOT=pathlib.Path(__file__).resolve().parent
HOME=pathlib.Path.home()
CONFIG=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',HOME/'.config'))
DATA=pathlib.Path(os.environ.get('XDG_DATA_HOME',HOME/'.local/share'))
STATE=pathlib.Path(os.environ.get('XDG_STATE_HOME',HOME/'.local/state'))/'agent-pet'
START='-- BEGIN Orbit portable'
END='-- END Orbit portable'
def remove_block(text):
    return re.sub(re.escape(START)+r'.*?'+re.escape(END)+r'\n?', '',text,flags=re.S)
def lua_string(value):
    import json
    return json.dumps(str(value),ensure_ascii=False)
def block(autostart):
    rule='hl.window_rule({ name = "orbit_portable", match = { class = "^(agent-pet|orbit-agent-pet)$", title = "^Orbit Agent Pet$" }, float = true, pin = true, no_follow_mouse = false, no_initial_focus = true, border_size = 0, no_blur = true, no_shadow = true, no_anim = true, opacity = 1.0 })'
    startup='\nhl.on("hyprland.start", function() hl.exec_cmd('+lua_string(shlex.quote(str(ROOT/'start.sh')))+') end)' if autostart else ''
    return START+'\n'+rule+startup+'\n'+END+'\n'
