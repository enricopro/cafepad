/*
 * ============================================================================
 *   CaféPad — Universal C Library for Nintendo Wii U Pro Controllers
 *   Implementation for Zero-Dongle Bluetooth, USB, and HID
 * ============================================================================
 */

#define _GNU_SOURCE
#include "../include/cafepad.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

#if defined(__linux__) && !defined(USE_HIDAPI)
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <linux/hidraw.h>
#include <linux/joystick.h>
#include <errno.h>
#include <ctype.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/l2cap.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>

typedef enum {
    BACKEND_HIDRAW,
    BACKEND_JOYSTICK,
    BACKEND_L2CAP
} cafepad_backend_t;

struct cafepad_device {
    int fd;
    int ctrl_fd;
    char path[512];
    cafepad_backend_t backend;
    cafepad_state_t last_state;
    uint64_t last_keepalive_us;
};

static uint64_t get_time_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000ULL + (uint64_t)ts.tv_nsec / 1000ULL;
}

int cafepad_init(void) {
    return 0;
}

void cafepad_exit(void) {
}

static void cafepad_init_hidraw(int fd) {
    /* 1. Request Status report */
    uint8_t req_status[] = { 0x15, 0x00 };
    (void)write(fd, req_status, sizeof(req_status));
    usleep(25000);

    /* 2. Set Player 1 LED ON (0x10 = LED 1) and Rumble OFF */
    uint8_t led_cmd[] = { 0x11, CAFEPAD_LED_P1 };
    (void)write(fd, led_cmd, sizeof(led_cmd));
    usleep(25000);

    /* 3. Initialize extension registers (0x55 to 0xa400f0, 0x00 to 0xa400fb) */
    uint8_t init_ext1[] = { 0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55 };
    (void)write(fd, init_ext1, sizeof(init_ext1));
    usleep(25000);

    uint8_t init_ext2[] = { 0x16, 0x04, 0xA4, 0x00, 0xFB, 0x01, 0x00 };
    (void)write(fd, init_ext2, sizeof(init_ext2));
    usleep(25000);

    /* 4. Set Data Reporting Mode to 0x3D (Continuous buttons + extension/analog sticks) */
    uint8_t drm_cmd[] = { 0x12, 0x00, 0x3D };
    (void)write(fd, drm_cmd, sizeof(drm_cmd));
    usleep(25000);
}

static bool get_saved_mac(char* out_mac, size_t max_len) {
    const char* home = getenv("HOME");
    if (!home) return false;
    char path[512];
    snprintf(path, sizeof(path), "%s/.config/cafepad.json", home);
    FILE* f = fopen(path, "r");
    if (!f) {
        /* Fall back to legacy wiiupro.json */
        snprintf(path, sizeof(path), "%s/.config/wiiupro.json", home);
        f = fopen(path, "r");
    }
    if (!f) return false;
    char buf[2048];
    size_t n = fread(buf, 1, sizeof(buf) - 1, f);
    fclose(f);
    buf[n] = '\0';
    
    /* Check "controllers": ["MAC", ...] or "target_mac": "MAC" */
    char* p = strstr(buf, "\"controllers\"");
    if (p) {
        p = strchr(p, '[');
        if (p) {
            p = strchr(p, '\"');
            if (p) {
                p++;
                char* end = strchr(p, '\"');
                if (end && (size_t)(end - p) < max_len) {
                    strncpy(out_mac, p, end - p);
                    out_mac[end - p] = '\0';
                    return true;
                }
            }
        }
    }
    p = strstr(buf, "\"target_mac\"");
    if (p) {
        p = strchr(p, ':');
        if (p) {
            p = strchr(p, '\"');
            if (p) {
                p++;
                char* end = strchr(p, '\"');
                if (end && (size_t)(end - p) < max_len) {
                    strncpy(out_mac, p, end - p);
                    out_mac[end - p] = '\0';
                    return true;
                }
            }
        }
    }
    return false;
}

static void save_mac(const char* mac) {
    const char* home = getenv("HOME");
    if (!home) return;
    char dir[512], path[512];
    snprintf(dir, sizeof(dir), "%s/.config", home);
    snprintf(path, sizeof(path), "%s/.config/cafepad.json", home);
    (void)mkdir(dir, 0755);
    FILE* f = fopen(path, "w");
    if (f) {
        fprintf(f, "{\n  \"controllers\": [\"%s\"],\n  \"updated_at\": %ld\n}\n", mac, (long)time(NULL));
        fclose(f);
    }
}

int cafepad_scan(char* out_mac, size_t mac_size, int timeout_sec) {
    if (!out_mac || mac_size < 18) return -1;

    int dev_id = hci_get_route(NULL);
    if (dev_id < 0) return -1;

    int sock = hci_open_dev(dev_id);
    if (sock < 0) return -1;

    /* Limited Inquiry Access Code (LIAC): 0x9E8B00 */
    uint8_t lap[3] = { 0x00, 0x8B, 0x9E };
    inquiry_info* ii = NULL;
    int len = (timeout_sec > 0) ? timeout_sec : 4;
    int num_rsp = hci_inquiry(dev_id, len, 8, lap, &ii, IREQ_CACHE_FLUSH);

    int result = -1;
    if (num_rsp > 0 && ii != NULL) {
        for (int i = 0; i < num_rsp; i++) {
            char addr[18];
            ba2str(&(ii+i)->bdaddr, addr);

            uint32_t dev_cls = ((ii+i)->dev_class[2] << 16) | ((ii+i)->dev_class[1] << 8) | (ii+i)->dev_class[0];
            uint8_t major = (dev_cls >> 8) & 0x1F;
            if (major != 0x05 && major != 0x00) continue;

            char name[248] = {0};
            if (hci_read_remote_name(sock, &(ii+i)->bdaddr, sizeof(name), name, 1500) >= 0) {
                if (strstr(name, "Nintendo") || strcasestr(name, "Pro Controller") || strcasestr(name, "RVL") || strcasestr(name, "Wii")) {
                    snprintf(out_mac, mac_size, "%s", addr);
                    save_mac(addr);
                    result = 0;
                    break;
                }
            }
            if (result != 0 && (strcasestr(name, "Controller") || strcasestr(name, "Gamepad") || (name[0] == '\0' && major == 0x05))) {
                snprintf(out_mac, mac_size, "%s", addr);
                save_mac(addr);
                result = 0;
                break;
            }
        }
        free(ii);
    }

    close(sock);
    return result;
}

cafepad_device_t* cafepad_open(void) {
    /* 1. Check if ~/.config/cafepad.json has a saved controller MAC */
    char saved_mac[32];
    if (get_saved_mac(saved_mac, sizeof(saved_mac))) {
        cafepad_device_t* dev = cafepad_open_path(saved_mac);
        if (dev) return dev;
    }

    /* 2. Try finding Bluetooth / virtual joystick in /dev/input/js* */
    for (int i = 0; i < 8; i++) {
        char path[64];
        snprintf(path, sizeof(path), "/dev/input/js%d", i);
        int fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd >= 0) {
            char name[128] = {0};
            if (ioctl(fd, JSIOCGNAME(sizeof(name)), name) >= 0) {
                if (strcasestr(name, "nintendo") || strcasestr(name, "wii") || 
                    strcasestr(name, "pro controller") || strcasestr(name, "rvl") ||
                    strcasestr(name, "x-box 360 pad") || strcasestr(name, "cafepad")) {
                    cafepad_device_t* dev = (cafepad_device_t*)calloc(1, sizeof(cafepad_device_t));
                    if (!dev) { close(fd); return NULL; }
                    dev->fd = fd;
                    dev->ctrl_fd = -1;
                    dev->backend = BACKEND_JOYSTICK;
                    snprintf(dev->path, sizeof(dev->path), "%s (%s)", path, name);
                    return dev;
                }
            }
            close(fd);
        }
    }

    /* 3. Try finding raw HID device in /dev/hidraw* */
    DIR* dir = opendir("/dev");
    if (dir) {
        struct dirent* entry;
        while ((entry = readdir(dir)) != NULL) {
            if (strncmp(entry->d_name, "hidraw", 6) == 0) {
                char path[280];
                snprintf(path, sizeof(path), "/dev/%s", entry->d_name);
                cafepad_device_t* dev = cafepad_open_path(path);
                if (dev) {
                    closedir(dir);
                    return dev;
                }
            }
        }
        closedir(dir);
    }

    return NULL;
}

cafepad_device_t* cafepad_open_path(const char* path) {
    if (!path) return NULL;

    /* Check if path is a Bluetooth MAC Address (XX:XX:XX:XX:XX:XX) */
    if (strlen(path) == 17 && path[2] == ':' && path[5] == ':' && path[8] == ':') {
        int ctrl_sock = socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
        int intr_sock = socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
        if (ctrl_sock < 0 || intr_sock < 0) {
            if (ctrl_sock >= 0) close(ctrl_sock);
            if (intr_sock >= 0) close(intr_sock);
            return NULL;
        }

        struct sockaddr_l2 addr;
        memset(&addr, 0, sizeof(addr));
        addr.l2_family = AF_BLUETOOTH;
        str2ba(path, &addr.l2_bdaddr);

        /* Connect Control Channel (PSM 0x0011) */
        addr.l2_psm = htobs(0x0011);
        if (connect(ctrl_sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            close(ctrl_sock);
            close(intr_sock);
            return NULL;
        }

        /* Connect Interrupt Channel (PSM 0x0013) */
        addr.l2_psm = htobs(0x0013);
        if (connect(intr_sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            close(ctrl_sock);
            close(intr_sock);
            return NULL;
        }

        cafepad_device_t* dev = (cafepad_device_t*)calloc(1, sizeof(cafepad_device_t));
        if (!dev) {
            close(ctrl_sock);
            close(intr_sock);
            return NULL;
        }
        dev->fd = intr_sock;
        dev->ctrl_fd = ctrl_sock;
        dev->backend = BACKEND_L2CAP;
        snprintf(dev->path, sizeof(dev->path), "%s", path);
        dev->last_keepalive_us = get_time_us();

        /* Initialize Extension Registers */
        uint8_t init1[] = {0xa2, 0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55};
        write(ctrl_sock, init1, sizeof(init1));
        usleep(25000);

        uint8_t init2[] = {0xa2, 0x16, 0x04, 0xA4, 0x00, 0xFB, 0x01, 0x00};
        write(ctrl_sock, init2, sizeof(init2));
        usleep(25000);

        uint8_t led_cmd[] = {0xa2, 0x11, CAFEPAD_LED_P1};
        write(ctrl_sock, led_cmd, sizeof(led_cmd));
        usleep(25000);

        uint8_t drm_cmd[] = {0xa2, 0x12, 0x00, 0x3D};
        write(ctrl_sock, drm_cmd, sizeof(drm_cmd));
        usleep(25000);

        return dev;
    }

    int fd = open(path, O_RDWR | O_NONBLOCK);
    if (fd < 0) {
        fd = open(path, O_RDONLY | O_NONBLOCK);
        if (fd < 0) return NULL;
    }

    if (strstr(path, "/js") != NULL) {
        cafepad_device_t* dev = (cafepad_device_t*)calloc(1, sizeof(cafepad_device_t));
        if (!dev) { close(fd); return NULL; }
        dev->fd = fd;
        dev->ctrl_fd = -1;
        dev->backend = BACKEND_JOYSTICK;
        snprintf(dev->path, sizeof(dev->path), "%s", path);
        return dev;
    }

    struct hidraw_devinfo info;
    if (ioctl(fd, HIDIOCGRAWINFO, &info) < 0) {
        close(fd);
        return NULL;
    }

    bool match = false;
    if (info.bustype == BUS_USB && info.vendor == CAFEPAD_USB_CLONE_VID && info.product == CAFEPAD_USB_CLONE_PID) {
        match = true;
    } else if (info.vendor == CAFEPAD_OFFICIAL_VID && info.product == CAFEPAD_OFFICIAL_PID) {
        match = true;
    } else if (info.bustype == BUS_BLUETOOTH) {
        char name[256] = {0};
        if (ioctl(fd, HIDIOCGRAWNAME(sizeof(name)), name) >= 0) {
            if (strcasestr(name, "Nintendo") || strcasestr(name, "Pro Controller") || strcasestr(name, "RVL")) {
                match = true;
            }
        }
    }

    if (!match) {
        close(fd);
        return NULL;
    }

    cafepad_device_t* dev = (cafepad_device_t*)calloc(1, sizeof(cafepad_device_t));
    if (!dev) {
        close(fd);
        return NULL;
    }

    dev->fd = fd;
    dev->ctrl_fd = -1;
    dev->backend = BACKEND_HIDRAW;
    snprintf(dev->path, sizeof(dev->path), "%s", path);
    dev->last_keepalive_us = get_time_us();

    if (info.bustype == BUS_BLUETOOTH) {
        cafepad_init_hidraw(fd);
    }

    return dev;
}

int cafepad_poll(cafepad_device_t* dev, cafepad_state_t* state, int timeout_ms) {
    if (!dev || dev->fd < 0 || !state) return -1;

    struct pollfd pfd;
    pfd.fd = dev->fd;
    pfd.events = POLLIN;

    int ret = poll(&pfd, 1, timeout_ms);
    if (ret <= 0) return ret;

    if (dev->backend == BACKEND_JOYSTICK) {
        struct js_event e;
        int bytes = read(dev->fd, &e, sizeof(e));
        if (bytes < (int)sizeof(e)) return -1;

        *state = dev->last_state;
        state->timestamp_us = get_time_us();

        uint8_t type = e.type & ~JS_EVENT_INIT;
        if (type == JS_EVENT_BUTTON) {
            uint32_t btn_mask = 0;
            switch (e.number) {
                case 0: btn_mask = CAFEPAD_BTN_A; break;
                case 1: btn_mask = CAFEPAD_BTN_B; break;
                case 2: btn_mask = CAFEPAD_BTN_X; break;
                case 3: btn_mask = CAFEPAD_BTN_Y; break;
                case 4: btn_mask = CAFEPAD_BTN_L; break;
                case 5: btn_mask = CAFEPAD_BTN_R; break;
                case 6: btn_mask = CAFEPAD_BTN_MINUS; break;
                case 7: btn_mask = CAFEPAD_BTN_PLUS; break;
                case 8: btn_mask = CAFEPAD_BTN_HOME; break;
                case 9: btn_mask = CAFEPAD_BTN_L3; break;
                case 10: btn_mask = CAFEPAD_BTN_R3; break;
                default: break;
            }
            if (e.value) {
                state->buttons |= btn_mask;
            } else {
                state->buttons &= ~btn_mask;
            }
        } else if (type == JS_EVENT_AXIS) {
            float val = (float)e.value / 32767.0f;
            if (val > 1.0f) val = 1.0f;
            if (val < -1.0f) val = -1.0f;
            switch (e.number) {
                case 0: state->left_stick.x = val; break;
                case 1: state->left_stick.y = val; break;
                case 2: if (e.value > 10000) state->buttons |= CAFEPAD_BTN_ZL; else state->buttons &= ~CAFEPAD_BTN_ZL; break;
                case 3: state->right_stick.x = val; break;
                case 4: state->right_stick.y = val; break;
                case 5: if (e.value > 10000) state->buttons |= CAFEPAD_BTN_ZR; else state->buttons &= ~CAFEPAD_BTN_ZR; break;
                case 6:
                    if (e.value < -10000) { state->buttons |= CAFEPAD_BTN_DPAD_LEFT; state->buttons &= ~CAFEPAD_BTN_DPAD_RIGHT; }
                    else if (e.value > 10000) { state->buttons |= CAFEPAD_BTN_DPAD_RIGHT; state->buttons &= ~CAFEPAD_BTN_DPAD_LEFT; }
                    else { state->buttons &= ~(CAFEPAD_BTN_DPAD_LEFT | CAFEPAD_BTN_DPAD_RIGHT); }
                    break;
                case 7:
                    if (e.value < -10000) { state->buttons |= CAFEPAD_BTN_DPAD_UP; state->buttons &= ~CAFEPAD_BTN_DPAD_DOWN; }
                    else if (e.value > 10000) { state->buttons |= CAFEPAD_BTN_DPAD_DOWN; state->buttons &= ~CAFEPAD_BTN_DPAD_UP; }
                    else { state->buttons &= ~(CAFEPAD_BTN_DPAD_UP | CAFEPAD_BTN_DPAD_DOWN); }
                    break;
                default: break;
            }
        }
        dev->last_state = *state;
        return 1;
    } else {
        uint8_t buffer[128];
        ssize_t bytes = read(dev->fd, buffer, sizeof(buffer));
        if (bytes <= 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) return 0;
            return -1;
        }

        uint64_t now_us = get_time_us();
        if (dev->ctrl_fd >= 0 && (now_us - dev->last_keepalive_us) > 2000000ULL) {
            uint8_t status_req[] = {0xa2, 0x15, 0x00};
            write(dev->ctrl_fd, status_req, sizeof(status_req));
            dev->last_keepalive_us = now_us;
        }

        const uint8_t* report_ptr = buffer;
        size_t report_len = (size_t)bytes;

        if (dev->backend == BACKEND_L2CAP && report_len > 0) {
            if (report_ptr[0] == 0xa1) {
                report_ptr++;
                report_len--;
            }
        }

        int parse_res = cafepad_parse_report(report_ptr, report_len, state);
        if (parse_res <= 0) {
            return 0;
        }
        dev->last_state = *state;
        return 1;
    }
}

int cafepad_set_rumble(cafepad_device_t* dev, bool enabled) {
    if (!dev || dev->fd < 0) return -1;
    if (dev->backend == BACKEND_HIDRAW) {
        uint8_t report[2] = {0x11, enabled ? 0x01 : 0x00};
        ssize_t written = write(dev->fd, report, sizeof(report));
        return (written == sizeof(report)) ? 0 : -1;
    } else if (dev->backend == BACKEND_L2CAP) {
        uint8_t report[3] = {0xa2, 0x11, enabled ? 0x11 : 0x10};
        ssize_t written = write(dev->fd, report, sizeof(report));
        return (written == sizeof(report)) ? 0 : -1;
    }
    return 0;
}

int cafepad_set_player_led(cafepad_device_t* dev, int player_id) {
    if (!dev || dev->fd < 0) return -1;
    uint8_t led_mask = CAFEPAD_LED_P1;
    switch (player_id) {
        case 0: led_mask = CAFEPAD_LED_P1; break;
        case 1: led_mask = CAFEPAD_LED_P2; break;
        case 2: led_mask = CAFEPAD_LED_P3; break;
        case 3: led_mask = CAFEPAD_LED_P4; break;
        default: break;
    }

    if (dev->backend == BACKEND_HIDRAW) {
        uint8_t report[2] = {0x11, led_mask};
        ssize_t written = write(dev->fd, report, sizeof(report));
        return (written == sizeof(report)) ? 0 : -1;
    } else if (dev->backend == BACKEND_L2CAP) {
        uint8_t report[3] = {0xa2, 0x11, led_mask};
        ssize_t written = write(dev->fd, report, sizeof(report));
        return (written == sizeof(report)) ? 0 : -1;
    }
    return 0;
}

void cafepad_close(cafepad_device_t* dev) {
    if (dev) {
        if (dev->fd >= 0) close(dev->fd);
        if (dev->ctrl_fd >= 0) close(dev->ctrl_fd);
        free(dev);
    }
}

#elif defined(USE_HIDAPI) || defined(_WIN32) || defined(__APPLE__)
#include <hidapi/hidapi.h>

struct cafepad_device {
    hid_device* handle;
};

int cafepad_init(void) { return hid_init(); }
void cafepad_exit(void) { hid_exit(); }

cafepad_device_t* cafepad_open(void) {
    hid_device* h = hid_open(CAFEPAD_USB_CLONE_VID, CAFEPAD_USB_CLONE_PID, NULL);
    if (!h) h = hid_open(CAFEPAD_OFFICIAL_VID, CAFEPAD_OFFICIAL_PID, NULL);
    if (!h) return NULL;

    cafepad_device_t* dev = (cafepad_device_t*)malloc(sizeof(cafepad_device_t));
    if (!dev) { hid_close(h); return NULL; }
    dev->handle = h;
    return dev;
}

cafepad_device_t* cafepad_open_path(const char* path) {
    hid_device* h = hid_open_path(path);
    if (!h) return NULL;
    cafepad_device_t* dev = (cafepad_device_t*)malloc(sizeof(cafepad_device_t));
    if (!dev) { hid_close(h); return NULL; }
    dev->handle = h;
    return dev;
}

int cafepad_poll(cafepad_device_t* dev, cafepad_state_t* state, int timeout_ms) {
    if (!dev || !dev->handle || !state) return -1;
    uint8_t buffer[64];
    int res = hid_read_timeout(dev->handle, buffer, sizeof(buffer), timeout_ms);
    if (res <= 0) return res;
    return cafepad_parse_report(buffer, (size_t)res, state);
}

int cafepad_set_rumble(cafepad_device_t* dev, bool enabled) {
    if (!dev || !dev->handle) return -1;
    uint8_t report[2] = {0x11, enabled ? 0x01 : 0x00};
    int res = hid_write(dev->handle, report, sizeof(report));
    return (res >= 0) ? 0 : -1;
}

int cafepad_set_player_led(cafepad_device_t* dev, int player_id) {
    if (!dev || !dev->handle) return -1;
    uint8_t led_mask = (player_id == 1) ? CAFEPAD_LED_P2 : (player_id == 2) ? CAFEPAD_LED_P3 : (player_id == 3) ? CAFEPAD_LED_P4 : CAFEPAD_LED_P1;
    uint8_t report[2] = {0x11, led_mask};
    int res = hid_write(dev->handle, report, sizeof(report));
    return (res >= 0) ? 0 : -1;
}

int cafepad_scan(char* out_mac, size_t mac_size, int timeout_sec) {
    (void)out_mac; (void)mac_size; (void)timeout_sec;
    return -1;
}

void cafepad_close(cafepad_device_t* dev) {
    if (dev) {
        if (dev->handle) hid_close(dev->handle);
        free(dev);
    }
}
#endif

static float normalize_stick(int16_t raw) {
    float val = ((float)raw - 2048.0f) / 1024.0f;
    if (val < -1.0f) val = -1.0f;
    if (val > 1.0f) val = 1.0f;
    if (fabsf(val) < 0.05f) val = 0.0f;
    return val;
}

static float normalize_stick_8bit(uint8_t raw) {
    float val = ((float)raw - 128.0f) / 128.0f;
    if (val < -1.0f) val = -1.0f;
    if (val > 1.0f) val = 1.0f;
    if (fabsf(val) < 0.08f) val = 0.0f;
    return val;
}

int cafepad_parse_report(const uint8_t* report, size_t length, cafepad_state_t* state) {
    if (!report || length == 0 || !state) return 0;

    /* Status reports (0x20), Read Memory (0x21), Acknowledge (0x22) */
    if (report[0] == 0x20 || report[0] == 0x21 || report[0] == 0x22) {
        return 0;
    }

    memset(state, 0, sizeof(cafepad_state_t));

    /* Check if this is Bluetooth Report 0x3D (Report ID + 11+ extension data) */
    if (report[0] == 0x3D && length >= 12) {
        const uint8_t* ext = report + 1;
        state->left_stick.raw_x  = (int16_t)(ext[0] | ((ext[1] & 0x0F) << 8));
        state->right_stick.raw_x = (int16_t)(ext[2] | ((ext[3] & 0x0F) << 8));
        state->left_stick.raw_y  = (int16_t)(ext[4] | ((ext[5] & 0x0F) << 8));
        state->right_stick.raw_y = (int16_t)(ext[6] | ((ext[7] & 0x0F) << 8));

        state->left_stick.x  = normalize_stick(state->left_stick.raw_x);
        state->left_stick.y  = -normalize_stick(state->left_stick.raw_y);
        state->right_stick.x = normalize_stick(state->right_stick.raw_x);
        state->right_stick.y = -normalize_stick(state->right_stick.raw_y);

        uint8_t b8  = ext[8];
        uint8_t b9  = ext[9];
        uint8_t b10 = ext[10];

        uint32_t btns = 0;
        if (!(b8 & (1U << 7))) btns |= CAFEPAD_BTN_DPAD_RIGHT;
        if (!(b8 & (1U << 6))) btns |= CAFEPAD_BTN_DPAD_DOWN;
        if (!(b8 & (1U << 5))) btns |= CAFEPAD_BTN_L;
        if (!(b8 & (1U << 4))) btns |= CAFEPAD_BTN_MINUS;
        if (!(b8 & (1U << 3))) btns |= CAFEPAD_BTN_HOME;
        if (!(b8 & (1U << 2))) btns |= CAFEPAD_BTN_PLUS;
        if (!(b8 & (1U << 1))) btns |= CAFEPAD_BTN_R;

        if (!(b9 & (1U << 7))) btns |= CAFEPAD_BTN_ZL;
        if (!(b9 & (1U << 6))) btns |= CAFEPAD_BTN_B;
        if (!(b9 & (1U << 5))) btns |= CAFEPAD_BTN_Y;
        if (!(b9 & (1U << 4))) btns |= CAFEPAD_BTN_A;
        if (!(b9 & (1U << 3))) btns |= CAFEPAD_BTN_X;
        if (!(b9 & (1U << 2))) btns |= CAFEPAD_BTN_ZR;
        if (!(b9 & (1U << 1))) btns |= CAFEPAD_BTN_DPAD_LEFT;
        if (!(b9 & (1U << 0))) btns |= CAFEPAD_BTN_DPAD_UP;

        if (!(b10 & (1U << 1))) btns |= CAFEPAD_BTN_L3;
        if (!(b10 & (1U << 0))) btns |= CAFEPAD_BTN_R3;

        state->buttons = btns;
        state->is_wired = !(b10 & (1U << 3));
        state->is_charging = !(b10 & (1U << 2));
        state->battery_level = (b10 >> 4) & 0x07;
        return 1;
    }

    /* Check if this is Bluetooth Report 0x34 (Report ID + 2 core button bytes + 11+ extension data) */
    if (report[0] == 0x34 && length >= 14) {
        const uint8_t* ext = report + 3;
        state->left_stick.raw_x  = (int16_t)(ext[0] | ((ext[1] & 0x0F) << 8));
        state->right_stick.raw_x = (int16_t)(ext[2] | ((ext[3] & 0x0F) << 8));
        state->left_stick.raw_y  = (int16_t)(ext[4] | ((ext[5] & 0x0F) << 8));
        state->right_stick.raw_y = (int16_t)(ext[6] | ((ext[7] & 0x0F) << 8));

        state->left_stick.x  = normalize_stick(state->left_stick.raw_x);
        state->left_stick.y  = -normalize_stick(state->left_stick.raw_y);
        state->right_stick.x = normalize_stick(state->right_stick.raw_x);
        state->right_stick.y = -normalize_stick(state->right_stick.raw_y);

        uint8_t b8  = ext[8];
        uint8_t b9  = ext[9];
        uint8_t b10 = ext[10];

        uint32_t btns = 0;
        if (!(b8 & (1U << 7))) btns |= CAFEPAD_BTN_DPAD_RIGHT;
        if (!(b8 & (1U << 6))) btns |= CAFEPAD_BTN_DPAD_DOWN;
        if (!(b8 & (1U << 5))) btns |= CAFEPAD_BTN_L;
        if (!(b8 & (1U << 4))) btns |= CAFEPAD_BTN_MINUS;
        if (!(b8 & (1U << 3))) btns |= CAFEPAD_BTN_HOME;
        if (!(b8 & (1U << 2))) btns |= CAFEPAD_BTN_PLUS;
        if (!(b8 & (1U << 1))) btns |= CAFEPAD_BTN_R;

        if (!(b9 & (1U << 7))) btns |= CAFEPAD_BTN_ZL;
        if (!(b9 & (1U << 6))) btns |= CAFEPAD_BTN_B;
        if (!(b9 & (1U << 5))) btns |= CAFEPAD_BTN_Y;
        if (!(b9 & (1U << 4))) btns |= CAFEPAD_BTN_A;
        if (!(b9 & (1U << 3))) btns |= CAFEPAD_BTN_X;
        if (!(b9 & (1U << 2))) btns |= CAFEPAD_BTN_ZR;
        if (!(b9 & (1U << 1))) btns |= CAFEPAD_BTN_DPAD_LEFT;
        if (!(b9 & (1U << 0))) btns |= CAFEPAD_BTN_DPAD_UP;

        if (!(b10 & (1U << 1))) btns |= CAFEPAD_BTN_L3;
        if (!(b10 & (1U << 0))) btns |= CAFEPAD_BTN_R3;

        state->buttons = btns;
        state->is_wired = !(b10 & (1U << 3));
        state->is_charging = !(b10 & (1U << 2));
        state->battery_level = (b10 >> 4) & 0x07;
        return 1;
    }

    /* Check if this is Bluetooth Report 0x35 */
    if (report[0] == 0x35 && length >= 17) {
        const uint8_t* ext = report + 6;
        state->left_stick.raw_x  = (int16_t)(ext[0] | ((ext[1] & 0x0F) << 8));
        state->right_stick.raw_x = (int16_t)(ext[2] | ((ext[3] & 0x0F) << 8));
        state->left_stick.raw_y  = (int16_t)(ext[4] | ((ext[5] & 0x0F) << 8));
        state->right_stick.raw_y = (int16_t)(ext[6] | ((ext[7] & 0x0F) << 8));

        state->left_stick.x  = normalize_stick(state->left_stick.raw_x);
        state->left_stick.y  = -normalize_stick(state->left_stick.raw_y);
        state->right_stick.x = normalize_stick(state->right_stick.raw_x);
        state->right_stick.y = -normalize_stick(state->right_stick.raw_y);

        uint8_t b8  = ext[8];
        uint8_t b9  = ext[9];
        uint8_t b10 = ext[10];

        uint32_t btns = 0;
        if (!(b8 & (1U << 7))) btns |= CAFEPAD_BTN_DPAD_RIGHT;
        if (!(b8 & (1U << 6))) btns |= CAFEPAD_BTN_DPAD_DOWN;
        if (!(b8 & (1U << 5))) btns |= CAFEPAD_BTN_L;
        if (!(b8 & (1U << 4))) btns |= CAFEPAD_BTN_MINUS;
        if (!(b8 & (1U << 3))) btns |= CAFEPAD_BTN_HOME;
        if (!(b8 & (1U << 2))) btns |= CAFEPAD_BTN_PLUS;
        if (!(b8 & (1U << 1))) btns |= CAFEPAD_BTN_R;

        if (!(b9 & (1U << 7))) btns |= CAFEPAD_BTN_ZL;
        if (!(b9 & (1U << 6))) btns |= CAFEPAD_BTN_B;
        if (!(b9 & (1U << 5))) btns |= CAFEPAD_BTN_Y;
        if (!(b9 & (1U << 4))) btns |= CAFEPAD_BTN_A;
        if (!(b9 & (1U << 3))) btns |= CAFEPAD_BTN_X;
        if (!(b9 & (1U << 2))) btns |= CAFEPAD_BTN_ZR;
        if (!(b9 & (1U << 1))) btns |= CAFEPAD_BTN_DPAD_LEFT;
        if (!(b9 & (1U << 0))) btns |= CAFEPAD_BTN_DPAD_UP;

        if (!(b10 & (1U << 1))) btns |= CAFEPAD_BTN_L3;
        if (!(b10 & (1U << 0))) btns |= CAFEPAD_BTN_R3;

        state->buttons = btns;
        state->is_wired = !(b10 & (1U << 3));
        state->is_charging = !(b10 & (1U << 2));
        state->battery_level = (b10 >> 4) & 0x07;
        return 1;
    }

    /* Core Buttons Report 0x30 / 0x31 / 0x32 / 0x33 */
    if ((report[0] == 0x30 || report[0] == 0x31 || report[0] == 0x32 || report[0] == 0x33) && length >= 3) {
        uint8_t k0 = report[1];
        uint8_t k1 = report[2];
        uint32_t btns = 0;

        if (k0 & 0x01) btns |= CAFEPAD_BTN_DPAD_LEFT;
        if (k0 & 0x02) btns |= CAFEPAD_BTN_DPAD_RIGHT;
        if (k0 & 0x04) btns |= CAFEPAD_BTN_DPAD_DOWN;
        if (k0 & 0x08) btns |= CAFEPAD_BTN_DPAD_UP;
        if (k0 & 0x10) btns |= CAFEPAD_BTN_PLUS;

        if (k1 & 0x01) btns |= CAFEPAD_BTN_R3;
        if (k1 & 0x02) btns |= CAFEPAD_BTN_L3;
        if (k1 & 0x04) btns |= CAFEPAD_BTN_B;
        if (k1 & 0x08) btns |= CAFEPAD_BTN_A;
        if (k1 & 0x10) btns |= CAFEPAD_BTN_MINUS;
        if (k1 & 0x80) btns |= CAFEPAD_BTN_HOME;

        state->buttons = btns;
        return 1;
    }

    /* 0471:0666 USB Wired Format */
    if ((length == 64 || length == 8 || length == 7) && report[0] != 0x3D && report[0] != 0x30 && report[0] != 0x31) {
        state->left_stick.raw_x  = report[0];
        state->left_stick.raw_y  = report[1];
        state->right_stick.raw_x = report[3];
        state->right_stick.raw_y = report[4];

        state->left_stick.x  = normalize_stick_8bit(report[0]);
        state->left_stick.y  = normalize_stick_8bit(report[1]);
        state->right_stick.x = normalize_stick_8bit(report[3]);
        state->right_stick.y = normalize_stick_8bit(report[4]);

        uint8_t b5 = report[5];
        uint8_t b6 = report[6];
        uint32_t btns = 0;

        if (b5 & 0x40) btns |= CAFEPAD_BTN_A;
        if (b5 & 0x80) btns |= CAFEPAD_BTN_B;
        if (b5 & 0x20) btns |= CAFEPAD_BTN_X;
        if (b5 & 0x10) btns |= CAFEPAD_BTN_Y;

        uint8_t hat = b5 & 0x0F;
        switch (hat) {
            case 0: btns |= CAFEPAD_BTN_DPAD_UP; break;
            case 1: btns |= (CAFEPAD_BTN_DPAD_UP | CAFEPAD_BTN_DPAD_RIGHT); break;
            case 2: btns |= CAFEPAD_BTN_DPAD_RIGHT; break;
            case 3: btns |= (CAFEPAD_BTN_DPAD_DOWN | CAFEPAD_BTN_DPAD_RIGHT); break;
            case 4: btns |= CAFEPAD_BTN_DPAD_DOWN; break;
            case 5: btns |= (CAFEPAD_BTN_DPAD_DOWN | CAFEPAD_BTN_DPAD_LEFT); break;
            case 6: btns |= CAFEPAD_BTN_DPAD_LEFT; break;
            case 7: btns |= (CAFEPAD_BTN_DPAD_UP | CAFEPAD_BTN_DPAD_LEFT); break;
            default: break;
        }

        if (b6 & 0x01) btns |= CAFEPAD_BTN_L;
        if (b6 & 0x02) btns |= CAFEPAD_BTN_R;
        if (b6 & 0x04) btns |= CAFEPAD_BTN_ZR;
        if (b6 & 0x08) btns |= CAFEPAD_BTN_ZL;
        if (b6 & 0x10) btns |= CAFEPAD_BTN_HOME;
        if (b6 & 0x20) btns |= CAFEPAD_BTN_PLUS;
        if (b6 & 0x40) btns |= CAFEPAD_BTN_MINUS;

        state->buttons = btns;
        state->is_wired = true;
        state->battery_level = 4;
        return 1;
    }

    if (length >= 11) {
        state->left_stick.raw_x  = (int16_t)(report[0] | ((report[1] & 0x0F) << 8));
        state->right_stick.raw_x = (int16_t)(report[2] | ((report[3] & 0x0F) << 8));
        state->left_stick.raw_y  = (int16_t)(report[4] | ((report[5] & 0x0F) << 8));
        state->right_stick.raw_y = (int16_t)(report[6] | ((report[7] & 0x0F) << 8));

        state->left_stick.x  = normalize_stick(state->left_stick.raw_x);
        state->left_stick.y  = -normalize_stick(state->left_stick.raw_y);
        state->right_stick.x = normalize_stick(state->right_stick.raw_x);
        state->right_stick.y = -normalize_stick(state->right_stick.raw_y);

        uint8_t b8  = report[8];
        uint8_t b9  = report[9];
        uint8_t b10 = report[10];

        uint32_t btns = 0;
        if (!(b8 & (1U << 7))) btns |= CAFEPAD_BTN_DPAD_RIGHT;
        if (!(b8 & (1U << 6))) btns |= CAFEPAD_BTN_DPAD_DOWN;
        if (!(b8 & (1U << 5))) btns |= CAFEPAD_BTN_L;
        if (!(b8 & (1U << 4))) btns |= CAFEPAD_BTN_MINUS;
        if (!(b8 & (1U << 3))) btns |= CAFEPAD_BTN_HOME;
        if (!(b8 & (1U << 2))) btns |= CAFEPAD_BTN_PLUS;
        if (!(b8 & (1U << 1))) btns |= CAFEPAD_BTN_R;

        if (!(b9 & (1U << 7))) btns |= CAFEPAD_BTN_ZL;
        if (!(b9 & (1U << 6))) btns |= CAFEPAD_BTN_B;
        if (!(b9 & (1U << 5))) btns |= CAFEPAD_BTN_Y;
        if (!(b9 & (1U << 4))) btns |= CAFEPAD_BTN_A;
        if (!(b9 & (1U << 3))) btns |= CAFEPAD_BTN_X;
        if (!(b9 & (1U << 2))) btns |= CAFEPAD_BTN_ZR;
        if (!(b9 & (1U << 1))) btns |= CAFEPAD_BTN_DPAD_LEFT;
        if (!(b9 & (1U << 0))) btns |= CAFEPAD_BTN_DPAD_UP;

        if (!(b10 & (1U << 1))) btns |= CAFEPAD_BTN_L3;
        if (!(b10 & (1U << 0))) btns |= CAFEPAD_BTN_R3;

        state->buttons = btns;
        state->is_wired = !(b10 & (1U << 3));
        state->is_charging = !(b10 & (1U << 2));
        state->battery_level = (b10 >> 4) & 0x07;
        return 1;
    }

    return 0;
}

/* ============================================================================
 *   Backwards-Compatibility Symbol Exports
 * ============================================================================
 */
int wiiupro_init(void) { return cafepad_init(); }
void wiiupro_exit(void) { cafepad_exit(); }
int wiiupro_scan(char* out_mac, size_t mac_size, int timeout_sec) { return cafepad_scan(out_mac, mac_size, timeout_sec); }
wiiupro_device_t* wiiupro_open(void) { return (wiiupro_device_t*)cafepad_open(); }
wiiupro_device_t* wiiupro_open_path(const char* path) { return (wiiupro_device_t*)cafepad_open_path(path); }
int wiiupro_poll(wiiupro_device_t* dev, wiiupro_state_t* state, int timeout_ms) { return cafepad_poll((cafepad_device_t*)dev, (cafepad_state_t*)state, timeout_ms); }
int wiiupro_parse_report(const uint8_t* report, size_t length, wiiupro_state_t* state) { return cafepad_parse_report(report, length, (cafepad_state_t*)state); }
int wiiupro_set_rumble(wiiupro_device_t* dev, bool enabled) { return cafepad_set_rumble((cafepad_device_t*)dev, enabled); }
void wiiupro_close(wiiupro_device_t* dev) { cafepad_close((cafepad_device_t*)dev); }
