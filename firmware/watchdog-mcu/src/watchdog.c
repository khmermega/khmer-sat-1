/* KHMER-SAT 1 watchdog MCU core logic. See include/watchdog.h. */
#include "watchdog.h"

#include <stdio.h>
#include <string.h>

/* Wrap-safe elapsed time for a free-running 32-bit millisecond counter. */
static uint32_t elapsed(uint32_t now, uint32_t since) { return now - since; }

ks_wdt_config_t ks_wdt_default_config(void) {
    ks_wdt_config_t c;
    c.timeout_ms = 10000u;
    c.reset_pulse_ms = 200u;
    c.boot_grace_ms = 30000u;
    c.storm_threshold = 3u;
    c.storm_window_ms = 3600000u;
    c.power_off_ms = 5000u;
    c.uv_threshold_mv = 3100u;
    c.uv_hysteresis_mv = 150u;
    return c;
}

static void enter(ks_wdt_t *w, ks_wdt_state_t s, uint32_t now) {
    w->state = s;
    w->state_since_ms = now;
}

bool ks_wdt_init(ks_wdt_t *w, const ks_wdt_config_t *cfg, const ks_wdt_hal_t *hal, uint32_t now_ms) {
    if (!w || !cfg || !hal || !hal->set_reset_line || !hal->set_obc_power) return false;
    if (cfg->timeout_ms == 0u || cfg->reset_pulse_ms == 0u || cfg->storm_threshold == 0u ||
        cfg->storm_threshold > KS_WDT_STORM_SLOTS) {
        return false;
    }
    memset(w, 0, sizeof(*w));
    w->cfg = *cfg;
    w->hal = *hal;
    w->hal.set_obc_power(true);
    w->hal.set_reset_line(false);
    w->last_kick_ms = now_ms;
    enter(w, KS_WDT_GRACE, now_ms);
    return true;
}

void ks_wdt_kick(ks_wdt_t *w, uint32_t now_ms) {
    if (w->state == KS_WDT_ARMED || w->state == KS_WDT_GRACE) {
        w->last_kick_ms = now_ms;
        if (w->state == KS_WDT_GRACE) enter(w, KS_WDT_ARMED, now_ms);
    }
}

/* Count resets inside the storm window (ring buffer of timestamps). */
static uint32_t recent_resets(const ks_wdt_t *w, uint32_t now) {
    uint32_t n = 0u;
    for (uint32_t i = 0u; i < w->storm_fill; i++) {
        if (elapsed(now, w->storm_times[i]) <= w->cfg.storm_window_ms) n++;
    }
    return n;
}

static void trigger_reset(ks_wdt_t *w, uint32_t now) {
    w->reset_count++;
    w->storm_times[w->storm_head] = now;
    w->storm_head = (w->storm_head + 1u) % KS_WDT_STORM_SLOTS;
    if (w->storm_fill < KS_WDT_STORM_SLOTS) w->storm_fill++;
    if (recent_resets(w, now) >= w->cfg.storm_threshold) {
        w->hal.set_obc_power(false);
        w->power_cycles++;
        enter(w, KS_WDT_POWER_CYCLE, now);
        /* Clear history so the next window starts fresh after the power cycle. */
        /* reset_count itself is preserved for telemetry. */
        memset(w->storm_times, 0, sizeof(w->storm_times));
        w->storm_head = 0u;
        w->storm_fill = 0u;
    } else {
        w->hal.set_reset_line(true);
        enter(w, KS_WDT_RESETTING, now);
    }
}

void ks_wdt_step(ks_wdt_t *w, uint32_t now_ms, uint32_t bus_mv) {
    /* Brown-out protection takes priority over everything else. */
    if (w->state != KS_WDT_UNDERVOLTAGE && bus_mv < w->cfg.uv_threshold_mv) {
        w->hal.set_reset_line(true);
        enter(w, KS_WDT_UNDERVOLTAGE, now_ms);
        return;
    }
    switch (w->state) {
    case KS_WDT_UNDERVOLTAGE:
        if (bus_mv >= w->cfg.uv_threshold_mv + w->cfg.uv_hysteresis_mv) {
            w->hal.set_reset_line(false);
            w->last_kick_ms = now_ms;
            enter(w, KS_WDT_GRACE, now_ms);
        }
        break;
    case KS_WDT_ARMED:
        if (elapsed(now_ms, w->last_kick_ms) > w->cfg.timeout_ms) trigger_reset(w, now_ms);
        break;
    case KS_WDT_GRACE:
        if (elapsed(now_ms, w->state_since_ms) > w->cfg.boot_grace_ms) trigger_reset(w, now_ms);
        break;
    case KS_WDT_RESETTING:
        if (elapsed(now_ms, w->state_since_ms) >= w->cfg.reset_pulse_ms) {
            w->hal.set_reset_line(false);
            w->last_kick_ms = now_ms;
            enter(w, KS_WDT_GRACE, now_ms);
        }
        break;
    case KS_WDT_POWER_CYCLE:
        if (elapsed(now_ms, w->state_since_ms) >= w->cfg.power_off_ms) {
            w->hal.set_obc_power(true);
            w->last_kick_ms = now_ms;
            enter(w, KS_WDT_GRACE, now_ms);
        }
        break;
    }
}

const char *ks_wdt_state_name(ks_wdt_state_t s) {
    switch (s) {
    case KS_WDT_ARMED: return "ARMED";
    case KS_WDT_RESETTING: return "RESETTING";
    case KS_WDT_GRACE: return "GRACE";
    case KS_WDT_POWER_CYCLE: return "POWER_CYCLE";
    case KS_WDT_UNDERVOLTAGE: return "UNDERVOLTAGE";
    }
    return "UNKNOWN";
}

bool ks_wdt_handle_line(ks_wdt_t *w, const char *line, uint32_t now_ms, char *reply, uint32_t reply_len) {
    if (!line || !reply || reply_len == 0u) return false;
    /* Trim trailing CR/LF/space without modifying the caller's buffer. */
    size_t n = strlen(line);
    while (n > 0u && (line[n - 1] == '\n' || line[n - 1] == '\r' || line[n - 1] == ' ')) n--;
    if (n == 2u && strncmp(line, "HB", 2) == 0) {
        ks_wdt_kick(w, now_ms);
        snprintf(reply, reply_len, "OK %lu", (unsigned long)w->reset_count);
    } else if (n == 6u && strncmp(line, "STATUS", 6) == 0) {
        snprintf(reply, reply_len, "STATE %s RESETS %lu CYCLES %lu", ks_wdt_state_name(w->state),
                 (unsigned long)w->reset_count, (unsigned long)w->power_cycles);
    } else {
        snprintf(reply, reply_len, "ERR");
    }
    return true;
}
