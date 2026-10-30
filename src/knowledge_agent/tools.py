"""Business tools bound to one snapshot; fault injection is test-only configuration."""

from dataclasses import dataclass, field

from .corpus import Corpus
from .retrieval import Retriever
from .schemas import ToolError, ToolResult


@dataclass
class FaultInjection:
    tool: str
    match_args: dict
    mode: str
    error_code: str
    retryable: bool
    _matches: int = field(default=0, init=False)

    def __post_init__(self):
        if self.tool not in {"search_docs", "read_document"}:
            raise ValueError("Invalid injected tool")
        if self.mode not in {"first_matching_call", "all_matching_calls"}:
            raise ValueError("Invalid injection mode")
        if self.error_code not in {"TOOL_UNAVAILABLE", "TEMPORARY_FAILURE"}:
            raise ValueError("Invalid injected error")
        if not isinstance(self.match_args, dict) or type(self.retryable) is not bool:
            raise ValueError("Invalid injection arguments")

    def observe(self, tool: str, arguments: dict) -> ToolError | None:
        if tool != self.tool or any(arguments.get(k) != v for k, v in self.match_args.items()):
            return None
        self._matches += 1
        if self.mode == "all_matching_calls" or self._matches == 1:
            return ToolError(self.error_code, "工具暂时无法完成请求。", self.retryable)
        return None


class KnowledgeTools:
    def __init__(self, corpus: Corpus, retrieval_mode: str = "improved", fault: FaultInjection | None = None):
        self.corpus = corpus
        self.retriever = Retriever(corpus, retrieval_mode)
        self.fault = fault

    def _failure(self, tool: str, args: dict) -> ToolResult | None:
        error = self.fault.observe(tool, args) if self.fault else None
        return ToolResult(False, error=error) if error else None

    def search_docs(self, query: str, top_k: int = 5) -> ToolResult:
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            return ToolResult(False, error=ToolError("INVALID_ARGUMENT", "query 必须是 1 至 2000 字符的非空文本。"))
        if type(top_k) is not int or not 1 <= top_k <= 10:
            return ToolResult(False, error=ToolError("INVALID_ARGUMENT", "top_k 必须是 1 至 10 的整数。"))
        failure = self._failure("search_docs", {"query": query, "top_k": top_k})
        return failure if failure else ToolResult(True, data=self.retriever.search(query, top_k))

    def read_document(self, doc_id: str, start: int = 0, end: int | None = None) -> ToolResult:
        if not isinstance(doc_id, str) or not doc_id.strip():
            return ToolResult(False, error=ToolError("INVALID_ARGUMENT", "doc_id 必须是非空文本。"))
        if type(start) is not int or (end is not None and type(end) is not int):
            return ToolResult(False, error=ToolError("INVALID_ARGUMENT", "片段位置必须是整数。"))
        doc = self.corpus.documents.get(doc_id)
        if doc is None:
            return ToolResult(False, error=ToolError("DOCUMENT_NOT_FOUND", "当前资料中没有该文档。"))
        stop = len(doc.content) if end is None else end
        if not 0 <= start < stop <= len(doc.content):
            return ToolResult(False, error=ToolError("INVALID_ARGUMENT", "片段范围必须位于正文内，且非空。"))
        failure = self._failure("read_document", {"doc_id": doc_id, "start": start, "end": end})
        if failure:
            return failure
        return ToolResult(True, data={"doc_id": doc.doc_id, "title": doc.title,
            "version_date": doc.version_date, "scope": doc.scope, "supersedes": list(doc.supersedes),
            "content": doc.content[start:stop], "start": start, "end": stop,
            "snapshot_id": self.corpus.snapshot_id})
