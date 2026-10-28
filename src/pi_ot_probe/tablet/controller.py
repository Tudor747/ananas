"""Visible focus and five-button navigation, shared by USB buttons and keyboard."""
import tkinter as tk


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
        self.selected = widget
        if widget is not None:
            widget.configure(highlightthickness=3, highlightbackground="#4ee3b3", highlightcolor="#4ee3b3")
            widget.focus_set()
            self.reveal(widget)
        self.app.controls_hint.set("UP/DOWN move · BACK return\nSELECT choose · OK run")

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
        elif action == "ok" and self.app.tool is not None and self.app.run_button is not None:
            # Invoke the same guarded Run control as touch; never bypass permission.
            self.app.run_button.invoke()
        elif action in {"select", "ok"} and self.selected is not None:
            if isinstance(self.selected, tk.Text):
                self.reading = True
                self.app.controls_hint.set("UP/DOWN scroll results | BACK / SELECT leave results")
            else:
                self.selected.invoke()
        return "break"
