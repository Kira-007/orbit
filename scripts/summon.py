#!/usr/bin/env python3
"""Ask a running Orbit pet to walk to a captured Hyprland cursor position."""
import argparse,json,math,os,pathlib,socket,subprocess,time

def endpoint():
    return pathlib.Path(os.environ.get('XDG_RUNTIME_DIR') or os.environ.get('XDG_STATE_HOME') or pathlib.Path.home()/'.local/state')/'orbit-agent-pet-control.sock'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('x',nargs='?',type=float);parser.add_argument('y',nargs='?',type=float)
    args=parser.parse_args()
    if (args.x is None)!=(args.y is None):parser.error('Supply both x and y, or neither')
    if args.x is None:
        try:
            point=json.loads(subprocess.check_output(['hyprctl','-j','cursorpos'],text=True,timeout=2));args.x,args.y=point['x'],point['y']
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):parser.exit(1,'Could not read the Hyprland cursor.\n')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (args.x,args.y)):parser.error('Cursor coordinates must be finite')
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(2);client.connect(str(endpoint()))
            client.sendall((json.dumps({'type':'summon','x':args.x,'y':args.y,'time':time.time()*1000})+'\n').encode())
            if client.recv(128).strip()!=b'ok':parser.exit(1,'Orbit could not move the pet.\n')
    except OSError:parser.exit(1,'Orbit is not running. Start Orbit, then try the shortcut again.\n')
if __name__=='__main__':main()
