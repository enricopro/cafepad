#!/usr/bin/env python3
"""
Wii U Pro Controller (USB) Signal Reverse Engineering Tool
Uses native Linux /dev/hidraw directly (no libusb detach conflicts).
"""

import sys
import time
import os
import glob
import json
import select
from datetime import datetime

TARGET_VID = 0x0471
TARGET_PID = 0x0666

COLOR_RESET   = "\033[0m"
COLOR_RED     = "\033[1;31m"
COLOR_GREEN   = "\033[1;32m"
COLOR_YELLOW  = "\033[1;33m"
COLOR_CYAN    = "\033[1;36m"

def find_hidraw():
    # 1. Match via sysfs
    for syspath in glob.glob("/sys/bus/hid/devices/*"):
        try:
            with open(os.path.join(syspath, "uevent"), "r") as f:
                content = f.read()
                if f"{TARGET_VID:08X}" in content and f"{TARGET_PID:08X}" in content:
                    hidraw_dir = os.path.join(syspath, "hidraw")
                    if os.path.exists(hidraw_dir):
                        for node in os.listdir(hidraw_dir):
                            if node.startswith("hidraw"):
                                return os.path.join("/dev", node)
        except Exception:
            continue

    # 2. Check /dev/hidraw1..15
    for f in sorted(glob.glob("/dev/hidraw*")):
        if f == "/dev/hidraw0":
            continue  # usually internal touchpad
        try:
            fd = os.open(f, os.O_RDWR | os.O_NONBLOCK)
            os.close(fd)
            return f
        except Exception:
            pass
    return None

def open_device():
    # Prefer native Linux /dev/hidraw directly
    node = find_hidraw()
    if node:
        try:
            fd = os.open(node, os.O_RDWR)
            return ("raw_hidraw", fd, f"Linux /dev/hidraw node ({node})")
        except PermissionError:
            print(f"{COLOR_RED}[!] Permission denied accessing {node}.{COLOR_RESET}")
            print(f"Run: sudo chmod 666 {node}")
        except Exception as e:
            pass

    # Fallback to hidapi on non-Linux or if hidraw not found
    try:
        import hid
        devs = hid.enumerate(TARGET_VID, TARGET_PID)
        if devs:
            d = hid.device()
            d.open_path(devs[0]['path'])
            return ("hidapi", d, "hidapi fallback")
    except Exception:
        pass

    return (None, None, None)

def analyze_packet(curr, prev, idx):
    changed_offsets = []
    bit_events = []

    if prev is not None:
        for i in range(min(len(curr), len(prev))):
            if curr[i] != prev[i]:
                changed_offsets.append(i)
                for bit in range(8):
                    mask = 1 << bit
                    c_bit = bool(curr[i] & mask)
                    p_bit = bool(prev[i] & mask)
                    if c_bit and not p_bit:
                        bit_events.append(f"{COLOR_GREEN}+ BIT PRESSED {COLOR_RESET} Byte[{i}], Bit {bit} (Mask: 0x{mask:02X})")
                    elif not c_bit and p_bit:
                        bit_events.append(f"{COLOR_YELLOW}- BIT RELEASED{COLOR_RESET} Byte[{i}], Bit {bit} (Mask: 0x{mask:02X})")

    # Format header
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"\n{COLOR_CYAN}=== PACKET #{idx:05d} [{ts}] Length: {len(curr)} bytes ==={COLOR_RESET}")

    # Format 32-byte hex view
    for row in range(0, min(len(curr), 32), 16):
        parts = []
        for i in range(row, min(row + 16, len(curr))):
            val = curr[i]
            if prev is not None and i < len(prev) and val != prev[i]:
                parts.append(f"{COLOR_RED}{val:02X}{COLOR_RESET}")
            else:
                parts.append(f"{val:02X}")
        print(f"  {row:02X}: " + " ".join(parts))

    if bit_events:
        print(f"  {COLOR_YELLOW}Button Events:{COLOR_RESET}")
        for ev in bit_events:
            print(f"    {ev}")
    elif changed_offsets:
        print(f"  {COLOR_YELLOW}Changed bytes:{COLOR_RESET} {changed_offsets}")
    print("-" * 65)

def main():
    print(f"{COLOR_CYAN}===================================================={COLOR_RESET}")
    print(f"{COLOR_CYAN}  Wii U Pro Controller (USB Native Raw HID Sniffer) {COLOR_RESET}")
    print(f"{COLOR_CYAN}===================================================={COLOR_RESET}")

    capture_path = os.path.join(os.path.dirname(__file__), "..", "capture.jsonl")
    capture_path = os.path.abspath(capture_path)
    log_file = open(capture_path, "a", buffering=1)

    prev_packet = None
    packet_count = 0

    while True:
        backend, dev, dev_name = open_device()
        if not dev:
            sys.stdout.write("\rWaiting for USB controller (unplug and replug USB cable)... ")
            sys.stdout.flush()
            time.sleep(1)
            continue

        print(f"\n{COLOR_GREEN}[+] CONNECTED via {dev_name}!{COLOR_RESET}")
        print(f"[*] Keep controller resting on desk. Press buttons gently.\n")

        try:
            while True:
                raw_data = None
                if backend == "raw_hidraw":
                    r, _, _ = select.select([dev], [], [], 0.5)
                    if r:
                        raw_data = os.read(dev, 64)
                elif backend == "hidapi":
                    d = dev.read(64, timeout_ms=500)
                    if d:
                        raw_data = bytes(d)

                if not raw_data:
                    continue

                packet_count += 1
                if prev_packet is None or raw_data != prev_packet:
                    analyze_packet(raw_data, prev_packet, packet_count)

                    entry = {
                        "timestamp": datetime.now().isoformat(),
                        "packet_idx": packet_count,
                        "hex": raw_data.hex(),
                        "bytes": list(raw_data),
                    }
                    log_file.write(json.dumps(entry) + "\n")
                    log_file.flush()

                    prev_packet = raw_data

        except (OSError, IOError) as e:
            print(f"\n{COLOR_RED}[!] Read error: {e}. Reconnecting...{COLOR_RESET}")
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Exiting.")
            break
        finally:
            try:
                if backend == "raw_hidraw" and dev:
                    os.close(dev)
                elif backend == "hidapi" and dev:
                    dev.close()
            except Exception:
                pass

    log_file.close()

if __name__ == "__main__":
    main()
