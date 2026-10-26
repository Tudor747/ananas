"""Append-only USB evidence, separate from manually supplied observations."""
import json
from datetime import datetime, timezone


class EvidenceStore:
    def __init__(self, repository):
        self.repository = repository
        repository.initialize()
        with repository.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS peripheral_events (
                id INTEGER PRIMARY KEY, received_at TEXT NOT NULL,
                node TEXT NOT NULL, session TEXT NOT NULL, kind TEXT NOT NULL,
                provenance TEXT NOT NULL, data_json TEXT NOT NULL)""")

    def append(self, node, session, kind, data, provenance="usb"):
        with self.repository.connect() as db:
            db.execute("INSERT INTO peripheral_events(received_at,node,session,kind,provenance,data_json) VALUES (?,?,?,?,?,?)",
                       (datetime.now(timezone.utc).isoformat(), node, session, kind, provenance,
                        json.dumps(data, allow_nan=False)))

    def events(self, after=0, limit=200):
        with self.repository.connect() as db:
            rows = db.execute("SELECT * FROM peripheral_events WHERE id>? ORDER BY id LIMIT ?", (after, limit)).fetchall()
        return [{**{k: r[k] for k in r.keys() if k != "data_json"}, "data": json.loads(r["data_json"])} for r in rows]

    def latest_id(self):
        with self.repository.connect() as db:
            return db.execute("SELECT COALESCE(MAX(id), 0) FROM peripheral_events").fetchone()[0]

    def markdown(self, after=0, limit=1000):
        lines = ["# RF Sentinel peripheral evidence", "", "USB records are device reports, not independently verified hardware measurements.",
                 "Host receive times use UTC; device uptime is not a synchronized clock.", ""]
        for event in self.events(after, limit):
            lines.extend([f"## Record {event['id']} — {event['received_at']}",
                          f"Node {event['node']}; {event['kind']}; source: {event['provenance']}", "",
                          "```json", json.dumps(event['data'], indent=2).replace("`", "\\u0060"), "```", ""])
        return "\n".join(lines)
