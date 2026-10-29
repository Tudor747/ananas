"""Keep Tk's interpreter finalizers on the thread that created the GUI."""
import gc
import sys
import threading

import pytest


@pytest.fixture(autouse=True)
def collect_gui_cycles_on_main_thread():
    yield
    # GUI tests leave widget/callback cycles after destroy(). A later USB or
    # startup worker can otherwise trigger GC and finalize Tcl on the wrong
    # thread (a native crash on Windows, not just an unraisable warning).
    if "tkinter" in sys.modules and threading.current_thread() is threading.main_thread():
        gc.collect()
