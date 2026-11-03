"""
Compatibility shim for python/wiiupro.py -> cafepad
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from cafepad import *

if __name__ == "__main__":
    main()
