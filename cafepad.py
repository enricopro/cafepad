#!/usr/bin/env python3
"""
======================================================================
  Wii U Pro Controller — Universal Linux Driver & Gamepad Bridge
  Zero-Dongle Native Bluetooth Engine for Genuine & Replica Controllers
======================================================================
"""

import sys
import os
import time
import socket
import struct
import select
import threading
import json
import fcntl
import queue
import ctypes
import argparse
import subprocess
import re

__version__ = "1.0.0"

COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

CONFIG_DIR = os.path.expanduser("~/.config")
LEGACY_CONFIG_PATH = os.path.join(CONFIG_DIR, "wiiupro.json")
CONFIG_PATH = os.path.join(CONFIG_DIR, "cafepad.json")

PSM_HID_CNTL = 0x0011
PSM_HID_INTR = 0x0013

# Linux Input Event Constants
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03
EV_FF = 0x15

SYN_REPORT = 0x00

ABS_X = 0x00
ABS_Y = 0x01
ABS_Z = 0x02       # Left Trigger (ZL)
ABS_RX = 0x03      # Right Stick X
ABS_RY = 0x04      # Right Stick Y
ABS_RZ = 0x05      # Right Trigger (ZR)
ABS_HAT0X = 0x10   # D-Pad X
ABS_HAT0Y = 0x11   # D-Pad Y

# Linux kernel button event codes
BTN_SOUTH = 0x130   # Bottom button (Xbox A, B0)
BTN_EAST  = 0x131   # Right button  (Xbox B, B1)
BTN_NORTH = 0x133   # Left button   (Xbox X, B2, in Linux BTN_NORTH is BTN_X)
BTN_WEST  = 0x134   # Top button    (Xbox Y, B3, in Linux BTN_WEST is BTN_Y)
BTN_TL = 0x136      # L
BTN_TR = 0x137      # R
BTN_SELECT = 0x13a  # -
BTN_START = 0x13b   # +
BTN_MODE = 0x13c    # HOME
BTN_THUMBL = 0x13d  # L3
BTN_THUMBR = 0x13e  # R3

# Force Feedback (FF) Constants
FF_RUMBLE = 0x50

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567
UI_SET_FFBIT = 0x4004556b
UI_DEV_SETUP = 0x405c5503
UI_ABS_SETUP = 0x401c5504
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

UI_BEGIN_FF_UPLOAD = 0xC06855C8
UI_END_FF_UPLOAD   = 0x406855C9
UI_BEGIN_FF_ERASE  = 0xC00C55CA
UI_END_FF_ERASE    = 0x400C55CB

EV_UINPUT = 0x0101
UI_FF_UPLOAD = 1
UI_FF_ERASE = 2

class ff_replay(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint16), ('delay', ctypes.c_uint16)]

class ff_trigger(ctypes.Structure):
    _fields_ = [('button', ctypes.c_uint16), ('interval', ctypes.c_uint16)]

class ff_effect(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.c_uint16),
        ('id', ctypes.c_int16),
        ('direction', ctypes.c_uint16),
        ('trigger', ff_trigger),
        ('replay', ff_replay),
        ('u', ctypes.c_uint8 * 32)
    ]

class uinput_ff_upload(ctypes.Structure):
    _fields_ = [
        ('request_id', ctypes.c_uint32),
        ('retval', ctypes.c_int32),
        ('effect', ff_effect),
        ('old', ff_effect)
    ]

class uinput_ff_erase(ctypes.Structure):
    _fields_ = [
        ('request_id', ctypes.c_uint32),
        ('retval', ctypes.c_int32),
        ('effect_id', ctypes.c_uint32)
    ]

# ====================================================================
# Config Storage Helpers (Multi-Controller Support)
# ====================================================================
def load_config():
    try:
        path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else LEGACY_CONFIG_PATH
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config_key(key, value):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = load_config()
        cfg[key] = value
        cfg["updated_at"] = time.time()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def load_saved_macs():
    try:
        data = load_config()
        if "controllers" in data and isinstance(data["controllers"], list):
            return [m.strip().upper() for m in data["controllers"] if m]
        if "target_mac" in data and data["target_mac"]:
            return [data["target_mac"].strip().upper()]
    except Exception:
        pass
    return []

def save_mac(mac):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = load_config()
        macs = load_saved_macs()
        mac = mac.strip().upper()
        if mac not in macs:
            macs.append(mac)
        cfg["controllers"] = macs
        cfg["updated_at"] = time.time()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def remove_mac(mac):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = load_config()
        macs = load_saved_macs()
        mac = mac.strip().upper()
        if mac in macs:
            macs.remove(mac)
        cfg["controllers"] = macs
        cfg["updated_at"] = time.time()
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
# ====================================================================
# Bluetooth Auto-Discovery Scanner
# ====================================================================
# Official Nintendo IEEE Organizationally Unique Identifiers (OUIs)
KNOWN_NINTENDO_OUIS = [
    "00:09:BF", "00:16:56", "00:17:AB", "00:19:1D", "00:1B:7A", "00:1C:BE",
    "00:1D:BC", "00:1E:35", "00:1F:32", "00:21:47", "00:21:BD", "00:22:4C",
    "00:22:AA", "00:22:D7", "00:23:31", "00:23:CC", "00:24:1E", "00:24:44",
    "00:25:A0", "00:26:59", "00:27:09", "18:2A:7B", "2C:10:C1", "34:AF:2C",
    "40:D2:8A", "58:2F:40", "78:A2:A0", "7C:BB:8A", "8C:56:C5", "8C:CD:E8",
    "94:58:CB", "98:B6:E9", "A4:5C:27", "A4:C0:E1", "B8:86:87", "CC:9E:00",
    "D8:6B:F7", "E0:0C:7F", "E0:E7:51"
]

def is_wii_u_candidate(props):
    name = str(props.get("Name", "") or props.get("Alias", "")).strip()
    dev_class = int(props.get("Class", 0))
    icon = str(props.get("Icon", ""))
    addr = str(props.get("Address", "")).upper()
    nl = name.lower()

    # 1. Reject non-gamepads by Major Device Class
    # (Computer=1, Phone=2, LAN=3, Audio/Video=4, Imaging=6, Wearable=7)
    major_class = (dev_class >> 8) & 0x1F
    if major_class in (0x01, 0x02, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09):
        return False, ""

    # 2. Reject non-Wii-U gaming devices (Switch, Joy-Con, PlayStation, Xbox, Quest, etc.)
    conflicting_controllers = [
        "switch", "joy-con", "xbox", "dualshock", "dualsense",
        "playstation", "stadia", "luna", "oculus", "quest"
    ]
    if any(c in nl for c in conflicting_controllers):
        return False, ""

    # Reject non-gamepad consumer devices
    for non_gamepad in ["tv", "printer", "laserjet", "mouse", "keyboard", "headphone", "headset", "earbuds", "speaker", "soundbar"]:
        if non_gamepad in nl and not any(k in nl for k in ["controller", "gamepad", "rvl"]):
            return False, ""

    # 3. Model Signature: RVL-CNT Family (Genuine controllers and clones)
    # The physical Wii U console CafeOS kernel requires this model string to pair
    if "rvl-cnt" in nl:
        if "uc" in nl or dev_class in (0x002504, 0x000504):
            return True, f"Wii U Pro Model Match: '{name}'"
        return True, f"RVL Family Controller: '{name}'"

    # 4. Explicit Wii / Wii U Branding (aftermarket controllers like Nyko, Afterglow, PDP)
    if "wii u" in nl or "wiiu" in nl or "wii-u" in nl:
        return True, f"Wii U Identifier: '{name}'"

    if "wii" in nl and (major_class in (0x00, 0x05) or any(k in nl for k in ["controller", "gamepad"])):
        return True, f"Wii Controller Identifier: '{name}'"

    # 5. Hardware Class Signature: Nintendo Limited Discoverable Mode (0x002504)
    # Bit 13 (0x2000) = Limited Discoverable Mode (SYNC button active)
    # Bit 8-12 (0x0500) = Peripheral
    # Bit 2 (0x04) = Joystick
    # This catches ANY clone even if its name is blank, omitted, or delayed during inquiry!
    if dev_class in (0x002504, 0x000504):
        return True, f"Nintendo Hardware Class of Device (0x{dev_class:06X})"

    return False, ""

# ====================================================================
# BlueZ Automated Reverse-MAC Authentication Agent
# ====================================================================
AGENT_PATH = "/org/bluez/cafepad_agent"

try:
    import dbus
    import dbus.service
    _HAS_DBUS = True
except ImportError:
    _HAS_DBUS = False

if _HAS_DBUS:
    class NintendoAgent(dbus.service.Object):
        """
        Automated BlueZ D-Bus Agent for Genuine Nintendo Hardware.
        Genuine Nintendo Wii / Wii U controllers enforce legacy Bluetooth PIN authentication,
        where the link PIN payload is the host Bluetooth adapter's MAC address in reverse byte order.
        """
        def __init__(self, bus, path, host_mac):
            super().__init__(bus, path)
            self.host_mac = host_mac
            mac_clean = host_mac.replace(":", "").strip()
            mac_bytes = [int(mac_clean[i:i+2], 16) for i in range(0, len(mac_clean), 2)]
            self.wii_pin = "".join(chr(b) for b in reversed(mac_bytes))

        @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
        def AuthorizeService(self, device, uuid):
            return

        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
        def RequestPinCode(self, device):
            return self.wii_pin

        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
        def RequestPasskey(self, device):
            return dbus.UInt32(0)

        @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
        def DisplayPasskey(self, device, passkey, entered):
            pass

        @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
        def RequestConfirmation(self, device, passkey):
            return

        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
        def RequestAuthorization(self, device):
            return

        @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
        def Cancel(self):
            pass
else:
    class NintendoAgent:
        def __init__(self, *args, **kwargs):
            pass

class NintendoAgentManager:
    """Manages the lifecycle and background GLib mainloop of the BlueZ PIN agent."""
    def __init__(self):
        self.agent = None
        self.bus = None
        self.loop = None
        self.thread = None
        self._lock = threading.Lock()
        self._started = False

    def start(self):
        with self._lock:
            if self._started:
                return True
            if not _HAS_DBUS:
                return False

            try:
                from dbus.mainloop.glib import DBusGMainLoop
                from gi.repository import GLib

                DBusGMainLoop(set_as_default=True)
                self.bus = dbus.SystemBus()

                # Discover host Bluetooth adapter MAC
                manager = dbus.Interface(self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
                objs = manager.GetManagedObjects()
                host_mac = None
                for p, ifaces in objs.items():
                    if "org.bluez.Adapter1" in ifaces:
                        host_mac = str(ifaces["org.bluez.Adapter1"].get("Address", ""))
                        break

                if not host_mac:
                    return False

                self.agent = NintendoAgent(self.bus, AGENT_PATH, host_mac)
                agent_mgr = dbus.Interface(self.bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
                try:
                    agent_mgr.RegisterAgent(AGENT_PATH, "KeyboardDisplay")
                    agent_mgr.RequestDefaultAgent(AGENT_PATH)
                except Exception:
                    try:
                        agent_mgr.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
                        agent_mgr.RequestDefaultAgent(AGENT_PATH)
                    except Exception:
                        pass

                self.loop = GLib.MainLoop()
                self.thread = threading.Thread(target=self.loop.run, daemon=True)
                self.thread.start()
                self._started = True
                return True
            except Exception:
                return False

    def stop(self):
        with self._lock:
            if not self._started:
                return
            try:
                if self.bus and self.agent:
                    agent_mgr = dbus.Interface(self.bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
                    agent_mgr.UnregisterAgent(AGENT_PATH)
            except Exception:
                pass
            if self.loop:
                try:
                    self.loop.quit()
                except Exception:
                    pass
            self.agent = None
            self._started = False

_agent_manager_instance = None

def get_agent_manager():
    global _agent_manager_instance
    if _agent_manager_instance is None:
        _agent_manager_instance = NintendoAgentManager()
    return _agent_manager_instance

def scan_dbus_glib(timeout_seconds=30, quiet=False, ignore_macs=None):
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    get_agent_manager().start()
    ignore_set = set(m.strip().upper() for m in (ignore_macs or []))

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")

    objs = manager.GetManagedObjects()
    adapter_path = None
    for p, ifaces in objs.items():
        if "org.bluez.Adapter1" in ifaces:
            adapter_path = p
            break
    if not adapter_path:
        return None

    adapter = dbus.Interface(bus.get_object("org.bluez", adapter_path), "org.bluez.Adapter1")
    loop = GLib.MainLoop()
    found = [None]
    spinner = ['|', '/', '-', '\\']
    sp_state = [0]
    t0 = time.time()

    def check_dev(props):
        matched, reason = is_wii_u_candidate(props)
        if matched and found[0] is None:
            addr = str(props.get("Address", "")).upper()
            if addr in ignore_set:
                return False
            name = str(props.get("Name", "") or props.get("Alias", "Wii U Pro Controller"))
            dev_class = int(props.get("Class", 0))
            found[0] = (addr, name, dev_class, reason)

            # Mark device as Trusted in BlueZ so baseband doesn't prompt for approval
            try:
                dev_path = f"{adapter_path}/dev_{addr.replace(':', '_')}"
                dev_obj = bus.get_object("org.bluez", dev_path)
                d_props = dbus.Interface(dev_obj, "org.freedesktop.DBus.Properties")
                d_props.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
            except Exception:
                pass

            try:
                adapter.StopDiscovery()
            except Exception:
                pass
            loop.quit()
            return True
        return False

    def on_interfaces_added(path, interfaces):
        if "org.bluez.Device1" in interfaces:
            check_dev(interfaces["org.bluez.Device1"])

    def on_properties_changed(interface, changed, invalidated, path):
        if interface == "org.bluez.Device1":
            try:
                dev_obj = bus.get_object("org.bluez", path)
                props_iface = dbus.Interface(dev_obj, "org.freedesktop.DBus.Properties")
                all_props = props_iface.GetAll("org.bluez.Device1")
                check_dev(all_props)
            except Exception:
                pass

    bus.add_signal_receiver(
        on_interfaces_added,
        signal_name="InterfacesAdded",
        dbus_interface="org.freedesktop.DBus.ObjectManager",
        bus_name="org.bluez"
    )
    bus.add_signal_receiver(
        on_properties_changed,
        signal_name="PropertiesChanged",
        dbus_interface="org.freedesktop.DBus.Properties",
        bus_name="org.bluez",
        path_keyword="path"
    )

    def on_tick():
        elapsed = time.time() - t0
        if elapsed >= timeout_seconds:
            try:
                adapter.StopDiscovery()
            except Exception:
                pass
            loop.quit()
            return False

        if not quiet:
            sp = spinner[sp_state[0] % len(spinner)]
            sp_state[0] += 1
            rem = int(timeout_seconds - elapsed)
            sys.stdout.write(f"\r[*] [{sp}] Sweeping 2.4 GHz radio for SYNC packets... [{rem}s left]   ")
            sys.stdout.flush()

        return True

    try:
        adapter.StartDiscovery()
    except dbus.DBusException as e:
        if "InProgress" not in str(e):
            raise

    GLib.timeout_add(200, on_tick)
    loop.run()
    return found[0]

def scan_dbus_poll(timeout_seconds=30, quiet=False, ignore_macs=None):
    import dbus
    get_agent_manager().start()
    ignore_set = set(m.strip().upper() for m in (ignore_macs or []))

    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    objs = manager.GetManagedObjects()
    adapter_path = None
    for p, ifaces in objs.items():
        if "org.bluez.Adapter1" in ifaces:
            adapter_path = p
            break
    if not adapter_path:
        return None

    adapter = dbus.Interface(bus.get_object("org.bluez", adapter_path), "org.bluez.Adapter1")
    try:
        adapter.StartDiscovery()
    except Exception:
        pass

    spinner = ['|', '/', '-', '\\']
    sp_i = 0
    t0 = time.time()
    try:
        while time.time() - t0 < timeout_seconds:
            if not quiet:
                sp = spinner[sp_i % len(spinner)]
                sp_i += 1
                rem = int(timeout_seconds - (time.time() - t0))
                sys.stdout.write(f"\r[*] [{sp}] Sweeping 2.4 GHz radio for SYNC packets... [{rem}s left]   ")
                sys.stdout.flush()

            objs = manager.GetManagedObjects()
            for p, ifaces in objs.items():
                if "org.bluez.Device1" in ifaces:
                    dev = ifaces["org.bluez.Device1"]
                    matched, reason = is_wii_u_candidate(dev)
                    if matched:
                        addr = str(dev.get("Address", "")).upper()
                        if addr in ignore_set:
                            continue
                        name = str(dev.get("Name", "") or dev.get("Alias", "Wii U Pro Controller"))
                        dev_class = int(dev.get("Class", 0))
                        try:
                            dev_path = f"{adapter_path}/dev_{addr.replace(':', '_')}"
                            dev_obj = bus.get_object("org.bluez", dev_path)
                            d_props = dbus.Interface(dev_obj, "org.freedesktop.DBus.Properties")
                            d_props.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True))
                        except Exception:
                            pass
                        return addr, name, dev_class, reason

            time.sleep(0.25)
    finally:
        try:
            adapter.StopDiscovery()
        except Exception:
            pass
    return None

def scan_bluetoothctl(timeout_seconds=30, quiet=False, ignore_macs=None):
    ignore_set = set(m.strip().upper() for m in (ignore_macs or []))
    spinner = ['|', '/', '-', '\\']
    sp_i = 0
    t0 = time.time()
    proc = subprocess.Popen(["bluetoothctl", "scan", "on"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        while time.time() - t0 < timeout_seconds:
            if not quiet:
                sp = spinner[sp_i % len(spinner)]
                sp_i += 1
                rem = int(timeout_seconds - (time.time() - t0))
                sys.stdout.write(f"\r[*] [{sp}] Sweeping 2.4 GHz radio for SYNC packets... [{rem}s left]   ")
                sys.stdout.flush()

            line = proc.stdout.readline()
            if line:
                m = re.search(r'Device\s+([0-9A-Fa-f:]{17})\s*(.*)', line)
                if m:
                    addr = m.group(1).upper()
                    if addr in ignore_set:
                        continue
                    name = m.group(2).strip()
                    props = {"Address": addr, "Name": name}
                    matched, reason = is_wii_u_candidate(props)
                    if matched:
                        return addr, name, 0, reason
            time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            subprocess.run(["bluetoothctl", "scan", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass
    return None

def scan_for_controller(timeout_seconds=30, quiet=False, ignore_macs=None):
    get_agent_manager().start()

    if not quiet:
        print(f"\n{COLOR_CYAN}[*] Searching for Wii U Pro Controllers over the air...{COLOR_RESET}")
        print(f"{COLOR_YELLOW}[!] ACTION REQUIRED:{COLOR_RESET}")
        print(f"    PRESS AND HOLD THE {COLOR_BOLD}RED SYNC BUTTON{COLOR_RESET} ON THE BACK OF YOUR CONTROLLER NOW.")
        print("    (Confirm the 4 blue LEDs at the bottom are flashing rapidly)\n")

    res = None
    scanned = False
    # Tier 1: Event-driven D-Bus + GLib
    try:
        res = scan_dbus_glib(timeout_seconds=timeout_seconds, quiet=quiet, ignore_macs=ignore_macs)
        scanned = True
    except Exception:
        scanned = False

    # Tier 2: D-Bus polling (fallback if GLib is not available)
    if not scanned:
        try:
            res = scan_dbus_poll(timeout_seconds=timeout_seconds, quiet=quiet, ignore_macs=ignore_macs)
            scanned = True
        except Exception:
            scanned = False

    # Tier 3: bluetoothctl CLI stream (fallback if python-dbus is not installed)
    if not scanned:
        try:
            res = scan_bluetoothctl(timeout_seconds=timeout_seconds, quiet=quiet, ignore_macs=ignore_macs)
            scanned = True
        except Exception:
            scanned = False

    if res:
        mac, name, dev_class, reason = res
        if not quiet:
            cls_str = f" (Class: 0x{dev_class:06X})" if dev_class else ""
            print(f"\n\n{COLOR_GREEN}=================================================================={COLOR_RESET}")
            print(f"{COLOR_GREEN}[+] GAMEPAD DETECTED OVER THE AIR: {COLOR_BOLD}{mac}{COLOR_RESET}")
            print(f"    Device: {name}{cls_str} [{reason}]")
            print(f"{COLOR_GREEN}=================================================================={COLOR_RESET}")
        save_mac(mac)
        if not quiet:
            print(f"[*] Saved controller MAC to {CONFIG_PATH}")
        time.sleep(0.15)
        return mac

    if not quiet:
        print(f"\n{COLOR_YELLOW}[-] Discovery timed out. Ensure LEDs were flashing rapidly.{COLOR_RESET}")
    return None

# ====================================================================
# Input Parsing & Normalization
# ====================================================================
def normalize_stick(val, center=2048, deadzone=120, max_val=4095):
    diff = val - center
    if abs(diff) < deadzone:
        return 0.0
    if diff > 0:
        norm = diff / (max_val - center)
    else:
        norm = diff / center
    return max(-1.0, min(1.0, norm))

def parse_buttons(b8, b9, b10):
    btns = []
    # Byte 8 (Active LOW)
    if not (b8 & (1 << 7)): btns.append("RIGHT")
    if not (b8 & (1 << 6)): btns.append("DOWN")
    if not (b8 & (1 << 5)): btns.append("L")
    if not (b8 & (1 << 4)): btns.append("-")
    if not (b8 & (1 << 3)): btns.append("HOME")
    if not (b8 & (1 << 2)): btns.append("+")
    if not (b8 & (1 << 1)): btns.append("R")

    # Byte 9 (Active LOW)
    if not (b9 & (1 << 7)): btns.append("ZL")
    if not (b9 & (1 << 6)): btns.append("B")
    if not (b9 & (1 << 5)): btns.append("Y")
    if not (b9 & (1 << 4)): btns.append("A")
    if not (b9 & (1 << 3)): btns.append("X")
    if not (b9 & (1 << 2)): btns.append("ZR")
    if not (b9 & (1 << 1)): btns.append("LEFT")
    if not (b9 & (1 << 0)): btns.append("UP")

    # Byte 10 (Active LOW)
    if not (b10 & (1 << 1)): btns.append("L3")
    if not (b10 & (1 << 0)): btns.append("R3")

    return btns

# ====================================================================
# Controller State Class
# ====================================================================
class ControllerState:
    def __init__(self, lx=0.0, ly=0.0, rx=0.0, ry=0.0, buttons=None, battery=0, is_charging=False):
        self.lx = lx
        self.ly = ly
        self.rx = rx
        self.ry = ry
        self.buttons = buttons or []
        self.battery = battery
        self.is_charging = is_charging

    def __repr__(self):
        btn_str = " ".join(self.buttons)
        return f"<State LX={self.lx:+0.2f} LY={self.ly:+0.2f} RX={self.rx:+0.2f} RY={self.ry:+0.2f} Bat={self.battery} Btns=[{btn_str}]>"

# ====================================================================
# High-Level Controller Engine (Python Library API)
# ====================================================================
class WiiUProController:
    """Universal Bluetooth Driver for Genuine & Replica Wii U Pro Controllers."""

    def __init__(self, mac=None, player_id=0):
        self.mac = mac
        self.player_id = player_id
        self.led_mask = 0x10 << (player_id % 4)  # P1: 0x10, P2: 0x20, P3: 0x40, P4: 0x80
        self.s_ctrl = None
        self.s_intr = None
        self.connected = False
        self.last_keepalive = 0.0
        self.last_packet_time = 0.0

    def connect(self, timeout=30, quiet=False):
        if not self.mac:
            macs = load_saved_macs()
            self.mac = macs[0] if macs else None
        if not self.mac:
            self.mac = scan_for_controller(timeout_seconds=timeout, quiet=quiet)
        if not self.mac:
            return False

        # Ensure BlueZ Agent is active for PIN authentication
        get_agent_manager().start()

        t0 = time.time()
        connected_ctrl = False
        while time.time() - t0 < timeout:
            try:
                self.s_ctrl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
                self.s_ctrl.settimeout(4.0)
                self.s_ctrl.connect((self.mac, PSM_HID_CNTL))
                connected_ctrl = True
                break
            except Exception:
                if self.s_ctrl:
                    try:
                        self.s_ctrl.close()
                    except Exception:
                        pass
                    self.s_ctrl = None
                time.sleep(0.3)

        if not connected_ctrl or not self.s_ctrl:
            return False

        # Give Broadcom BCM20730 stack 80ms to settle after Control channel connection
        time.sleep(0.08)

        connected_intr = False
        t_intr = time.time()
        while time.time() - t_intr < 5.0:
            try:
                self.s_intr = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
                self.s_intr.settimeout(4.0)
                self.s_intr.connect((self.mac, PSM_HID_INTR))
                connected_intr = True
                break
            except Exception:
                if self.s_intr:
                    try:
                        self.s_intr.close()
                    except Exception:
                        pass
                    self.s_intr = None
                time.sleep(0.2)

        if not connected_intr or not self.s_intr:
            self.close()
            return False

        # Initialize controller microcode with Player-specific LED
        try:
            self.s_intr.send(bytes([0xa2, 0x11, self.led_mask]))  # Solid Player LED
        except Exception:
            try:
                self.s_ctrl.send(bytes([0xa2, 0x11, self.led_mask]))
            except Exception:
                pass
        time.sleep(0.04)

        try:
            self.s_intr.send(b"\xa2\x16\x04\xa4\x00\xf0\x01\x55")  # Init ext register 1
        except Exception:
            pass
        time.sleep(0.04)

        try:
            self.s_intr.send(b"\xa2\x16\x04\xa4\x00\xfb\x01\x00")  # Init ext register 2
        except Exception:
            pass
        time.sleep(0.04)

        try:
            self.s_intr.send(b"\xa2\x12\x00\x3d")  # Continuous Data Reporting Mode 0x3D
        except Exception:
            pass
        time.sleep(0.04)

        self.s_intr.setblocking(False)
        self.s_ctrl.setblocking(False)
        self.connected = True
        self.last_keepalive = time.time()
        self.last_packet_time = time.time()
        return True

    def poll(self, timeout=0.04):
        if not self.connected or not self.s_intr:
            return None

        now = time.time()

        # 1. Periodic Keepalive Heartbeat (every 3.5 seconds)
        if now - self.last_keepalive >= 3.5:
            try:
                self.s_intr.send(b"\xa2\x15\x00")
            except Exception:
                pass
            self.last_keepalive = now

        # 2. Watchdog Recovery (re-enable DRM 0x3D if silent)
        if now - self.last_packet_time >= 1.5:
            try:
                self.s_intr.send(b"\xa2\x12\x00\x3d")
            except Exception:
                pass

        # 3. Drain Control channel
        try:
            while True:
                cdata = self.s_ctrl.recv(64)
                if not cdata: break
        except (BlockingIOError, socket.error):
            pass

        # 4. Wait for Interrupt packets
        r, _, _ = select.select([self.s_intr], [], [], timeout)
        if not r:
            return None

        try:
            data = self.s_intr.recv(64)
        except (BlockingIOError, socket.error):
            return None

        if not data:
            self.connected = False
            return None

        self.last_packet_time = time.time()

        if len(data) >= 13 and data[0] == 0xa1 and data[1] == 0x3d:
            ext = data[2:]
            lx_raw = ext[0] | ((ext[1] & 0x0f) << 8)
            rx_raw = ext[2] | ((ext[3] & 0x0f) << 8)
            ly_raw = ext[4] | ((ext[5] & 0x0f) << 8)
            ry_raw = ext[6] | ((ext[7] & 0x0f) << 8)

            lx = normalize_stick(lx_raw)
            rx = normalize_stick(rx_raw)
            ly = -normalize_stick(ly_raw)
            ry = -normalize_stick(ry_raw)

            b8, b9, b10 = ext[8], ext[9], ext[10]
            bat = (b10 >> 4) & 0x07
            is_charging = not bool(b10 & (1 << 2))
            btns = parse_buttons(b8, b9, b10)

            return ControllerState(lx, ly, rx, ry, btns, bat, is_charging)

        return None

    def set_rumble(self, enabled=True):
        if not self.connected or not self.s_intr:
            return
        cmd = bytes([0xa2, 0x11, self.led_mask | (0x01 if enabled else 0x00)])
        try:
            self.s_intr.send(cmd)
        except Exception:
            pass

    def close(self):
        self.connected = False
        if self.s_intr:
            try: self.s_intr.close()
            except Exception: pass
            self.s_intr = None
        if self.s_ctrl:
            try: self.s_ctrl.close()
            except Exception: pass
            self.s_ctrl = None

# ====================================================================
# Standard Xbox 360 Virtual Gamepad Bridge with Force Feedback (/dev/uinput)
# ====================================================================
class UInputBridge:
    def __init__(self, player_id=0, nintendo_layout=False):
        self.fd = None
        self.active = False
        self.player_id = player_id
        self.nintendo_layout = nintendo_layout

        try:
            self.fd = os.open("/dev/uinput", os.O_RDWR | os.O_NONBLOCK)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_FF)
            fcntl.ioctl(self.fd, UI_SET_FFBIT, FF_RUMBLE)

            # Register standard buttons (matching Linux xpad.c)
            for btn in [
                BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST,
                BTN_TL, BTN_TR,
                BTN_SELECT, BTN_START, BTN_MODE,
                BTN_THUMBL, BTN_THUMBR
            ]:
                fcntl.ioctl(self.fd, UI_SET_KEYBIT, btn)

            # Register Sticks (-32767 to 32767)
            for axis in [ABS_X, ABS_Y, ABS_RX, ABS_RY]:
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, axis)
                abs_setup = struct.pack('HHiiiiii', axis, 0, 0, -32767, 32767, 16, 128, 0)
                fcntl.ioctl(self.fd, UI_ABS_SETUP, abs_setup)

            # Register Analog Triggers ZL/ZR (0 to 255)
            for trig in [ABS_Z, ABS_RZ]:
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, trig)
                abs_setup = struct.pack('HHiiiiii', trig, 0, 0, 0, 255, 0, 0, 0)
                fcntl.ioctl(self.fd, UI_ABS_SETUP, abs_setup)

            # Register D-Pad Hat (-1 to 1)
            for hat in [ABS_HAT0X, ABS_HAT0Y]:
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, hat)
                abs_setup = struct.pack('HHiiiiii', hat, 0, 0, -1, 1, 0, 0, 0)
                fcntl.ioctl(self.fd, UI_ABS_SETUP, abs_setup)

            name = f"Microsoft X-Box 360 pad (Player {player_id + 1})".encode('utf-8')
            dev_setup = struct.pack('HHHH80sI', 0x03, 0x045E, 0x028E, 1, name.ljust(80, b'\x00'), 16)
            fcntl.ioctl(self.fd, UI_DEV_SETUP, dev_setup)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
            self.active = True
        except Exception:
            if self.fd is not None:
                try: os.close(self.fd)
                except Exception: pass
                self.fd = None
            self.active = False

    def check_ff_events(self, rumble_callback):
        if not self.active or self.fd is None:
            return
        try:
            while True:
                data = os.read(self.fd, 24)
                if len(data) < 24:
                    break
                sec, usec, ev_type, ev_code, ev_val = struct.unpack('qqHHi', data)
                if ev_type == EV_UINPUT:
                    if ev_code == UI_FF_UPLOAD:
                        upload = uinput_ff_upload()
                        upload.request_id = 0
                        if fcntl.ioctl(self.fd, UI_BEGIN_FF_UPLOAD, upload) >= 0:
                            upload.retval = 0
                            fcntl.ioctl(self.fd, UI_END_FF_UPLOAD, upload)
                    elif ev_code == UI_FF_ERASE:
                        erase = uinput_ff_erase()
                        erase.request_id = 0
                        if fcntl.ioctl(self.fd, UI_BEGIN_FF_ERASE, erase) >= 0:
                            erase.retval = 0
                            fcntl.ioctl(self.fd, UI_END_FF_ERASE, erase)
                elif ev_type == EV_FF:
                    rumble_callback(ev_val > 0)
        except (BlockingIOError, OSError):
            pass

    def emit(self, lx, ly, rx, ry, btns):
        if not self.active or self.fd is None: return
        now = time.time()
        sec = int(now)
        usec = int((now - sec) * 1_000_000)

        zl_val = 255 if "ZL" in btns else 0
        zr_val = 255 if "ZR" in btns else 0

        hat_x = 0
        if "LEFT" in btns: hat_x -= 1
        if "RIGHT" in btns: hat_x += 1

        hat_y = 0
        if "UP" in btns: hat_y -= 1
        if "DOWN" in btns: hat_y += 1

        if self.nintendo_layout:
            btn_bottom = "A" in btns
            btn_right  = "B" in btns
            btn_left   = "X" in btns
            btn_top    = "Y" in btns
        else:
            btn_bottom = "B" in btns
            btn_right  = "A" in btns
            btn_left   = "Y" in btns
            btn_top    = "X" in btns

        evs = [
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_X, int(lx * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_Y, int(ly * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_RX, int(rx * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_RY, int(ry * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_Z, zl_val),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_RZ, zr_val),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_HAT0X, hat_x),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_HAT0Y, hat_y),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_SOUTH, 1 if btn_bottom else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_EAST,  1 if btn_right  else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_NORTH, 1 if btn_left   else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_WEST,  1 if btn_top    else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_TL, 1 if "L" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_TR, 1 if "R" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_SELECT, 1 if "-" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_START,  1 if "+" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_MODE,   1 if "HOME" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_THUMBL, 1 if "L3" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_THUMBR, 1 if "R3" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_SYN, SYN_REPORT, 0)
        ]
        try:
            os.write(self.fd, b"".join(evs))
        except Exception:
            pass

    def close(self):
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None
            self.active = False

# ====================================================================
# Player Worker Thread (Multi-Controller Architecture)
# ====================================================================
class PlayerWorker(threading.Thread):
    def __init__(self, mac, player_id=0, nintendo_layout=False, quiet=False, controller=None):
        super().__init__(daemon=True)
        self.mac = mac.strip().upper()
        self.player_id = player_id
        self.nintendo_layout = nintendo_layout
        self.quiet = quiet
        self.running = True
        self.controller = controller or WiiUProController(mac=self.mac, player_id=self.player_id)
        self.uinput = None
        self.last_battery_alert = 0.0
        self.last_config_check = 0.0
        self.current_state = None
        self.connected_event = threading.Event()
        if self.controller.connected:
            self.connected_event.set()

    def run(self):
        self.uinput = UInputBridge(player_id=self.player_id, nintendo_layout=self.nintendo_layout)
        p_name = f"Player {self.player_id + 1}"

        while self.running:
            if not self.controller.connected:
                if not self.controller.connect(timeout=5, quiet=True):
                    time.sleep(0.5)
                    continue

                self.connected_event.set()
                if not self.quiet:
                    print(f"\n{COLOR_GREEN}[+] {p_name} ONLINE ({self.mac}) — LED {self.player_id + 1} Locked! (Xbox 360 /dev/input/js* with Rumble){COLOR_RESET}")
            else:
                self.connected_event.set()

            deadman_active = False
            try:
                while self.running and self.controller.connected:
                    # 1. Handle in-game Force Feedback (Rumble) from games/emulators
                    self.uinput.check_ff_events(self.controller.set_rumble)

                    # 2. Poll controller input
                    state = self.controller.poll(timeout=0.04)
                    now = time.time()

                    # Dynamic config sync (hot-reload layout without disconnect)
                    if now - self.last_config_check >= 3.0:
                        self.last_config_check = now
                        cfg = load_config()
                        if "nintendo_layout" in cfg:
                            self.set_nintendo_layout(bool(cfg["nintendo_layout"]))

                    # 3. Dead-man Failsafe (clear inputs if silent > 3.0s)
                    if now - self.controller.last_packet_time >= 3.0 and not deadman_active:
                        self.uinput.emit(0.0, 0.0, 0.0, 0.0, [])
                        deadman_active = True

                    if state:
                        deadman_active = False
                        self.current_state = state
                        self.uinput.emit(state.lx, state.ly, state.rx, state.ry, state.buttons)

                        # 4. Low Battery Desktop Notification
                        if state.battery <= 1 and not state.is_charging:
                            if now - self.last_battery_alert > 600:
                                self.last_battery_alert = now
                                try:
                                    subprocess.Popen([
                                        "notify-send", "-i", "input-gaming",
                                        "CaféPad",
                                        f"{p_name} controller battery low ({state.battery} bar left)"
                                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                except Exception:
                                    pass

            except Exception:
                pass

            # Controller disconnected
            self.connected_event.clear()
            self.current_state = None
            if self.uinput:
                self.uinput.emit(0.0, 0.0, 0.0, 0.0, [])
            self.controller.close()
            if self.running and not self.quiet:
                print(f"\n{COLOR_YELLOW}[-] {p_name} ({self.mac}) disconnected. Press any button to reconnect...{COLOR_RESET}")
            time.sleep(1.0)

    def set_nintendo_layout(self, enabled: bool):
        self.nintendo_layout = bool(enabled)
        if self.uinput:
            self.uinput.nintendo_layout = bool(enabled)

    def trigger_rumble_test(self, duration=0.5):
        def _rumble():
            if self.controller.connected:
                self.controller.set_rumble(True)
                time.sleep(duration)
                self.controller.set_rumble(False)
        threading.Thread(target=_rumble, daemon=True).start()

    def stop(self):
        self.running = False
        if self.controller:
            self.controller.close()
        if self.uinput:
            self.uinput.close()

# ====================================================================
# Main Connection & Service Loop
# ====================================================================
def main():
    parser = argparse.ArgumentParser(
        description="CaféPad — Universal Linux Driver & Gamepad Bridge (Multi-Player)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cafepad                      Auto-connect to all saved controller(s) or scan
  cafepad --scan               Scan and pair a new controller (Player 1-4)
  cafepad --target MAC         Connect to a specific controller MAC
  cafepad --test-rumble        Test physical rumble motors on connected controller
  cafepad --nintendo-layout    Use printed letter markings (A->A)
  cafepad --daemon             Run silently in background
"""
    )
    parser.add_argument("--target", "--mac", dest="target_mac", default=None,
                        help="Target controller Bluetooth MAC address")
    parser.add_argument("--scan", "--pair", action="store_true",
                        help="Force inquiry scan for nearby controllers in SYNC mode")
    parser.add_argument("--nintendo-layout", action="store_true",
                        help="Map buttons by printed letters (A->A) instead of Xbox positions")
    parser.add_argument("--test-rumble", action="store_true",
                        help="Test physical vibration motor on controller")
    parser.add_argument("--daemon", action="store_true",
                        help="Run in quiet background mode (suppress terminal updates)")
    parser.add_argument("--status", action="store_true",
                        help="Show saved controller config and exit")
    parser.add_argument("--gui", action="store_true",
                        help="Launch graphical desktop interface (CaféPad GUI)")
    parser.add_argument("-v", "--version", action="version", version=f"cafepad {__version__}")

    args = parser.parse_args()

    if args.gui:
        gui_script = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cafepad_gui.py")
        if not os.path.exists(gui_script):
            gui_script = "cafepad-gui"
        os.execvp("python3", ["python3", gui_script] + sys.argv[2:])

    if args.status:
        cfg = load_config()
        macs = load_saved_macs()
        layout_str = "Nintendo Letters (A->A, B->B)" if cfg.get("nintendo_layout", False) else "Xbox 360 Physical Position"
        print(f"Profile Layout: {layout_str}")
        if macs:
            print("Configured controller MACs:")
            for i, m in enumerate(macs[:4]):
                print(f"  Player {i + 1}: {m}")
        else:
            print("No saved controllers found. Run 'cafepad --scan' to pair.")
        return 0

    if args.test_rumble:
        macs = load_saved_macs()
        target = args.target_mac or (macs[0] if macs else None)
        if not target:
            print(f"{COLOR_YELLOW}[!] No controller found to test rumble. Pair one first with '--scan'{COLOR_RESET}")
            return 1
        print(f"[*] Testing rumble on controller {target}...")
        ctrl = WiiUProController(mac=target, player_id=0)
        if ctrl.connect(timeout=5, quiet=False):
            print(f"{COLOR_GREEN}[+] Connected! Triggering 0.6s rumble pulse...{COLOR_RESET}")
            ctrl.set_rumble(True)
            time.sleep(0.6)
            ctrl.set_rumble(False)
            time.sleep(0.2)
            ctrl.close()
            print(f"{COLOR_GREEN}[+] Rumble test complete.{COLOR_RESET}")
            return 0
        else:
            print(f"{COLOR_YELLOW}[-] Could not connect to controller. Make sure it is awake.{COLOR_RESET}")
            return 1

    if not args.daemon:
        print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
        print(f"{COLOR_CYAN}   CaféPad — Universal Linux Driver & Bridge (Multi-Player)       {COLOR_RESET}")
        print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")

    # 1. Resolve Target MAC Addresses
    get_agent_manager().start()

    macs = []
    if args.target_mac:
        macs = [args.target_mac.strip().upper()]
    else:
        macs = load_saved_macs()

    if args.scan or not macs:
        new_mac = scan_for_controller(timeout_seconds=30, quiet=args.daemon, ignore_macs=macs)
        if not new_mac and not macs:
            if not args.daemon:
                print(f"\n{COLOR_YELLOW}[!] Could not find any controller. Ensure controller LEDs are flashing rapidly.{COLOR_RESET}")
            return 1
        if new_mac and new_mac not in macs:
            macs.append(new_mac)
            save_mac(new_mac)

    macs = macs[:4]  # Maximum 4 players

    cfg = load_config()
    active_nintendo = args.nintendo_layout or bool(cfg.get("nintendo_layout", False))

    if not args.daemon:
        layout_name = "Nintendo Letters (A->A, B->B)" if active_nintendo else "Physical Position Match (Bottom->A, Right->B)"
        print(f"{COLOR_GREEN}[+] Linux Virtual Gamepads: ACTIVE (/dev/input/js*){COLOR_RESET}")
        print(f"    Profile: Standard Xbox 360 Controller ({layout_name})")
        print(f"    In-Game Force Feedback Rumble: ACTIVE (EV_FF / FF_RUMBLE)")
        print(f"\n[*] Configured Player Slots:")
        for idx, m in enumerate(macs):
            print(f"    {COLOR_BOLD}Player {idx + 1}:{COLOR_RESET} {m} (LED {idx + 1} Solid)")
        print(f"\n[!] Press ANY BUTTON on your controller to connect...")
        if len(macs) < 4:
            print(f"    (Run 'cafepad --scan' at any time to pair Player {len(macs) + 1})")
        print()

    # Launch worker threads
    workers = []
    for idx, m in enumerate(macs):
        w = PlayerWorker(m, player_id=idx, nintendo_layout=active_nintendo, quiet=args.daemon)
        w.start()
        workers.append(w)

    try:
        while True:
            time.sleep(0.1)
            if not args.daemon:
                active_lines = []
                for w in workers:
                    st = w.current_state
                    if st:
                        btn_str = " ".join(st.buttons)
                        active_lines.append(f"P{w.player_id + 1}: L[{st.lx:+0.2f},{st.ly:+0.2f}] R[{st.rx:+0.2f},{st.ry:+0.2f}] Bat:{st.battery} [{btn_str}]")
                if active_lines:
                    sys.stdout.write(f"\r{' | '.join(active_lines):<100}")
                    sys.stdout.flush()
    except KeyboardInterrupt:
        if not args.daemon:
            print("\n\n[*] Stopping CaféPad...")
    finally:
        for w in workers:
            w.stop()
        get_agent_manager().stop()

if __name__ == "__main__":
    sys.exit(main() or 0)
