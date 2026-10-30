"""Immutable documents and JSON-serializable contracts for subsequent stages."""

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    TOOL_ERROR = "tool_error"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    version_date: str
    scope: str | None
    supersedes: tuple[str, ...]
    content: str

    @classmethod
    def from_dict(cls, raw: dict) -> "Document":
        fields = {"doc_id", "title", "version_date", "scope", "supersedes", "content"}
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValueError("Document fields do not match schema")
        for name in ("doc_id", "title", "version_date", "content"):
            if not isinstance(raw[name], str) or not raw[name].strip():
                raise ValueError(f"Invalid document {name}")
        if date.fromisoformat(raw["version_date"]).isoformat() != raw["version_date"]:
            raise ValueError("version_date must be YYYY-MM-DD")
        if raw["scope"] is not None and (
            not isinstance(raw["scope"], str) or not raw["scope"].strip()
        ):
            raise ValueError("Invalid scope")
        refs = raw["supersedes"]
        if not isinstance(refs, list) or any(not isinstance(x, str) or not x for x in refs):
            raise ValueError("Invalid supersedes")
        if len(set(refs)) != len(refs) or raw["doc_id"] in refs:
            raise ValueError("Invalid replacement references")
        return cls(**{**raw, "supersedes": tuple(refs)})


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Citation:
    doc_id: str
    version_date: str
    quote: str
    start: int
    end: int
    supports: str
    snapshot_id: str


@dataclass
class Answer:
    """Output contract only; semantic/citation validation belongs to stage 3."""

    answer: str
    status: TaskStatus
    citations: list[Citation] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    follow_up_question: str | None = None

    def to_dict(self) -> dict:
        return {**asdict(self), "status": self.status.value}
