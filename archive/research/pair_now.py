#!/usr/bin/env python3
"""
Real-time Bluetooth Pairing Watcher for Wii U Pro Controller / Clone
"""

import sys
import time
import re
import subprocess

TARGET_KEYWORDS = ["nintendo", "rvl", "wii", "pro controller", "gamepad", "joystick", "wireless controller"]

def main():
    print("=" * 65)
    print("  Real-time Bluetooth Pairing Watcher")
    print("=" * 65)

    known_out = subprocess.check_output(["bluetoothctl", "devices"], text=True)
    known = set(re.findall(r"([0-9A-Fa-f:]{17})", known_out))
    print(f"[*] Already paired: {list(known)}")

    p = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    p.stdin.write("power on\nagent on\ndefault-agent\npairable on\nscan on\n")
    p.stdin.flush()

    print("\n[*] SCANNING ACTIVATED. PRESS SYNC ON THE CONTROLLER NOW!\n")

    start = time.time()
    seen = set(known)
    paired = None

    while time.time() - start < 35:
        line = p.stdout.readline()
        if not line:
            break

        # Match: [NEW] Device XX:XX:XX:XX:XX:XX Name...
        m = re.search(r"\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)", line)
        if m:
            mac = m.group(1).upper()
            name = m.group(2).strip()

            if mac not in seen:
                seen.add(mac)
                print(f"[+] New device detected: {mac} | '{name}'")

                # Match candidate
                if any(k in name.lower() for k in TARGET_KEYWORDS):
                    print(f"\n[***] TARGET FOUND: {mac} ({name}) [***]")
                    print(f"[*] Trusting, pairing, connecting to {mac}...")
                    p.stdin.write(f"trust {mac}\npair {mac}\nconnect {mac}\n")
                    p.stdin.flush()
                    paired = mac
                    break

        # Also match: [CHG] Device XX:XX:XX:XX:XX:XX Name: ...
        m_chg = re.search(r"Device\s+([0-9A-Fa-f:]{17})\s+Name:\s+(.*)", line)
        if m_chg:
            mac = m_chg.group(1).upper()
            name = m_chg.group(2).strip()
            print(f"[i] Device name updated: {mac} -> '{name}'")
            if any(k in name.lower() for k in TARGET_KEYWORDS):
                print(f"\n[***] TARGET FOUND: {mac} ({name}) [***]")
                p.stdin.write(f"trust {mac}\npair {mac}\nconnect {mac}\n")
                p.stdin.flush()
                paired = mac
                break

    if paired:
        print(f"\n[*] Waiting for connection confirmation...")
        time.sleep(4)
        p.stdin.write(f"info {paired}\nscan off\nexit\n")
        p.stdin.flush()
        print("\nChecking /dev/input:")
        subprocess.run(["ls", "-la", "/dev/input"], check=False)
    else:
        p.stdin.write("scan off\nexit\n")
        p.stdin.flush()
        print("\n[-] Scan timed out. See all devices detected above.")

if __name__ == "__main__":
    main()
