# Servo calibration & first power-up

Do this **once per arm**, before assembling the links if possible.

## 1. Centre every servo before mounting horns

1. Flash the firmware, connect servos (no arm links yet), power on.
2. All servos go to **HOME** (90°, gripper 180°).
3. Fit each horn so the link is in its "home" orientation:
   * waist facing forward, shoulder vertical, elbow at 90° to the upper arm,
     wrist straight, gripper fully open.

## 2. Find the real pulse range

Cheap MG996R / SG90 clones rarely span exactly 500–2500 µs.

1. Open `host/arm_cli.py` (or the Arduino Serial Monitor at 115200, newline ending).
2. For each joint send `J <i> 0` and `J <i> 180`.
3. If the servo buzzes / strains at an end, it is past its mechanical stop:
   raise `PULSE_MIN[i]` or lower `PULSE_MAX[i]` in 50 µs steps and re-flash.
4. If 0→180 gives clearly less than 180° of travel, widen the range slightly.

```cpp
const uint16_t PULSE_MIN[N] = {500, 500, 500, 500, 500, 500};
const uint16_t PULSE_MAX[N] = {2500, 2500, 2500, 2400, 2400, 2400};
```

If **every** servo is off by the same amount, trim `pwm.setOscillatorFrequency()`
(typical PCA9685 boards: 25–27 MHz).

## 3. Set software joint limits

With the arm assembled, jog each joint slowly (`SPEED 30`) until just before it
hits the base, the table or another link. Copy those angles into `LIMIT_MIN / LIMIT_MAX`
in the firmware **and** into `JOINTS` at the top of `host/arm_gui.py`.

## 4. Gripper

Adjust `GRIPPER_OPEN / GRIPPER_CLOSED` (GUI) and gripper limits (firmware) so the
closed position just grips your test object; continuous stall will overheat an SG90.

## Safety checklist

- [ ] Common ground between ESP32 and servo supply
- [ ] Separate ≥5 A supply for servos
- [ ] Workspace clear before power-on (servos jump to HOME)
- [ ] Start with `SPEED 30–60` until limits are verified
- [ ] `STOP` (Space/Esc in the GUI) and `OFF` known by everyone near the arm
