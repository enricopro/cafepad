#!/usr/bin/env python3
"""
Automated Bluetooth Pairing Tool for Wii U Pro Controller (Official & Clones)
"""

import sys
import time
import re
import subprocess
import pexpect

NINTENDO_OUIS = [
    "00:1e:35", "00:1f:32", "00:21:47", "00:22:d7", "00:23:cc", 
    "00:24:1e", "00:24:44", "00:25:a0", "00:26:59", "18:2a:7b",
    "28:a1:83", "34:2f:bd", "7c:bb:8a", "8c:56:c5", "98:b6:e9",
    "a4:5c:27", "b8:78:26", "c8:fe:0f", "cc:9e:00", "d8:6b:f7"
]

def main():
    print("="*65)
    print("  Auto-Pairing Tool for Wii U Pro Controller (Bluetooth) ")
    print("="*65)
    print("[*] Starting Bluetooth discovery agent...")

    child = pexpect.spawn("bluetoothctl", encoding="utf-8", timeout=60)
    child.logfile_read = sys.stdout

    child.sendline("power on")
    child.sendline("agent on")
    child.sendline("default-agent")
    child.sendline("pairable on")
    child.sendline("scan on")

    print("\n" + "="*65)
    print(">>> PLEASE PRESS THE RED 'SYNC' BUTTON OR MAKE IT BLINK NOW! <<<")
    print("="*65 + "\n")

    start_time = time.time()
    seen_devices = set()
    paired_device = None

    while time.time() - start_time < 45:
        try:
            line = child.readline()
            if not line:
                continue

            mac_match = re.search(r"Device\s+([0-9A-Fa-f:]{17})\s*(.*)", line)
            if mac_match:
                mac = mac_match.group(1).upper()
                name = mac_match.group(2).strip()

                is_target = False
                name_lower = name.lower()

                # Keywords
                if any(w in name_lower for w in ["nintendo", "rvl", "wii", "pro controller", "gamepad", "joystick"]):
                    is_target = True

                # Known Nintendo OUI prefixes
                if any(mac.lower().startswith(oui) for oui in NINTENDO_OUIS):
                    is_target = True

                if is_target and mac not in seen_devices:
                    print(f"\n\n[+] TARGET CONTROLLER FOUND: {mac} ({name})")
                    print(f"[*] Sending trust, pair, and connect...")
                    child.sendline(f"trust {mac}")
                    time.sleep(0.5)
                    child.sendline(f"pair {mac}")
                    time.sleep(1)
                    child.sendline(f"connect {mac}")
                    paired_device = mac
                    break

        except pexpect.TIMEOUT:
            pass

    if paired_device:
        print(f"\n[*] Waiting 4s for driver attachment on {paired_device}...")
        time.sleep(4)
        child.sendline(f"info {paired_device}")
        time.sleep(1)
        child.sendline("scan off")
        child.sendline("quit")
        print("\n[+] Done! Verifying /dev/input devices...")
        subprocess.run(["ls", "-la", "/dev/input"], check=False)
    else:
        child.sendline("scan off")
        child.sendline("quit")
        print("\n[-] Scan finished. If the controller didn't show up, try pressing the red SYNC button on the back.")

if __name__ == "__main__":
    main()
