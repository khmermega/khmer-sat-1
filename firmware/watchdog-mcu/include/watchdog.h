/*
 * KHMER-SAT 1 independent watchdog & health MCU - portable core logic.
 *
 * The core is hardware-independent C99: all I/O goes through the HAL
 * function pointers in ks_wdt_hal_t, so the same code is unit-tested on the
 * host (test/test_watchdog.c) and runs on the MCU (src/main_*.c ports).
 *
 * Behaviour (mirrors onboard/safety/watchdog.py SimWatchdogMCU):
 *   - OBC sends "HB\n" heartbeats over UART; MCU answers "OK <resets>\n".
 *   - No heartbeat for timeout_ms -> assert OBC reset line for reset_pulse_ms,
 *     increment reset counter, then re-arm with a boot grace period.
 *   - >= storm_threshold resets inside storm_window_ms -> latch POWER_CYCLE
 *     request (cut OBC power via load switch for power_off_ms).
 *   - Undervoltage on the OBC rail (bus_mv < uv_threshold_mv) holds the OBC
 *     in reset (brown-out protection).
 *
 * PROTOTYPE ONLY - not flight software. Thresholds are placeholders (TBD).
 */
#ifndef KS_WATCHDOG_H
#define KS_WATCHDOG_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    KS_WDT_ARMED = 0,      /* waiting for heartbeats */
    KS_WDT_RESETTING,      /* reset line asserted */
    KS_WDT_GRACE,          /* OBC booting; heartbeats not yet required */
    KS_WDT_POWER_CYCLE,    /* reset storm: OBC power removed */
    KS_WDT_UNDERVOLTAGE    /* bus below threshold: OBC held in reset */
} ks_wdt_state_t;

typedef struct {
    uint32_t timeout_ms;
    uint32_t reset_pulse_ms;
    uint32_t boot_grace_ms;
    uint32_t storm_threshold;
    uint32_t storm_window_ms;
    uint32_t power_off_ms;
    uint32_t uv_threshold_mv;
    uint32_t uv_hysteresis_mv;
} ks_wdt_config_t;

typedef struct {
    void (*set_reset_line)(bool asserted);
    void (*set_obc_power)(bool on);
} ks_wdt_hal_t;

#define KS_WDT_STORM_SLOTS 8u

typedef struct {
    ks_wdt_config_t cfg;
    ks_wdt_hal_t hal;
    ks_wdt_state_t state;
    uint32_t last_kick_ms;
    uint32_t state_since_ms;
    uint32_t reset_count;
    uint32_t power_cycles;
    uint32_t storm_times[KS_WDT_STORM_SLOTS];
    uint32_t storm_head;
    uint32_t storm_fill; /* valid entries in storm_times */
} ks_wdt_t;

/* Sensible bench defaults (placeholders, see docs/safety.md). */
ks_wdt_config_t ks_wdt_default_config(void);

/* Returns false if the configuration is invalid. */
bool ks_wdt_init(ks_wdt_t *w, const ks_wdt_config_t *cfg, const ks_wdt_hal_t *hal, uint32_t now_ms);

/* Heartbeat received from the OBC. Ignored while resetting/power-cycling. */
void ks_wdt_kick(ks_wdt_t *w, uint32_t now_ms);

/* Periodic update (call every 1-10 ms). bus_mv = measured OBC rail voltage. */
void ks_wdt_step(ks_wdt_t *w, uint32_t now_ms, uint32_t bus_mv);

/*
 * Line-oriented UART command handler. Fills `reply` (NUL-terminated, at most
 * reply_len bytes). Commands: "HB" (heartbeat), "STATUS". Returns true if a
 * reply was produced. Unknown input yields "ERR".
 */
bool ks_wdt_handle_line(ks_wdt_t *w, const char *line, uint32_t now_ms, char *reply, uint32_t reply_len);

const char *ks_wdt_state_name(ks_wdt_state_t s);

#ifdef __cplusplus
}
#endif
#endif /* KS_WATCHDOG_H */
