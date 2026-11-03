#include "../include/wiiupro.h"
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

void print_buttons(uint32_t btns) {
    if (btns & WIIUPRO_BTN_A)          printf("A ");
    if (btns & WIIUPRO_BTN_B)          printf("B ");
    if (btns & WIIUPRO_BTN_X)          printf("X ");
    if (btns & WIIUPRO_BTN_Y)          printf("Y ");
    if (btns & WIIUPRO_BTN_DPAD_UP)    printf("UP ");
    if (btns & WIIUPRO_BTN_DPAD_DOWN)  printf("DOWN ");
    if (btns & WIIUPRO_BTN_DPAD_LEFT)  printf("LEFT ");
    if (btns & WIIUPRO_BTN_DPAD_RIGHT) printf("RIGHT ");
    if (btns & WIIUPRO_BTN_L)          printf("L ");
    if (btns & WIIUPRO_BTN_R)          printf("R ");
    if (btns & WIIUPRO_BTN_ZL)         printf("ZL ");
    if (btns & WIIUPRO_BTN_ZR)         printf("ZR ");
    if (btns & WIIUPRO_BTN_PLUS)       printf("+ ");
    if (btns & WIIUPRO_BTN_MINUS)      printf("- ");
    if (btns & WIIUPRO_BTN_HOME)       printf("HOME ");
    if (btns & WIIUPRO_BTN_L3)         printf("L3 ");
    if (btns & WIIUPRO_BTN_R3)         printf("R3 ");
}

int main(int argc, char* argv[]) {
    printf("=== Wii U Pro Controller (USB) Live Test ===\n");

    if (wiiupro_init() != 0) {
        fprintf(stderr, "Failed to initialize subsystem\n");
        return 1;
    }

    const char* target_path = (argc > 1) ? argv[1] : NULL;
    if (target_path) {
        printf("Waiting for controller at %s...\n", target_path);
    } else {
        printf("Waiting for controller...\n");
    }

    wiiupro_device_t* dev = NULL;
    while (!dev) {
        if (target_path) {
            dev = wiiupro_open_path(target_path);
        } else {
            dev = wiiupro_open();
        }
        if (!dev) {
            usleep(500000);
        }
    }

    printf("Controller connected!\n");
    printf("Press buttons and move sticks (Ctrl+C to quit):\n\n");

    wiiupro_state_t state;

    while (1) {
        int res = wiiupro_poll(dev, &state, 100);
        if (res > 0) {
            printf("\rL-Stick: [%+0.2f, %+0.2f]  R-Stick: [%+0.2f, %+0.2f]  Bat: %d  Btns: [",
                   state.left_stick.x, state.left_stick.y,
                   state.right_stick.x, state.right_stick.y,
                   state.battery_level);
            print_buttons(state.buttons);
            printf("]           ");
            fflush(stdout);
        } else if (res < 0) {
            printf("\nController disconnected or error: %s (errno=%d, res=%d)\n", strerror(errno), errno, res);
            break;
        }
    }

    wiiupro_close(dev);
    wiiupro_exit();
    return 0;
}
