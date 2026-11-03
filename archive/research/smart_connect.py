#!/usr/bin/env python3
"""
Wii U Pro Controller Smart Pair & Auto-Connect Suite (Dual GIAC + LIAC with Radio Isolation)
- Pulses Nintendo Dedicated LIAC (0x9E8B00) + BlueZ Classic BR/EDR discovery.
- The INSTANT a candidate is detected, stops all inquiries to give the radio 100% bandwidth for paging.
- Automated zero-prompt pairing agent.
- Connects directly without broken Link Key bonding.
- Confirms Linux joystick node (/dev/input/js*) before launching the live tester.
"""

import sys
import os
import re
import time
import datetime
import threading
import subprocess
import glob
import fcntl
import socket
import ctypes
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

COLOR_RESET   = "\033[0m"
COLOR_RED     = "\033[1;31m"
COLOR_GREEN   = "\033[1;32m"
COLOR_YELLOW  = "\033[1;33m"
COLOR_CYAN    = "\033[1;36m"
COLOR_BOLD    = "\033[1m"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE_PATH = os.path.join(PROJECT_DIR, "wiiupro_bluetooth.log")
AGENT_PATH = "/org/bluez/wiiupro_agent"

# Persistent blacklist of known non-gamepad devices
BLACKLIST_MACS = {
    "DC:03:98:E2:22:67",  # [LG] webOS TV UP751C0ZF
    "C8:AA:B2:61:3B:A0",  # SWTV-24AE-FHD
    "3C:C5:DD:93:65:94",  # Gaoshengda Smart TV/Audio
    "06:19:A9:56:7B:80",  # DR06 BT Smartwatch
    "4C:91:57:86:17:80",  # APOS A8OVS
    "26:FB:E3:F8:0C:38",  # 3002dw LJ printer
    "CC:B1:1A:E5:E0:95",  # Samsung 5 Series TV
    "60:AB:D2:67:80:EA",  # Bose SoundLink
    "AC:BF:71:DE:03:00",  # Bose QC Headphones
    "F3:B0:CF:EC:EE:50",  # Surface Mouse
    "D7:A5:C3:F2:F0:BE",  # i80
    "C0:23:8D:CF:E9:EA",  # Samsung AU7175 TV
}

# Known Nintendo Vendor OUIs
NINTENDO_OUIS = [
    "00:1F:32", "00:26:59", "00:27:09", "18:2A:7B", "40:F4:07", 
    "58:2F:40", "78:A2:A0", "7C:BB:8A", "8C:CD:E8", "98:B6:E9", 
    "A4:5C:27", "B8:86:87", "CC:9E:00", "D8:6B:F7", "E0:E7:51"
]

class Logger:
    def __init__(self, filepath):
        self.filepath = filepath
        self.file = open(filepath, "a", buffering=1, encoding="utf-8")
        self._lock = threading.Lock()

    def log(self, level, message):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{ts}] [{level:<5}] {message}\n"
        with self._lock:
            self.file.write(line)

    def close(self):
        try:
            with self._lock:
                self.file.close()
        except Exception:
            pass

logger = Logger(LOG_FILE_PATH)

class BluetoothAgent(dbus.service.Object):
    def __init__(self, bus, path, host_mac):
        super().__init__(bus, path)
        self.host_mac = host_mac
        mac_bytes = [int(x, 16) for x in host_mac.split(':')]
        self.wii_pin = "".join(chr(b) for b in reversed(mac_bytes))
        logger.log("INFO", f"Agent initialized with host MAC {host_mac}, reverse-byte PIN ready.")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        logger.log("AGENT", f"AuthorizeService({device}, {uuid}) -> Authorized")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        logger.log("AGENT", f"RequestPinCode({device}) -> Supplying automated reverse-MAC PIN")
        print(f"\n{COLOR_CYAN}[*] Agent: Supplying automated reverse-MAC PIN for {device}...{COLOR_RESET}")
        return self.wii_pin

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        logger.log("AGENT", f"RequestPasskey({device}) -> 0")
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        logger.log("AGENT", f"DisplayPasskey({device}, {passkey}, {entered})")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        logger.log("AGENT", f"RequestConfirmation({device}, {passkey}) -> Confirmed")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        logger.log("AGENT", f"RequestAuthorization({device}) -> Authorized")
        return

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        logger.log("AGENT", "Pairing Cancel() called by remote device.")

def get_host_mac(bus):
    try:
        adapter = bus.get_object('org.bluez', '/org/bluez/hci0')
        props = dbus.Interface(adapter, 'org.freedesktop.DBus.Properties')
        return str(props.Get('org.bluez.Adapter1', 'Address'))
    except Exception as e:
        logger.log("ERROR", f"Failed to get host MAC: {e}")
        return "00:00:00:00:00:00"

def evaluate_device(addr, name, dev_class, icon, uuids, rssi):
    """
    Evaluates if a device could be the Nintendo controller.
    Returns (status, reason) where status is 'MATCH' or 'IGNORE' or 'PROBE'.
    """
    addr_upper = addr.upper()
    if addr_upper in BLACKLIST_MACS:
        return "IGNORE", f"Blacklisted non-gamepad MAC ({addr_upper})"

    name_lower = name.lower()

    # Blacklist keywords
    ignore_names = [
        "tv", "webos", "soundlink", "nuki", "aqara", "govee", "bose", "qc", 
        "printer", "headphone", "headset", "mouse", "keyboard", "trackpad", "touchpad",
        "apos", "phone", "swtv", "laserjet", "3002dw", "lj", "deskjet", "epson", "canon"
    ]
    for ign in ignore_names:
        if ign in name_lower:
            return "IGNORE", f"Ignored by keyword '{ign}'"
    
    # Non-gamepad icons
    if icon in ["input-mouse", "input-keyboard", "audio-headphones", "audio-headset", "audio-card", "phone", "printer"]:
        return "IGNORE", f"Ignored by non-gamepad icon '{icon}'"

    # Known non-gamepad classes
    if dev_class in [0x280428, 0x0C243C, 0x240418, 0x340404, 0x2C0420, 0x2C0414, 0x5A020C, 0x0C043C]:
        return "IGNORE", f"Ignored by non-gamepad class 0x{dev_class:06X}"

    # Major class Audio/Video (0x0400)
    if (dev_class & 0x001F00) == 0x000400:
        return "IGNORE", f"Ignored by Audio/Video major class 0x{dev_class:06X}"

    # Wearables / Watches (Major class 0x0700)
    if (dev_class & 0x001F00) == 0x000700:
        return "IGNORE", f"Ignored by wearable class 0x{dev_class:06X}"

    # Minor class check: peripheral (0x0500) specifying mouse (0x80) or keyboard (0x40)
    if (dev_class & 0x001F00) == 0x0500:
        minor = dev_class & 0x0000FF
        if minor in [0x80, 0x40, 0xC0]:
            return "IGNORE", f"Ignored by peripheral class 0x{minor:02X} (Mouse/Keyboard)"

    # Positive Match 1: Official Nintendo Vendor OUIs
    for oui in NINTENDO_OUIS:
        if addr_upper.startswith(oui):
            return "MATCH", f"Nintendo Vendor OUI ({oui})"

    # Positive Match 2: Gamepad Keywords in Name
    gamepad_keywords = ["nintendo", "rvl", "wii", "pro controller", "gamepad", "joystick", "wireless controller", "057e", "wiiu"]
    for kw in gamepad_keywords:
        if kw in name_lower:
            return "MATCH", f"Positive match on keyword '{kw}'"

    # Positive Match 3: Peripheral Class (Major 0x0500, Minor Gamepad 0x08, Joystick 0x04, or Peripheral 0x00)
    if (dev_class & 0x001F00) == 0x0500:
        minor = dev_class & 0x0000FF
        if minor in [0x04, 0x08, 0x00]:
            return "MATCH", f"Positive match on Peripheral Class 0x{dev_class:06X}"

    # Positive Match 4: Icon
    if icon in ["input-gaming", "input-joystick"]:
        return "MATCH", f"Positive match on Icon '{icon}'"

    # Positive Match 5: Classic HID Service UUID (0x1124)
    for u in uuids:
        if "00001124" in u.lower():
            return "MATCH", f"Positive match on Classic HID UUID '{u}'"

    return "PROBE", f"Potential candidate (Class: 0x{dev_class:06X})"

def get_all_joysticks():
    nodes = []
    # 1. Standard Linux joystick nodes (/dev/input/js*)
    for node in sorted(glob.glob("/dev/input/js*")):
        try:
            with open(node, "rb") as f:
                buf = bytearray(128)
                fcntl.ioctl(f.fileno(), 0x80806a13, buf)
                name = buf.split(b"\x00")[0].decode("utf-8", errors="replace")
                nodes.append((node, name))
        except Exception:
            nodes.append((node, "Joystick"))

    # 2. Raw HID nodes (/dev/hidraw*) via sysfs (no root required)
    for path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = os.path.join(path, "device", "uevent")
        if os.path.exists(uevent):
            try:
                with open(uevent, "r") as f:
                    content = f.read().lower()
                    if ("057e" in content and "0330" in content) or "0471:0666" in content or "0079:1800" in content:
                        dev_name = os.path.join("/dev", os.path.basename(path))
                        nodes.append((dev_name, "Nintendo RVL-CNT-01-UC (hidraw)"))
            except Exception:
                pass

    return nodes

def check_joysticks(baseline=None):
    current = get_all_joysticks()
    if baseline is not None:
        # First check for any new standard joystick nodes
        for node, name in current:
            if node not in baseline and node.startswith("/dev/input/js"):
                return node, name
        # Second check for any new raw hidraw nodes
        for node, name in current:
            if node not in baseline:
                return node, name
        return None, None
    elif current:
        for node, name in current:
            if node.startswith("/dev/input/js"):
                return node, name
        return current[0]
    return None, None

class LIACScanner(threading.Thread):
    """
    Background hardware inquiry thread pulsing LIAC (0x9E8B00).
    Can be cleanly paused when connection is underway.
    """
    def __init__(self, callback, stop_event, pause_event):
        super().__init__(daemon=True)
        self.callback = callback
        self.stop_event = stop_event
        self.pause_event = pause_event

    def run(self):
        try:
            libbt = ctypes.CDLL('libbluetooth.so')

            class bdaddr_t(ctypes.Structure):
                _fields_ = [('b', ctypes.c_uint8 * 6)]

            class inquiry_info(ctypes.Structure):
                _fields_ = [
                    ('bdaddr', bdaddr_t),
                    ('pscan_rep_mode', ctypes.c_uint8),
                    ('pscan_period_mode', ctypes.c_uint8),
                    ('pscan_mode', ctypes.c_uint8),
                    ('dev_class', ctypes.c_uint8 * 3),
                    ('clock_offset', ctypes.c_uint16),
                ]

            hci_get_route = libbt.hci_get_route
            hci_get_route.restype = ctypes.c_int
            hci_get_route.argtypes = [ctypes.c_void_p]

            hci_inquiry = libbt.hci_inquiry
            hci_inquiry.restype = ctypes.c_int
            hci_inquiry.argtypes = [
                ctypes.c_int, ctypes.c_uint8, ctypes.c_int,
                ctypes.c_char_p, ctypes.POINTER(ctypes.POINTER(inquiry_info)), ctypes.c_long
            ]

            dev_id = hci_get_route(None)
            if dev_id < 0:
                logger.log("ERROR", "LIAC Scanner: hci_get_route failed.")
                return

            lap = b'\x00\x8b\x9e'  # Nintendo LIAC (0x9E8B00)
            flags = 0x0001        # IREQ_CACHE_FLUSH

            logger.log("INFO", "LIAC (0x9E8B00) background hardware scanner active.")

            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    time.sleep(0.2)
                    continue

                ii = ctypes.POINTER(inquiry_info)()
                num_rsp = hci_inquiry(dev_id, 2, 255, lap, ctypes.byref(ii), flags)
                if num_rsp > 0 and not self.stop_event.is_set() and not self.pause_event.is_set():
                    for i in range(num_rsp):
                        b = ii[i].bdaddr.b
                        mac = ':'.join(f'{b[5-x]:02X}' for x in range(6))
                        dev_cls = (ii[i].dev_class[2] << 16) | (ii[i].dev_class[1] << 8) | ii[i].dev_class[0]
                        self.callback(mac, dev_cls)
                time.sleep(0.5)
        except Exception as e:
            logger.log("WARN", f"LIAC scanner notice: {e}")

def main():
    logger.log("INFO", "==================================================")
    logger.log("INFO", "Starting Wii U Pro Controller Smart Pair Suite (Radio Isolation)")
    logger.log("INFO", f"PID: {os.getpid()}, Log file: {LOG_FILE_PATH}")

    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"{COLOR_CYAN}    Wii U Pro Controller Smart Pair & Auto-Connect Suite          {COLOR_RESET}")
    print(f"{COLOR_CYAN}=================================================================={COLOR_RESET}")
    print(f"[*] Dual-Protocol Engine: Standard GIAC + Dedicated Nintendo LIAC.")
    print(f"[*] Radio Isolation: Inquiries pause instantly on detection to prioritize Paging.")
    print(f"[*] Automated Zero-Prompt Reverse-MAC PIN Agent ready.")
    print(f"[*] Detailed debug log saving to:")
    print(f"    {COLOR_BOLD}{LOG_FILE_PATH}{COLOR_RESET}\n")

    target_mac = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--target":
        target_mac = sys.argv[2].upper()

    initial_joysticks = set(node for node, _ in get_all_joysticks())

    if not target_mac:
        js_node, js_name = check_joysticks()
        if js_node and any(k in js_name.lower() for k in ["nintendo", "wii", "pro controller", "rvl"]):
            print(f"{COLOR_GREEN}[+] Controller is already active at: {js_node} ({js_name}){COLOR_RESET}")
            logger.log("INFO", f"Controller already connected at {js_node} ({js_name})")
            print(f"[*] Launching live tester...\n")
            os.system(f"{PROJECT_DIR}/test_controller {js_node}")
            return

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # Setup adapter
    adapter_obj = bus.get_object('org.bluez', '/org/bluez/hci0')
    adapter_props = dbus.Interface(adapter_obj, 'org.freedesktop.DBus.Properties')
    adapter_iface = dbus.Interface(adapter_obj, 'org.bluez.Adapter1')

    adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(True))
    adapter_props.Set('org.bluez.Adapter1', 'Pairable', dbus.Boolean(True))
    adapter_props.Set('org.bluez.Adapter1', 'Discoverable', dbus.Boolean(True))
    adapter_props.Set('org.bluez.Adapter1', 'DiscoverableTimeout', dbus.UInt32(0))

    host_mac = get_host_mac(bus)
    logger.log("INFO", f"Local Bluetooth Adapter: {host_mac}")
    print(f"[*] Local Bluetooth Adapter: {host_mac}")

    # Register custom Agent for automated PIN injection
    agent = BluetoothAgent(bus, AGENT_PATH, host_mac)
    agent_mgr = dbus.Interface(bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.AgentManager1')
    try:
        agent_mgr.RegisterAgent(AGENT_PATH, "KeyboardDisplay")
        agent_mgr.RequestDefaultAgent(AGENT_PATH)
        logger.log("INFO", "Automated Zero-Prompt Pairing Agent registered with KeyboardDisplay capability.")
        print(f"[*] Automated Zero-Prompt Pairing Agent registered.")
    except Exception as e:
        try:
            agent_mgr.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
            agent_mgr.RequestDefaultAgent(AGENT_PATH)
        except Exception:
            pass
        logger.log("WARN", f"RegisterAgent notice: {e}")

    loop = GLib.MainLoop()
    stop_event = threading.Event()
    pause_event = threading.Event()
    connected = [False]
    connecting_lock = threading.Lock()
    active_connecting = set()
    active_joystick_node = [None]

    def do_connect_thread(addr, dev_path=None):
        addr_upper = addr.upper()
        if target_mac and addr_upper != target_mac:
            return

        with connecting_lock:
            if connected[0] or addr_upper in active_connecting:
                return
            active_connecting.add(addr_upper)

        logger.log("ACTION", f"Connection worker started for candidate {addr_upper}")
        print(f"\n{COLOR_GREEN}[+] GAMEPAD DETECTED: {COLOR_BOLD}{addr_upper}{COLOR_RESET}")
        print(f"{COLOR_CYAN}[*] Pausing inquiries to allocate full radio bandwidth for Paging...{COLOR_RESET}")

        # 1. PAUSE ALL INQUIRIES immediately
        pause_event.set()
        try:
            adapter_iface.StopDiscovery()
            logger.log("ACTION", "Stopped BlueZ discovery for paging window.")
        except Exception:
            pass

        # Give transceiver 300ms to exit inquiry state cleanly
        time.sleep(0.3)

        if not dev_path:
            dev_path = f"/org/bluez/hci0/dev_{addr_upper.replace(':', '_')}"

        try:
            # Poll for BlueZ device object (created from the inquiry event)
            dev_obj = None
            t_poll = time.time()
            while time.time() - t_poll < 3.0:
                try:
                    dev_obj = bus.get_object('org.bluez', dev_path)
                    d_props = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
                    _ = d_props.Get('org.bluez.Device1', 'Address')
                    break
                except Exception:
                    time.sleep(0.2)

            if not dev_obj:
                logger.log("WARN", f"Device object {dev_path} not found in BlueZ tree.")
                print(f"{COLOR_YELLOW}[!] Device {addr_upper} not yet registered in BlueZ. Resuming scan...{COLOR_RESET}")
                pause_event.clear()
                try:
                    adapter_iface.StartDiscovery()
                except Exception:
                    pass
                return

            d_props = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
            d_iface = dbus.Interface(dev_obj, 'org.bluez.Device1')

            # Mark Trusted
            try:
                d_props.Set('org.bluez.Device1', 'Trusted', dbus.Boolean(True))
                logger.log("ACTION", f"Set Trusted=True on {addr_upper}")
                print(f"{COLOR_GREEN}[+] Marked Trusted in BlueZ.{COLOR_RESET}")
            except Exception as te:
                logger.log("WARN", f"Set Trusted on {addr_upper}: {te}")

            # Connect HID profile directly (UUID 00001124) to bypass generic SDP discovery
            hid_uuid = "00001124-0000-1000-8000-00805f9b34fb"
            logger.log("ACTION", f"Calling Device1.ConnectProfile({hid_uuid}) on {addr_upper}...")
            print(f"{COLOR_CYAN}[*] Connecting HID service to {addr_upper}...{COLOR_RESET}")
            try:
                d_iface.ConnectProfile(hid_uuid, timeout=15)
                logger.log("SUCCESS", f"ConnectProfile() acknowledged for {addr_upper}")
                print(f"{COLOR_GREEN}[+] ConnectProfile() acknowledged by controller!{COLOR_RESET}")
            except Exception as e1:
                logger.log("WARN", f"ConnectProfile() notice on {addr_upper}: {e1}")
                try:
                    d_iface.Connect(timeout=10)
                except Exception:
                    pass

            # Check if Bluetooth link is active
            time.sleep(1.0)
            try:
                if d_props.Get('org.bluez.Device1', 'Connected'):
                    print(f"{COLOR_GREEN}[+] Bluetooth link active! Initializing input driver...{COLOR_RESET}")
            except Exception:
                pass

            # Poll for joystick node creation (/dev/input/js* or /dev/hidraw*) for up to 30 seconds
            sys.stdout.write(f"[*] Waiting for Linux joystick node creation...")
            sys.stdout.flush()
            t0 = time.time()
            while time.time() - t0 < 30.0:
                js_node, js_name = check_joysticks(baseline=initial_joysticks)
                if not js_node:
                    js_node, js_name = check_joysticks()
                if js_node:
                    connected[0] = True
                    active_joystick_node[0] = js_node
                    print(f"\n\n{COLOR_GREEN}=================================================================={COLOR_RESET}")
                    print(f"{COLOR_GREEN}[+] SUCCESS: CONTROLLER CONNECTED & ACTIVE!{COLOR_RESET}")
                    print(f"{COLOR_GREEN}[+] Linux Joystick Node: {COLOR_BOLD}{js_node} ({js_name}){COLOR_RESET}")
                    print(f"{COLOR_GREEN}=================================================================={COLOR_RESET}\n")
                    logger.log("SUCCESS", f"Controller connected at {js_node} ({js_name})")
                    stop_event.set()
                    GLib.idle_add(loop.quit)
                    return

                try:
                    is_conn = bool(d_props.Get('org.bluez.Device1', 'Connected'))
                except Exception:
                    is_conn = False

                if not is_conn and (time.time() - t0 > 10.0):
                    logger.log("INFO", f"Device {addr_upper} dropped link during handshake.")
                    break

                time.sleep(0.5)
                sys.stdout.write(".")
                sys.stdout.flush()

            # If still connected to host, KEEP waiting and NEVER restart radio inquiry!
            try:
                is_conn = bool(d_props.Get('org.bluez.Device1', 'Connected'))
            except Exception:
                is_conn = False

            if is_conn:
                logger.log("INFO", f"Device {addr_upper} link remains active. Continuing wait without radio disruption...")
                while not stop_event.is_set():
                    js_node, js_name = check_joysticks(baseline=initial_joysticks)
                    if not js_node:
                        js_node, js_name = check_joysticks()
                    if js_node:
                        connected[0] = True
                        active_joystick_node[0] = js_node
                        print(f"\n\n{COLOR_GREEN}=================================================================={COLOR_RESET}")
                        print(f"{COLOR_GREEN}[+] SUCCESS: CONTROLLER CONNECTED & ACTIVE!{COLOR_RESET}")
                        print(f"{COLOR_GREEN}[+] Linux Joystick Node: {COLOR_BOLD}{js_node} ({js_name}){COLOR_RESET}")
                        print(f"{COLOR_GREEN}=================================================================={COLOR_RESET}\n")
                        logger.log("SUCCESS", f"Controller connected at {js_node} ({js_name})")
                        stop_event.set()
                        GLib.idle_add(loop.quit)
                        return
                    try:
                        if not d_props.Get('org.bluez.Device1', 'Connected'):
                            break
                    except Exception:
                        break
                    time.sleep(0.5)
                    sys.stdout.write(".")
                    sys.stdout.flush()

            print(f"\n{COLOR_YELLOW}[!] Connection handshake pending. Resuming scan... (Keep holding SYNC){COLOR_RESET}")
            logger.log("INFO", f"Device {addr_upper} did not create joystick node within window. Resuming inquiry.")

            # Resume inquiries ONLY when link is no longer connected
            pause_event.clear()
            try:
                adapter_iface.StartDiscovery()
            except Exception:
                pass

        except Exception as ex:
            logger.log("ERROR", f"Exception in connection worker for {addr_upper}: {ex}")
            pause_event.clear()
            try:
                adapter_iface.StartDiscovery()
            except Exception:
                pass
        finally:
            with connecting_lock:
                active_connecting.discard(addr_upper)

    def process_device(dev_path, dev_props):
        if connected[0] or pause_event.is_set():
            return

        addr = str(dev_props.get('Address', ''))
        name = str(dev_props.get('Name', dev_props.get('Alias', '')))
        dev_class = int(dev_props.get('Class', 0))
        icon = str(dev_props.get('Icon', ''))
        uuids = [str(u) for u in dev_props.get('UUIDs', [])]
        rssi = int(dev_props.get('RSSI', 0))

        if target_mac and addr.upper() != target_mac:
            return

        status, reason = evaluate_device(addr, name, dev_class, icon, uuids, rssi)
        logger.log("DISCOVERY", f"Device: {addr} | Name: '{name}' | Class: 0x{dev_class:06X} | Status: {status} ({reason})")

        if status in ["MATCH", "PROBE"]:
            t = threading.Thread(target=do_connect_thread, args=(addr, dev_path), daemon=True)
            t.start()
        else:
            sys.stdout.write(f"\r[*] Filtered: {addr} ({name[:16]}) - {reason[:28]}   ")
            sys.stdout.flush()

    def on_liac_device(addr, dev_class):
        if connected[0] or pause_event.is_set():
            return
        addr_upper = addr.upper()
        if target_mac and addr_upper != target_mac:
            return

        if addr_upper in BLACKLIST_MACS:
            return

        status, reason = evaluate_device(addr_upper, "", dev_class, "", [], 0)
        logger.log("DISCOVERY", f"LIAC Device: {addr_upper} | Class: 0x{dev_class:06X} | Status: {status} ({reason})")

        if status in ["MATCH", "PROBE"]:
            t = threading.Thread(target=do_connect_thread, args=(addr_upper, None), daemon=True)
            t.start()

    def on_interfaces_added(path, interfaces):
        if 'org.bluez.Device1' in interfaces:
            process_device(path, interfaces['org.bluez.Device1'])

    def on_properties_changed(iface, changed_props, invalidated, path=None):
        if iface == 'org.bluez.Device1' and path:
            try:
                dev_obj = bus.get_object('org.bluez', path)
                props_iface = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
                all_props = props_iface.GetAll('org.bluez.Device1')
                process_device(path, all_props)
            except Exception:
                pass

    bus.add_signal_receiver(
        on_interfaces_added,
        dbus_interface="org.freedesktop.DBus.ObjectManager",
        signal_name="InterfacesAdded"
    )

    bus.add_signal_receiver(
        on_properties_changed,
        dbus_interface="org.freedesktop.DBus.Properties",
        signal_name="PropertiesChanged",
        path_keyword="path"
    )

    # Start BlueZ standard discovery (GIAC)
    try:
        adapter_iface.SetDiscoveryFilter(dbus.Dictionary({
            'Transport': dbus.String('bredr')
        }, signature='sv'))
        adapter_iface.StartDiscovery()
        logger.log("INFO", "SetDiscoveryFilter(Transport=bredr) and StartDiscovery() active.")
        print(f"[*] Bluetooth Classic (BR/EDR) GIAC discovery filter set.")
    except Exception as e:
        logger.log("ERROR", f"StartDiscovery error: {e}")
        print(f"[*] StartDiscovery: {e}")

    # Start background Nintendo LIAC inquiry scanner
    liac_scanner = LIACScanner(on_liac_device, stop_event, pause_event)
    liac_scanner.start()
    print(f"[*] Nintendo Dedicated LIAC (0x9E8B00) radio scanner active.")

    if target_mac:
        print(f"\n{COLOR_CYAN}[*] Target MAC Filter: {COLOR_BOLD}{target_mac}{COLOR_RESET}")

    print(f"\n{COLOR_YELLOW}[!] ACTION REQUIRED:{COLOR_RESET}")
    print(f"  1. Ensure your real Wii U console is UNPLUGGED from the wall.")
    print(f"  2. Hold controller 5-10cm from laptop.")
    print(f"  3. HOLD the RED SYNC BUTTON on the back so the 4 blue LEDs are flashing.\n")
    print(f"[*] Actively sweeping 2.4 GHz spectrum... (Ctrl+C to stop)")

    start_time = time.time()
    spinner = ['|', '/', '-', '\\']
    spinner_idx = [0]

    def heartbeat_cb():
        if connected[0]:
            return False
        if pause_event.is_set():
            return True
        elapsed = int(time.time() - start_time)
        spin = spinner[spinner_idx[0] % len(spinner)]
        spinner_idx[0] += 1
        remaining = max(0, 90 - elapsed)
        sys.stdout.write(f"\r[*] [{spin}] Sweeping GIAC + LIAC spectrum... [{remaining}s remaining]   ")
        sys.stdout.flush()
        return True

    GLib.timeout_add(500, heartbeat_cb)

    def timeout_cb():
        if not connected[0]:
            print(f"\n\n{COLOR_YELLOW}[i] Discovery timed out after 90s without detecting controller.{COLOR_RESET}")
            print(f"[*] Check the detailed debug log at: {COLOR_BOLD}{LOG_FILE_PATH}{COLOR_RESET}")
            logger.log("INFO", "Discovery timed out after 90s.")
            stop_event.set()
            loop.quit()
        return False

    GLib.timeout_add_seconds(90, timeout_cb)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n[*] Stopped by user.")
        logger.log("INFO", "Stopped by user KeyboardInterrupt.")
    finally:
        stop_event.set()
        try:
            adapter_iface.StopDiscovery()
            logger.log("INFO", "StopDiscovery() called.")
        except Exception:
            pass
        logger.close()

    if connected[0]:
        time.sleep(0.5)
        node = active_joystick_node[0]
        if not node:
            node, _ = check_joysticks()
        if node:
            print(f"\n{COLOR_GREEN}[+] JOYSTICK READY: {node}{COLOR_RESET}")
            if "hidraw" in node:
                try:
                    os.chmod(node, 0o666)
                except Exception:
                    pass
            print(f"[*] Starting live controller test...\n")
            os.system(f"{PROJECT_DIR}/test_controller {node}")

if __name__ == "__main__":
    main()
