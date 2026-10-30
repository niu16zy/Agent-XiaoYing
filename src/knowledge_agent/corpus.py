"""Load explicit scenario snapshots without exposing evaluation expectations."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .schemas import Document


@dataclass(frozen=True)
class Corpus:
    documents: Mapping[str, Document]
    snapshot_id: str


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ValueError(f"Unsupported schema: {path.name}")
    return value


def _unique(items: list, key: str) -> dict:
    if not isinstance(items, list) or not items:
        raise ValueError(f"Expected nonempty {key} collection")
    result = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get(key), str) or not item[key]:
            raise ValueError(f"Missing {key}")
        if item[key] in result:
            raise ValueError(f"Duplicate {key}: {item[key]}")
        result[item[key]] = item
    return result


def load_corpus(data_dir: str | Path, scenario_id: str | None = None) -> Corpus:
    data_dir = Path(data_dir)
    source = _read(data_dir / "documents.json")
    documents = {
        key: Document.from_dict(raw)
        for key, raw in _unique(source.get("documents"), "doc_id").items()
    }
    for doc in documents.values():
        if any(ref not in documents for ref in doc.supersedes):
            raise ValueError(f"Unknown replacement reference: {doc.doc_id}")
    config = _read(data_dir / "scenarios.json")
    scenarios = _unique(config.get("scenarios"), "scenario_id")
    selected = config.get("default_scenario") if scenario_id is None else scenario_id
    if not isinstance(selected, str) or selected not in scenarios:
        raise ValueError("Unknown scenario")
    scenario = scenarios[selected]
    ids = scenario.get("include_doc_ids")
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
        raise ValueError("Invalid include_doc_ids")
    if len(set(ids)) != len(ids) or any(x not in documents for x in ids):
        raise ValueError("Duplicate or unknown scenario document")
    visible = {key: documents[key] for key in ids}
    overrides = scenario.get("overrides", [])
    if not isinstance(overrides, list):
        raise ValueError("Invalid overrides")
    changed = set()
    for patch in overrides:
        if not isinstance(patch, dict) or not isinstance(patch.get("doc_id"), str):
            raise ValueError("Invalid override document")
        key = patch["doc_id"]
        if key not in visible or key in changed:
            raise ValueError("Override targets hidden/duplicate document")
        raw = asdict(visible[key])
        raw["supersedes"] = list(raw["supersedes"])
        raw.update(patch)
        visible[key] = Document.from_dict(raw)
        if any(ref not in documents for ref in visible[key].supersedes):
            raise ValueError("Unknown overridden replacement reference")
        changed.add(key)
    canonical = json.dumps(
        [asdict(visible[key]) for key in sorted(visible)],
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return Corpus(MappingProxyType(visible), digest)
