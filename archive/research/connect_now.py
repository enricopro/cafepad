#!/usr/bin/env python3
"""
Wrapper calling direct_connect.py with target 40:F4:07:CD:23:4C
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DIRECT_CONNECT = os.path.join(SCRIPT_DIR, "direct_connect.py")
cmd = [sys.executable, DIRECT_CONNECT, "--target", "40:F4:07:CD:23:4C"] + sys.argv[1:]
os.execv(sys.executable, cmd)
