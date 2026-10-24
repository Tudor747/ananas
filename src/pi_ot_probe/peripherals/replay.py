"""Import a bounded evidence export as replay, never as live USB measurements."""
import argparse
import json
from pathlib import Path

from pi_ot_probe.config.paths import default_database
from pi_ot_probe.database.repository import Repository
from .protocol import Frame, MAX_FRAME
from .store import EvidenceStore


def import_replay(path, store):
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError("replay export exceeds 10 MB; use a paginated export")
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "rf-sentinel-evidence-v1":
        raise ValueError("not an RF Sentinel evidence export")
    events = document.get("events")
    if not isinstance(events, list) or len(events) > 1000:
        raise ValueError("expected at most 1000 exported events")
    verified = []
    for event in events:
        if event.get("kind") not in {"event", "reply"}:
            continue
        raw = event["data"]
        if len(json.dumps(raw, allow_nan=False).encode()) > MAX_FRAME:
            raise ValueError("oversized replay frame")
        frame = Frame.model_validate(raw)
        verified.append((frame, event.get("received_at")))
    for frame, original_time in verified:
        store.append(frame.node, frame.session, "replay",
                     {"original_received_at": original_time, "frame": frame.model_dump()}, "replay")
    return len(verified)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--database", type=Path, default=default_database())
    args = parser.parse_args()
    try:
        count = import_replay(args.input, EvidenceStore(Repository(args.database)))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(1, f"Replay rejected: {exc}\n")
    print(f"Imported {count} explicitly labelled replay records; no hardware commands sent.")


if __name__ == "__main__":
    main()
