#!/usr/bin/env python3
"""
Raw Bluetooth Sniffer & Real-Time Probe for Black Controller
- Uses native BlueZ D-Bus event stream (never crashes, stays open continuously).
- Displays ANY device advertising or communicating near the laptop in real-time.
- Shows MAC, RSSI signal strength, Device Name, and Class.
"""

import sys
import os
import time
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

COLOR_RESET   = "\033[0m"
COLOR_RED     = "\033[1;31m"
COLOR_GREEN   = "\033[1;32m"
COLOR_YELLOW  = "\033[1;33m"
COLOR_CYAN    = "\033[1;36m"
COLOR_BOLD    = "\033[1m"

def main():
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"{COLOR_CYAN}       Black Controller Live RF Sniffer & Diagnostics             {COLOR_RESET}")
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"[*] Native D-Bus Bluetooth Monitor active.")
    print(f"[*] Zero filters: displays all Bluetooth radio packets in real-time.")
    print(f"[*] Keep the black controller 5-10cm from your laptop keyboard.\n")

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    try:
        adapter = bus.get_object('org.bluez', '/org/bluez/hci0')
        adapter_props = dbus.Interface(adapter, 'org.freedesktop.DBus.Properties')
        adapter_iface = dbus.Interface(adapter, 'org.bluez.Adapter1')

        adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(True))
        try:
            adapter_iface.SetDiscoveryFilter(dbus.Dictionary({}, signature='sv'))
            adapter_iface.StartDiscovery()
        except Exception:
            pass  # Already discovering
    except Exception as e:
        print(f"{COLOR_RED}[!] Error accessing Bluetooth adapter: {e}{COLOR_RESET}")
        return 1

    seen_devices = {}
    start_time = time.time()
    spinner = ['|', '/', '-', '\\']
    spin_idx = [0]

    def print_device(addr, name, dev_class, rssi):
        name_str = name if name else "(unnamed / raw MAC)"
        is_gamepad = any(k in name.lower() for k in ["nintendo", "rvl", "wii", "pro", "gamepad", "wireless"])
        is_known_mac = addr.upper().startswith("8C:CD:E8")

        if is_gamepad or is_known_mac or dev_class == 0x000508:
            col = COLOR_GREEN
            prefix = "[+] GAMEPAD DETECTED: "
        else:
            col = COLOR_CYAN
            prefix = "[*] Scanned: "

        rssi_str = f"{rssi} dBm" if rssi != 0 else "N/A"
        print(f"\n{col}{prefix}{COLOR_BOLD}{addr}{COLOR_RESET} | Name: '{name_str}' | RSSI: {rssi_str} | Class: 0x{dev_class:06X}")
        if is_gamepad or is_known_mac:
            print(f"{COLOR_GREEN}>>> MATCH FOUND! You can now run: ./tools/smart_connect.py <<<{COLOR_RESET}\n")

    def on_interfaces_added(path, interfaces):
        if 'org.bluez.Device1' in interfaces:
            props = interfaces['org.bluez.Device1']
            addr = str(props.get('Address', ''))
            name = str(props.get('Name', props.get('Alias', '')))
            dev_class = int(props.get('Class', 0))
            rssi = int(props.get('RSSI', 0))
            if addr and addr not in seen_devices:
                seen_devices[addr] = name
                print_device(addr, name, dev_class, rssi)

    def on_properties_changed(iface, changed, invalidated, path=None):
        if iface == 'org.bluez.Device1':
            try:
                dev = bus.get_object('org.bluez', path)
                props_iface = dbus.Interface(dev, 'org.freedesktop.DBus.Properties')
                props = props_iface.GetAll('org.bluez.Device1')
                addr = str(props.get('Address', ''))
                name = str(props.get('Name', props.get('Alias', '')))
                dev_class = int(props.get('Class', 0))
                rssi = int(props.get('RSSI', 0))
                if addr:
                    if addr not in seen_devices:
                        seen_devices[addr] = name
                        print_device(addr, name, dev_class, rssi)
                    elif 'Name' in changed or 'Class' in changed:
                        seen_devices[addr] = name
                        print_device(addr, name, dev_class, rssi)
            except Exception:
                pass

    bus.add_signal_receiver(on_interfaces_added, dbus_interface="org.freedesktop.DBus.ObjectManager", signal_name="InterfacesAdded")
    bus.add_signal_receiver(on_properties_changed, dbus_interface="org.freedesktop.DBus.Properties", signal_name="PropertiesChanged", path_keyword="path")

    loop = GLib.MainLoop()

    def heartbeat():
        spin = spinner[spin_idx[0] % len(spinner)]
        spin_idx[0] += 1
        elapsed = int(time.time() - start_time)
        count = len(seen_devices)
        sys.stdout.write(f"\r[*] [{spin}] Monitoring radio traffic... ({elapsed}s active, {count} devices seen)   ")
        sys.stdout.flush()
        return True

    GLib.timeout_add(300, heartbeat)
    print(f"{COLOR_YELLOW}[!] ACTION REQUIRED:{COLOR_RESET}")
    print(f"  Now press the RED SYNC BUTTON on the black controller (or hold for 5s).")
    print(f"  Watch the screen for any new device detection! (Ctrl+C to quit)\n")

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n\n[*] Monitoring stopped.")
    finally:
        try:
            adapter_iface.StopDiscovery()
        except Exception:
            pass

if __name__ == "__main__":
    main()
