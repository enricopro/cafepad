<p align="center">
  <img src="assets/icon-256.png" width="140" height="140" alt="CaféPad Logo" />
</p>

<h1 align="center">CaféPad</h1>
<p align="center"><b>Universal Linux Driver, C99 Library &amp; GUI Suite for Nintendo Wii U Pro Controllers</b><br/>
<i>Named in homage to Nintendo's internal Wii U hardware codename: <b>Project Café</b></i></p>

<p align="center">
  <a href="https://kernel.org"><img src="https://img.shields.io/badge/Platform-Linux-orange.svg" alt="Platform" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue.svg" alt="License" /></a>
</p>

---

## Why CaféPad?

The Nintendo Wii U Pro Controller is known for its ergonomics, symmetrical analog sticks, responsive D-Pad, and 80-hour battery life.

However, using it on modern Linux distributions presents several challenges:
1. **Hidden from standard Bluetooth scans:** Standard Bluetooth utilities search via GIAC (`0x9E8B33`). The Wii U Pro Controller broadcasts exclusively on **LIAC** (*Limited Inquiry Access Code*, `0x9E8B00`).
2. **Third-party replica issues:** Many replica and clone controllers lack Nintendo vendor IDs or SDP records, causing kernel `hid-wiimote` and BlueZ plugins to reject them.
3. **The 90-Second Sleep Timeout:** Controllers enter sleep mode after 60–90 seconds of inactivity due to an internal firmware power-saving watchdog.
4. **Missing Force Feedback & Multi-Controller LEDs:** Standard tools often lack in-game rumble (`EV_FF`) or player LED assignment.

CaféPad addresses these issues out of the box with a dedicated C userspace daemon and companion GUI.

---

## Features

* **Zero External Dongles:** Connects directly via your system's built-in Bluetooth controller (Intel, Realtek, Broadcom, Qualcomm, etc.). No USB adapters needed.
* **Universal Detection:** Discovers and pairs both genuine Nintendo controllers and third-party clones (including VID `0471` / PID `0666` and unbranded replicas) using over-the-air BlueZ discovery without hardcoded MAC addresses.
* **4-Player Local Multiplayer:** Independent worker threads for Players 1 to 4 with respective hardware LED bitmasks (`0x10`, `0x20`, `0x40`, `0x80`).
* **In-Game Force Feedback (Rumble):** Translates Linux kernel `/dev/uinput` `EV_FF` / `FF_RUMBLE` ioctls from games (Steam, Cemu, retro emulators) into physical motor vibration.
* **Desktop GUI (`cafepad-gui`):** Dark-mode interface for real-time stick calibration, button diagnostics, battery monitoring, one-click pairing, and vibration testing.
* **Low-Battery Alerts:** Desktop notifications (`notify-send`) when battery drops to $\le 1$ bar.
* **Virtual Xbox 360 Emulation:** Exposes controllers system-wide as standard `/dev/input/js*` and `/dev/input/event*` devices with zero deadzones.
* **Active Watchdog Heartbeat:** Periodic status keepalive requests (`0x15`) prevent the 90-second firmware sleep timeout.
* **Portable C99 Core:** Self-contained POSIX C99 library (`include/cafepad.h` and `src/cafepad.c`) compatible with Android NDK, RetroArch cores, and embedded platforms.

---

## How It Works

### High-Level Summary
CaféPad acts as a userspace bridge between the proprietary Nintendo Wii U Pro Bluetooth protocol and the standard Linux input subsystem:

1. **Discovery & Connection:** Scans the Limited Inquiry Access Code (**LIAC**) used by Wii U controllers in SYNC mode and establishes raw dual-channel **L2CAP sockets** directly to the hardware.
2. **Signal Decoding & Translation:** Ingests raw hardware reports, decodes 12-bit analog stick values, maps button states into standard Linux input codes, and injects them into the Linux kernel via `/dev/uinput` as a virtual Xbox 360 controller (`/dev/input/js*` and `/dev/input/event*`).
3. **Bidirectional Force Feedback (Rumble):** Intercepts `EV_FF` / `FF_RUMBLE` effects emitted by games through `/dev/uinput` and translates them into physical motor commands sent back to the controller over Bluetooth.
4. **Hardware Keepalive:** Transmits periodic status requests to prevent the controller's internal power-saving microcode from sleeping after 90 seconds.
5. **Desktop Management:** An asynchronous desktop GUI interacts with the daemon's configuration and telemetry to display real-time calibration, battery levels, and player assignments.

---

### System Architecture & Data Flow

<p align="center">
  <img src="assets/architecture.png" width="100%" alt="CaféPad System Architecture & Data Flow" />
</p>

---

### Detailed Subsystem Breakdown

#### 1. Discovery & Connection Negotiation
Standard Linux Bluetooth managers (BlueZ desktop applets, GNOME Control Center, KDE Bluedevil) search only for devices answering **GIAC** (*General Inquiry Access Code*, `0x9E8B33`). The Wii U Pro Controller deliberately broadcasts only on **LIAC** (*Limited Inquiry Access Code*, `0x9E8B00`) for a brief window when the SYNC button is pressed.
* CaféPad drives low-level BlueZ inquiry routines directly with the LIAC LAP filter to detect incoming pairing beacons instantly.
* Many third-party replica controllers lack proper Nintendo Vendor/Product IDs (VID `0x057e` / PID `0x0330`), exposing instead generic or unbranded chipsets (such as VID `0x0471` / PID `0x0666`). CaféPad inspects Bluetooth Class of Device (`0x002504` – Gamepad) and SDP service records to reliably pair both genuine Nintendo controllers and clones without manual configuration.
* Once detected, CaféPad opens two dedicated L2CAP connections: **PSM `0x11`** (HID Control) for sending commands/rumble, and **PSM `0x13`** (HID Interrupt) for high-frequency input streams.

#### 2. Input Report Decoding & Normalization
The controller transmits state packets using **Report `0x3D`** (an 11-byte continuous data stream):
* **Analog Sticks:** Stick positions are encoded as 12-bit values (range 0–4095). CaféPad normalizes these readings using pre-calibrated center baselines (`2048`) and dynamic travel limits, converting them into smooth, zero-latency floating-point values and standard Linux axis values (`ABS_X`, `ABS_Y`, `ABS_RX`, `ABS_RY`).
* **Button Layout Mapping:** Buttons are decoded from raw bitmasks. Users can select between:
  * **Xbox 360 Style (Default):** Maps buttons by *physical spatial position* (bottom button is `BTN_SOUTH` / A, right button is `BTN_EAST` / B). This matches modern PC game prompts and Steam Deck muscle memory.
  * **Nintendo Native Style:** Maps buttons by *printed label* (physical A maps to `BTN_EAST`, physical B maps to `BTN_SOUTH`).

#### 3. Virtual Input Subsystem (`/dev/uinput`)
Instead of acting merely as a translation script, CaféPad registers a virtual hardware device directly with the Linux kernel using `/dev/uinput`:
* Games interact with it as a standard native controller via `/dev/input/event*` and `/dev/input/js*`.
* Because it presents standard Xbox 360 capability bits, Steam Input, Wine, Proton, and native Linux engines immediately recognize it with zero manual mapping or configuration files required.

#### 4. Force Feedback (Rumble) Engine
To support genuine physical vibration:
* CaféPad declares `EV_FF` and `FF_RUMBLE` capabilities on the virtual uinput node.
* When a game fires an explosion or tactile feedback effect, the kernel routes the `FF_RUMBLE` request to CaféPad's force-feedback worker.
* The daemon computes the composite motor intensity and formats an output **Report `0x11`** with the appropriate motor activation flag, sending it over L2CAP PSM `0x11` to the physical controller with sub-millisecond dispatch time.

#### 5. Watchdog Keepalive & Power Management
The Wii U Pro Controller's onboard firmware features an aggressive internal sleep timer designed for the Wii U console: if no communication is received from the host within 60–90 seconds, the controller disconnects automatically.
* CaféPad's worker thread runs a dedicated asynchronous timer that periodically transmits a non-intrusive status request (**Report `0x15`**).
* This ping prevents the controller from falling asleep mid-game, preserves battery health, and allows CaféPad to continuously read back live battery level telemetry.

#### 6. Desktop GUI & Telemetry Integration
The companion desktop application (`cafepad-gui`) is built in Python/Tkinter:
* It reads configuration profiles and telemetry from `~/.config/cafepad.json`.
* It provides a 60 FPS visual diagnostic canvas displaying real-time stick deflection, button presses, battery meters, and a one-click rumble test.
* It manages user systemd autostart services without requiring manual terminal administration.

---

## Quick Start

### 1. Install (One-Step Script)
Clone the repository and run the universal installer:

```bash
git clone https://github.com/enricopro/cafepad.git
cd cafepad
./install.sh
```

### 2. Connect Your Controller
1. Turn on your controller and **press and hold the red SYNC button** on the back until the 4 blue LEDs at the bottom start flashing rapidly.
2. Run CaféPad in your terminal:
   ```bash
   cafepad
   ```
   *(Or launch the graphical interface with `cafepad-gui`)*
3. The controller vibrates, Player 1 LED locks solid blue, and your gamepad is ready system-wide.

> [!TIP]
> The controller's MAC address is automatically saved to `~/.config/cafepad.json`. On subsequent uses, simply press any button on your controller to connect in under 1 second.

---

## Desktop GUI (`cafepad-gui`)

CaféPad includes a dedicated desktop application for configuration and hardware verification:

<p align="center">
  <img src="assets/screenshot_home.png" width="48%" alt="CaféPad Dashboard" />
  <img src="assets/screenshot_diagnostics.png" width="48%" alt="Hardware Diagnostics" />
</p>
<p align="center">
  <img src="assets/screenshot_settings.png" width="48%" alt="Preferences & Mappings" />
  <img src="assets/screenshot_modal.png" width="48%" alt="Modal Confirmation" />
</p>

```bash
cafepad-gui
```

*(You can also launch it directly from application launchers like GNOME Dash or KDE Kickoff)*

### Key GUI Capabilities:
* **4-Player Hardware Cards:** View connection states, MAC addresses, and battery indicators.
* **Authentic Symmetrical Diagnostics:** 60 FPS visualizer displaying analog stick deflection in authentic Wii U top positions, triggers, and ABXY diamond.
* **One-Click Sync Wizard:** Click **"Pair Controller"** and hold the red SYNC button; the GUI automatically pairs and registers the pad to the next available player slot.
* **Haptic Rumble Testing:** One-click vibration motor test button.
* **Layout Switcher:** Instantly toggle between **Xbox 360 Mode** (standard PC gaming) and **Nintendo Native Mode** (A=A, B=B).
* **Systemd Integration:** Enable or disable background login autostart with a single click.
* **In-Window Modal Confirmations:** Dialogs for disconnecting and forgetting saved controllers.

---

## Background Service (systemd)

To have controllers connect automatically on any button press without opening a terminal:

```bash
systemctl --user enable --now cafepad
```

To view live service logs:
```bash
journalctl --user -u cafepad -f
```

---

## Controller Layout & Mapping

By default, buttons are mapped by **physical position** (Xbox 360 layout) for seamless compatibility with Steam and modern PC games:

| Wii U Pro Label | Physical Position | Linux Evdev Button | Xbox 360 Equivalent |
|:---:|:---:|:---:|:---:|
| **B** | Bottom | `BTN_SOUTH` (`0x130`) | **A** |
| **A** | Right | `BTN_EAST` (`0x131`) | **B** |
| **Y** | Left | `BTN_NORTH` (`0x133`) | **X** |
| **X** | Top | `BTN_WEST` (`0x134`) | **Y** |
| **L** / **R** | Shoulders | `BTN_TL` / `BTN_TR` | **LB** / **RB** |
| **ZL** / **ZR** | Triggers | `ABS_Z` / `ABS_RZ` | **LT** / **RT** |
| **-** / **+** | Center | `BTN_SELECT` / `BTN_START` | **Back** / **Start** |
| **HOME** | Center Guide | `BTN_MODE` (`0x13c`) | **Xbox / Guide** |
| **L3** / **R3** | Stick Clicks | `BTN_THUMBL` / `BTN_THUMBR` | **L3** / **R3** |
| **D-Pad** | Directional | `ABS_HAT0X` / `ABS_HAT0Y` | **Hat Switch** |

> [!NOTE]
> To map buttons by printed letter (A maps to A, B maps to B), use the `--nintendo-layout` flag or switch it in the GUI:
> ```bash
> cafepad --nintendo-layout
> ```

---

## CLI Reference

```text
Usage: cafepad [OPTIONS]

Options:
  -h, --help            Show help message and exit
  --target, --mac MAC   Connect directly to a specific Bluetooth MAC address
  --scan, --pair        Force inquiry scan for nearby controllers in SYNC mode
  --test-rumble         Test physical vibration motors on connected controller
  --nintendo-layout     Map buttons by printed letters (A->A) instead of Xbox positions
  --gui                 Launch CaféPad graphical desktop interface
  --status              Print configured controller slots and exit
  --daemon              Run silently in background (for systemd service)
  -v, --version         Print version information
```

---

## C API (`libcafepad`)

CaféPad includes a POSIX C99 library (`libcafepad.so` and `libcafepad.a`):

### Example Usage
Save as `example.c`:
```c
#include <stdio.h>
#include <unistd.h>
#include <cafepad.h>

int main(void) {
    /* Automatically opens saved Bluetooth controller, USB, or /dev/input/js* */
    cafepad_device_t* dev = cafepad_open();
    if (!dev) {
        printf("Controller not found. Put controller in SYNC mode and retry.\n");
        return 1;
    }

    printf("Connected! Polling inputs...\n");
    cafepad_state_t state;

    while (1) {
        if (cafepad_poll(dev, &state, 10) > 0) {
            printf("\rL-Stick: [%+0.2f, %+0.2f]  R-Stick: [%+0.2f, %+0.2f]  Btns: 0x%05X  Bat: %d  ",
                   state.left_stick.x, state.left_stick.y,
                   state.right_stick.x, state.right_stick.y,
                   state.buttons, state.battery_level);
            fflush(stdout);
        }
    }

    cafepad_close(dev);
    return 0;
}
```

### Compiling with pkg-config:
```bash
gcc example.c $(pkg-config --cflags --libs cafepad) -o example
./example
```

---

## Portability & Embedded Platforms

CaféPad is designed to be portable beyond traditional desktop Linux:
* **Self-Contained C99 Implementation:** [`src/cafepad.c`](src/cafepad.c) and [`include/cafepad.h`](include/cafepad.h) have no dependencies on Python or desktop runtimes.
* **Android NDK Compatibility:** The packet parser and L2CAP sequencing compile cleanly under Android's Bionic libc / NDK, making it embeddable into Android TV, Google TV native apps, or RetroArch input drivers.
* **USB & Bluetooth Dual Engine:** Supports both wireless Bluetooth L2CAP and wired USB clone protocols (`0471:0666`).

---

## Backwards Compatibility

For existing scripts or build workflows configured for `wiiupro`:
* The executable command `wiiupro` is symlinked to `cafepad`.
* The header `<wiiupro.h>` automatically includes `<cafepad.h>` and provides aliases for all types and constants.
* `libwiiupro.so`, `libwiiupro.a`, and `wiiupro.pc` are provided out of the box.

---

## Uninstallation

To cleanly remove udev rules, binaries, libraries, and desktop entries:

```bash
./uninstall.sh
```

---

## License

Distributed under the **GNU General Public License v3.0** (GPL-3.0). See [LICENSE](LICENSE) for the full text.
