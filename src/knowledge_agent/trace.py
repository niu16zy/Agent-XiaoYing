"""Incremental JSONL traces and run artifacts, with secret-value redaction."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class RunTrace:
    def __init__(self, root=None):
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        self.directory = Path(root) / self.run_id if root else None
        self.events = []
        self.secrets = tuple(v for k, v in os.environ.items() if ("API_KEY" in k or "TOKEN" in k) and len(v) > 8)
        if self.directory:
            self.directory.mkdir(parents=True, exist_ok=False)

    def clean(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        return value

    def write(self, name, value):
        if self.directory:
            (self.directory / name).write_text(json.dumps(self.clean(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def add(self, **event):
        event = self.clean({"step": len(self.events) + 1, **event})
        self.events.append(event)
        if self.directory:
            with (self.directory / "trace.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def write_text(self, name, value):
        if self.directory:
            (self.directory / name).write_text(self.clean(value), encoding="utf-8")
