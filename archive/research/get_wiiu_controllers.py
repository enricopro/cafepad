#!/usr/bin/env python3
"""
Wii U Safe Controller MAC Extractor
Connects to Wii U over local network via wupserver (Port 1337).
Mounts /dev/slc01 and parses system event logs for Bluetooth connections.
100% safe, read-only, zero kernel memory modification.
"""

import sys
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from wupclient import wupclient

def main():
    target_ip = sys.argv[1] if len(sys.argv) > 1 else '192.168.1.141'
    print(f"[*] Connecting to Wii U at {target_ip}:1337 via wupserver...")
    try:
        w = wupclient(target_ip, 1337)
    except Exception as e:
        print(f"[!] Cannot connect to {target_ip}: {e}")
        return 1

    print("[+] Connected to Wii U!")
    fsa = w.get_fsa_handle()
    w.FSA_Mount(fsa, '/dev/slc01', '/vol/storage_slc01', 2)

    found_devices = {}
    print("[*] Scanning system event logs for connected controllers...")

    # Search the newest 20 system logs
    for num in range(62, 40, -1):
        log_path = f"/vol/storage_slc01/sys/logs/{num}.log"
        try:
            buf = w.dl_buf(log_path, show_progress=False)
            if not buf:
                continue
            text = buf.decode('ascii', errors='replace')
            matches = re.findall(r'WPAD:[^\n]*bd_addr=([0-9a-fA-F:]{17})[^\n]*device=([A-Za-z0-9_-]+)', text)
            for mac, dev_type in matches:
                mac_upper = mac.upper()
                if mac_upper not in found_devices:
                    found_devices[mac_upper] = (dev_type, f"{num}.log")
        except Exception:
            pass

    print("\n==================================================================")
    print("           Wii U Registered Bluetooth Controllers                 ")
    print("==================================================================")
    for mac, (dev_type, log_file) in sorted(found_devices.items()):
        print(f"[+] Controller MAC: {mac} (Device: {dev_type}, Verified in {log_file})")
    print("==================================================================")
    return 0

if __name__ == "__main__":
    sys.exit(main())
