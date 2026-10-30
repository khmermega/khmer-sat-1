# Host build + unit tests for the portable watchdog core.
# MCU builds use the board port in src/main_rp2040.c (Pico SDK, see README).
CC ?= cc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -Wconversion -pedantic -O2 -g
CFLAGS += -Iinclude
SAN ?= -fsanitize=address,undefined -fno-omit-frame-pointer

BUILD := build

.PHONY: test clean

test: $(BUILD)/test_watchdog
	./$(BUILD)/test_watchdog

$(BUILD)/test_watchdog: src/watchdog.c test/test_watchdog.c include/watchdog.h | $(BUILD)
	$(CC) $(CFLAGS) $(SAN) src/watchdog.c test/test_watchdog.c -o $@

$(BUILD):
	mkdir -p $(BUILD)

clean:
	rm -rf $(BUILD)
