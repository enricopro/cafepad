# CaféPad — Reverse Engineering & Research Archive

This directory contains the historical reverse-engineering tools, packet analyzers, Bluetooth protocol probes, and forensic scripts developed during the creation of **CaféPad**.

### Contents:
- **`probe_black.py` / `hunt_black.c`**: Low-level Bluetooth LIAC (Limited Inquiry Access Code `0x9E8B00`) and Class-of-Device (`0x002504`) scanners used to isolate non-standard clone controllers broadcasting blank or obfuscated names.
- **`sniffer.py` / `monitor_usb.py`**: Raw L2CAP / USB HID packet capturers that reverse-engineered the Wii U Pro handshake (reports `0x15`, `0x11`, extension register initialization `0x16 0x04 0xA4 0x00 0xF0`, and DRM mode `0x12 0x00 0x3D`).
- **`direct_connect.py` / `smart_connect.py`**: Early prototypes of the zero-dongle direct L2CAP bridge prior to consolidation into `cafepad.py` and `cafepad.c`.
- **`Dolphin_IOLinux.*` / `bluubomb/` / `wupclient.py`**: Reference implementations from the Wii U / Dolphin homebrew ecosystems used to verify hardware timing and bitmask alignments.

*These scripts are preserved for archival, educational, and hardware research purposes. For production usage, use the unified `cafepad` daemon or `libcafepad`.*
