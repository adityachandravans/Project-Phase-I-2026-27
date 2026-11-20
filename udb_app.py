"""
udb_app.py - Desktop application for Arduino Nano + Universal Dev Board (UDB)
Exchanges 16 Boolean + 16 Analog values over UART (pyserial + tkinter).

Protocol (ASCII lines, '\n' terminated, 9600 baud)
  Arduino -> PC : D,<16 bits>,<a0>,...,<a15>
  PC -> Arduino : C,<16 bits>,<v0>,...,<v15>

Run:   python udb_app.py          (needs: pip install pyserial)
Pick "SIMULATOR" in the port list to demo without hardware.
"""

import math
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

BAUD_DEFAULT = 9600
N = 16
SEND_PERIOD_MS = 300

# ---- channel labels (match UDB_Final.ino) ----
IN_B = ["SW1 (D11)", "SW2 (D10)", "SW3 (D9)", "SW4 (D6)"] + [f"echo B{i:02d}" for i in range(4, N)]
IN_A = ["POT (A3)", "A6 input", "A7 input", "POT %", "Uptime s"] + [f"echo A{i:02d}" for i in range(5, N)]
OUT_B = ["Relay 1", "Relay 2", "Relay 3", "LED D13", "Buzzer D3", "LED D4"] + [f"virtual B{i:02d}" for i in range(6, N)]
OUT_A = ["PWM D5"] + [f"virtual A{i:02d}" for i in range(1, N)]


# ---------------------------------------------------------------- protocol --
def build_command(bits, vals):
    """Merge 16 booleans + 16 analog values into one command string."""
    return "C," + "".join("1" if b else "0" for b in bits) + "," + \
           ",".join(str(int(v)) for v in vals) + "\n"


def parse_data(line):
    """Split 'D,<16 bits>,<16 ints>' -> (bits[16], vals[16]) or None if invalid."""
    line = line.strip()
    if not line.startswith("D,"):
        return None
    parts = line[2:].split(",")
    if len(parts) != 1 + N:
        return None
    bits_s = parts[0]
    if len(bits_s) != N or any(c not in "01" for c in bits_s):
        return None
    try:
        vals = [int(x) for x in parts[1:]]
    except ValueError:
        return None
    return [c == "1" for c in bits_s], vals


# ------------------------------------------------------------------- links --
class SerialLink:
    def __init__(self, port, baud, rx_queue):
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.q = rx_queue
        self.running = True
        time.sleep(2)                      # Nano auto-resets when the port opens
        self.ser.reset_input_buffer()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while self.running:
            try:
                raw = self.ser.readline()
            except Exception as e:
                self.q.put(("ERR", str(e)))
                break
            if raw:
                self.q.put(("RX", raw.decode(errors="ignore").strip()))

    def write(self, text):
        self.ser.write(text.encode())

    def close(self):
        self.running = False
        try:
            self.ser.close()
        except Exception:
            pass


class SimLink:
    """Fake Arduino so the UI can be demonstrated with no hardware."""
    def __init__(self, rx_queue):
        self.q = rx_queue
        self.running = True
        self.b_out = [False] * N
        self.a_out = [0] * N
        self.t0 = time.time()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            t = time.time() - self.t0
            pot = int(512 + 500 * math.sin(t / 2))
            bits = [(int(t) % 5 == i) if i < 4 else self.b_out[i] for i in range(N)]
            vals = [0] * N
            vals[0] = pot
            vals[1] = int(512 + 400 * math.sin(t))
            vals[2] = int(512 + 400 * math.cos(t))
            vals[3] = pot * 100 // 1023
            vals[4] = int(t) % 1024
            for i in range(5, N):
                vals[i] = self.a_out[i]
            self.q.put(("RX", "D," + "".join("1" if b else "0" for b in bits) + "," +
                        ",".join(map(str, vals))))
            time.sleep(0.3)

    def write(self, text):
        t = text.strip()
        if t.startswith("C,"):
            p = t[2:].split(",")
            if len(p) == N + 1 and len(p[0]) == N:
                self.b_out = [c == "1" for c in p[0]]
                try:
                    self.a_out = [int(x) for x in p[1:]]
                except ValueError:
                    pass

    def close(self):
        self.running = False


# --------------------------------------------------------------------- GUI --
class App:
    def __init__(self, root):
        self.root = root
        root.title("UDB + Arduino Nano  -  16 Boolean / 16 Analog UART Monitor")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.q = queue.Queue()
        self.link = None
        self.rx_frames = 0
        self.tx_frames = 0
        self.last_rx = 0.0

        self.out_bits = [tk.IntVar(value=0) for _ in range(N)]
        self.out_vals = [tk.IntVar(value=0) for _ in range(N)]
        self.auto_send = tk.IntVar(value=1)
        self.scales = []

        self._build_top()
        self._build_panels()
        self._build_log()
        self.refresh_ports()
        self.root.after(50, self.poll_rx)
        self.root.after(SEND_PERIOD_MS, self.send_tick)
        self.root.after(500, self.update_status)

    # ---- layout
    def _build_top(self):
        f = ttk.Frame(self.root, padding=6)
        f.pack(fill="x")
        ttk.Label(f, text="Port:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(f, textvariable=self.port_var, width=18, state="readonly")
        self.port_cb.pack(side="left", padx=4)
        ttk.Button(f, text="Refresh", command=self.refresh_ports).pack(side="left")
        ttk.Label(f, text="Baud:").pack(side="left", padx=(10, 0))
        self.baud_var = tk.StringVar(value=str(BAUD_DEFAULT))
        ttk.Combobox(f, textvariable=self.baud_var, width=8, state="readonly",
                     values=["9600", "19200", "38400", "57600", "115200"]).pack(side="left", padx=4)
        self.conn_btn = ttk.Button(f, text="Connect", command=self.toggle_connect)
        self.conn_btn.pack(side="left", padx=10)
        ttk.Checkbutton(f, text="Auto-send every 300 ms", variable=self.auto_send).pack(side="left")
        ttk.Button(f, text="Send now", command=self.send_now).pack(side="left", padx=6)
        self.status = ttk.Label(f, text="Disconnected", foreground="red")
        self.status.pack(side="right")

    def _build_panels(self):
        main = ttk.Frame(self.root, padding=6)
        main.pack(fill="both", expand=True)

        inp = ttk.LabelFrame(main, text="Arduino -> PC   (Boolean + Analog inputs)", padding=6)
        inp.grid(row=0, column=0, sticky="nsew", padx=4)
        self.leds, self.bars, self.val_lbls = [], [], []
        for i in range(N):
            c = tk.Canvas(inp, width=18, height=18, highlightthickness=0)
            led = c.create_oval(2, 2, 16, 16, fill="grey30", outline="black")
            c.grid(row=i, column=0, padx=2, pady=1)
            ttk.Label(inp, text=f"B{i:02d} {IN_B[i]}", width=17).grid(row=i, column=1, sticky="w")
            ttk.Label(inp, text=f"A{i:02d} {IN_A[i]}", width=17).grid(row=i, column=2, sticky="w", padx=(8, 2))
            bar = ttk.Progressbar(inp, maximum=1023, length=120)
            bar.grid(row=i, column=3, padx=2)
            v = ttk.Label(inp, text="0", width=5, anchor="e")
            v.grid(row=i, column=4)
            self.leds.append((c, led)); self.bars.append(bar); self.val_lbls.append(v)

        out = ttk.LabelFrame(main, text="PC -> Arduino   (Boolean + Analog outputs)", padding=6)
        out.grid(row=0, column=1, sticky="nsew", padx=4)
        for i in range(N):
            ttk.Checkbutton(out, text=f"B{i:02d} {OUT_B[i]}", variable=self.out_bits[i],
                            width=18).grid(row=i, column=0, sticky="w")
            ttk.Label(out, text=f"A{i:02d} {OUT_A[i]}", width=17).grid(row=i, column=1, sticky="w", padx=(8, 2))
            sc = ttk.Scale(out, from_=0, to=1023, orient="horizontal", length=130,
                           command=lambda v, k=i: self.out_vals[k].set(int(float(v))))
            sc.grid(row=i, column=2)
            self.scales.append(sc)
            ttk.Label(out, textvariable=self.out_vals[i], width=5, anchor="e").grid(row=i, column=3)
        ttk.Button(out, text="All OFF / 0", command=self.reset_outputs).grid(
            row=N, column=0, columnspan=4, pady=6)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

    def _build_log(self):
        lf = ttk.LabelFrame(self.root, text="Serial log (raw strings)", padding=4)
        lf.pack(fill="both", padx=6, pady=(0, 6))
        self.log = tk.Text(lf, height=7, state="disabled", font=("Consolas", 9))
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ---- helpers
    def log_line(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 300:
            self.log.delete("1.0", "50.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_ports(self):
        ports = []
        if serial is not None:
            ports = [p.device for p in serial.tools.list_ports.comports()]
        ports.append("SIMULATOR")
        self.port_cb["values"] = ports
        if not self.port_var.get() or self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    # ---- connection
    def toggle_connect(self):
        if self.link:
            self.disconnect()
            return
        port = self.port_var.get()
        try:
            if port == "SIMULATOR":
                self.link = SimLink(self.q)
            else:
                if serial is None:
                    raise RuntimeError("pyserial not installed: pip install pyserial")
                self.status.config(text="Opening port (2 s)...", foreground="orange")
                self.root.update()
                self.link = SerialLink(port, int(self.baud_var.get()), self.q)
        except Exception as e:
            messagebox.showerror("Connection failed", str(e))
            self.link = None
            return
        self.conn_btn.config(text="Disconnect")
        self.log_line(f"Connected to {port}")

    def disconnect(self):
        if self.link:
            self.link.close()
        self.link = None
        self.conn_btn.config(text="Connect")
        self.log_line("Disconnected")

    # ---- TX
    def current_command(self):
        return build_command([v.get() for v in self.out_bits],
                             [v.get() for v in self.out_vals])

    def send_now(self):
        if not self.link:
            return
        cmd = self.current_command()
        try:
            self.link.write(cmd)
            self.tx_frames += 1
            self.log_line("TX " + cmd.strip())
        except Exception as e:
            self.log_line(f"TX error: {e}")
            self.disconnect()

    def send_tick(self):
        if self.link and self.auto_send.get():
            try:
                self.link.write(self.current_command())
                self.tx_frames += 1
            except Exception as e:
                self.log_line(f"TX error: {e}")
                self.disconnect()
        self.root.after(SEND_PERIOD_MS, self.send_tick)

    def reset_outputs(self):
        for v in self.out_bits:
            v.set(0)
        for sc in self.scales:
            sc.set(0)
        for v in self.out_vals:
            v.set(0)

    # ---- RX
    def poll_rx(self):
        shown = False
        try:
            while True:
                kind, text = self.q.get_nowait()
                if kind == "ERR":
                    self.log_line("Serial error: " + text)
                    self.disconnect()
                    continue
                parsed = parse_data(text)
                if parsed:
                    self.rx_frames += 1
                    self.last_rx = time.time()
                    self.update_inputs(*parsed)
                    if not shown:                 # keep the log readable
                        self.log_line("RX " + text)
                        shown = True
                else:
                    self.log_line("RX (info) " + text)
        except queue.Empty:
            pass
        self.root.after(50, self.poll_rx)

    def update_inputs(self, bits, vals):
        for i in range(N):
            c, led = self.leds[i]
            c.itemconfig(led, fill="lime" if bits[i] else "grey30")
            self.bars[i]["value"] = min(vals[i], 1023)
            self.val_lbls[i].config(text=str(vals[i]))

    def update_status(self):
        if not self.link:
            self.status.config(text="Disconnected", foreground="red")
        elif time.time() - self.last_rx < 2:
            self.status.config(text=f"Connected  RX:{self.rx_frames}  TX:{self.tx_frames}",
                               foreground="green")
        else:
            self.status.config(text="Connected - no data from Arduino", foreground="orange")
        self.root.after(500, self.update_status)

    def on_close(self):
        self.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
