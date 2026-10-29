"""The first window must paint while USB/database initialization is slow."""
import threading
import time

import pytest


@pytest.mark.parametrize("failure", [False, True])
def test_startup_keeps_event_loop_alive(monkeypatch, tmp_path, failure):
    import tkinter as tk
    from pi_ot_probe.tablet import __main__ as entry, app, backend

    entered, release = threading.Event(), threading.Event()
    observed = []

    class Root:
        def __init__(self): self.pending, self.finished = [], False
        def title(self, *a): pass
        def configure(self, **k): pass
        def geometry(self, *a): pass
        def attributes(self, *a): pass
        def after(self, delay, callback): self.pending.append(callback)
        def destroy(self): self.finished = True
        def mainloop(self):
            assert entered.wait(1)
            observed.append("paint")
            release.set()
            deadline = time.monotonic() + 3
            while not self.finished and time.monotonic() < deadline:
                if self.pending:
                    self.pending.pop(0)()
                time.sleep(.001)
            assert self.finished

    root = Root()

    class Label:
        def __init__(self, *a, **k): pass
        def pack(self, **k): pass
        def destroy(self): pass
        def configure(self, **k):
            assert "Startup failed" in k["text"]
            observed.append("error")
            root.finished = True

    class Backend:
        def __init__(self, *a):
            entered.set()
            assert release.wait(2)
            if failure:
                raise OSError("database unavailable")
        def close(self): observed.append("close")

    class App:
        def __init__(self, *a, **k):
            observed.append("app")
            root.finished = True
        def close_gpio(self): pass

    monkeypatch.setattr(tk, "Tk", lambda: root)
    monkeypatch.setattr(tk, "Label", Label)
    monkeypatch.setattr(backend, "TabletBackend", Backend)
    monkeypatch.setattr(app, "TabletApp", App)
    assert entry.main(["--database", str(tmp_path / "tablet.db"), "--windowed"]) == 0
    assert observed == (["paint", "error"] if failure else ["paint", "app", "close"])
