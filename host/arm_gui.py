#!/usr/bin/env python3
"""
Manual control GUI for the 6-DOF ESP32 + PCA9685 robotic arm.

Features
  * one slider per joint (limits match the firmware)
  * keyboard jogging (Q/A W/S E/D R/F T/G Y/H), gripper open/close
  * HOME / STOP / servos OFF-ON / speed setting / POT mode toggle
  * teach poses, then play them back as a sequence (optionally looped)
  * save / load poses as JSON
  * SIMULATION port so you can try everything without hardware

Run:  pip install -r requirements.txt  &&  python arm_gui.py
"""

import json
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # still allow the simulator to run
    serial = None

SIM_PORT = "SIMULATION"
BAUD = 115200

JOINTS = [
    # name,          min, max, home, jog keys (+, -)
    ("Waist",          0, 180,  90, ("q", "a")),
    ("Shoulder",      15, 165,  90, ("w", "s")),
    ("Elbow",          0, 180,  90, ("e", "d")),
    ("Wrist roll",     0, 180,  90, ("r", "f")),
    ("Wrist pitch",    0, 180,  90, ("t", "g")),
    ("Gripper",       90, 180, 180, ("y", "h")),
]
GRIPPER_OPEN, GRIPPER_CLOSED = 180, 90
SEND_PERIOD_MS = 50  # max 20 commands / s to avoid flooding the ESP32


class ArmLink:
    """Thin wrapper around pyserial with a reader thread and a simulator."""

    def __init__(self, on_line):
        self.ser = None
        self.sim = False
        self.on_line = on_line
        self._stop = threading.Event()

    @staticmethod
    def ports():
        found = []
        if serial is not None:
            found = [p.device for p in serial.tools.list_ports.comports()]
        return found + [SIM_PORT]

    @property
    def connected(self):
        return self.sim or (self.ser is not None and self.ser.is_open)

    def open(self, port):
        self.close()
        if port == SIM_PORT:
            self.sim = True
            self.on_line("READY (simulation)")
            return
        if serial is None:
            raise RuntimeError("pyserial not installed: pip install pyserial")
        self.ser = serial.Serial(port, BAUD, timeout=0.1)
        time.sleep(2.0)  # ESP32 resets when the port opens
        self._stop.clear()
        threading.Thread(target=self._reader, daemon=True).start()

    def close(self):
        self._stop.set()
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.sim = False

    def send(self, line):
        if self.sim:
            self.on_line(f"> {line}")
            return
        if self.ser is not None and self.ser.is_open:
            self.ser.write((line + "\n").encode())

    def _reader(self):
        while not self._stop.is_set() and self.ser is not None:
            try:
                raw = self.ser.readline()
            except Exception as exc:
                self.on_line(f"serial error: {exc}")
                break
            if raw:
                self.on_line(raw.decode(errors="replace").strip())


class ArmGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("6-DOF Robotic Arm - Manual Control")
        self.resizable(False, False)
        self.link = ArmLink(self._queue_log)
        self.vars = [tk.DoubleVar(value=j[3]) for j in JOINTS]
        self.dirty = False
        self.poses = []          # list of {"name": str, "angles": [6 floats]}
        self.playing = False
        self._log_queue = []

        self._build_ui()
        self._bind_keys()
        self.after(SEND_PERIOD_MS, self._send_loop)
        self.after(100, self._flush_log)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # connection bar
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(bar, text="Port").pack(side="left")
        self.port_cb = ttk.Combobox(bar, width=22, values=ArmLink.ports())
        self.port_cb.pack(side="left", padx=4)
        if self.port_cb["values"]:
            self.port_cb.current(0)
        ttk.Button(bar, text="↻", width=3, command=self._refresh_ports).pack(side="left")
        self.conn_btn = ttk.Button(bar, text="Connect", command=self._toggle_connect)
        self.conn_btn.pack(side="left", padx=4)
        self.status = ttk.Label(bar, text="● disconnected", foreground="red")
        self.status.pack(side="left", padx=8)

        # joint sliders
        jf = ttk.LabelFrame(self, text="Joints (deg)")
        jf.grid(row=1, column=0, sticky="nsew", **pad)
        for i, (name, lo, hi, _home, keys) in enumerate(JOINTS):
            ttk.Label(jf, text=f"{name}  [{keys[0].upper()}/{keys[1].upper()}]", width=20).grid(
                row=i, column=0, sticky="w")
            tk.Scale(jf, from_=lo, to=hi, orient="horizontal", length=320, resolution=1,
                     variable=self.vars[i], command=lambda _v: self._mark_dirty()).grid(row=i, column=1)

        # actions
        af = ttk.LabelFrame(self, text="Actions")
        af.grid(row=2, column=0, sticky="ew", **pad)
        for col, (txt, cmd) in enumerate([
            ("HOME", self._home), ("STOP", lambda: self.link.send("STOP")),
            ("Grip open", lambda: self._set_joint(5, GRIPPER_OPEN)),
            ("Grip close", lambda: self._set_joint(5, GRIPPER_CLOSED)),
            ("Servos OFF", lambda: self.link.send("OFF")), ("Servos ON", lambda: self.link.send("ON")),
        ]):
            ttk.Button(af, text=txt, command=cmd).grid(row=0, column=col, padx=2, pady=2)

        ttk.Label(af, text="Speed °/s").grid(row=1, column=0, sticky="e")
        self.speed = tk.IntVar(value=90)
        tk.Scale(af, from_=10, to=360, orient="horizontal", length=220, variable=self.speed,
                 command=lambda v: self.link.send(f"SPEED {int(float(v))}")).grid(
            row=1, column=1, columnspan=3, sticky="w")
        self.pot_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(af, text="Potentiometer mode", variable=self.pot_mode,
                        command=self._toggle_pot).grid(row=1, column=4, columnspan=2, sticky="w")
        ttk.Label(af, text="Jog step").grid(row=2, column=0, sticky="e")
        self.jog_step = tk.IntVar(value=2)
        ttk.Spinbox(af, from_=1, to=20, width=5, textvariable=self.jog_step).grid(row=2, column=1, sticky="w")

        # poses / sequence
        pf = ttk.LabelFrame(self, text="Teach & playback")
        pf.grid(row=1, column=1, rowspan=2, sticky="nsew", **pad)
        self.pose_list = tk.Listbox(pf, width=34, height=14)
        self.pose_list.grid(row=0, column=0, columnspan=3, padx=4, pady=4)
        self.pose_list.bind("<Double-Button-1>", lambda _e: self._goto_selected())
        btns = [("Save pose", self._save_pose), ("Go to", self._goto_selected), ("Delete", self._delete_pose),
                ("Move up", lambda: self._move_pose(-1)), ("Move down", lambda: self._move_pose(1)),
                ("Clear", self._clear_poses), ("Load JSON", self._load_json), ("Save JSON", self._save_json)]
        for k, (txt, cmd) in enumerate(btns):
            ttk.Button(pf, text=txt, command=cmd).grid(row=1 + k // 3, column=k % 3, sticky="ew", padx=2, pady=2)

        ttk.Label(pf, text="Dwell (s)").grid(row=4, column=0, sticky="e")
        self.dwell = tk.DoubleVar(value=1.5)
        ttk.Spinbox(pf, from_=0.2, to=10, increment=0.1, width=6, textvariable=self.dwell).grid(
            row=4, column=1, sticky="w")
        self.loop = tk.BooleanVar(value=False)
        ttk.Checkbutton(pf, text="Loop", variable=self.loop).grid(row=4, column=2, sticky="w")
        self.play_btn = ttk.Button(pf, text="▶ Play sequence", command=self._toggle_play)
        self.play_btn.grid(row=5, column=0, columnspan=3, sticky="ew", padx=2, pady=4)

        # log
        lf = ttk.LabelFrame(self, text="Log")
        lf.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        self.log = tk.Text(lf, height=7, width=100, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both")

    def _bind_keys(self):
        for i, (_n, _lo, _hi, _h, (kp, km)) in enumerate(JOINTS):
            for key, sign in ((kp, 1), (km, -1)):
                self.bind(f"<KeyPress-{key}>", lambda e, i=i, s=sign: self._jog(e, i, s))
                self.bind(f"<KeyPress-{key.upper()}>", lambda e, i=i, s=sign: self._jog(e, i, s))
        self.bind("<space>", lambda e: self._ignore_in_entry(e) or self.link.send("STOP"))
        self.bind("<Escape>", lambda e: self.link.send("STOP"))

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _ignore_in_entry(event):
        return isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox, tk.Text))

    def _queue_log(self, msg):  # called from reader thread
        self._log_queue.append(msg)

    def _flush_log(self):
        while self._log_queue:
            msg = self._log_queue.pop(0)
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(100, self._flush_log)

    def _angles(self):
        return [round(v.get(), 1) for v in self.vars]

    def _mark_dirty(self):
        self.dirty = True

    def _set_joint(self, i, deg):
        lo, hi = JOINTS[i][1], JOINTS[i][2]
        self.vars[i].set(max(lo, min(hi, deg)))
        self._mark_dirty()

    def _set_all(self, angles):
        for i, a in enumerate(angles):
            self._set_joint(i, a)

    def _send_loop(self):
        if self.dirty and self.link.connected and not self.pot_mode.get():
            self.link.send(",".join(f"{a:g}" for a in self._angles()))
            self.dirty = False
        self.after(SEND_PERIOD_MS, self._send_loop)

    def _jog(self, event, i, sign):
        if self._ignore_in_entry(event):
            return
        self._set_joint(i, self.vars[i].get() + sign * self.jog_step.get())

    # ------------------------------------------------------------ actions
    def _refresh_ports(self):
        self.port_cb["values"] = ArmLink.ports()

    def _toggle_connect(self):
        if self.link.connected:
            self.link.close()
            self.conn_btn.config(text="Connect")
            self.status.config(text="● disconnected", foreground="red")
            return
        port = self.port_cb.get()
        try:
            self.link.open(port)
        except Exception as exc:
            messagebox.showerror("Connection failed", str(exc))
            return
        self.conn_btn.config(text="Disconnect")
        self.status.config(text=f"● {port}", foreground="green")
        self.link.send(f"SPEED {self.speed.get()}")
        self.link.send("?")

    def _home(self):
        self._set_all([j[3] for j in JOINTS])

    def _toggle_pot(self):
        self.link.send("MODE POT" if self.pot_mode.get() else "MODE SERIAL")
        if not self.pot_mode.get():
            self._mark_dirty()

    def _refresh_pose_list(self):
        self.pose_list.delete(0, "end")
        for k, p in enumerate(self.poses):
            self.pose_list.insert("end", f"{k + 1:02d}. {p['name']}: " + ", ".join(f"{a:g}" for a in p["angles"]))

    def _save_pose(self):
        name = simpledialog.askstring("Save pose", "Pose name:", initialvalue=f"pose{len(self.poses) + 1}",
                                      parent=self)
        if name:
            self.poses.append({"name": name, "angles": self._angles()})
            self._refresh_pose_list()

    def _selected(self):
        sel = self.pose_list.curselection()
        return sel[0] if sel else None

    def _goto_selected(self):
        k = self._selected()
        if k is not None:
            self._set_all(self.poses[k]["angles"])

    def _delete_pose(self):
        k = self._selected()
        if k is not None:
            del self.poses[k]
            self._refresh_pose_list()

    def _move_pose(self, d):
        k = self._selected()
        if k is None or not 0 <= k + d < len(self.poses):
            return
        self.poses[k], self.poses[k + d] = self.poses[k + d], self.poses[k]
        self._refresh_pose_list()
        self.pose_list.selection_set(k + d)

    def _clear_poses(self):
        if self.poses and messagebox.askyesno("Clear", "Delete all saved poses?"):
            self.poses.clear()
            self._refresh_pose_list()

    def _save_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w") as f:
                json.dump({"poses": self.poses, "dwell_s": self.dwell.get()}, f, indent=2)

    def _load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path) as f:
            data = json.load(f)
        self.poses = [p for p in data.get("poses", []) if len(p.get("angles", [])) == 6]
        if "dwell_s" in data:
            self.dwell.set(data["dwell_s"])
        self._refresh_pose_list()

    def _toggle_play(self):
        if self.playing:
            self.playing = False
            self.play_btn.config(text="▶ Play sequence")
            return
        if not self.poses:
            messagebox.showinfo("Playback", "Save at least one pose first.")
            return
        self.playing = True
        self.play_btn.config(text="■ Stop playback")
        self._play_step(0)

    def _play_step(self, k):
        if not self.playing:
            return
        if k >= len(self.poses):
            if self.loop.get():
                k = 0
            else:
                self._toggle_play()
                return
        self.pose_list.selection_clear(0, "end")
        self.pose_list.selection_set(k)
        self._set_all(self.poses[k]["angles"])
        self.after(int(self.dwell.get() * 1000), lambda: self._play_step(k + 1))

    def _on_close(self):
        self.playing = False
        self.link.close()
        self.destroy()


if __name__ == "__main__":
    ArmGUI().mainloop()
