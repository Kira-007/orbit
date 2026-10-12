#!/usr/bin/env python3
"""Run the Orbit integration command."""
import pathlib,runpy,sys
scripts=pathlib.Path(__file__).resolve().parent/"scripts"
sys.path.insert(0,str(scripts))
runpy.run_path(str(scripts/"install.py"),run_name="__main__")
