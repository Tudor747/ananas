# Learning and changing the code

Start with the working website. You do not need Raspberry Pi hardware, a
frontend build tool, or knowledge of every folder to make your first change.

## Read these files in order

1. `src/pi_ot_probe/web/app.py` creates the website and connects its parts.
2. `web/routes/scans.py` receives a browser request and calls a use case.
3. `application/service.py` checks authorization and coordinates the operation.
4. `collectors/nmap.py` runs Nmap and converts its output into Python objects.
5. `scanners/orchestrator.py` saves progress, observations, and final status.
6. `application/dashboard.py` reads stored evidence for the browser.
7. `web/static/js/app.js` handles buttons; `js/views/` displays the results.

Paths after the first item are relative to `src/pi_ot_probe/`.

## Where do I make a change?

| Change | File or folder |
| --- | --- |
| Page text, tabs, or layout | `web/static/index.html` |
| Colors, spacing, responsive design | `web/static/css/styles.css` |
| Button actions and refresh behavior | `web/static/js/app.js` |
| Device details | `web/static/js/views/assets.js` |
| Wi-Fi rows | `web/static/js/views/wifi.js` |
| Change review form | `web/static/js/views/changes.js` |
| Browser requests and error messages | `web/static/js/api.js` |
| Accepted API input | `web/schemas.py` |
| An HTTP endpoint | `web/routes/` |
| Scan workflow and cancellation | `application/service.py` |
| Rules for baseline differences | `application/baselines.py` |
| Current vs. historical evidence | `application/dashboard.py`, `database/current_asset.py` |
| Local network adapters | `collectors/interfaces.py` |
| Allowed scan targets | `collectors/targets.py` |
| Nmap commands and XML parsing | `collectors/nmap.py` |
| HTTP/TLS observations | `collectors/http.py` |
| SQLite tables and migrations | `database/schema.py`, `database/repository.py` |
| JSON/CSV downloads | `reports/site.py` |

## Follow one button from click to result

For **Discover devices**, the browser controller sends JSON through `api.js`.
FastAPI validates it with `DiscoveryRequest`. The scan route calls
`ProbeService.run_real()`. The service validates the target, acquires the scan
lock, and passes a scanner to the orchestrator. The scanner yields observations;
the orchestrator stores them and handles completion or cancellation. The browser
refreshes `/api/state`, and the views render the stored observations.

The scan lock allows only one operation to update progress at a time. Immutable
scan snapshots preserve what was observed then, even if a device changes later.
Collectors report evidence; they do not guess device identity or vulnerability.

## Make a small first edit

1. Start the website using `run.ps1` from the project root.
2. Change a label in `web/static/index.html` and refresh the browser.
3. Change a display label in `web/static/js/views/assets.js` and refresh again.
4. For a Python change, stop and restart the server, or use auto-reload below.
5. Run the tests before moving on to another behavior.

```powershell
.\.venv\Scripts\python.exe -m uvicorn pi_ot_probe.web.app:app --host 127.0.0.1 --port 8088 --reload --reload-dir src
.\.venv\Scripts\python.exe -m pytest -q
```

Install test dependencies once with
`.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.
To test only baseline changes, run
`.\.venv\Scripts\python.exe -m pytest tests/web/test_baseline.py -q`.

## Keep changes understandable

- Give functions names that describe what they do. Keep HTTP details in routes,
  network calls in collectors, and presentation in views.
- Use short comments for reasons: why an observation is ignored, why a timeout
  exists, or why a snapshot must remain immutable. Avoid repeating the code.
- Use docstrings to explain a module's responsibility or an unusual contract.
- Keep missing evidence missing. Display **Not observed** instead of inventing it.
- Use `textContent` for observed strings, parameterized SQL for database values,
  and subprocess argument lists for external tools.
- Test meaningful behavior: for example, address reassignment must not turn a
  known MAC into a new device. Tests should survive a function being renamed.

## Tests versus real observations

Most tests use controlled fixtures so they are repeatable without network scans.
`tests/web/test_http.py` additionally starts a real local website and checks its
HTML, imported JavaScript modules, APIs, exports, and authorization gate.

For actual interface, TCP, and HTTP evidence from this PC:

```powershell
.\.venv\Scripts\python.exe -m pi_ot_probe.diagnostics.local_check
```

Read `data/local-check.json`. The temporary endpoint is on `127.0.0.1`; this
does not test another device, Wi-Fi scanning, TLS, or industrial protocols.

## Old and planned code

`experimental/` holds unfinished hardware/protocol boundaries and legacy
analysis. `hardware/` contains LCD/button contracts and terminal mocks.
Neither is where you implement website features. `simulation/` powers the
explicit synthetic CLI example, separate from real collection.

`kali_demo/` keeps tiny compatibility launchers and your existing local data.
Edit the canonical implementation under `src/`, not those launchers. SQLite
tables and existing observations were not migrated by the folder reorganization.
