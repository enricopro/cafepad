#!/usr/bin/env python3
"""
Direct L2CAP Connection Suite for Wii U Pro Controllers.
Bypasses BlueZ D-Bus service-discovery crashes completely by connecting
directly to L2CAP PSM 0x11 (HID Control) and PSM 0x13 (HID Interrupt),
exactly like Dolphin Emulator.

Features:
1. Low-latency direct L2CAP packet polling with solid blue LED locking.
2. Built-in Local Web Flight Game & Diagnostic Arena (http://localhost:8080).
3. Automatic uinput virtual gamepad bridge (/dev/input/js*) when available.
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
import http.server

COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_BOLD = "\033[1m"
COLOR_RESET = "\033[0m"

PSM_HID_CNTL = 0x0011
PSM_HID_INTR = 0x0013

# Linux Input Event Constants
EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

SYN_REPORT = 0x00

ABS_X = 0x00
ABS_Y = 0x01
ABS_Z = 0x02       # Left Trigger (ZL)
ABS_RX = 0x03      # Right Stick X
ABS_RY = 0x04      # Right Stick Y
ABS_RZ = 0x05      # Right Trigger (ZR)
ABS_HAT0X = 0x10   # D-Pad X
ABS_HAT0Y = 0x11   # D-Pad Y

BTN_SOUTH = 0x130   # Bottom button (Xbox A, B0)
BTN_EAST  = 0x131   # Right button  (Xbox B, B1)
BTN_NORTH = 0x133   # Left button   (Xbox X, B2, in Linux BTN_NORTH is BTN_X)
BTN_WEST  = 0x134   # Top button    (Xbox Y, B3, in Linux BTN_WEST is BTN_Y)
BTN_TL = 0x136      # L
BTN_TR = 0x137      # R
BTN_TL2 = 0x138     # ZL
BTN_TR2 = 0x139     # ZR
BTN_SELECT = 0x13a  # -
BTN_START = 0x13b   # +
BTN_MODE = 0x13c    # HOME
BTN_THUMBL = 0x13d  # L3
BTN_THUMBR = 0x13e  # R3
BTN_DPAD_UP = 0x220
BTN_DPAD_DOWN = 0x221
BTN_DPAD_LEFT = 0x222
BTN_DPAD_RIGHT = 0x223

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_SET_ABSBIT = 0x40045567
UI_DEV_SETUP = 0x405c5503
UI_ABS_SETUP = 0x401c5504
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502

def normalize_stick(raw):
    val = (raw - 2048.0) / 1024.0
    if val < -1.0: val = -1.0
    if val > 1.0: val = 1.0
    if abs(val) < 0.05: val = 0.0
    return val

def parse_buttons(b8, b9, b10):
    btns = []
    # Byte 8 (active low)
    if not (b8 & (1 << 7)): btns.append("RIGHT")
    if not (b8 & (1 << 6)): btns.append("DOWN")
    if not (b8 & (1 << 5)): btns.append("L")
    if not (b8 & (1 << 4)): btns.append("-")
    if not (b8 & (1 << 3)): btns.append("HOME")
    if not (b8 & (1 << 2)): btns.append("+")
    if not (b8 & (1 << 1)): btns.append("R")

    # Byte 9 (active low)
    if not (b9 & (1 << 7)): btns.append("ZL")
    if not (b9 & (1 << 6)): btns.append("B")
    if not (b9 & (1 << 5)): btns.append("Y")
    if not (b9 & (1 << 4)): btns.append("A")
    if not (b9 & (1 << 3)): btns.append("X")
    if not (b9 & (1 << 2)): btns.append("ZR")
    if not (b9 & (1 << 1)): btns.append("LEFT")
    if not (b9 & (1 << 0)): btns.append("UP")

    # Byte 10 (active low)
    if not (b10 & (1 << 1)): btns.append("L3")
    if not (b10 & (1 << 0)): btns.append("R3")

    return btns

# ====================================================================
# SSE Web Server for Browser Testing & Playable Mini-Game
# ====================================================================
class SSEManager:
    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()

    def add(self, q):
        with self.lock:
            self.clients.append(q)

    def remove(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def broadcast(self, data):
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass

sse_manager = SSEManager()

class WebHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path.startswith('/index.html'):
            html_path = os.path.join(os.path.dirname(__file__), "web_game", "index.html")
            try:
                with open(html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, str(e))
        elif self.path == '/events':
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = queue.Queue(maxsize=10)
            sse_manager.add(q)
            try:
                while True:
                    data = q.get()
                    msg = f"data: {json.dumps(data)}\n\n".encode('utf-8')
                    self.wfile.write(msg)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                sse_manager.remove(q)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass

def start_web_server(port=8080):
    try:
        server = http.server.ThreadingHTTPServer(('0.0.0.0', port), WebHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return port
    except Exception:
        try:
            server = http.server.ThreadingHTTPServer(('0.0.0.0', port + 1), WebHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            return port + 1
        except Exception:
            return None

# ====================================================================
# Standard Xbox 360 Virtual Gamepad Bridge (/dev/uinput)
# Presents as a standard Xbox 360 controller so Chrome, Steam, and 
# Gamepad Tester map every button, stick, and trigger 1:1 natively.
# ====================================================================
class UInputBridge:
    def __init__(self, nintendo_layout=False):
        self.fd = None
        self.active = False
        self.nintendo_layout = nintendo_layout

        try:
            self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_SYN)

            # Register the exact 11 standard buttons (matching Linux xpad.c)
            # This aligns button indices 0..10 with W3C / Chromium MapperXInputStyleGamepad:
            # 0:BTN_SOUTH, 1:BTN_EAST, 2:BTN_NORTH, 3:BTN_WEST, 4:BTN_TL, 5:BTN_TR,
            # 6:BTN_SELECT (-), 7:BTN_START (+), 8:BTN_MODE (HOME), 9:BTN_THUMBL (L3), 10:BTN_THUMBR (R3)
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

            # Present as standard Microsoft Xbox 360 controller (Universal Standard Gamepad ID)
            name = b"Microsoft X-Box 360 pad"
            dev_setup = struct.pack('HHHH80sI', 0x03, 0x045E, 0x028E, 1, name.ljust(80, b'\x00'), 0)
            fcntl.ioctl(self.fd, UI_DEV_SETUP, dev_setup)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
            self.active = True
        except Exception:
            if self.fd is not None:
                try: os.close(self.fd)
                except Exception: pass
                self.fd = None
            self.active = False

    def emit(self, lx, ly, rx, ry, btns):
        if not self.active or self.fd is None: return
        now = time.time()
        sec = int(now)
        usec = int((now - sec) * 1_000_000)

        # Trigger analog values
        zl_val = 255 if "ZL" in btns else 0
        zr_val = 255 if "ZR" in btns else 0

        # D-Pad hat values
        hat_x = 0
        if "LEFT" in btns: hat_x -= 1
        if "RIGHT" in btns: hat_x += 1

        hat_y = 0
        if "UP" in btns: hat_y -= 1
        if "DOWN" in btns: hat_y += 1

        # Button layout mapping
        if self.nintendo_layout:
            # Letter-name matching (Nintendo A -> Xbox A, etc.)
            btn_bottom = "A" in btns
            btn_right  = "B" in btns
            btn_left   = "X" in btns
            btn_top    = "Y" in btns
        else:
            # Physical position matching (Bottom -> Bottom/A, Right -> Right/B, Left -> Left/X, Top -> Top/Y)
            btn_bottom = "B" in btns
            btn_right  = "A" in btns
            btn_left   = "Y" in btns
            btn_top    = "X" in btns

        evs = [
            # Sticks
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_X, int(lx * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_Y, int(ly * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_RX, int(rx * 32767)),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_RY, int(ry * 32767)),
            # Triggers as axes
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_Z, zl_val),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_RZ, zr_val),
            # D-Pad as hat
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_HAT0X, hat_x),
            struct.pack('qqHHi', sec, usec, EV_ABS, ABS_HAT0Y, hat_y),
            # Buttons (B0=Bottom, B1=Right, B2=Left, B3=Top)
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_SOUTH, 1 if btn_bottom else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_EAST,  1 if btn_right  else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_NORTH, 1 if btn_left   else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_WEST,  1 if btn_top    else 0),
            # Shoulders (B4=LB, B5=RB)
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_TL, 1 if "L" in btns else 0),
            struct.pack('qqHHi', sec, usec, EV_KEY, BTN_TR, 1 if "R" in btns else 0),
            # Core buttons in strict xpad order: B6=SELECT (-), B7=START (+), B8=MODE (HOME), B9=L3, B10=R3
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
# Main Connection Loop
# ====================================================================
def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: ./tools/direct_connect.py [--target MAC_ADDRESS]")
        print("Default target: 40:F4:07:CD:23:4C")
        return 0

    target_mac = "40:F4:07:CD:23:4C"
    if len(sys.argv) >= 3 and sys.argv[1] == "--target":
        target_mac = sys.argv[2].upper()
    elif len(sys.argv) >= 2 and not sys.argv[1].startswith("-"):
        target_mac = sys.argv[1].upper()

    print("==================================================================")
    print("   Wii U Pro Controller Direct L2CAP Connection Engine            ")
    print("==================================================================")
    print(f"[*] Target Gamepad: {COLOR_BOLD}{target_mac}{COLOR_RESET}")

    # 1. Start Local Web Server
    web_port = start_web_server(8080)
    if web_port:
        print(f"[*] Built-in Web Arena Server: {COLOR_CYAN}http://localhost:{web_port}{COLOR_RESET}")

    # 2. Setup uinput Virtual Gamepad
    nintendo_layout = "--nintendo-layout" in sys.argv
    uinput = UInputBridge(nintendo_layout=nintendo_layout)
    if uinput.active:
        layout_name = "Nintendo Letters (A->A, B->B)" if nintendo_layout else "Physical Position Match (Bottom->A, Right->B)"
        print(f"{COLOR_GREEN}[+] Linux /dev/input/js* Virtual Gamepad bridge ACTIVE!{COLOR_RESET}")
        print(f"    Profile: Standard Xbox 360 Controller ({layout_name})")
        print(f"    (HardwareTester, Slow Roads & Steam will map every button & axis 1:1 natively)")
    else:
        print(f"[*] Virtual /dev/input/js* bridge: Standby (run with sudo to activate for external games)")

    print()
    print("[!] ACTION REQUIRED:")
    print("  1. HOLD the RED SYNC BUTTON on the controller so the 4 LEDs flash.")
    print()

    s_ctrl = None
    s_intr = None
    t0 = time.time()
    spinner = ['|', '/', '-', '\\']
    sp_i = 0

    while time.time() - t0 < 60:
        sp = spinner[sp_i % len(spinner)]
        sp_i += 1
        sys.stdout.write(f"\r[*] [{sp}] Paging {target_mac} on PSM 0x11... (Keep holding SYNC)   ")
        sys.stdout.flush()

        try:
            s_ctrl = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
            s_ctrl.settimeout(2.0)
            s_ctrl.connect((target_mac, PSM_HID_CNTL))
            break
        except Exception:
            if s_ctrl:
                s_ctrl.close()
                s_ctrl = None
            time.sleep(0.5)

    if not s_ctrl:
        print(f"\n{COLOR_YELLOW}[-] Timed out connecting to {target_mac}. Ensure LEDs are blinking.{COLOR_RESET}")
        return 1

    print(f"\n{COLOR_GREEN}[+] L2CAP Control channel connected!{COLOR_RESET}")
    print(f"[*] Connecting L2CAP Interrupt channel to {target_mac} (PSM 0x13)...")

    try:
        s_intr = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        s_intr.settimeout(3.0)
        s_intr.connect((target_mac, PSM_HID_INTR))
        print(f"{COLOR_GREEN}[+] L2CAP Interrupt channel connected!{COLOR_RESET}")
    except Exception as e:
        print(f"{COLOR_YELLOW}[-] Failed to connect Interrupt channel: {e}{COLOR_RESET}")
        s_ctrl.close()
        return 1

    print(f"[*] Initializing gamepad microcode...")
    # Set Player 1 LED solid blue
    s_intr.send(b"\xa2\x11\x10")
    time.sleep(0.05)

    # Init extension registers
    s_intr.send(b"\xa2\x16\x04\xa4\x00\xf0\x01\x55")
    time.sleep(0.05)
    s_intr.send(b"\xa2\x16\x04\xa4\x00\xfb\x01\x00")
    time.sleep(0.05)

    # Set continuous reporting mode 0x3D
    s_intr.send(b"\xa2\x12\x00\x3d")
    time.sleep(0.05)

    print(f"\n{COLOR_GREEN}=================================================================={COLOR_RESET}")
    print(f"{COLOR_GREEN}[+] SUCCESS: CONTROLLER ONLINE & LINK LOCKED!{COLOR_RESET}")
    print(f"{COLOR_GREEN}[+] Player 1 LED active (Solid Blue). Continuous DRM 0x3D active.{COLOR_RESET}")
    if web_port:
        print(f"{COLOR_CYAN}[+] PLAY / TEST THE FEELING IN BROWSER:{COLOR_RESET}")
        print(f"    Open: {COLOR_BOLD}http://localhost:{web_port}{COLOR_RESET}")
    print(f"{COLOR_GREEN}=================================================================={COLOR_RESET}\n")

    s_intr.setblocking(False)
    s_ctrl.setblocking(False)

    last_keepalive = time.time()
    last_packet_time = time.time()
    deadman_active = False

    try:
        while True:
            now = time.time()

            # 1. Periodic Keepalive Heartbeat (every 3.5 seconds)
            # Prevents controller microcode sleep watchdog from timing out during gameplay
            if now - last_keepalive >= 3.5:
                try:
                    s_intr.send(b"\xa2\x15\x00")
                except Exception:
                    pass
                last_keepalive = now

            # 2. Watchdog Recovery: If no packet received for > 1.5 seconds, re-kick continuous mode
            if now - last_packet_time >= 1.5:
                try:
                    s_intr.send(b"\xa2\x12\x00\x3d")
                except Exception:
                    pass

            # 3. Dead-man Failsafe: If no packet received for > 3.0 seconds, zero out inputs
            # Prevents in-game car or player from getting stuck driving or shooting into a wall
            if now - last_packet_time >= 3.0 and not deadman_active:
                uinput.emit(0.0, 0.0, 0.0, 0.0, [])
                sse_manager.broadcast({
                    "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0,
                    "btns": [], "bat": 0
                })
                deadman_active = True

            # 4. Drain any pending packets on Control channel (s_ctrl)
            try:
                while True:
                    cdata = s_ctrl.recv(64)
                    if not cdata:
                        break
            except (BlockingIOError, socket.error):
                pass

            # 5. Wait for Interrupt packets (up to 40ms)
            r, _, _ = select.select([s_intr], [], [], 0.04)
            if not r:
                continue

            try:
                data = s_intr.recv(64)
            except (BlockingIOError, socket.error):
                continue

            if not data:
                print("\n[-] Controller disconnected.")
                uinput.emit(0.0, 0.0, 0.0, 0.0, [])
                break

            last_packet_time = time.time()
            deadman_active = False

            if len(data) >= 13 and data[0] == 0xa1 and data[1] == 0x3d:
                ext = data[2:]
                lx_raw = ext[0] | ((ext[1] & 0x0f) << 8)
                rx_raw = ext[2] | ((ext[3] & 0x0f) << 8)
                ly_raw = ext[4] | ((ext[5] & 0x0f) << 8)
                ry_raw = ext[6] | ((ext[7] & 0x0f) << 8)

                lx = normalize_stick(lx_raw)
                rx = normalize_stick(rx_raw)
                # Standard joystick: Up is negative (-1.0), Down is positive (+1.0)
                ly = -normalize_stick(ly_raw)
                ry = -normalize_stick(ry_raw)

                b8, b9, b10 = ext[8], ext[9], ext[10]
                bat = (b10 >> 4) & 0x07
                btn_list = parse_buttons(b8, b9, b10)
                btn_str = " ".join(btn_list)

                # 1. Update terminal
                sys.stdout.write(f"\rL-Stick: [{lx:+0.2f}, {ly:+0.2f}]  R-Stick: [{rx:+0.2f}, {ry:+0.2f}]  Bat: {bat}  Btns: [{btn_str}]               ")
                sys.stdout.flush()

                # 2. Broadcast to web browser game & diagnostic arena
                sse_manager.broadcast({
                    "lx": round(lx, 3),
                    "ly": round(ly, 3),
                    "rx": round(rx, 3),
                    "ry": round(ry, 3),
                    "btns": btn_list,
                    "bat": bat
                })

                # 3. Emit to Linux uinput virtual gamepad
                uinput.emit(lx, ly, rx, ry, btn_list)

            elif len(data) >= 4 and data[0] == 0xa1 and data[1] == 0x20:
                # Status report response to keepalive (Report 0x20)
                pass

    except KeyboardInterrupt:
        print("\n\n[*] Stopped by user.")
    finally:
        uinput.close()
        if s_intr: s_intr.close()
        if s_ctrl: s_ctrl.close()

if __name__ == "__main__":
    main()
