#!/usr/bin/env bash
# ====================================================================
#   CaféPad — Universal Linux Installer
#   One-step setup for Zero-Dongle Bluetooth, Virtual Gamepads & GUI
# ====================================================================

set -e

COLOR_GREEN="\033[92m"
COLOR_YELLOW="\033[93m"
COLOR_CYAN="\033[96m"
COLOR_BOLD="\033[1m"
COLOR_RESET="\033[0m"

echo -e "${COLOR_CYAN}==================================================================${COLOR_RESET}"
echo -e "${COLOR_CYAN}${COLOR_BOLD}  CaféPad — Linux Universal Installer (Project Café)${COLOR_RESET}"
echo -e "${COLOR_CYAN}==================================================================${COLOR_RESET}"
echo

# Helper for elevated commands
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "${COLOR_YELLOW}[!] Please run as root or install sudo.${COLOR_RESET}"
        exit 1
    fi
fi

# Detect Package Manager & Check Build Dependencies
echo -e "[*] Checking system dependencies..."

MISSING_DEPS=()

if ! command -v python3 >/dev/null 2>&1; then
    MISSING_DEPS+=("python3")
fi
if ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
    MISSING_DEPS+=("gcc")
fi
if ! command -v make >/dev/null 2>&1; then
    MISSING_DEPS+=("make")
fi

# Check for BlueZ development header
if [ ! -f /usr/include/bluetooth/bluetooth.h ]; then
    if [ -f /etc/debian_version ] || command -v apt-get >/dev/null 2>&1; then
        MISSING_DEPS+=("libbluetooth-dev")
    elif [ -f /etc/fedora-release ] || [ -f /etc/redhat-release ] || command -v dnf >/dev/null 2>&1; then
        MISSING_DEPS+=("bluez-libs-devel")
    elif [ -f /etc/arch-release ] || command -v pacman >/dev/null 2>&1; then
        MISSING_DEPS+=("bluez-libs")
    elif command -v zypper >/dev/null 2>&1; then
        MISSING_DEPS+=("bluez-devel")
    else
        MISSING_DEPS+=("bluez-development-headers")
    fi
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${COLOR_YELLOW}[!] Missing required packages: ${MISSING_DEPS[*]}${COLOR_RESET}"
    echo -e "    Please install them using your package manager:"
    if command -v apt-get >/dev/null 2>&1; then
        echo -e "    ${COLOR_BOLD}sudo apt update && sudo apt install -y python3 build-essential libbluetooth-dev python3-tk${COLOR_RESET}"
    elif command -v dnf >/dev/null 2>&1; then
        echo -e "    ${COLOR_BOLD}sudo dnf install -y python3 gcc make bluez-libs-devel python3-tkinter${COLOR_RESET}"
    elif command -v pacman >/dev/null 2>&1; then
        echo -e "    ${COLOR_BOLD}sudo pacman -S --needed python gcc make bluez-libs tk${COLOR_RESET}"
    fi
    echo
    exit 1
fi

echo -e "${COLOR_GREEN}[✓] All core dependencies satisfied.${COLOR_RESET}"

# Build C Libraries
echo -e "\n[*] Building libcafepad C library and tools..."
make clean >/dev/null 2>&1 || true
make

# Install C Library & Headers & pkg-config
echo -e "\n[*] Installing C library to /usr/local/lib and headers to /usr/local/include..."
$SUDO make install

# Install Udev Rules for Zero-Sudo Access
echo -e "\n[*] Installing udev rules for zero-sudo controller & virtual gamepad access..."
$SUDO install -m 644 udev/99-cafepad.rules /etc/udev/rules.d/99-cafepad.rules
$SUDO ln -sf /etc/udev/rules.d/99-cafepad.rules /etc/udev/rules.d/99-wiiupro.rules

# Reload udev
echo -e "[*] Reloading udev rules..."
$SUDO udevadm control --reload-rules || true
$SUDO udevadm trigger /dev/uinput 2>/dev/null || true

# Grant current user immediate access to /dev/uinput without reboot/logout
ACTUAL_USER="${SUDO_USER:-$USER}"
if [ -n "$ACTUAL_USER" ] && [ -e /dev/uinput ]; then
    if command -v setfacl >/dev/null 2>&1; then
        $SUDO setfacl -m u:"$ACTUAL_USER":rw /dev/uinput 2>/dev/null || true
    else
        $SUDO chmod 666 /dev/uinput 2>/dev/null || true
    fi
fi

# Install cafepad CLI and GUI wrappers
echo -e "\n[*] Installing CLI and GUI binaries to /usr/local/bin/..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
$SUDO ln -sf "$SCRIPT_DIR/cafepad.py" /usr/local/bin/cafepad
$SUDO ln -sf "$SCRIPT_DIR/cafepad_gui.py" /usr/local/bin/cafepad-gui
$SUDO ln -sf "$SCRIPT_DIR/cafepad.py" /usr/local/bin/wiiupro

# Install application icon & desktop entry
echo -e "[*] Installing application icons and desktop shortcut..."
for sz in 16 32 48 64 128 256 512; do
    if [ -f "$SCRIPT_DIR/assets/icon-${sz}.png" ]; then
        if [ -d /usr/share/icons/hicolor ]; then
            $SUDO mkdir -p "/usr/share/icons/hicolor/${sz}x${sz}/apps"
            $SUDO install -m 644 "$SCRIPT_DIR/assets/icon-${sz}.png" "/usr/share/icons/hicolor/${sz}x${sz}/apps/cafepad.png" 2>/dev/null || true
        fi
        if [ -n "$TARGET_HOME" ]; then
            mkdir -p "$TARGET_HOME/.local/share/icons/hicolor/${sz}x${sz}/apps"
            cp "$SCRIPT_DIR/assets/icon-${sz}.png" "$TARGET_HOME/.local/share/icons/hicolor/${sz}x${sz}/apps/cafepad.png" 2>/dev/null || true
        fi
    fi
done
$SUDO gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true

if [ -d /usr/share/applications ]; then
    $SUDO install -m 644 "$SCRIPT_DIR/cafepad.desktop" /usr/share/applications/cafepad.desktop 2>/dev/null || true
fi

# Install GUI shared assets
echo -e "[*] Installing GUI assets to /usr/local/share/cafepad/assets..."
$SUDO mkdir -p /usr/local/share/cafepad/assets
$SUDO cp -r "$SCRIPT_DIR/assets/"* /usr/local/share/cafepad/assets/ 2>/dev/null || true

# Install systemd user service template
TARGET_HOME="$HOME"
if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    TARGET_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
fi

if [ -n "$TARGET_HOME" ] && [ -d "$TARGET_HOME" ]; then
    USER_SYSTEMD_DIR="$TARGET_HOME/.config/systemd/user"
    mkdir -p "$USER_SYSTEMD_DIR"
    cp "$SCRIPT_DIR/systemd/cafepad.service" "$USER_SYSTEMD_DIR/cafepad.service"
    ln -sf "$USER_SYSTEMD_DIR/cafepad.service" "$USER_SYSTEMD_DIR/wiiupro.service"
    if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
        chown -R "$SUDO_USER":"$SUDO_USER" "$TARGET_HOME/.config/systemd" 2>/dev/null || true
    fi
    echo -e "[*] Installed systemd user service to $USER_SYSTEMD_DIR/cafepad.service"
fi

echo
echo -e "${COLOR_GREEN}==================================================================${COLOR_RESET}"
echo -e "${COLOR_GREEN}${COLOR_BOLD}  CAFÉPAD INSTALLATION COMPLETE!${COLOR_RESET}"
echo -e "${COLOR_GREEN}==================================================================${COLOR_RESET}"
echo
echo -e "${COLOR_BOLD}How to use:${COLOR_RESET}"
echo -e "  1. Turn on your Wii U Pro Controller and hold the ${COLOR_YELLOW}RED SYNC BUTTON${COLOR_RESET}."
echo -e "  2. In your terminal, run:"
echo -e "     ${COLOR_CYAN}${COLOR_BOLD}cafepad${COLOR_RESET}        (or launch the GUI with ${COLOR_CYAN}${COLOR_BOLD}cafepad-gui${COLOR_RESET})"
echo
echo -e "  Your controller will vibrate, the Player 1 LED will lock solid blue,"
echo -e "  and an Xbox 360 controller will appear system-wide for Steam, Cemu, Dolphin, etc."
echo
echo -e "${COLOR_BOLD}Optional — Run automatically in the background on login:${COLOR_RESET}"
echo -e "  ${COLOR_CYAN}systemctl --user enable --now cafepad${COLOR_RESET}"
echo
echo -e "${COLOR_BOLD}For C/C++ Developers:${COLOR_RESET}"
echo -e "  Headers:    #include <cafepad.h>  (or <wiiupro.h>)"
echo -e "  pkg-config: \$(pkg-config --cflags --libs cafepad)"
echo -e "${COLOR_GREEN}==================================================================${COLOR_RESET}"
