#!/usr/bin/env python3
"""
Wii U Pro Controller Bluetooth Auto-Pair & Connection Tool
Uses Limited Inquiry Access Code (LIAC / 0x9E8B00) to discover and automatically
pair/connect Nintendo Wii U Pro Controllers directly to native Linux Bluetooth
without requiring any Mayflash or 8BitDo adapters.
"""

import sys
import os
import re
import time
import subprocess
import glob

COLOR_RESET   = "\033[0m"
COLOR_RED     = "\033[1;31m"
COLOR_GREEN   = "\033[1;32m"
COLOR_YELLOW  = "\033[1;33m"
COLOR_CYAN    = "\033[1;36m"
COLOR_BOLD    = "\033[1m"

def run_cmd(cmd, check=False):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check)
        return res.stdout.strip()
    except Exception as e:
        return ""

def ensure_bluetooth_ready():
    print(f"[*] Ensuring Bluetooth adapter is powered on...")
    run_cmd(["rfkill", "unblock", "bluetooth"])
    run_cmd(["bluetoothctl", "power", "on"])
    run_cmd(["bluetoothctl", "pairable", "on"])
    run_cmd(["bluetoothctl", "discoverable", "on"])
    time.sleep(1)

def scan_liac(duration=10):
    """Scan for devices responding to LIAC (Limited Inquiry Access Code / 0x9E8B00)."""
    # hcitool inq --iac=liac --flush
    cmd = ["hcitool", "inq", "--iac=liac", f"--length={duration}", "--flush"]
    out = run_cmd(cmd)
    found = []
    # Output format:
    # Inquiring ...
    #   00:1E:35:XX:XX:XX  clock offset: 0x...  class: 0x...
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", line)
        if m:
            found.append(m.group(1))
    return found

def get_device_name(mac):
    # Try bluetoothctl info
    info = run_cmd(["bluetoothctl", "info", mac])
    for line in info.splitlines():
        if "Name:" in line or "Alias:" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                name = parts[1].strip()
                if name:
                    return name
    return "Unknown"

def pair_and_connect(mac):
    print(f"\n{COLOR_GREEN}[+] Found candidate controller: {COLOR_BOLD}{mac}{COLOR_RESET}")
    print(f"[*] Trusting device {mac}...")
    run_cmd(["bluetoothctl", "trust", mac])
    
    print(f"[*] Attempting connection to {mac}...")
    out = run_cmd(["bluetoothctl", "connect", mac])
    if "Connection successful" in out or "connected: yes" in out.lower():
        print(f"{COLOR_GREEN}[+] Successfully connected to {mac}!{COLOR_RESET}")
        return True

    # Try pair then connect
    print(f"[*] Pairing with {mac}...")
    run_cmd(["bluetoothctl", "pair", mac])
    time.sleep(1)
    out = run_cmd(["bluetoothctl", "connect", mac])
    if "Connection successful" in out or "connected: yes" in out.lower():
        print(f"{COLOR_GREEN}[+] Successfully connected to {mac}!{COLOR_RESET}")
        return True

    return False

def find_joystick_node():
    for node in sorted(glob.glob("/dev/input/js*")):
        try:
            with open(node, "rb") as f:
                import fcntl
                # JSIOCGNAME(len) = 0x80806a13 (for 128 bytes)
                buf = bytearray(128)
                fcntl.ioctl(f.fileno(), 0x80806a13, buf)
                name = buf.split(b"\x00")[0].decode("utf-8", errors="replace")
                return node, name
        except Exception:
            return node, "Joystick"
    return None, None

def main():
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"{COLOR_CYAN}    Wii U Pro Controller Native Bluetooth Connector (Direct)      {COLOR_RESET}")
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"[*] Zero adapters required (No Mayflash, No 8BitDo).")
    print(f"[*] Uses native Linux kernel hid-wiimote driver.\n")

    ensure_bluetooth_ready()

    # Check if already connected
    js_node, js_name = find_joystick_node()
    if js_node and any(w in js_name.lower() for w in ["nintendo", "wii", "pro controller", "rvl"]):
        print(f"{COLOR_GREEN}[+] Controller already connected! Node: {js_node} ({js_name}){COLOR_RESET}")
        print(f"[*] Launching test_controller...")
        subprocess.run(["/home/enrico/Documents/workspace/wiiupro-usb/test_controller"])
        return

    print(f"\n{COLOR_YELLOW}[!] ACTION REQUIRED:{COLOR_RESET}")
    print(f"  1. Press the {COLOR_BOLD}RED SYNC BUTTON{COLOR_RESET} on the back of the controller.")
    print(f"     (The 4 blue LEDs at the bottom will start blinking back and forth)")
    print(f"  2. Keep pressing it or press any face button (A/B/X/Y) so LEDs keep blinking.")
    print(f"\n[*] Listening on Bluetooth LIAC (Limited Inquiry Access Code / 0x9E8B00)...")

    attempts = 0
    while attempts < 10:
        attempts += 1
        sys.stdout.write(f"\r[*] Scanning pass {attempts}/10... ")
        sys.stdout.flush()

        devices = scan_liac(duration=5)
        if devices:
            print(f"\n{COLOR_GREEN}[+] Detected LIAC Bluetooth device(s): {devices}{COLOR_RESET}")
            for mac in devices:
                if pair_and_connect(mac):
                    print(f"\n{COLOR_GREEN}[+] Controller is now paired and active!{COLOR_RESET}")
                    time.sleep(2)
                    js_node, js_name = find_joystick_node()
                    if js_node:
                        print(f"{COLOR_GREEN}[+] Joystick registered at: {js_node} ({js_name}){COLOR_RESET}")
                        print(f"[*] Starting controller test...\n")
                        subprocess.run(["/home/enrico/Documents/workspace/wiiupro-usb/test_controller"])
                    return
        time.sleep(0.5)

    print(f"\n{COLOR_YELLOW}[i] No controller detected in 10 scan passes.{COLOR_RESET}")
    print(f"    Make sure the controller LEDs are blinking when scanning starts.")

if __name__ == "__main__":
    main()
