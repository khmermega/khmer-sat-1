/* Host-side unit tests for the watchdog core: `make test` */
#include <stdio.h>
#include <string.h>

#include "watchdog.h"

static int failures = 0;
#define CHECK(cond)                                                              \
    do {                                                                         \
        if (!(cond)) {                                                           \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            failures++;                                                          \
        }                                                                        \
    } while (0)

static bool reset_line = false;
static bool obc_power = false;
static void hal_reset(bool a) { reset_line = a; }
static void hal_power(bool on) { obc_power = on; }
static const ks_wdt_hal_t HAL = {hal_reset, hal_power};
#define BUS_OK 5000u

static ks_wdt_t fresh(uint32_t now) {
    ks_wdt_t w;
    ks_wdt_config_t c = ks_wdt_default_config();
    CHECK(ks_wdt_init(&w, &c, &HAL, now));
    return w;
}

static void run(ks_wdt_t *w, uint32_t *t, uint32_t until, uint32_t kick_every, uint32_t bus) {
    for (; *t < until; *t += 10u) {
        if (kick_every && (*t % kick_every) == 0u) ks_wdt_kick(w, *t);
        ks_wdt_step(w, *t, bus);
    }
}

static void test_init_validation(void) {
    ks_wdt_t w;
    ks_wdt_config_t c = ks_wdt_default_config();
    c.timeout_ms = 0;
    CHECK(!ks_wdt_init(&w, &c, &HAL, 0));
    c = ks_wdt_default_config();
    c.storm_threshold = KS_WDT_STORM_SLOTS + 1u;
    CHECK(!ks_wdt_init(&w, &c, &HAL, 0));
    ks_wdt_hal_t bad = {NULL, hal_power};
    c = ks_wdt_default_config();
    CHECK(!ks_wdt_init(&w, &c, &bad, 0));
}

static void test_no_reset_with_heartbeats(void) {
    uint32_t t = 0;
    ks_wdt_t w = fresh(t);
    CHECK(obc_power && !reset_line && w.state == KS_WDT_GRACE);
    run(&w, &t, 120000u, 1000u, BUS_OK);
    CHECK(w.state == KS_WDT_ARMED);
    CHECK(w.reset_count == 0u);
}

static void test_reset_after_timeout_then_recovers(void) {
    uint32_t t = 0;
    ks_wdt_t w = fresh(t);
    run(&w, &t, 5000u, 1000u, BUS_OK); /* healthy */
    run(&w, &t, 15100u, 0u, BUS_OK);   /* heartbeats stop at ~5 s; timeout 10 s */
    CHECK(w.reset_count == 1u);
    CHECK(w.state == KS_WDT_RESETTING || w.state == KS_WDT_GRACE);
    run(&w, &t, 16000u, 0u, BUS_OK);
    CHECK(!reset_line && w.state == KS_WDT_GRACE); /* pulse released, booting */
    run(&w, &t, 20000u, 1000u, BUS_OK);            /* OBC alive again */
    CHECK(w.state == KS_WDT_ARMED && w.reset_count == 1u);
}

static void test_boot_grace_expiry_resets(void) {
    uint32_t t = 0;
    ks_wdt_t w = fresh(t);
    run(&w, &t, 31000u, 0u, BUS_OK); /* OBC never boots */
    CHECK(w.reset_count == 1u);
}

static void test_reset_storm_power_cycles(void) {
    uint32_t t = 0;
    ks_wdt_t w = fresh(t);
    run(&w, &t, 200000u, 0u, BUS_OK); /* never alive: grace expiries 3x */
    CHECK(w.power_cycles >= 1u);
    /* Find the power-off window and check power is restored afterwards. */
    t = 0;
    w = fresh(t);
    while (w.state != KS_WDT_POWER_CYCLE && t < 400000u) {
        ks_wdt_step(&w, t, BUS_OK);
        t += 10u;
    }
    CHECK(w.state == KS_WDT_POWER_CYCLE && !obc_power);
    run(&w, &t, t + 6000u, 0u, BUS_OK);
    CHECK(obc_power && w.state == KS_WDT_GRACE);
    /* Regression: a single reset after the power cycle must NOT trigger another
       power cycle (cleared storm history must not count as recent resets). */
    uint32_t cycles = w.power_cycles;
    run(&w, &t, t + 31000u, 0u, BUS_OK); /* one grace expiry */
    CHECK(w.power_cycles == cycles && w.state != KS_WDT_POWER_CYCLE);
}

static void test_undervoltage_holds_reset_with_hysteresis(void) {
    uint32_t t = 0;
    ks_wdt_t w = fresh(t);
    run(&w, &t, 2000u, 500u, BUS_OK);
    run(&w, &t, 3000u, 500u, 3000u);
    CHECK(w.state == KS_WDT_UNDERVOLTAGE && reset_line);
    run(&w, &t, 4000u, 500u, 3200u); /* above threshold but inside hysteresis */
    CHECK(w.state == KS_WDT_UNDERVOLTAGE);
    run(&w, &t, 5000u, 500u, 3300u);
    CHECK(!reset_line && (w.state == KS_WDT_GRACE || w.state == KS_WDT_ARMED));
}

static void test_counter_wraparound(void) {
    uint32_t t = 0xFFFFF000u; /* ~4 s before the 32-bit ms counter wraps */
    ks_wdt_t w = fresh(t);
    for (int i = 0; i < 2000; i++) {
        if (i % 100 == 0) ks_wdt_kick(&w, t);
        ks_wdt_step(&w, t, BUS_OK);
        t += 10u;
    }
    CHECK(w.reset_count == 0u);
}

static void test_uart_protocol(void) {
    uint32_t t = 0;
    ks_wdt_t w = fresh(t);
    char r[48];
    CHECK(ks_wdt_handle_line(&w, "HB\r\n", 100, r, sizeof r) && strcmp(r, "OK 0") == 0);
    CHECK(w.state == KS_WDT_ARMED);
    CHECK(ks_wdt_handle_line(&w, "STATUS\n", 100, r, sizeof r) && strncmp(r, "STATE ARMED", 11) == 0);
    CHECK(ks_wdt_handle_line(&w, "HBX", 100, r, sizeof r) && strcmp(r, "ERR") == 0);
    CHECK(ks_wdt_handle_line(&w, "", 100, r, sizeof r) && strcmp(r, "ERR") == 0);
    char tiny[3];
    CHECK(ks_wdt_handle_line(&w, "STATUS", 100, tiny, sizeof tiny) && strlen(tiny) == 2u); /* truncated, not overflowed */
}

int main(void) {
    test_init_validation();
    test_no_reset_with_heartbeats();
    test_reset_after_timeout_then_recovers();
    test_boot_grace_expiry_resets();
    test_reset_storm_power_cycles();
    test_undervoltage_holds_reset_with_hysteresis();
    test_counter_wraparound();
    test_uart_protocol();
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    printf("watchdog-mcu: all tests passed\n");
    return 0;
}
