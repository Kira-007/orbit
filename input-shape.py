#!/usr/bin/env python3
"""Restrict only the X11 input surface; retain the full alpha drawing surface."""
import ctypes as C
import json
import sys

class Rect(C.Structure):
    _fields_ = [('x', C.c_short), ('y', C.c_short), ('width', C.c_ushort), ('height', C.c_ushort)]
x = C.CDLL('libX11.so.6')
s = C.CDLL('libXext.so.6')
x.XOpenDisplay.argtypes = [C.c_char_p]
x.XOpenDisplay.restype = C.c_void_p
x.XSync.argtypes = [C.c_void_p, C.c_int]
x.XCloseDisplay.argtypes = [C.c_void_p]
s.XShapeCombineRectangles.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_int, C.POINTER(Rect), C.c_int, C.c_int, C.c_int]
display = x.XOpenDisplay(None)
if not display:
    sys.exit('X display unavailable')
window = int(sys.argv[1])
print('ready', flush=True)
try:
    for line in sys.stdin:
        regions = json.loads(line)
        rects = (Rect * len(regions))(*[Rect(round(r['x']), round(r['y']), max(1, round(r['width'])), max(1, round(r['height']))) for r in regions])
        s.XShapeCombineRectangles(display, window, 2, 0, 0, rects, len(rects), 0, 0)
        x.XSync(display, 0)
finally:
    x.XCloseDisplay(display)
