/*
 * ESP32 + PCA9685 controller for a 6-DOF hobby robotic arm
 * (HowToMechatronics-style: MG996R on waist/shoulder/elbow, SG90 on wrist roll/pitch/gripper)
 *
 * Two manual operation modes:
 *   SERIAL : angles come from the PC (arm_gui.py sliders / keyboard jog / pose playback)
 *   POT    : angles come from 6 potentiometers wired to the ESP32 ADC (stand-alone, no PC)
 *
 * Every command is one text line terminated by '\n' at 115200 baud:
 *   a0,a1,a2,a3,a4,a5   set all 6 target angles (deg)  e.g. 90,90,90,90,90,180
 *   J <i> <deg>         set one joint target            e.g. J 5 90
 *   HOME                go to home pose
 *   STOP                freeze at current position
 *   SPEED <deg/s>       max joint speed (5..360)
 *   MODE SERIAL|POT     select input source
 *   OFF / ON            release / re-energise servos
 *   ?                   report -> "POS a0,...,a5 MODE x SPEED y EN z"
 *
 * Wiring: PCA9685 SDA->GPIO21, SCL->GPIO22, VCC->3V3, GND common with servo supply,
 *         V+ -> external 5-6 V / >=5 A supply. Servos on channels 0..5.
 *
 * Library: "Adafruit PWM Servo Driver Library" (Library Manager)
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ------------------------------- configuration -------------------------------
const uint8_t N = 6;
const char *NAMES[N]      = {"waist", "shoulder", "elbow", "wrist_roll", "wrist_pitch", "gripper"};
const uint8_t CHANNEL[N]  = {0, 1, 2, 3, 4, 5};

// Pulse width (us) at 0 deg and 180 deg  -> tune per servo (see docs/calibration.md)
const uint16_t PULSE_MIN[N] = {500, 500, 500, 500, 500, 500};
const uint16_t PULSE_MAX[N] = {2500, 2500, 2500, 2400, 2400, 2400};

// Software joint limits (deg) -> stop the arm from hitting itself / the table
const float LIMIT_MIN[N] = {0, 15, 0, 0, 0, 90};     // gripper: 90 = closed
const float LIMIT_MAX[N] = {180, 165, 180, 180, 180, 180}; // gripper: 180 = open
const float HOME_POSE[N] = {90, 90, 90, 90, 90, 180};

// Potentiometer inputs (ADC1 pins only - ADC2 does not work with WiFi on)
const uint8_t POT_PIN[N] = {36, 39, 34, 35, 32, 33};
const float POT_DEADBAND_DEG = 1.5;   // ignore jitter smaller than this
const float POT_EMA_ALPHA    = 0.15;  // 0..1, lower = smoother

const uint8_t I2C_SDA = 21, I2C_SCL = 22;
const uint32_t BAUD = 115200;
const uint32_t UPDATE_MS = 20;        // 50 Hz motion loop

// --------------------------------- state -------------------------------------
Adafruit_PWMServoDriver pwm(0x40);
float cur[N], tgt[N], potFilt[N];
float speedDps = 90.0;
bool enabled = true;
enum Mode { MODE_SERIAL, MODE_POT };
Mode mode = MODE_SERIAL;
String lineBuf;
uint32_t lastUpdate = 0;

// -------------------------------- helpers ------------------------------------
float clampJoint(uint8_t i, float deg) {
  if (deg < LIMIT_MIN[i]) return LIMIT_MIN[i];
  if (deg > LIMIT_MAX[i]) return LIMIT_MAX[i];
  return deg;
}

void writeServo(uint8_t i, float deg) {
  uint16_t us = PULSE_MIN[i] + (uint16_t)((PULSE_MAX[i] - PULSE_MIN[i]) * deg / 180.0f);
  pwm.writeMicroseconds(CHANNEL[i], us);
}

void releaseServos() {
  for (uint8_t i = 0; i < N; i++) pwm.setPWM(CHANNEL[i], 0, 4096); // full OFF
}

void report() {
  Serial.print("POS ");
  for (uint8_t i = 0; i < N; i++) {
    Serial.print(cur[i], 1);
    if (i < N - 1) Serial.print(',');
  }
  Serial.print(" MODE ");
  Serial.print(mode == MODE_POT ? "POT" : "SERIAL");
  Serial.print(" SPEED ");
  Serial.print(speedDps, 0);
  Serial.print(" EN ");
  Serial.println(enabled ? 1 : 0);
}

void err(const String &msg) {
  Serial.print("ERR ");
  Serial.println(msg);
}

// ----------------------------- command parser --------------------------------
void handleLine(String s) {
  s.trim();
  if (s.length() == 0) return;
  String up = s;
  up.toUpperCase();

  if (up == "?")    { report(); return; }
  if (up == "HOME") { for (uint8_t i = 0; i < N; i++) tgt[i] = HOME_POSE[i]; Serial.println("OK HOME"); return; }
  if (up == "STOP") { for (uint8_t i = 0; i < N; i++) tgt[i] = cur[i];       Serial.println("OK STOP"); return; }
  if (up == "OFF")  { enabled = false; releaseServos(); Serial.println("OK OFF"); return; }
  if (up == "ON")   { enabled = true;  for (uint8_t i = 0; i < N; i++) writeServo(i, cur[i]); Serial.println("OK ON"); return; }

  if (up.startsWith("SPEED")) {
    float v = s.substring(5).toFloat();
    if (v < 5 || v > 360) { err("speed 5..360"); return; }
    speedDps = v;
    Serial.println("OK SPEED");
    return;
  }
  if (up.startsWith("MODE")) {
    if (up.indexOf("POT") > 0)         { mode = MODE_POT;    for (uint8_t i = 0; i < N; i++) potFilt[i] = cur[i]; }
    else if (up.indexOf("SERIAL") > 0) { mode = MODE_SERIAL; for (uint8_t i = 0; i < N; i++) tgt[i] = cur[i]; }
    else { err("MODE SERIAL|POT"); return; }
    Serial.println("OK MODE");
    return;
  }
  if (up.startsWith("J ")) {
    if (mode != MODE_SERIAL) { err("in POT mode"); return; }
    int sp = s.indexOf(' ', 2);
    if (sp < 0) { err("J <i> <deg>"); return; }
    int i = s.substring(2, sp).toInt();
    if (i < 0 || i >= N) { err("joint 0..5"); return; }
    tgt[i] = clampJoint(i, s.substring(sp + 1).toFloat());
    Serial.println("OK");
    return;
  }

  // "a0,a1,a2,a3,a4,a5"
  if (mode != MODE_SERIAL) { err("in POT mode"); return; }
  float vals[N];
  uint8_t n = 0;
  int start = 0;
  while (n < N) {
    int comma = s.indexOf(',', start);
    String tok = (comma < 0) ? s.substring(start) : s.substring(start, comma);
    tok.trim();
    if (tok.length() == 0) break;
    vals[n++] = tok.toFloat();
    if (comma < 0) break;
    start = comma + 1;
  }
  if (n != N) { err("need 6 comma-separated angles"); return; }
  for (uint8_t i = 0; i < N; i++) tgt[i] = clampJoint(i, vals[i]);
  Serial.println("OK");
}

// ---------------------------------- pots -------------------------------------
void readPots() {
  for (uint8_t i = 0; i < N; i++) {
    float raw = analogRead(POT_PIN[i]);                       // 0..4095
    float deg = LIMIT_MIN[i] + (LIMIT_MAX[i] - LIMIT_MIN[i]) * raw / 4095.0f;
    potFilt[i] += POT_EMA_ALPHA * (deg - potFilt[i]);
    if (fabs(potFilt[i] - tgt[i]) > POT_DEADBAND_DEG) tgt[i] = clampJoint(i, potFilt[i]);
  }
}

// --------------------------------- motion ------------------------------------
void stepMotion(float dt) {
  float maxStep = speedDps * dt;
  for (uint8_t i = 0; i < N; i++) {
    float d = tgt[i] - cur[i];
    if (fabs(d) < 0.05f) continue;
    if (d > maxStep) d = maxStep;
    if (d < -maxStep) d = -maxStep;
    cur[i] += d;
    if (enabled) writeServo(i, cur[i]);
  }
}

// ---------------------------------- main -------------------------------------
void setup() {
  Serial.begin(BAUD);
  Wire.begin(I2C_SDA, I2C_SCL);
  pwm.begin();
  pwm.setOscillatorFrequency(27000000); // typical PCA9685 board; trim if angles are off
  pwm.setPWMFreq(50);
  analogReadResolution(12);
  delay(10);

  for (uint8_t i = 0; i < N; i++) {
    cur[i] = tgt[i] = potFilt[i] = HOME_POSE[i];
    writeServo(i, cur[i]);
    delay(150);  // stagger start-up to limit inrush current
  }
  Serial.println("READY 6DOF-ARM");
  report();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineBuf.length()) handleLine(lineBuf);
      lineBuf = "";
    } else if (lineBuf.length() < 96) {
      lineBuf += c;
    }
  }

  uint32_t now = millis();
  if (now - lastUpdate >= UPDATE_MS) {
    float dt = (now - lastUpdate) / 1000.0f;
    lastUpdate = now;
    if (mode == MODE_POT) readPots();
    stepMotion(dt);
  }
}
