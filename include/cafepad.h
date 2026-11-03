/*
 * ============================================================================
 *   CaféPad — Universal C Library for Nintendo Wii U Pro Controllers
 *   Zero-Dongle Native Bluetooth & USB Engine for Genuine & Replica Pads
 * ============================================================================
 */

#ifndef CAFEPAD_H
#define CAFEPAD_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* USB Identifiers */
#define CAFEPAD_USB_CLONE_VID     0x0471
#define CAFEPAD_USB_CLONE_PID     0x0666
#define CAFEPAD_OFFICIAL_VID      0x057E
#define CAFEPAD_OFFICIAL_PID      0x0330

/* Button Bitmask Flags */
#define CAFEPAD_BTN_A             (1U << 0)
#define CAFEPAD_BTN_B             (1U << 1)
#define CAFEPAD_BTN_X             (1U << 2)
#define CAFEPAD_BTN_Y             (1U << 3)
#define CAFEPAD_BTN_DPAD_UP       (1U << 4)
#define CAFEPAD_BTN_DPAD_DOWN     (1U << 5)
#define CAFEPAD_BTN_DPAD_LEFT     (1U << 6)
#define CAFEPAD_BTN_DPAD_RIGHT    (1U << 7)
#define CAFEPAD_BTN_L             (1U << 8)
#define CAFEPAD_BTN_R             (1U << 9)
#define CAFEPAD_BTN_ZL            (1U << 10)
#define CAFEPAD_BTN_ZR            (1U << 11)
#define CAFEPAD_BTN_PLUS          (1U << 12)
#define CAFEPAD_BTN_MINUS         (1U << 13)
#define CAFEPAD_BTN_HOME          (1U << 14)
#define CAFEPAD_BTN_L3            (1U << 15)
#define CAFEPAD_BTN_R3            (1U << 16)

/* Player LED Bitmasks */
#define CAFEPAD_LED_P1            0x10
#define CAFEPAD_LED_P2            0x20
#define CAFEPAD_LED_P3            0x40
#define CAFEPAD_LED_P4            0x80

/* Analog Stick Data Structure */
typedef struct {
    int16_t raw_x;     /* Raw stick value (0 - 4095, center ~2048) */
    int16_t raw_y;
    float x;           /* Normalized [-1.0f, +1.0f], right positive / left negative */
    float y;           /* Normalized [-1.0f, +1.0f], down positive / up negative */
} cafepad_stick_t;

/* Controller State Structure */
typedef struct {
    cafepad_stick_t left_stick;
    cafepad_stick_t right_stick;
    uint32_t buttons;      /* Bitmask of CAFEPAD_BTN_* */
    uint8_t battery_level; /* 0 to 4 (4 = full) */
    bool is_charging;
    bool is_wired;
    uint64_t timestamp_us;
} cafepad_state_t;

/* Opaque controller device handle */
typedef struct cafepad_device cafepad_device_t;

/**
 * Initialize library subsystems.
 * @return 0 on success, negative on error.
 */
int cafepad_init(void);

/**
 * Scan for nearby Wii U Pro Controllers in Bluetooth SYNC mode.
 * @param out_mac Destination buffer for the controller's MAC address ("XX:XX:XX:XX:XX:XX").
 * @param mac_size Size of out_mac buffer (minimum 18 bytes).
 * @param timeout_sec Inquiry timeout in seconds (typically 3-5).
 * @return 0 on success, negative on error or timeout.
 */
int cafepad_scan(char* out_mac, size_t mac_size, int timeout_sec);

/**
 * Open the first detected Wii U Pro Controller (clone or official).
 * @return Device handle or NULL if not found or cannot open.
 */
cafepad_device_t* cafepad_open(void);

/**
 * Open a specific device by system path or MAC address.
 * @param path System device path (e.g., "/dev/hidraw1") or MAC address.
 * @return Device handle or NULL.
 */
cafepad_device_t* cafepad_open_path(const char* path);

/**
 * Read the current controller state.
 * @param dev Controller handle.
 * @param state Pointer to state structure to fill.
 * @param timeout_ms Timeout in milliseconds (0 for non-blocking, negative for infinite).
 * @return 1 if new state read, 0 on timeout, negative on error or disconnect.
 */
int cafepad_poll(cafepad_device_t* dev, cafepad_state_t* state, int timeout_ms);

/**
 * Parse a raw 64-byte HID input report buffer into state.
 */
int cafepad_parse_report(const uint8_t* report, size_t length, cafepad_state_t* state);

/**
 * Send rumble command to controller.
 * @param dev Controller handle.
 * @param enabled True to enable rumble, false to stop.
 * @return 0 on success, negative on error.
 */
int cafepad_set_rumble(cafepad_device_t* dev, bool enabled);

/**
 * Set Player LED indicator (1 to 4).
 * @param dev Controller handle.
 * @param player_id Player index (0-3 for P1-P4).
 * @return 0 on success, negative on error.
 */
int cafepad_set_player_led(cafepad_device_t* dev, int player_id);

/**
 * Close device handle and release resources.
 */
void cafepad_close(cafepad_device_t* dev);

/**
 * Deinitialize library.
 */
void cafepad_exit(void);

/* ============================================================================
 *   Backwards-Compatibility Aliases (wiiupro -> cafepad)
 * ============================================================================
 */
#define WIIUPRO_USB_CLONE_VID     CAFEPAD_USB_CLONE_VID
#define WIIUPRO_USB_CLONE_PID     CAFEPAD_USB_CLONE_PID
#define WIIUPRO_OFFICIAL_VID      CAFEPAD_OFFICIAL_VID
#define WIIUPRO_OFFICIAL_PID      CAFEPAD_OFFICIAL_PID

#define WIIUPRO_BTN_A             CAFEPAD_BTN_A
#define WIIUPRO_BTN_B             CAFEPAD_BTN_B
#define WIIUPRO_BTN_X             CAFEPAD_BTN_X
#define WIIUPRO_BTN_Y             CAFEPAD_BTN_Y
#define WIIUPRO_BTN_DPAD_UP       CAFEPAD_BTN_DPAD_UP
#define WIIUPRO_BTN_DPAD_DOWN     CAFEPAD_BTN_DPAD_DOWN
#define WIIUPRO_BTN_DPAD_LEFT     CAFEPAD_BTN_DPAD_LEFT
#define WIIUPRO_BTN_DPAD_RIGHT    CAFEPAD_BTN_DPAD_RIGHT
#define WIIUPRO_BTN_L             CAFEPAD_BTN_L
#define WIIUPRO_BTN_R             CAFEPAD_BTN_R
#define WIIUPRO_BTN_ZL            CAFEPAD_BTN_ZL
#define WIIUPRO_BTN_ZR            CAFEPAD_BTN_ZR
#define WIIUPRO_BTN_PLUS          CAFEPAD_BTN_PLUS
#define WIIUPRO_BTN_MINUS         CAFEPAD_BTN_MINUS
#define WIIUPRO_BTN_HOME          CAFEPAD_BTN_HOME
#define WIIUPRO_BTN_L3            CAFEPAD_BTN_L3
#define WIIUPRO_BTN_R3            CAFEPAD_BTN_R3

typedef cafepad_stick_t  wiiupro_stick_t;
typedef cafepad_state_t  wiiupro_state_t;
typedef cafepad_device_t wiiupro_device_t;

int wiiupro_init(void);
int wiiupro_scan(char* out_mac, size_t mac_size, int timeout_sec);
wiiupro_device_t* wiiupro_open(void);
wiiupro_device_t* wiiupro_open_path(const char* path);
int wiiupro_poll(wiiupro_device_t* dev, wiiupro_state_t* state, int timeout_ms);
int wiiupro_parse_report(const uint8_t* report, size_t length, wiiupro_state_t* state);
int wiiupro_set_rumble(wiiupro_device_t* dev, bool enabled);
void wiiupro_close(wiiupro_device_t* dev);
void wiiupro_exit(void);

#ifdef __cplusplus
}
#endif

#endif /* CAFEPAD_H */
