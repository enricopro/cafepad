/**
 * Minimal Example — Nintendo Wii U Pro Controller C Library
 *
 * Demonstrates connecting to the controller and polling input.
 * Compile:
 *   gcc minimal_example.c -lwiiupro -lbluetooth -lm -o minimal_example
 */

#include <stdio.h>
#include <unistd.h>
#include <wiiupro.h>

int main(void) {
    printf("Connecting to Wii U Pro Controller...\n");

    /* Automatically connects via saved MAC, USB, or Bluetooth sync */
    wiiupro_device_t* dev = wiiupro_open();
    if (!dev) {
        fprintf(stderr, "No controller found. Put controller in SYNC mode (or connect via USB) and retry.\n");
        return 1;
    }

    printf("Connected! Press buttons (Ctrl+C to quit):\n");

    wiiupro_state_t state;
    while (1) {
        /* Poll with 10ms timeout */
        int ret = wiiupro_poll(dev, &state, 10);
        if (ret > 0) {
            printf("\rL-Stick: [%+0.2f, %+0.2f]  R-Stick: [%+0.2f, %+0.2f]  Btns: 0x%05X  Bat: %d  ",
                   state.left_stick.x, state.left_stick.y,
                   state.right_stick.x, state.right_stick.y,
                   state.buttons, state.battery_level);
            fflush(stdout);
        } else if (ret < 0) {
            printf("\nController disconnected.\n");
            break;
        }
    }

    wiiupro_close(dev);
    return 0;
}
