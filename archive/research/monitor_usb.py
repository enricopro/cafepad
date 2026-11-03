#!/usr/bin/env python3
"""
Wii U Pro Controller (USB 0471:0666) Native Live Monitor
- Uses direct Linux /dev/hidraw syscalls (no libusb detaches).
- Auto-detects device plug/unplug.
- Decodes sticks and buttons based on GBAtemp Nintendont specification.
"""

import os
import sys
import glob
import time
import fcntl
import select

COLOR_RESET   = "\033[0m"
COLOR_GREEN   = "\033[1;32m"
COLOR_YELLOW  = "\033[1;33m"
COLOR_CYAN    = "\033[1;36m"
COLOR_BOLD    = "\033[1m"

TARGET_VID = 0x0471
TARGET_PID = 0x0666

# ioctl HIDIOCGRAWINFO
HIDIOCGRAWINFO = 0x80084803

def find_hidraw():
    for path in sorted(glob.glob("/dev/hidraw*")):
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            buf = bytearray(8)
            fcntl.ioctl(fd, HIDIOCGRAWINFO, buf)
            os.close(fd)
            # buf contains: bustype (4 bytes), vendor (2 bytes), product (2 bytes)
            bustype = int.from_bytes(buf[0:4], byteorder='little')
            vendor = int.from_bytes(buf[4:6], byteorder='little')
            product = int.from_bytes(buf[6:8], byteorder='little')
            if vendor == TARGET_VID and product == TARGET_PID:
                return path
        except Exception:
            pass
    return None

def decode_report(data):
    if len(data) < 7:
        return None

    # 8-bit analog sticks (0 to 255, center ~128)
    # Byte 0: Left X, Byte 1: Left Y
    # Byte 3: Right X, Byte 4: Right Y
    lx = round((data[0] - 128) / 128.0, 2)
    ly = round(-(data[1] - 128) / 128.0, 2)
    rx = round((data[3] - 128) / 128.0, 2)
    ry = round(-(data[4] - 128) / 128.0, 2)

    b5 = data[5]
    b6 = data[6]

    buttons = []
    if b5 & 0x40: buttons.append("A")
    if b5 & 0x80: buttons.append("B")
    if b5 & 0x20: buttons.append("X")
    if b5 & 0x10: buttons.append("Y")

    hat = b5 & 0x0F
    hat_names = {
        0: "UP", 1: "UP+RIGHT", 2: "RIGHT", 3: "DOWN+RIGHT",
        4: "DOWN", 5: "DOWN+LEFT", 6: "LEFT", 7: "UP+LEFT"
    }
    if hat in hat_names:
        buttons.append(hat_names[hat])

    if b6 & 0x01: buttons.append("L")
    if b6 & 0x02: buttons.append("R")
    if b6 & 0x04: buttons.append("ZR")
    if b6 & 0x08: buttons.append("ZL")
    if b6 & 0x10: buttons.append("HOME")
    if b6 & 0x20: buttons.append("+")
    if b6 & 0x40: buttons.append("-")

    return {
        "lx": lx, "ly": ly,
        "rx": rx, "ry": ry,
        "buttons": buttons,
        "raw": data[:8].hex()
    }

def main():
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"{COLOR_CYAN}  Wii U Pro Controller (USB 0471:0666) Native Input Monitor       {COLOR_RESET}")
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")

    while True:
        node = find_hidraw()
        if not node:
            sys.stdout.write("\r[*] Waiting for controller at /dev/hidraw* (unplug and replug USB cable)...   ")
            sys.stdout.flush()
            time.sleep(1)
            continue

        print(f"\n{COLOR_GREEN}[+] Found controller at {node}! Opening...{COLOR_RESET}")
        try:
            fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
        except Exception as e:
            print(f"[!] Cannot open {node}: {e}")
            time.sleep(1)
            continue

        print(f"{COLOR_GREEN}[+] CONNECTED! Press buttons or move sticks (Ctrl+C to stop)...{COLOR_RESET}\n")

        try:
            while True:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    data = os.read(fd, 64)
                    if data:
                        state = decode_report(data)
                        if state:
                            btn_str = " ".join(state["buttons"]) if state["buttons"] else "None"
                            sys.stdout.write(
                                f"\rL-Stick: [{state['lx']:+0.2f}, {state['ly']:+0.2f}]  "
                                f"R-Stick: [{state['rx']:+0.2f}, {state['ry']:+0.2f}]  "
                                f"Btns: {btn_str:<25}  Raw: {state['raw']}   "
                            )
                            sys.stdout.flush()
                else:
                    # Keep polling
                    pass
        except KeyboardInterrupt:
            print("\n[*] Stopped by user.")
            os.close(fd)
            break
        except Exception as e:
            print(f"\n{COLOR_YELLOW}[!] Disconnected or error: {e}{COLOR_RESET}")
            os.close(fd)
            time.sleep(1)

if __name__ == "__main__":
    main()
