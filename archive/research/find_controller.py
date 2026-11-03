#!/usr/bin/env python3
"""
Continuous Bluetooth Classic (BR/EDR) scanner and auto-connector for Wii U Pro Controller.
"""

import subprocess
import time
import sys
import re

def main():
    print("=" * 60)
    print("  Continuous Bluetooth Classic (BR/EDR) Auto-Connector")
    print("=" * 60)
    print("[*] Listening for Bluetooth Classic Inquiry Responses...")
    print("[*] Looking for Wii U Pro Controller / Nintendo RVL-CNT-01-UC\n")
    print(">>> CRITICAL: Press the RED 'SYNC' button on the BACK of the controller! <<<")
    print("    (Do not just press front buttons; the red SYNC button is required)\n")

    start = time.time()
    seen = set()

    while time.time() - start < 45:
        sys.stdout.write(".")
        sys.stdout.flush()

        try:
            # hcitool scan specifically performs BR/EDR inquiry
            res = subprocess.run(["hcitool", "scan", "--flush"], capture_output=True, text=True, timeout=10)
            for line in res.stdout.splitlines():
                m = re.search(r"([0-9A-Fa-f:]{17})\s*(.*)", line)
                if m:
                    mac = m.group(1).upper()
                    name = m.group(2).strip()

                    if mac in seen:
                        continue
                    seen.add(mac)

                    print(f"\n[?] Discovered device: {mac} | Name: '{name}'")

                    # Check if it's the controller or newly appeared
                    is_candidate = any(w in name.lower() for w in ["nintendo", "rvl", "wii", "pro", "controller", "gamepad"]) or not name
                    
                    if is_candidate:
                        print(f"\n[+] MATCH FOUND: {mac} ({name or 'Unknown Name'})")
                        print(f"[*] Attempting to pair, trust, and connect...")
                        
                        subprocess.run(["bluetoothctl", "trust", mac], check=False)
                        subprocess.run(["bluetoothctl", "pair", mac], check=False)
                        time.sleep(1)
                        subprocess.run(["bluetoothctl", "connect", mac], check=False)
                        
                        time.sleep(3)
                        info = subprocess.run(["bluetoothctl", "info", mac], capture_output=True, text=True)
                        if "Connected: yes" in info.stdout:
                            print(f"\n[SUCCESS] Successfully connected to {mac}!")
                            print("[*] Checking /dev/input:")
                            subprocess.run(["ls", "-la", "/dev/input"], check=False)
                            return
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            print(f"\n[!] Error during scan: {e}")

    print("\n[-] Scan timed out. Please verify the red SYNC button on the back was pressed.")

if __name__ == "__main__":
    main()
