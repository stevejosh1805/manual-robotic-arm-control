# Manual Robotic Arm Control (6-DOF, ESP32 + PCA9685)

## 🌐 Control it from the browser

**https://stevejosh1805.github.io/manual-robotic-arm-control/**

Plug the ESP32 into your laptop over USB, open the link in **Chrome or Edge**, and click **Connect USB**.
The page talks to the arm directly through the Web Serial API, so there's nothing to install. Use **Simulation** to try it without hardware.

---

Everything needed to **manually operate** a 6-DOF hobby robotic arm
(HowToMechatronics-style: MG996R ×3 + SG90 ×3):

* **ESP32 firmware** – smooth, speed-limited motion with joint limits, text serial protocol
* **Desktop GUI** (Python/Tkinter) – sliders, keyboard jogging, gripper buttons, teach & playback of poses
* **Stand-alone pot mode** – drive the arm from 6 potentiometers with no PC
* **Terminal tool** – for a headless Raspberry Pi or quick tests
* **Docs** – wiring, power, calibration and safety

This is the manual-control base layer for the machine-vision inspection station
(camera → classical dimensional measurement → arm rotates / sorts parts).

```
manual-robotic-arm-control/
├── firmware/esp32_arm_controller/esp32_arm_controller.ino
├── host/
│   ├── arm_gui.py          # slider + keyboard GUI, teach/playback
│   ├── arm_cli.py          # terminal controller
│   └── requirements.txt
├── config/poses_example.json   # sample pick-and-place sequence
└── docs/
    ├── wiring.md
    └── calibration.md
```

## Hardware

| Item | Qty | Notes |
|------|-----|-------|
| 6-DOF arm frame (3D-printed / kit) | 1 | L1 = 125 mm shoulder→elbow, L2 = 85 mm elbow→wrist |
| MG996R servo | 3 | waist, shoulder, elbow |
| SG90 / MG90S servo | 3 | wrist roll, wrist pitch, gripper (MG90S recommended – metal gears) |
| ESP32 DevKit V1 | 1 | |
| PCA9685 16-ch PWM board | 1 | I2C address 0x40 |
| 5–6 V, ≥5 A power supply | 1 | servos only – **not** from USB |
| 1000 µF capacitor | 1 | across servo V+ / GND |
| 10 kΩ linear pots *(optional)* | 6 | stand-alone manual mode |
| Jumper wires, USB cable | – | |

Full pin-out: **[docs/wiring.md](docs/wiring.md)**

## Quick start

### 1. Flash the ESP32
1. Arduino IDE → *Boards Manager* → install **esp32 by Espressif**.
2. *Library Manager* → install **Adafruit PWM Servo Driver Library**.
3. Open `firmware/esp32_arm_controller/esp32_arm_controller.ino`, board **ESP32 Dev Module**, upload.
4. Serial Monitor (115200, *Newline*) should print `READY 6DOF-ARM`.

### 2. Run the GUI
```bash
cd host
pip install -r requirements.txt
python arm_gui.py
```
Pick the ESP32 port (or **SIMULATION** to try without hardware) → **Connect**.

### 3. Calibrate
Follow **[docs/calibration.md](docs/calibration.md)** before running at full speed.

## GUI controls

| Control | Action |
|---------|--------|
| Sliders | set each joint angle (sent at ≤20 Hz) |
| `Q/A` `W/S` `E/D` `R/F` `T/G` `Y/H` | jog waist / shoulder / elbow / wrist roll / wrist pitch / gripper (+/−) |
| `Space` / `Esc` | **STOP** (freeze in place) |
| HOME | return to 90,90,90,90,90,180 |
| Grip open / close | gripper 180° / 90° |
| Servos OFF / ON | release torque / re-energise |
| Speed | max joint speed 10–360 °/s (firmware ramps every move) |
| Potentiometer mode | hand control to the pot box |
| Save pose → Play sequence | teach-and-repeat with adjustable dwell, optional loop |
| Save / Load JSON | store sequences (see `config/poses_example.json`) |

## Serial protocol (115200 baud, one line per command)

| Command | Example | Meaning |
|---------|---------|---------|
| `a0,a1,a2,a3,a4,a5` | `90,90,90,90,90,180` | all six targets (deg) |
| `J <i> <deg>` | `J 5 90` | single joint (0 = waist … 5 = gripper) |
| `HOME` | | go to home pose |
| `STOP` | | hold current position |
| `SPEED <dps>` | `SPEED 60` | max speed 5–360 °/s |
| `MODE SERIAL` / `MODE POT` | | input source |
| `OFF` / `ON` | | release / enable servos |
| `?` | | → `POS 90.0,90.0,... MODE SERIAL SPEED 90 EN 1` |

Replies: `OK …` or `ERR <reason>`. Out-of-range angles are clamped to the joint limits.
The format is the same comma-separated 6-angle string used by earlier host scripts,
so existing vision / pick-and-place code can drive this firmware unchanged.

## Safety

* Servos snap to HOME at power-up – keep hands and objects clear.
* Always share ground between ESP32 and the servo supply.
* Start at `SPEED 30–60` until joint limits are verified.
* Don't hold the gripper stalled on an object for long – SG90s overheat.

## Roadmap
- [ ] Inverse kinematics (x, y, z) jogging using L1/L2
- [ ] Camera-to-arm coordinate calibration for the vision inspection station
- [ ] Rotation-stage routine (present part to camera at N views)
- [ ] Accept / reject sorting routine driven by measurement result

## License
MIT – see [LICENSE](LICENSE).
