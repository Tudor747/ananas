"""Real HTTP through the node queue, serial fixture, evidence and export paths."""
import json
import socket
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
import uvicorn

from pi_ot_probe.web.app import create_app
from tests.test_peripherals import FakeSerial, config, wait_until


def test_console_command_to_serial_and_export(tmp_path):
    port = FakeSerial("C")
    app = create_app(tmp_path / "test.db", node_configs=[config("C")], serial_opener=lambda _: port)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets":[listener]}, daemon=True)
        thread.start()
        try:
            wait_until(lambda: server.started)
            wait_until(lambda: app.state.node_manager.state()[2]["connection"] == "online")
            def post(body, origin=None):
                headers = {"Content-Type":"application/json"}
                if origin:
                    headers["Origin"] = origin
                request = Request(base + "/api/nodes/C/commands", method="POST",
                                  data=json.dumps(body).encode(), headers=headers)
                return urlopen(request, timeout=5)
            body = {"command":"OBSERVE", "authorized":True, "operator":"test", "purpose":"serial fixture",
                    "args":{"sensor":"ir", "duration_ms":1000}}
            with pytest.raises(HTTPError) as denied:
                post({**body, "authorized":False})
            assert denied.value.code == 400
            denied.value.close()
            with pytest.raises(HTTPError) as cross_origin:
                post(body, "https://unrelated.invalid")
            assert cross_origin.value.code == 403
            cross_origin.value.close()
            with post(body, base) as response:
                assert response.status == 202
                request_id = json.load(response)["id"]
            wait_until(lambda: any(c["command"] == "OBSERVE" and c["id"] == request_id for c in port.commands))
            wait_until(lambda: any(e["kind"] == "reply" and e["data"].get("id") == request_id
                                   for e in app.state.node_manager.store.events()))
            with urlopen(base + "/api/reports/peripherals.json", timeout=5) as response:
                report = json.load(response)
            assert report["hardware_verified"] is False
            assert any(e["kind"] == "queued" and e["provenance"] == "operator" for e in report["events"])
            assert any(e["kind"] == "reply" and e["provenance"] == "usb" for e in report["events"])
            with post({"command":"STOP"}) as response:
                assert response.status == 202
        finally:
            server.should_exit = True
            thread.join(timeout=10)
        assert not thread.is_alive()
        assert port.closed
