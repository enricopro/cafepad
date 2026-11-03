#!/usr/bin/env python3
"""
Dedicated Bluetooth Pairing & Pairing Assistant for Clone Gamepads
Tracks ALL newly discovered Bluetooth devices (Classic + BLE) and auto-pairs.
"""

import sys
import time
import re
import subprocess
import pexpect

HID_UUID = "00001124"

def main():
    print("=" * 65)
    print("  Clone Gamepad Bluetooth Discovery & Auto-Pairing Tool")
    print("=" * 65)

    # Initial known devices
    known_out = subprocess.check_output(["bluetoothctl", "devices"], text=True)
    known_macs = set(re.findall(r"Device\s+([0-9A-Fa-f:]{17})", known_out))
    print(f"[*] Ignoring existing paired devices: {known_macs}\n")

    child = pexpect.spawn("bluetoothctl", encoding="utf-8", timeout=60)
    
    # Configure agent
    child.sendline("power on")
    child.sendline("agent on")
    child.sendline("default-agent")
    child.sendline("pairable on")
    child.sendline("discoverable on")
    
    # Clear discovery filter to catch BOTH Classic and LE
    child.sendline("menu scan")
    child.sendline("clear")
    child.sendline("back")
    child.sendline("scan on")

    print("\n" + "=" * 65)
    print(">>> 1. UNPLUG the USB cable from the controller.")
    print(">>> 2. PRESS AND HOLD the SYNC button (or Home) until LEDs flash.")
    print("=" * 65 + "\n")

    start_time = time.time()
    seen_macs = set(known_macs)
    target_mac = None

    print("[*] Scanning... Waiting for controller to broadcast...")

    while time.time() - start_time < 45:
        try:
            line = child.readline()
            if not line:
                continue

            # Check for [NEW] Device XX:XX:XX:XX:XX:XX Name
            m = re.search(r"\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s*(.*)", line)
            if m:
                mac = m.group(1).upper()
                name = m.group(2).strip()

                if mac not in seen_macs:
                    seen_macs.add(mac)
                    print(f"\n[!] Detected new device: {mac} | Name: '{name}'")

                    # Check device info in background
                    try:
                        info_out = subprocess.check_output(["bluetoothctl", "info", mac], text=True, stderr=subprocess.DEVNULL)
                    except Exception:
                        info_out = ""

                    is_controller = False

                    # Check for gamepad clues
                    name_lower = name.lower()
                    if any(k in name_lower for k in ["pro", "controller", "gamepad", "joystick", "wii", "nintendo", "rvl", "wireless"]):
                        is_controller = True
                        print(f"    -> Matched controller name: '{name}'!")

                    if "Icon: input-gaming" in info_out or "Class: 0x002508" in info_out or "Class: 0x000508" in info_out:
                        is_controller = True
                        print(f"    -> Matched Gaming Device Class/Icon!")

                    if HID_UUID in info_out or "00001124-0000-1000-8000-00805f9b34fb" in info_out:
                        is_controller = True
                        print(f"    -> Matched HID Gamepad Service!")

                    if is_controller:
                        print(f"\n[+] TARGET GAMEPAD IDENTIFIED: {mac} ({name})")
                        target_mac = mac
                        break
        except pexpect.TIMEOUT:
            pass

    if target_mac:
        print(f"\n[*] Initiating pairing with {target_mac}...")
        child.sendline(f"trust {target_mac}")
        time.sleep(0.5)
        child.sendline(f"pair {target_mac}")
        time.sleep(1.5)
        child.sendline(f"connect {target_mac}")
        
        # Monitor for PIN prompt or success
        for _ in range(10):
            try:
                out_line = child.readline()
                if "PIN" in out_line or "passkey" in out_line:
                    print("[!] PIN Prompt detected! Sending empty/0000...")
                    child.sendline("")
                    child.sendline("0000")
                if "Connection successful" in out_line:
                    print(f"[SUCCESS] Connected to {target_mac}!")
                    break
            except pexpect.TIMEOUT:
                pass

        time.sleep(3)
        child.sendline(f"info {target_mac}")
        child.sendline("scan off")
        child.sendline("quit")

        print("\n[+] Verification: Checking /dev/input for gamepad...")
        subprocess.run(["ls", "-la", "/dev/input"], check=False)
    else:
        child.sendline("scan off")
        child.sendline("quit")
        print("\n[-] Scan completed. If the controller did not appear, verify if the battery is charged and flashing.")

if __name__ == "__main__":
    main()
