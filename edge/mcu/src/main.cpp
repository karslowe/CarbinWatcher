/*
 * CarbinWatcher MCU firmware
 *
 * Hardware: Arduino UNO Q (or UNO R4 WiFi) + Modulino Distance / Pixels / Buzzer
 *
 * Serial protocol (115200 baud, line-based ASCII):
 *   MCU  → Linux : "DIST:<mm>\n"          — distance reading every DIST_INTERVAL_MS
 *   Linux → MCU  : "CMD:<TYPE>:<ARG>\n"   — feedback command
 *
 * CMD types:
 *   LED  GREEN   — all 8 pixels green   (correct bin)
 *   LED  RED     — all 8 pixels red     (wrong bin)
 *   LED  SPLIT   — alternating amber    (multiple items, ask user to split)
 *   LED  OFF     — all pixels off
 *   BUZZ <n>     — buzz n times at 1 kHz, 200 ms each
 */

#include <Arduino.h>
#include <Arduino_Modulino.h>

ModulinoDistance distance;
ModulinoPixels   pixels;
ModulinoBuzzer   buzzer;

static constexpr unsigned long DIST_INTERVAL_MS = 100;
static unsigned long lastDistMs = 0;

// ---------------------------------------------------------------------------
// LED helpers
// ---------------------------------------------------------------------------
static void setAll(uint8_t r, uint8_t g, uint8_t b, uint8_t brightness = 50) {
    for (int i = 0; i < 8; i++) {
        pixels.set(i, r, g, b, brightness);
    }
    pixels.show();
}

static void ledGreen()  { setAll(0,   255, 0); }
static void ledRed()    { setAll(255, 0,   0); }
static void ledOff()    { setAll(0,   0,   0); }

static void ledSplit() {
    for (int i = 0; i < 8; i++) {
        if (i % 2 == 0) {
            pixels.set(i, 255, 165, 0, 50);  // amber
        } else {
            pixels.set(i, 0, 0, 0, 0);
        }
    }
    pixels.show();
}

// ---------------------------------------------------------------------------
// Command parser
// ---------------------------------------------------------------------------
struct Cmd {
    char type[16];
    char arg[16];
};

static Cmd parseCmd(const String& line) {
    Cmd cmd = {};
    // Format: CMD:<type>:<arg>
    int first  = line.indexOf(':');          // after "CMD"
    int second = line.indexOf(':', first + 1);
    if (first < 0) return cmd;

    String t = (second > 0) ? line.substring(first + 1, second)
                             : line.substring(first + 1);
    String a = (second > 0) ? line.substring(second + 1) : "";

    t.trim(); a.trim();
    t.toCharArray(cmd.type, sizeof(cmd.type));
    a.toCharArray(cmd.arg,  sizeof(cmd.arg));
    return cmd;
}

static void handleLED(const char* arg) {
    String a(arg);
    if      (a == "GREEN") ledGreen();
    else if (a == "RED")   ledRed();
    else if (a == "SPLIT") ledSplit();
    else if (a == "OFF")   ledOff();
}

static void handleBuzz(const char* arg) {
    int times = max(1, min(atoi(arg), 10));  // clamp 1–10
    for (int i = 0; i < times; i++) {
        buzzer.tone(1000, 200);
        delay(300);
    }
}

// ---------------------------------------------------------------------------
// Arduino lifecycle
// ---------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    while (!Serial) {}  // wait for USB CDC to enumerate

    Modulino.begin();
    distance.begin();
    pixels.begin();
    buzzer.begin();

    ledOff();
}

void loop() {
    unsigned long now = millis();

    // Emit distance reading at DIST_INTERVAL_MS cadence
    if (now - lastDistMs >= DIST_INTERVAL_MS) {
        lastDistMs = now;
        if (distance.available()) {
            float dist = distance.get();
            Serial.print("DIST:");
            Serial.println(dist, 0);
        }
    }

    // Process incoming commands from Linux
    if (Serial.available()) {
        String line = Serial.readStringUntil('\n');
        line.trim();
        if (line.startsWith("CMD:")) {
            Cmd cmd = parseCmd(line);
            if (strcmp(cmd.type, "LED")  == 0) handleLED(cmd.arg);
            if (strcmp(cmd.type, "BUZZ") == 0) handleBuzz(cmd.arg);
        }
    }
}
