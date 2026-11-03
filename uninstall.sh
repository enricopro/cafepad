#!/usr/bin/env bash
# ====================================================================
#   CaféPad — Universal Linux Uninstaller
# ====================================================================

set -e

COLOR_GREEN="\033[92m"
COLOR_YELLOW="\033[93m"
COLOR_CYAN="\033[96m"
COLOR_BOLD="\033[1m"
COLOR_RESET="\033[0m"

echo -e "${COLOR_CYAN}==================================================================${COLOR_RESET}"
echo -e "${COLOR_CYAN}${COLOR_BOLD}  CaféPad — Uninstaller${COLOR_RESET}"
echo -e "${COLOR_CYAN}==================================================================${COLOR_RESET}"
echo

SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "${COLOR_YELLOW}[!] Please run as root or install sudo.${COLOR_RESET}"
        exit 1
    fi
fi

# 1. Stop and disable systemd service if active
TARGET_HOME="$HOME"
if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    TARGET_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
fi

if command -v systemctl >/dev/null 2>&1; then
    echo -e "[*] Disabling systemd user service..."
    if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
        sudo -u "$SUDO_USER" systemctl --user disable --now cafepad 2>/dev/null || true
        sudo -u "$SUDO_USER" systemctl --user disable --now wiiupro 2>/dev/null || true
    else
        systemctl --user disable --now cafepad 2>/dev/null || true
        systemctl --user disable --now wiiupro 2>/dev/null || true
    fi
fi
if [ -n "$TARGET_HOME" ]; then
    rm -f "$TARGET_HOME/.config/systemd/user/cafepad.service"
    rm -f "$TARGET_HOME/.config/systemd/user/wiiupro.service"
fi

# 2. Remove CLI & GUI binaries
echo -e "[*] Removing /usr/local/bin/cafepad and cafepad-gui..."
$SUDO rm -f /usr/local/bin/cafepad /usr/local/bin/cafepad-gui /usr/local/bin/wiiupro

# 3. Remove desktop entry & shared assets
$SUDO rm -f /usr/share/applications/cafepad.desktop
$SUDO rm -rf /usr/local/share/cafepad

# 4. Remove udev rules
echo -e "[*] Removing udev rules..."
$SUDO rm -f /etc/udev/rules.d/99-cafepad.rules /etc/udev/rules.d/99-wiiupro.rules
$SUDO udevadm control --reload-rules 2>/dev/null || true
$SUDO udevadm trigger 2>/dev/null || true

# 5. Remove C library
echo -e "[*] Removing C library and headers..."
$SUDO make uninstall 2>/dev/null || true

echo
echo -e "${COLOR_GREEN}[✓] CaféPad suite has been cleanly uninstalled.${COLOR_RESET}"
