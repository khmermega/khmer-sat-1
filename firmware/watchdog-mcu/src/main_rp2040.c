/*
 * Raspberry Pi Pico (RP2040) port of the KHMER-SAT 1 watchdog MCU.
 *
 * STATUS: written against the Pico SDK API but NOT yet built or run on
 * hardware (milestone M3). Pin assignments are bench placeholders - see
 * docs/hardware-bom.md and firmware/watchdog-mcu/README.md.
 *
 * Build:  mkdir build-pico && cd build-pico && cmake .. -DPICO_SDK_PATH=... && make
 */
#include <stdio.h>
#include <string.h>

#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "watchdog.h"

#define OBC_UART uart0
#define OBC_UART_TX 0
#define OBC_UART_RX 1
#define PIN_OBC_RESET 15   /* drives an open-drain transistor on the Pi RUN pin */
#define PIN_OBC_POWER 14   /* enables the OBC load switch */
#define ADC_BUS_PIN 26     /* OBC 5V rail through a divider (ratio TBD) */
#define ADC_DIVIDER_MV_PER_COUNT 2.44f /* placeholder: calibrate on the bench */

static void set_reset_line(bool asserted) { gpio_put(PIN_OBC_RESET, asserted); }
static void set_obc_power(bool on) { gpio_put(PIN_OBC_POWER, on); }

static uint32_t read_bus_mv(void) {
    return (uint32_t)((float)adc_read() * ADC_DIVIDER_MV_PER_COUNT);
}

int main(void) {
    stdio_init_all();
    uart_init(OBC_UART, 115200);
    gpio_set_function(OBC_UART_TX, GPIO_FUNC_UART);
    gpio_set_function(OBC_UART_RX, GPIO_FUNC_UART);
    gpio_init(PIN_OBC_RESET);
    gpio_set_dir(PIN_OBC_RESET, GPIO_OUT);
    gpio_init(PIN_OBC_POWER);
    gpio_set_dir(PIN_OBC_POWER, GPIO_OUT);
    adc_init();
    adc_gpio_init(ADC_BUS_PIN);
    adc_select_input(0);

    /* The MCU itself is guarded by the RP2040 hardware watchdog. */
    watchdog_enable(500, true);

    ks_wdt_t wdt;
    ks_wdt_config_t cfg = ks_wdt_default_config();
    ks_wdt_hal_t hal = {set_reset_line, set_obc_power};
    if (!ks_wdt_init(&wdt, &cfg, &hal, to_ms_since_boot(get_absolute_time()))) {
        while (true) tight_loop_contents(); /* hardware watchdog will reset us */
    }

    char line[32];
    size_t len = 0;
    char reply[64];
    while (true) {
        uint32_t now = to_ms_since_boot(get_absolute_time());
        while (uart_is_readable(OBC_UART)) {
            char c = uart_getc(OBC_UART);
            if (c == '\n' || len == sizeof(line) - 1) {
                line[len] = '\0';
                if (ks_wdt_handle_line(&wdt, line, now, reply, sizeof reply)) {
                    uart_puts(OBC_UART, reply);
                    uart_puts(OBC_UART, "\n");
                }
                len = 0;
            } else if (c != '\r') {
                line[len++] = c;
            }
        }
        ks_wdt_step(&wdt, now, read_bus_mv());
        watchdog_update();
        sleep_ms(5);
    }
}
