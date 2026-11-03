#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <bluetooth/bluetooth.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>

#define COLOR_RESET   "\033[0m"
#define COLOR_RED     "\033[1;31m"
#define COLOR_GREEN   "\033[1;32m"
#define COLOR_YELLOW  "\033[1;33m"
#define COLOR_CYAN    "\033[1;36m"
#define COLOR_BOLD    "\033[1m"

static volatile int g_running = 1;
void sig_handler(int sig) { (void)sig; g_running = 0; }

static int is_blacklisted(const char* mac, uint32_t dev_cls) {
    const char* blacklist[] = {
        "DC:03:98:E2:22:67", /* LG TV */
        "C8:AA:B2:61:3B:A0", /* SWTV */
        "3C:C5:DD:93:65:94", /* Gaoshengda Smart TV/Audio */
        "06:19:A9:56:7B:80", /* DR06 BT Smartwatch */
        "4C:91:57:86:17:80", /* APOS */
        "26:FB:E3:F8:0C:38", /* Printer */
        "CC:B1:1A:E5:E0:95", /* Samsung TV */
        "8C:CD:E8:23:90:8D", /* White Controller already paired */
        NULL
    };
    for (int i = 0; blacklist[i]; i++) {
        if (strcasecmp(mac, blacklist[i]) == 0) return 1;
    }
    /* Strictly filter out Audio/Video devices (Class 0x0400 major) */
    if ((dev_cls & 0x001F00) == 0x000400) return 1;
    /* Strictly filter out Wearable devices (Class 0x0700 major) */
    if ((dev_cls & 0x001F00) == 0x000700) return 1;
    /* Filter out TVs and audio service classes */
    if (dev_cls == 0x2C0414 || dev_cls == 0x2C0420 || dev_cls == 0x0C243C) return 1;
    return 0;
}

int main(void) {
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    printf("%s==================================================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   Wii U Pro Black Controller Dedicated LIAC Hunter (Dolphin Mode)%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s==================================================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("[*] Pure LIAC (0x9E8B00) Low-Level Radio Inquiry active.\n");
    printf("[*] Standard Bluetooth (GIAC) ignored - strictly hunting 3rd-party clones.\n");
    printf("[*] Keep the black controller 5-10cm from your laptop.\n\n");

    int dev_id = hci_get_route(NULL);
    int sock = hci_open_dev(dev_id);
    if (dev_id < 0 || sock < 0) {
        fprintf(stderr, "%s[!] Error opening local Bluetooth adapter (hci0).%s\n", COLOR_RED, COLOR_RESET);
        return 1;
    }

    bdaddr_t local_bdaddr;
    hci_devba(dev_id, &local_bdaddr);
    char local_mac[19] = { 0 };
    ba2str(&local_bdaddr, local_mac);
    printf("[*] Local Bluetooth Adapter: %s%s%s\n", COLOR_BOLD, local_mac, COLOR_RESET);

    printf("\n%s[!] ACTION REQUIRED:%s\n", COLOR_YELLOW, COLOR_RESET);
    printf("  1. Ensure your real Wii U console is UNPLUGGED from power.\n");
    printf("  2. Hold the black controller 5-10cm from the laptop keyboard.\n");
    printf("  3. Press the %sRED SYNC BUTTON%s firmly (or hold for 3-5 seconds).\n\n", COLOR_BOLD, COLOR_RESET);

    printf("[*] Actively sweeping 2.4 GHz spectrum with LIAC pulses... (Ctrl+C to stop)\n");

    int round = 1;
    while (g_running) {
        printf("\r[*] [Round %d] Pulsing LIAC inquiry (0x9E8B00)...   ", round++);
        fflush(stdout);

        inquiry_info* ii = NULL;
        uint8_t lap[3] = {0x00, 0x8b, 0x9e}; /* LIAC 0x9E8B00 */
        int len = 3; /* ~3.84 seconds */
        int max_rsp = 255;
        int flags = IREQ_CACHE_FLUSH;

        int num_rsp = hci_inquiry(dev_id, len, max_rsp, lap, &ii, flags);
        if (num_rsp > 0) {
            for (int i = 0; i < num_rsp; i++) {
                char mac[19] = { 0 };
                ba2str(&(ii + i)->bdaddr, mac);
                uint32_t dev_cls = ((uint32_t)(ii + i)->dev_class[2] << 16) |
                                   ((uint32_t)(ii + i)->dev_class[1] << 8) |
                                   ((uint32_t)(ii + i)->dev_class[0]);

                if (is_blacklisted(mac, dev_cls)) {
                    continue;
                }

                printf("\n\n%s==================================================================%s\n", COLOR_GREEN, COLOR_RESET);
                printf("%s[+] TARGET CLONE DETECTED: %s%s%s (Class: 0x%06X)\n", COLOR_GREEN, COLOR_BOLD, mac, COLOR_GREEN, dev_cls);
                printf("%s==================================================================%s\n", COLOR_GREEN, COLOR_RESET);
                printf("[*] Launching auto-connect and pairing agent for %s...\n", mac);

                /* Call smart_connect to pair and bond this target MAC */
                char cmd[256];
                snprintf(cmd, sizeof(cmd), "/home/enrico/Documents/workspace/wiiupro-usb/tools/smart_connect.py --target %s", mac);
                free(ii);
                close(sock);

                system(cmd);
                return 0;
            }
        }
        if (ii) free(ii);
        usleep(200000);
    }

    close(sock);
    printf("\n[*] Stopped.\n");
    return 0;
}
