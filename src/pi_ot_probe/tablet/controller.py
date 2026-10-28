"""Shared visible selection for keyboard, USB and direct Pi GPIO navigation."""
import tkinter as tk
from .catalog import CATEGORIES, category_tools


class Controller:
    def __init__(self, app):
        self.app = app
        self.selected = None
        self.reading = False
        self.tag = f"SentinelController{id(self)}"
        for key, action in {"Up": "up", "Down": "down", "Left": "back", "BackSpace": "back",
                            "Right": "select", "space": "select", "Return": "ok"}.items():
            app.root.bind_class(self.tag, f"<{key}>", lambda event, a=action: self.handle(a))
        app.root.bindtags((self.tag, *app.root.bindtags()))

    def widgets(self, parent):
        for widget in parent.winfo_children():
            yield widget
            yield from self.widgets(widget)

    def items(self):
        if self.app.tool is None:
            candidates = self.app.body.winfo_children()
        else:
            candidates = [*self.widgets(self.app.body), *self.widgets(self.app.footer)]
            # Keep Run and Stop adjacent, and put the result reader last.
            candidates.sort(key=lambda w: isinstance(w, tk.Text))
        return [w for w in candidates if isinstance(w, (tk.Button, tk.Checkbutton, tk.Radiobutton, tk.Text))
                and (isinstance(w, tk.Text) or str(w.cget("state")) != "disabled")]

    def refresh(self):
        if not self.alive():
            return
        self.reading = False
        for widget in self.widgets(self.app.root):
            if self.tag not in widget.bindtags():
                # Handle keys before Tk's widget/class bindings to avoid double execution.
                widget.bindtags((self.tag, *widget.bindtags()))
        items = self.items()
        preferred = next((w for w in items if isinstance(w, tk.Checkbutton)), None)
        self.focus(preferred if preferred is not None else items[0] if items else None)

    def focus(self, widget):
        if self.selected is not None and self.selected.winfo_exists():
            self.selected.configure(highlightbackground="#172638", highlightcolor="#172638")
            if hasattr(self.selected, "_unfocused_bg"):
                self.selected.configure(bg=self.selected._unfocused_bg)
        self.selected = widget
        if widget is not None:
            if isinstance(widget, tk.Button):
                if not hasattr(widget, "_unfocused_bg"):
                    widget._unfocused_bg = widget.cget("bg")
                widget.configure(bg="#29644f")
            widget.configure(highlightthickness=3, highlightbackground="#4ee3b3", highlightcolor="#4ee3b3")
            widget.focus_set()
            self.reveal(widget)
        self.app.controls_hint.set("UP/DOWN move · LEFT back\nOK choose · RIGHT next page" if self.app.tool is None else
                                   "UP/DOWN move · LEFT back · OK choose")

    def navigate_gpio(self, direction):
        """D-pad semantics from the Pi handoff, reusing the existing selected widget."""
        if not self.alive():
            return
        # Finish a pending page rebuild before handling a second rapid press.
        self.app.root.update_idletasks()
        if self.app.tool is not None:
            action = {"left": "back", "ok": "select", "up": "up", "down": "down"}.get(direction)
            if action:
                self.handle(action)
            return
        items = self.items()
        if not items:
            return
        if self.selected not in items:
            self.focus(items[0])
        if direction in {"up", "down"}:
            self.handle(direction)
        elif direction == "left":
            if self.app.page > 0:
                self.app.turn_page(-1)
            elif self.app.category:
                self.app.back()
        elif direction == "right":
            choices = category_tools(self.app.category) if self.app.category else CATEGORIES
            if self.app.page < (len(choices) - 1) // 2:
                self.app.turn_page(1)
        elif direction == "ok":
            self.handle("select")

    def alive(self):
        if self.app.closing:
            return False
        try:
            return bool(self.app.root.winfo_exists())
        except tk.TclError:
            return False

    def reveal(self, widget):
        canvas = getattr(self.app, "scroll_canvas", None)
        if canvas is None or not canvas.winfo_exists() or not str(widget).startswith(str(canvas) + "."):
            return
        self.app.root.update_idletasks()
        bounds = canvas.bbox("all")
        if not bounds:
            return
        top = widget.winfo_rooty() - canvas.winfo_rooty() + canvas.canvasy(0)
        bottom = top + widget.winfo_height()
        visible_top = canvas.canvasy(0)
        height = canvas.winfo_height()
        if top < visible_top or bottom > visible_top + height:
            target = top if top < visible_top or widget.winfo_height() > height else bottom - height
            canvas.yview_moveto(max(0, target) / max(1, bounds[3]))

    def handle(self, action):
        if self.app.closing:
            return "break"
        items = self.items()
        if self.selected not in items:
            self.focus(items[0] if items else None)
            self.reading = False
        if self.reading:
            if action in {"up", "down"}:
                self.selected.yview_scroll(-3 if action == "up" else 3, "units")
            elif action in {"back", "select", "ok"}:
                self.reading = False
                self.focus(self.selected)
            return "break"
        if action == "back":
            self.app.back()
        elif action in {"up", "down"} and items:
            step = -1 if action == "up" else 1
            index = items.index(self.selected) + step
            if self.app.tool is None and not 0 <= index < len(items):
                old_page = self.app.page
                self.app.turn_page(step)
                self.app.root.update_idletasks()
                items = self.items()
                if items:
                    if self.app.page != old_page:
                        target = -1 if step < 0 else 0
                    else:
                        target = 0 if step < 0 else -1
                    self.focus(items[target])
            else:
                self.focus(items[index % len(items)])
        elif action in {"select", "ok"} and self.selected is not None:
            if isinstance(self.selected, tk.Text):
                self.reading = True
                gpio = getattr(self.app, "gpio_buttons", None)
                self.app.controls_hint.set("UP/DOWN scroll results | LEFT / OK leave results"
                                           if gpio is not None and gpio.active else
                                           "UP/DOWN scroll results | BACK / SELECT leave results")
            else:
                self.selected.invoke()
        return "break"
