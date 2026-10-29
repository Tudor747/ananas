"""Touch and physical-button Tk window; device work runs in backend workers."""
from __future__ import annotations

import queue
import logging
import random
import sys
import threading
import time
import tkinter as tk

from pi_ot_probe.peripherals.manager import port_key
from .catalog import BY_KEY, CATEGORIES, NODE_NAMES, TOOLS, category_tools
from .diagnostics import discover_choices
from .controller import Controller
from .gpio_buttons import GPIOButtons
from .presentation import connection_summary, describe_node, format_result, pretty_record

BG = "#0c1420"
PANEL = "#172638"
TEXT = "#eef6ff"
MUTED = "#a4b7cf"
ACCENT = "#4ee3b3"
ERROR = "#ffb5a5"
logger = logging.getLogger(__name__)

GRAPH_ACTIONS = {"wifi", "radar", "channels", "sentinel", "ble", "bt_analyzer",
                 "bt_spectrum", "nrf", "scope", "sweep", "advisor", "coex"}


class TabletApp:
    def __init__(self, root, backend, fullscreen=True, size=None, enable_gpio=None):
        self.root, self.backend = root, backend
        self.gpio_buttons = None
        self.gpio_requested = sys.platform == "linux" if enable_gpio is None else enable_gpio
        self._gpio_retry_at = 0
        self.usb_step = "start"
        self._menu_refresh_id = None
        root.title("RF Sentinel · Tablet")
        root.configure(bg=BG)
        width, height = size or (root.winfo_screenwidth(), root.winfo_screenheight())
        root.geometry(f"{width}x{height}")
        root.minsize(240, 240)
        root.attributes("-fullscreen", fullscreen)
        self.font_size = max(10, min(18, int(min(width / 26, height / 22))))
        self.button_padding = 5 if height <= 320 else 9
        root.option_add("*Font", ("DejaVu Sans", self.font_size))
        root.bind("<Escape>", lambda _: root.attributes("-fullscreen", False))
        root.bind("<F11>", lambda _: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.category = None
        self.page = 0
        self.tool = None
        self.samples = []
        self.networks = []
        self.ports = []
        self.selected_port = tk.StringVar(root)
        self.role = tk.StringVar(root, "A")
        self.target = tk.StringVar(root)
        self.authorized = tk.BooleanVar(root, False)
        self.press_y = 0
        self.closing = False
        self.generation = 0
        self.active_job = None
        self.result_widget = None
        self.result_text = None
        self.graph = None
        self.run_button = None
        self.forget_button = None
        self.refreshing = False
        self.choice_errors = []
        self.node_notice = tk.StringVar(root)
        self.status = tk.StringVar(root, "Connecting to configured nodes…")
        self.notice = tk.StringVar(root, "")
        self.controls_hint = tk.StringVar(root)

        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", padx=4, pady=2)
        self.button(header, "‹", self.back).pack(side="left")
        self.button(header, "Home", self.home).pack(side="left", padx=3)
        self.button(header, "×", self.close).pack(side="right")
        self.title = tk.Label(header, text="RF Sentinel", bg=BG, fg=TEXT, anchor="w")
        self.title.pack(side="left", fill="x", expand=True, padx=3)
        self.status_label = tk.Label(root, textvariable=self.status, bg=BG, fg=ACCENT,
                                     font=("DejaVu Sans", max(9, self.font_size - 2)), anchor="w")
        self.status_label.pack(fill="x", padx=8)
        self.status_label.configure(cursor="hand2")
        self.status_label.bind("<ButtonRelease-1>", lambda _: self.open_devices())
        hint = tk.Label(root, textvariable=self.controls_hint, bg=BG, fg=MUTED,
                        font=("DejaVu Sans", 9), wraplength=width - 12)
        hint.pack(side="bottom", fill="x", padx=4)
        hint.bind("<Configure>", lambda e: hint.configure(wraplength=max(100, e.width - 8)))
        self.footer = tk.Frame(root, bg=BG)
        self.footer.pack(side="bottom", fill="x", padx=4, pady=3)
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=5, pady=3)
        self.controller = Controller(self)
        self.home()
        self.refresh_choices()
        self.poll()

    def start_gpio(self):
        if self.closing or (self.gpio_buttons is not None and self.gpio_buttons.active):
            return
        self.close_gpio()
        self._gpio_retry_at = time.monotonic() + 5
        try:
            self.gpio_buttons = GPIOButtons(self.root, self.gpio_navigate)
            logger.info("GPIO navigation buttons activated")
        except Exception as exc:
            logger.warning("GPIO initialization failed; keyboard/touch remain available: %s", exc)

    def gpio_navigate(self, direction):
        if not self.closing:
            self.controller.navigate_gpio(direction)

    def close_gpio(self):
        if self.gpio_buttons is not None:
            try:
                self.gpio_buttons.close()
            except Exception:
                logger.exception("GPIO close failed")
            self.gpio_buttons = None

    def refresh_selection(self):
        self._menu_refresh_id = None
        if not self.closing:
            self.controller.refresh()

    def button(self, parent, text, command, primary=False, **kwargs):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else PANEL,
                         fg=BG if primary else TEXT, activebackground="#2c7169", activeforeground=TEXT,
                         disabledforeground="#73869b", relief="flat", borderwidth=0,
                         padx=9, pady=self.button_padding, highlightthickness=3,
                         highlightbackground=PANEL, highlightcolor=ACCENT, **kwargs)

    def reset_body(self):
        self.generation += 1
        for parent in (self.body, self.footer):
            for child in parent.winfo_children():
                child.destroy()
        for index in range(4):
            self.body.rowconfigure(index, weight=0, uniform="")
            self.body.columnconfigure(index, weight=0, uniform="")
        self.active_job = None
        self.result_widget = self.graph = self.run_button = None
        self.host_actions = None
        self.forget_button = None
        self.result_text = None
        self.scroll_canvas = None
        if self._menu_refresh_id is not None:
            self.root.after_cancel(self._menu_refresh_id)
        self._menu_refresh_id = self.root.after_idle(self.refresh_selection)

    def home(self):
        if self.backend.busy:
            self.request_stop()
        self.category, self.page, self.tool = None, 0, None
        self.show_menu()

    def open_devices(self):
        self.category, self.page = "System", 0
        key = "usb" if all(s["connection"] == "unconfigured" for s in self.backend.state()) else "slave"
        self.show_tool(BY_KEY[key])

    def back(self):
        if self.tool and self.tool.action == "pair" and not self.backend.busy:
            previous = {"role": "start", "port": "role", "confirm": "port", "forget": "port", "done": "start", "error": "start"}
            if self.usb_step in previous:
                self.usb_screen(previous[self.usb_step])
                return
        if self.backend.busy:
            self.request_stop()
        if self.tool:
            self.tool = None
        elif self.category:
            self.category, self.page = None, 0
        self.show_menu()

    def open_category(self, category):
        self.category, self.page, self.tool = category, 0, None
        self.show_menu()

    def show_menu(self):
        self.reset_body()
        self.title.configure(text=self.category or "RF Sentinel")
        choices = category_tools(self.category) if self.category else list(CATEGORIES)
        last = max(0, (len(choices) - 1) // 2)
        self.page = min(self.page, last)
        self.body.columnconfigure(0, weight=1)
        for index in range(2):
            self.body.rowconfigure(index, weight=1, uniform="tiles")
            position = self.page * 2 + index
            if position >= len(choices):
                continue
            choice = choices[position]
            if isinstance(choice, str):
                label, callback = choice, lambda c=choice: self.open_category(c)
                count = sum(t.action is not None for t in category_tools(choice))
                subtitle = f"{count} available · SELECT to open" if count else "Original entries · unavailable"
            else:
                label, callback = choice.title, lambda c=choice: self.show_tool(c)
                subtitle = (f"ESP-{choice.node}" if choice.node else "Raspberry Pi") if choice.action else "Unavailable"
            tile = self.button(self.body, label + "\n" + subtitle, callback, anchor="w", justify="left")
            tile.grid(row=index, column=0, sticky="nsew", pady=3)
            tile.bind("<Configure>", lambda e: e.widget.configure(wraplength=max(80, e.width - 24)))
            tile.bind("<ButtonPress-1>", lambda e: setattr(self, "press_y", e.y_root))
            tile.bind("<ButtonRelease-1>", self.menu_release)
        previous = self.button(self.footer, "↑ Previous", lambda: self.turn_page(-1))
        previous.pack(side="left", expand=True, fill="x")
        previous.configure(state="normal" if self.page else "disabled")
        tk.Label(self.footer, text=f"{self.page + 1}/{last + 1}", bg=BG, fg=MUTED).pack(side="left", padx=6)
        following = self.button(self.footer, "Next ↓", lambda: self.turn_page(1))
        following.pack(side="right", expand=True, fill="x")
        following.configure(state="normal" if self.page < last else "disabled")

    def menu_release(self, event):
        delta = event.y_root - self.press_y
        if abs(delta) > 35:
            self.root.after_idle(lambda: self.turn_page(1 if delta < 0 else -1))
            return "break"

    def turn_page(self, amount):
        if self.tool is None:
            self.page = max(0, self.page + amount)
            self.show_menu()

    def scroll_area(self):
        canvas = tk.Canvas(self.body, bg=BG, highlightthickness=0)
        bar = tk.Scrollbar(self.body, command=canvas.yview, width=22)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=bar.set)
        content = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self.scroll_canvas = canvas
        return content

    def bind_scroll(self, widget):
        widget.bind("<ButtonPress-1>", lambda e: self.scroll_canvas.scan_mark(e.x_root, e.y_root))
        widget.bind("<B1-Motion>", lambda e: self.scroll_canvas.scan_dragto(e.x_root, e.y_root, gain=1))
        widget.bind("<MouseWheel>", lambda e: self.scroll_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        widget.bind("<Button-4>", lambda _: self.scroll_canvas.yview_scroll(-1, "units"))
        widget.bind("<Button-5>", lambda _: self.scroll_canvas.yview_scroll(1, "units"))

    def label(self, parent, text="", color=TEXT, variable=None):
        label = tk.Label(parent, text=text, textvariable=variable, bg=BG, fg=color, anchor="w", justify="left")
        label.pack(fill="x", pady=5)
        label.bind("<Configure>", lambda e: e.widget.configure(wraplength=max(80, e.width - 8)))
        self.bind_scroll(label)
        return label

    def show_tool(self, tool):
        if self.backend.busy and tool != self.tool:
            self.request_stop()
        if tool.action == "pair" and (self.tool is None or self.tool.action != "pair"):
            self.usb_step = "start"
        self.tool = tool
        self.reset_body()
        self.title.configure(text=tool.title)
        self.samples = []
        self.notice.set("")
        if tool.action == "memory":
            self.memory_game()
            return
        if tool.action == "pair":
            self.show_usb_setup()
            return
        content = self.scroll_area()
        self.label(content, tool.description, MUTED)
        if not tool.action:
            self.label(content, tool.unavailable, ERROR)
            self.button(self.footer, "Back to tools", self.back).pack(fill="x")
            return
        if tool.node:
            self.label(content, variable=self.node_notice, color=MUTED)
            self.button(content, "USB Setup", lambda: self.show_tool(BY_KEY["usb"])).pack(fill="x", pady=4)
        if tool.action == "overview":
            self.button(content, "USB Setup", lambda: self.show_tool(BY_KEY["usb"])).pack(fill="x", pady=4)
        if tool.node or tool.action in {"ip", "pi_wifi"}:
            permission = tk.Checkbutton(content, text="I have permission for this test", variable=self.authorized,
                                        bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG,
                                        activeforeground=TEXT, anchor="w", pady=10, wraplength=220)
            permission.pack(fill="x")
        if tool.action == "ip":
            self.label(content, "Select a local subnet:")
            for network in self.networks:
                tk.Radiobutton(content, text=f"{network['interface']} · {network['safe_target']}\nPi address: {network.get('address', '?')}",
                               variable=self.target, value=network["safe_target"], bg=BG, fg=TEXT,
                               selectcolor=PANEL, activebackground=BG, activeforeground=TEXT,
                               anchor="w", pady=10, wraplength=230).pack(fill="x")
            if not self.networks:
                self.label(content, "No local private network found yet. Tap Refresh after connecting.", ERROR)
            self.button(content, "Refresh networks", self.refresh_choices).pack(fill="x", pady=4)
        if tool.action in {"pair", "ip"} and self.choice_errors:
            self.label(content, "\n".join(self.choice_errors), ERROR)
        self.label(content, variable=self.notice, color=ACCENT)
        if tool.action in GRAPH_ACTIONS:
            self.graph = tk.Canvas(content, bg=PANEL, height=135, highlightthickness=0)
            self.graph.pack(fill="x", pady=3)
            self.graph.bind("<Configure>", lambda _: self.draw_graph())
            self.bind_scroll(self.graph)
        self.result_widget = tk.Text(content, height=14, bg=PANEL, fg=TEXT, wrap="word", relief="flat",
                                     padx=8, pady=8, state="disabled", insertbackground=TEXT)
        self.result_widget.pack(fill="both", expand=True, pady=4)
        if tool.action == "ip":
            self.host_actions = tk.Frame(content, bg=BG)
            self.host_actions.pack(fill="x")
        # Dragging a result scrolls its own content. The outer scrollbar reaches the form.
        self.result_widget.bind("<ButtonPress-1>", lambda e: self.result_widget.scan_mark(e.x, e.y))
        self.result_widget.bind("<B1-Motion>", lambda e: self.result_widget.scan_dragto(e.x, e.y))
        self.run_button = self.button(self.footer, "Connect" if tool.action == "pair" else "Run", self.run_tool, primary=True)
        self.run_button.pack(side="left", fill="x", expand=True, padx=2)
        self.button(self.footer, "Stop all", self.stop_work).pack(side="left", fill="x", expand=True, padx=2)
        if tool.action in {"about", "overview", "dependencies", "logs"} and not self.backend.busy:
            self.run_tool()

    def usb_screen(self, step, *, role=None, port=None):
        if self.backend.busy:
            return
        if role is not None:
            self.role.set(role)
        if port is not None:
            self.selected_port.set(port)
        self.usb_step = step
        self.show_tool(BY_KEY["usb"])

    def show_usb_setup(self):
        """Short, linear screens: every choice is a full-width D-pad target."""
        content = self.scroll_area()
        role = self.role.get()
        step = self.usb_step
        self.title.configure(text={"start": "USB Setup", "error": "Connection problem", "role": "1/3 Choose ESP", "port": "2/3 Choose USB",
                                   "confirm": "3/3 Connect ESP", "forget": "Forget setup?",
                                   "done": "Setup saved"}[step])

        def choice(text, command):
            button = self.button(content, text, command, anchor="w", justify="left")
            button.pack(fill="x", pady=3)
            button.bind("<Configure>", lambda e: button.configure(wraplength=max(80, e.width - 24)))
            return button

        states = self.backend.state()
        assigned = {port_key(s["port"]): s["node"] for s in states if s.get("port")}
        if step == "start":
            self.run_button = choice("Find & connect ESPs", lambda: self.run_tool(auto=True))
            choice("Choose ESP manually", lambda: self.usb_screen("role"))
            self.label(content, "Plug in your boards, then choose Find. Their firmware identifies A, B and C automatically.", MUTED)
        elif step == "role":
            for name in "ABC":
                state = next((s for s in states if s["node"] == name), {})
                status = state.get("connection", "unconfigured")
                choice(f"ESP-{name}  |  {status}\n{NODE_NAMES[name]}",
                       lambda n=name: self.usb_screen("port", role=n))
        elif step == "port":
            self.label(content, f"ESP-{role}: {NODE_NAMES[role]}", MUTED)
            available = [p for p in self.ports if assigned.get(port_key(p["port"])) in {None, role}]
            for index, port in enumerate(available, 1):
                # ttyUSB number plus socket/serial suffix distinguishes identical bridges.
                endpoint = port_key(port["port"]).replace("\\", "/").rsplit("/", 1)[-1]
                suffix = port["port"].replace("\\", "/").rsplit("/", 1)[-1]
                suffix = suffix if len(suffix) <= 28 else "..." + suffix[-25:]
                choice(f"USB {index}: {endpoint}\n{suffix}",
                       lambda p=port["port"]: self.usb_screen("confirm", port=p))
            if not available:
                self.label(content, "No free USB ports. Plug in the ESP, then choose Refresh.", ERROR)
            for owner in sorted(set(assigned.values()) - {role}):
                self.label(content, f"ESP-{owner}'s USB port is already assigned.", MUTED)
            choice("Refresh USB ports", self.refresh_choices)
            if role in assigned.values():
                choice(f"Forget ESP-{role} setup...", lambda: self.usb_screen("forget"))
        elif step in {"confirm", "forget"}:
            forgetting = step == "forget"
            endpoint = port_key(self.selected_port.get()).replace("\\", "/").rsplit("/", 1)[-1]
            self.label(content, f"ESP-{role}: {NODE_NAMES[role]}" + ("" if forgetting else f"\nUSB: {endpoint}"), MUTED)
            self.run_button = choice(f"Forget ESP-{role}" if forgetting else f"Connect ESP-{role} now",
                                     lambda: self.run_tool(forget=True) if forgetting else self.run_tool())
            choice("Cancel / choose another port", lambda: self.usb_screen("port"))
            self.label(content, "Other boards and reports are kept." if forgetting else self.selected_port.get())
            self.label(content, "USB connections pause briefly during setup.", MUTED)
        else:
            choice("Try again" if step == "error" else "Set up another ESP", lambda: self.usb_screen("start"))
            choice("Back to System", lambda: self.open_category("System"))
        if getattr(self.backend, "config_error", ""):
            self.label(content, self.backend.config_error, ERROR)
        if self.choice_errors:
            self.label(content, "\n".join(self.choice_errors), ERROR)
        if step in {"error", "done"}:
            self.result_widget = tk.Text(content, height=5, bg=PANEL, fg=TEXT, wrap="word",
                                         state="disabled", relief="flat")
            self.result_widget.pack(fill="both", expand=True)
        tk.Label(self.footer, textvariable=self.notice, bg=BG, fg=ACCENT, height=2,
                 wraplength=max(180, self.root.winfo_width() - 20)).pack(fill="x")
        self.button(self.footer, "Back", self.back).pack(fill="x")

    def refresh_choices(self):
        if self.refreshing:
            return
        self.refreshing = True
        def work():
            self.backend.emit("choices", **discover_choices())
        threading.Thread(target=work, daemon=True).start()

    def request_stop(self):
        stop = getattr(self.backend, "stop_async", self.backend.stop)
        stop()

    def stop_work(self):
        self.request_stop()
        self.notice.set("Stopping all connected ESPs...")

    def run_tool(self, **options):
        if not self.tool:
            return
        try:
            self.backend.start(self.tool.key, authorized=self.authorized.get(), target=self.target.get(),
                               port=self.selected_port.get(), role=self.role.get(), **options)
            self.active_job = self.backend.job_id
            if self.host_actions is not None and self.tool.action == "ip" and not options.get("host"):
                for widget in self.host_actions.winfo_children():
                    widget.destroy()
            self.samples = []
            self.notice.set("Running…")
            self.set_result("")
            self.draw_graph()
        except (ValueError, KeyError) as exc:
            self.notice.set(str(exc))

    def set_result(self, text):
        if self.result_widget and text != self.result_text:
            self.result_text = text
            self.result_widget.configure(state="normal")
            self.result_widget.delete("1.0", "end")
            self.result_widget.insert("end", text)
            self.result_widget.configure(state="disabled")

    def read_results(self):
        if self.result_widget is not None:
            self.root.update_idletasks()
            self.controller.focus(self.result_widget)
            self.controller.reading = False
            self.controller.handle("select")

    def draw_graph(self):
        if not self.graph or not self.tool:
            return
        graph = self.graph
        graph.delete("all")
        width = max(100, graph.winfo_width())
        if not self.samples:
            graph.create_text(10, 18, anchor="nw", fill=MUTED, text="Measurements appear here", font=("DejaVu Sans", 10))
            return
        action = self.tool.action
        if action in {"channels", "bt_spectrum"}:
            from .backend import summarize
            summary = summarize(action, self.samples)
            values = summary.get("access_points_per_channel", summary.get("devices_per_rssi_bin_dbm", {}))
            rows = list(values.items())
            maximum = max(values.values(), default=1)
            for i, (label, count) in enumerate(rows):
                step = (width - 16) / max(1, len(rows))
                x = 8 + i * step
                graph.create_rectangle(x, 100 - 70 * count / maximum, x + max(2, step - 4), 100, fill=ACCENT, outline="")
                graph.create_text(x + step / 2, 112, text=str(label), fill=TEXT)
                graph.create_text(x + step / 2, 90 - 70 * count / maximum, text=str(count), fill=MUTED)
            graph.create_text(8, 4, anchor="nw", text="APs by channel" if action == "channels" else "BLE devices by RSSI bin (dBm)", fill=MUTED)
            return
        if action in {"nrf", "scope"}:
            rows = [r for r in self.samples if "nrf1_carrier" in r][-40:]
            for key, base, color in (("nrf1_carrier", 55, ACCENT), ("nrf2_carrier", 110, "#72b6ff")):
                points = []
                for i, row in enumerate(rows):
                    points.extend((10 + i * (width - 20) / max(1, len(rows) - 1), base - 25 * bool(row[key])))
                if len(points) >= 4:
                    graph.create_line(*points, fill=color, width=2)
                graph.create_text(8, base - 35, anchor="w", text=key.replace("_carrier", ""), fill=color)
            return
        if action in {"sweep", "advisor"}:
            from .backend import summarize
            rows = summarize("sweep", self.samples)["sampled_channels"]
            for row in rows:
                x = 6 + (row["channel"] / 125) * (width - 18)
                height = 12 + row["hit_fraction"] * 80
                graph.create_rectangle(x, 115 - height, x + max(3, width / 30), 115, fill=ACCENT, outline="")
            graph.create_text(8, 8, anchor="nw", text="Carrier hits · sampled channels only", fill=MUTED)
            return
        key = "bssid" if any("bssid" in r for r in self.samples) else "address"
        rows = list({r[key]: r for r in self.samples if key in r and "rssi_dbm" in r}.values())
        rows.sort(key=lambda r: r["rssi_dbm"], reverse=True)
        if rows:
            graph.create_text(8, 5, anchor="nw", text=f"Strongest {min(4, len(rows))} of {len(rows)} - full list below",
                              fill=MUTED, font=("DejaVu Sans", 9))
        for i, row in enumerate(rows[:4]):
            value = row["rssi_dbm"]
            y = 24 + i * 26
            graph.create_rectangle(6, y, 6 + max(0, min(1, (value + 100) / 70)) * (width - 12), y + 24,
                                   fill="#275850", outline="")
            name = row.get("ssid") or row.get("name") or row[key]
            graph.create_text(10, y + 12, anchor="w", text=f"{str(name)[:22]}  {value} dBm", fill=TEXT)
        if not rows:
            graph.create_text(10, 18, anchor="nw", text="See readings below", fill=MUTED)

    def poll(self):
        if self.closing:
            return
        try:
            self.poll_once()
        except Exception:
            logger.exception("Tablet update failed; retrying without disabling buttons")
        finally:
            if not self.closing:
                self.root.after(150, self.poll)

    def poll_once(self):
        if self.closing:
            return
        if (self.gpio_requested and time.monotonic() >= self._gpio_retry_at and
                (self.gpio_buttons is None or not self.gpio_buttons.active)):
            self.start_gpio()
        states = self.backend.state()
        self.status.set(connection_summary(states))
        trouble = any(s.get("health") == "error" or s["connection"] == "offline" for s in states)
        self.status_label.configure(fg=ERROR if trouble else ACCENT)
        if self.tool and self.tool.node:
            state = next((s for s in states if s["node"] == self.tool.node),
                         {"node": self.tool.node, "connection": "unconfigured"})
            self.node_notice.set(describe_node(state))
        changed_samples = False
        for _ in range(200):
            try:
                message = self.backend.messages.get_nowait()
            except queue.Empty:
                break
            kind = message["kind"]
            if message.get("job") is not None and message["job"] != self.active_job:
                continue
            if kind == "sample":
                self.samples.append(message["payload"])
                self.samples = self.samples[-1000:]
                changed_samples = True
            elif kind == "done":
                changed_samples = False
                self.notice.set(f"Results saved to {message['path']}")
                result = message["result"]
                if self.tool and self.tool.action == "pair":
                    self.usb_step = "done"
                    # Rebuild assignments before showing the result so freed ports are selectable.
                    self.show_tool(self.tool)
                    self.notice.set("Setup saved. Other boards kept.")
                if self.tool and self.tool.action == "about":
                    result = {**result, "screen_pixels": [self.root.winfo_screenwidth(), self.root.winfo_screenheight()],
                              "window_pixels": [self.root.winfo_width(), self.root.winfo_height()],
                              "available_tools": sum(t.action is not None for t in TOOLS)}
                self.set_result(format_result(result))
                if self.host_actions is not None and result.get("scan") == "discovery":
                    for widget in self.host_actions.winfo_children():
                        widget.destroy()
                    for host in result["assets"]:
                        self.button(self.host_actions, f"Check ports: {host['ip']}",
                                    lambda ip=host["ip"]: self.run_tool(host=ip)).pack(fill="x", pady=3)
                    self.controller.refresh()
                if self.tool and self.tool.action not in {"pair", "overview", "about", "logs", "dependencies"}:
                    self.read_results()
                self.draw_graph()
            elif kind in {"error", "cancelled", "progress"}:
                if kind == "error" and self.tool and self.tool.action == "pair":
                    self.usb_step = "error"
                    self.show_tool(self.tool)
                    self.set_result(message["message"])
                    self.notice.set("Connection failed. Select details to read.")
                else:
                    self.notice.set(message["message"])
                    if kind in {"error", "cancelled"}:
                        changed_samples = False
                        self.set_result(format_result(message.get("result", {
                            "status": kind, "error": message["message"], "records": self.samples})))
                        self.read_results()
            elif kind == "choices":
                self.refreshing = False
                self.choice_errors = message.get("errors", [])
                self.networks, self.ports = message["networks"], message["ports"]
                if self.target.get() not in {n["safe_target"] for n in self.networks}:
                    self.target.set(self.networks[0]["safe_target"] if self.networks else "")
                if self.usb_step != "confirm" and self.selected_port.get() not in {p["port"] for p in self.ports}:
                    self.selected_port.set(self.ports[0]["port"] if self.ports else "")
                if (self.tool and not self.backend.busy and
                        ((self.tool.action == "ip" and self.active_job is None) or
                         (self.tool.action == "pair" and self.usb_step == "port"))):
                    self.show_tool(self.tool)
        if changed_samples:
            self.set_result("\n\n".join(pretty_record(r) for r in self.samples[-30:]))
            self.draw_graph()
        if self.tool and self.tool.action == "overview" and not self.backend.busy:
            self.set_result(format_result({"nodes": states,
                                           "configuration_error": getattr(self.backend, "config_error", "")}))
        if self.run_button:
            available = not self.backend.busy
            if self.tool.node:
                available &= any(s["node"] == self.tool.node and s["connection"] == "online" for s in states)
            if self.tool.action == "pair":
                available &= (self.usb_step in {"start", "forget"} or
                              self.selected_port.get() in {p["port"] for p in self.ports})
            if self.tool.action == "ip":
                available &= bool(self.target.get())
            self.run_button.configure(state="normal" if available else "disabled")
        if self.forget_button:
            self.forget_button.configure(state="disabled" if self.backend.busy else "normal")
        for action in getattr(self.backend, "button_actions", lambda: [])():
            self.controller.handle(action)

    def memory_game(self):
        values = list("ABCDEF") * 2
        random.shuffle(values)
        opened, matched = [], set()
        buttons = []
        generation = self.generation
        moves = [0]
        self.notice.set("Match the pairs")
        for column in range(4):
            self.body.columnconfigure(column, weight=1, uniform="cards")
        for row in range(3):
            self.body.rowconfigure(row, weight=1, uniform="cards")

        def flip(index):
            if index in matched or index in opened or len(opened) == 2:
                return
            opened.append(index)
            buttons[index].configure(text=values[index], bg="#295c52")
            if len(opened) == 2:
                moves[0] += 1
                if values[opened[0]] == values[opened[1]]:
                    matched.update(opened)
                    opened.clear()
                    self.notice.set(f"{len(matched) // 2}/6 pairs · {moves[0]} turns")
                else:
                    def hide():
                        if self.generation != generation:
                            return
                        for item in opened:
                            buttons[item].configure(text="?", bg=PANEL)
                        opened.clear()
                    self.root.after(700, hide)

        for index in range(12):
            button = self.button(self.body, "?", lambda i=index: flip(i))
            button.grid(row=index // 4, column=index % 4, sticky="nsew", padx=2, pady=2)
            buttons.append(button)
        tk.Label(self.footer, textvariable=self.notice, bg=BG, fg=TEXT).pack(side="left", expand=True)
        self.button(self.footer, "New", lambda: self.show_tool(self.tool)).pack(side="right")

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.close_gpio()
        if self._menu_refresh_id is not None:
            self.root.after_cancel(self._menu_refresh_id)
            self._menu_refresh_id = None
        self.status.set("Stopping devices…")
        finished = threading.Event()

        def shutdown():
            try:
                self.backend.close()
            finally:
                finished.set()

        threading.Thread(target=shutdown, daemon=True).start()

        def finish():
            if finished.is_set():
                self.root.destroy()
            else:
                self.root.after(100, finish)
        finish()
