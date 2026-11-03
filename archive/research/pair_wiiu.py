#!/usr/bin/env python3
"""
Direct Bluetooth Auto-Pairing Tool for Wii U Pro Controller & Clones
Leverages BlueZ's native plugins/wiimote.c driver.
"""

import sys
import time
import re
import subprocess

def main():
    print("=" * 65)
    print("  Wii U Pro Controller Bluetooth Direct Pairing Tool")
    print("=" * 65)
    print("[*] Initializing Bluetooth...")

    # Start interactive bluetoothctl process
    p = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # Initial commands
    p.stdin.write("power on\n")
    p.stdin.write("agent on\n")
    p.stdin.write("default-agent\n")
    p.stdin.write("pairable on\n")
    p.stdin.write("scan on\n")
    p.stdin.flush()

    print("\n" + "=" * 65)
    print(">>> 1. KEEP USB CABLE UNPLUGGED FROM CONTROLLER.")
    print(">>> 2. PRESS AND HOLD THE RED 'SYNC' BUTTON ON THE BACK (2 SEC).")
    print(">>> 3. WATCH THE 4 BLUE LEDS FLASH.")
    print("=" * 65 + "\n")

    start_time = time.time()
    seen = set()
    paired_mac = None

    while time.time() - start_time < 60:
        line = p.stdout.readline()
        if not line:
            break

        line_str = line.strip()

        # Print all device discoveries
        if any(keyword in line_str for keyword in ["[NEW]", "[CHG]", "Device"]):
            # Filter out noisy RSSI spam
            if "RSSI" not in line_str and "TxPower" not in line_str:
                print(f"  {line_str}")

        # Check for target device
        # Examples:
        # [NEW] Device 00:1F:32:84:1A:10 Nintendo RVL-CNT-01-UC
        # [NEW] Device XX:XX:XX:XX:XX:XX Pro Controller
        m = re.search(r"Device\s+([0-9A-Fa-f:]{17})\s*(.*)", line_str)
        if m:
            mac = m.group(1).upper()
            name = m.group(2).strip()

            target_keywords = ["nintendo", "rvl", "wii", "pro controller", "controller", "gamepad"]
            if any(k in name.lower() for k in target_keywords):
                print(f"\n\n{'*'*50}")
                print(f"[+] FOUND WII U PRO CONTROLLER: {mac} ({name})")
                print(f"[*] Pairing, trusting, and connecting...")
                print(f"{'*'*50}\n")

                p.stdin.write(f"trust {mac}\n")
                p.stdin.write(f"pair {mac}\n")
                p.stdin.write(f"connect {mac}\n")
                p.stdin.flush()
                paired_mac = mac
                break

    if paired_mac:
        print(f"\n[*] Waiting 5s for driver binding and Player 1 LED to stabilize...")
        time.sleep(5)
        p.stdin.write(f"info {paired_mac}\n")
        p.stdin.write("scan off\nexit\n")
        p.stdin.flush()
        
        # Check /dev/input
        print("\n" + "=" * 65)
        print("[+] VERIFYING INPUT DEVICES:")
        subprocess.run(["ls", "-la", "/dev/input"], check=False)
        print("=" * 65)
    else:
        p.stdin.write("scan off\nexit\n")
        p.stdin.flush()
        print("\n[-] Scan timed out after 60s.")

if __name__ == "__main__":
    main()
