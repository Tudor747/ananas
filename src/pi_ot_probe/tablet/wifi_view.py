"""BWifiKiller-style list, channel drill-down, AP details and signal tracking for Tk."""
import math
import tkinter as tk
import tkinter.font as tkfont

from .wifi_results import ap_details, channel_summary, hidden, security, signal_bars, signal_label, track_summary, unique_aps

BG, PANEL, TEXT, MUTED, ACCENT = "#0c1420", "#172638", "#eef6ff", "#a4b7cf", "#4ee3b3"


class WifiResults(tk.Frame):
    def __init__(self, app, result):
        super().__init__(app.body, bg=BG)
        self.app = app
        self.result = {}
        self.rows = []
        self.mode = "channels" if app.tool.action == "channels" else "list"
        self.index = 0
        self.channel = None
        self.target = None
        self.offset = 0
        self.hits = []
        self.scanning = False
        self.summary = tk.Label(self, bg=BG, fg=ACCENT, anchor="w", justify="left", font=("DejaVu Sans", 10))
        self.summary.pack(fill="x", pady=(0, 3))
        self.canvas = tk.Canvas(self, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw())
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<MouseWheel>", lambda e: self.handle("up" if e.delta > 0 else "down"))
        self.canvas.bind("<Button-4>", lambda _: self.handle("up"))
        self.canvas.bind("<Button-5>", lambda _: self.handle("down"))
        self.pack(fill="both", expand=True)
        self.back_button = app.button(app.footer, "Back", lambda: self.handle("back"))
        self.back_button.pack(side="left", fill="x", expand=True, padx=2)
        app.run_button = app.button(app.footer, "Rescan", self.run, primary=True)
        app.run_button.pack(side="left", fill="x", expand=True, padx=2)
        app.button(app.footer, "Stop", app.stop_work).pack(side="left", fill="x", expand=True, padx=2)
        if app.root.winfo_height() <= 320:
            for button in app.footer.winfo_children():
                button.configure(font=("DejaVu Sans", 10), pady=4, padx=5)
        self.update_result(result)

    def update_result(self, result):
        self.result = result
        self.scanning = False
        snapshots = result.get("snapshots")
        rows = (snapshots[-1] if snapshots else result.get("records", result.get("access_points", [])))
        self.rows = unique_aps(rows)
        if result.get("target_bssid"):
            self.mode = "track"
        elif self.mode in {"detail", "track"}:
            self.mode = "channels" if self.app.tool.action == "channels" else "list"
            self.target = None
        self.index = min(self.index, max(0, len(self.choices()) - 1))
        self.draw()

    def start_scan(self, tracking=False):
        self.scanning = True
        if tracking:
            self.mode = "track"
            self.result = {"target_bssid": self.target["bssid"], "snapshots": []}
        else:
            self.mode = "channels" if self.app.tool.action == "channels" else "list"
            self.result, self.rows, self.target = {}, [], None
            self.channel, self.index = None, 0
        self.draw()

    def choices(self):
        if self.mode == "channels":
            # Zero means none observed in this scan, not an unused channel.
            return list(range(1, 15))
        return [r for r in self.rows if self.channel is None or r.get("channel") == self.channel]

    def run(self):
        if self.mode in {"detail", "track"} and self.target and self.app.tool.action == "radar":
            self.app.run_tool(wifi_target=self.target["bssid"])
        else:
            self.app.run_tool()

    def handle(self, action):
        if self.mode == "track" and self.app.backend.busy and action in {"ok", "select"}:
            self.app.stop_work()
            return
        if action == "rescan":
            self.app.stop_work() if self.app.backend.busy else self.run()
            return
        if action == "back":
            if self.mode == "track":
                if self.app.backend.busy:
                    self.app.stop_work()
                    return
                self.mode, self.offset = "detail", 0
            elif self.mode == "detail":
                self.mode = "list"
            elif self.mode == "list" and self.channel is not None:
                self.mode, self.index, self.channel = "channels", self.channel - 1, None
            else:
                if self.app.backend.busy:
                    self.app.stop_work()
                self.app.show_tool(self.app.tool)
                return
        elif action in {"up", "down"}:
            step = -1 if action == "up" else 1
            if self.mode == "detail":
                self.offset = max(0, min(self.offset + step, getattr(self, "max_offset", 0)))
            elif self.mode != "track":
                self.index = (self.index + step) % (len(self.choices()) + 1)
        elif action in {"ok", "select"} and not self.scanning:
            choices = self.choices()
            if self.mode in {"channels", "list"} and self.index == len(choices):
                self.run()
            elif self.mode == "channels":
                self.channel, self.index, self.mode = choices[self.index], 0, "list"
            elif self.mode == "list" and choices:
                self.target, self.offset, self.mode = choices[self.index], 0, "detail"
            elif self.mode in {"detail", "track"}:
                if self.app.tool.action == "radar":
                    self.app.stop_work() if self.app.backend.busy else self.run()
                else:
                    self.mode = "list"
            elif not choices:
                self.run()
        self.draw()

    def press(self, event):
        self.press_y = event.y

    def release(self, event):
        movement = event.y - getattr(self, "press_y", event.y)
        if abs(movement) > 25:
            self.handle("down" if movement < 0 else "up")
        elif self.mode in {"detail", "track"}:
            self.handle("select")
        else:
            for top, bottom, index in self.hits:
                if top <= event.y < bottom:
                    self.index = index
                    self.handle("select")
                    break

    def text(self, x, y, text, *, fill=TEXT, size=10, **kwargs):
        return self.canvas.create_text(x, y, text=text, anchor="nw", fill=fill,
                                       font=("DejaVu Sans", size), **kwargs)

    def fitted(self, value, width, size=10):
        font = tkfont.Font(family="DejaVu Sans", size=size)
        value = str(value).replace("\n", " ").replace("\r", " ").replace("\t", " ")
        if font.measure(value) <= width:
            return value
        while value and font.measure(value + "…") > width:
            value = value[:-1]
        return value + "…"

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        self.hits = []
        width, height = max(120, canvas.winfo_width()), max(30, canvas.winfo_height())
        metadata = self.result.get("observation", {})
        state = self.result.get("status")
        if state in {"error", "cancelled"}:
            summary = ("FAILED" if state == "error" else "STOPPED") + " · incomplete\n" + self.result.get("error", "")
        elif self.scanning:
            summary = "Scanning…"
        elif self.mode == "track":
            summary = f"Target RSSI · {len(self.result.get('snapshots', []))}/12 scans"
        else:
            count = len(self.rows)
            names = len({r.get("ssid") for r in self.rows if not hidden(r)})
            summary = f"{count} APs · {names} SSIDs · {sum(hidden(r) for r in self.rows)} hidden"
        if metadata.get("truncated"):
            summary += f"\nPARTIAL: {metadata.get('reported', '?')}/{metadata.get('total_found', '?')} returned"
        elif any(m.get("truncated") for m in self.result.get("observations", [])):
            summary += "\nPARTIAL: one or more scans reached the firmware limit"
        self.summary.configure(text=summary, wraplength=width - 8)
        self.app.run_button.configure(text="Track" if self.mode in {"detail", "track"} and self.app.tool.action == "radar" else "Rescan")
        if self.mode == "track":
            self.draw_track(width, height)
            self.app.controls_hint.set("LEFT back · OK stop / track again · RIGHT rescan")
            return
        if self.mode == "detail":
            self.draw_details(width, height)
            self.app.controls_hint.set("UP/DOWN scroll · LEFT list · OK " + ("track AP" if self.app.tool.action == "radar" else "list"))
            return
        choices = self.choices()
        if not choices or (self.scanning and not self.rows):
            self.text(10, 10, "Scanning access points…" if self.scanning else "No observations received.\nRescan with Wi-Fi enabled and the receiver connected.", width=width - 20)
        else:
            row_height = 44
            per_page = max(1, height // row_height)
            first = self.index // per_page * per_page
            counts = channel_summary(self.rows)
            for slot, index in enumerate(range(first, min(first + per_page, len(choices) + 1))):
                y = slot * row_height
                self.hits.append((y, y + row_height, index))
                canvas.create_rectangle(0, y, width, y + row_height - 2, fill="#244f49" if index == self.index else PANEL, outline="")
                if index == len(choices):
                    self.text(8, y + 6, "Rescan", fill=ACCENT, size=11)
                    self.text(8, y + 27, "OK to refresh observations", fill=MUTED, size=9)
                elif self.mode == "channels":
                    channel = choices[index]
                    count = counts.get(channel, 0)
                    strongest = next((r for r in self.rows if r.get("channel") == channel), None)
                    self.text(8, y + 3, f"CH {channel:02}    {count} AP{'s' if count != 1 else ''}", size=11)
                    self.text(8, y + 25, signal_label(strongest) if strongest else "None observed", fill=MUTED, size=9)
                    x = width * .65
                    canvas.create_rectangle(x, y + 12, width - 8, y + 24, fill=BG, outline="")
                    if count:
                        canvas.create_rectangle(x, y + 12, x + (width - 8 - x) * count / max(counts.values()), y + 24, fill=ACCENT, outline="")
                else:
                    row = choices[index]
                    name = "<hidden>" if hidden(row) else row.get("ssid", "")
                    siblings = sum(r.get("ssid") == row.get("ssid") for r in self.rows) if not hidden(row) else 1
                    if siblings > 1:
                        name += f" ({siblings} APs)"
                    self.text(8, y + 3, self.fitted(name, width - 108, 11), size=11)
                    self.text(width - 95, y + 4, signal_label(row), size=9, fill=ACCENT)
                    self.text(8, y + 25, self.fitted(f"CH {row.get('channel') or '?'} · {security(row)} · {row.get('bssid') or '?'}", width - 44, 9), size=9, fill=MUTED)
                    bars = signal_bars(row)
                    for bar in range(4):
                        x = width - 30 + bar * 6
                        canvas.create_rectangle(x, y + 40 - (bar + 1) * 4, x + 4, y + 40,
                                                fill=ACCENT if bar < bars else BG, outline="")
            self.app.controls_hint.set(f"{min(self.index + 1, len(choices))}/{len(choices)} · UP/DOWN · OK open\nLEFT back · RIGHT rescan")

    def draw_details(self, width, height):
        lines = ap_details(self.target)
        if not hidden(self.target):
            siblings = sum(r.get("ssid") == self.target.get("ssid") for r in self.rows)
            if siblings > 1:
                lines.append(("Radios with this SSID", str(siblings)))
        # Canvas wrapping keeps full SSIDs and BSSIDs readable on 240-pixel panels.
        entries = []
        y = 6
        for label, value in lines:
            item = self.text(8, y, f"{label}: {value}", width=width - 16, size=10)
            bounds = self.canvas.bbox(item)
            entries.append(item)
            y = bounds[3] + 8
        self.max_offset = max(0, math.ceil((y - height) / 24))
        self.offset = min(self.offset, self.max_offset)
        self.canvas.move("all", 0, -self.offset * 24)

    def draw_track(self, width, height):
        bssid = self.result.get("target_bssid", self.target.get("bssid", "") if self.target else "")
        track = track_summary(self.result.get("snapshots", []), bssid)
        name = self.target.get("ssid") if self.target else bssid
        self.text(8, 4, self.fitted(name or "<hidden>", width - 16, 11), size=11)
        current = f"{track['current']:g} dBm" if track["current"] is not None else "— dBm"
        self.text(8, 26, f"{current} · {track['trend']}", fill=ACCENT, size=11)
        low, high = 55, max(70, height - 24)
        if height > 100:
            for dbm in (-40, -70, -100):
                y = low + (-dbm - 30) / 70 * (high - low)
                self.canvas.create_line(36, y, width - 8, y, fill="#304154")
                self.text(2, y - 6, str(dbm), fill=MUTED, size=8)
            previous = None
            for index, value in enumerate(track["values"]):
                if value is None:
                    previous = None  # Never draw a stale value across a missed observation.
                    continue
                x = 38 + index / max(1, len(track["values"]) - 1) * (width - 50)
                y = low + max(0, min(70, -value - 30)) / 70 * (high - low)
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=ACCENT, outline="")
                if previous:
                    self.canvas.create_line(*previous, x, y, fill=ACCENT, width=2)
                previous = x, y
            self.text(8, height - 18, f"Seen {track['seen']}/{track['total']} · missed {track['missed']} · RSSI, not distance", fill=MUTED, size=8)
