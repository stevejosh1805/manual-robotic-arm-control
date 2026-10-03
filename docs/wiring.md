# Wiring

## Block diagram

```
 PC / Raspberry Pi ──USB──► ESP32 DevKit ──I2C──► PCA9685 ──PWM──► 6 servos
                              │                     ▲
                    6 pots ───┘ (optional)          │ V+ (servo power)
                                                    │
                              5–6 V, ≥5 A supply ───┘
```

## ESP32 ↔ PCA9685

| ESP32  | PCA9685 | Note |
|--------|---------|------|
| 3V3    | VCC     | logic supply only |
| GND    | GND     | **must be common** with the servo supply ground |
| GPIO21 | SDA     | |
| GPIO22 | SCL     | |
| —      | OE      | leave unconnected (pulled low on board = outputs on) |

## Servo power

| Supply | PCA9685 |
|--------|---------|
| +5–6 V | V+ screw terminal |
| GND    | GND screw terminal |

* Three MG996R can each draw **~2.5 A at stall**. Use a 5 V / ≥5 A (better 10 A) SMPS or a 2S LiPo through a 5–6 V UBEC.
* **Never** power servos from the ESP32 5 V / USB pin.
* Add a 1000 µF / 16 V electrolytic across V+ and GND close to the PCA9685.

## Servo channels

| Channel | Joint | Servo | Limits (°) | Home (°) |
|---------|-------|-------|-----------|----------|
| 0 | Waist        | MG996R | 0–180  | 90  |
| 1 | Shoulder     | MG996R | 15–165 | 90  |
| 2 | Elbow        | MG996R | 0–180  | 90  |
| 3 | Wrist roll   | SG90   | 0–180  | 90  |
| 4 | Wrist pitch  | SG90   | 0–180  | 90  |
| 5 | Gripper      | SG90   | 90 (closed) – 180 (open) | 180 |

Servo plug orientation on the PCA9685: **brown/black = GND, red = V+, orange/yellow = PWM**.

## Optional potentiometer box (stand-alone manual mode)

Six 10 kΩ linear pots: outer legs to **3V3** and **GND**, wiper to the ESP32 ADC1 pin.

| Joint | ESP32 pin |
|-------|-----------|
| Waist       | GPIO36 (VP) |
| Shoulder    | GPIO39 (VN) |
| Elbow       | GPIO34 |
| Wrist roll  | GPIO35 |
| Wrist pitch | GPIO32 |
| Gripper     | GPIO33 |

Only ADC1 pins are used, so the inputs keep working if Wi-Fi/Bluetooth is added later.
A 100 nF capacitor from each wiper to GND reduces jitter.
