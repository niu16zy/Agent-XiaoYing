"""Run-local evidence and persistent conflict ledger; no access to hidden corpus."""

import copy
import hashlib
import re

from .model import ActionError


class EvidenceState:
    def __init__(self, snapshot_id):
        self.snapshot_id = snapshot_id
        self._reads = []
        self.facts = []
        self.conflicts = {}

    @property
    def reads(self):
        return copy.deepcopy(self._reads)

    def cite(self, citation):
        if not isinstance(citation, dict) or set(citation) != {"doc_id", "version_date", "quote", "supports"} or any(not isinstance(v, str) or not v.strip() for v in citation.values()):
            raise ActionError("引用必须包含 doc_id、version_date、quote、supports 非空文本。")
        for doc in self._reads:
            if doc["doc_id"] == citation["doc_id"] and doc["version_date"] == citation["version_date"] and citation["quote"] in doc["content"]:
                start = doc["start"] + doc["content"].index(citation["quote"])
                return {**citation, "start": start, "end": start + len(citation["quote"]), "snapshot_id": self.snapshot_id}
        raise ActionError("引用不匹配本次成功读取的原文或版本。")

    def add_read(self, doc):
        if doc["snapshot_id"] != self.snapshot_id or doc["end"] - doc["start"] != len(doc["content"]):
            raise ValueError("Evidence snapshot/offset mismatch")
        if doc not in self._reads:
            self._reads.append(copy.deepcopy(doc))
        # Conservative hint: identical sentence templates and scopes with differing
        # numeric values. This cannot discover every semantic contradiction.
        sentences = []
        for read in self._reads:
            for sentence in re.findall(r"[^。！？\n]+[。！？]?", read["content"]):
                numbers = re.findall(r"\d+(?:\.\d+)?", sentence)
                if not numbers:
                    continue
                template = re.sub(r"\d+(?:\.\d+)?", "#", sentence)
                for other, text, pattern, values in sentences:
                    if other["doc_id"] == read["doc_id"] or other["scope"] != read["scope"] or pattern != template or values == numbers:
                        continue
                    ids = sorted([other["doc_id"], read["doc_id"]])
                    key = "C-" + hashlib.sha256((str(ids) + template).encode()).hexdigest()[:10]
                    if key not in self.conflicts:
                        citations = [self.cite({"doc_id": d["doc_id"], "version_date": d["version_date"], "quote": q, "supports": "同范围同句式出现不同数值，需查证适用关系。"}) for d, q in [(other, text), (read, sentence)]]
                        self.conflicts[key] = {"conflict_id": key, "topic": "同句式数值规则待查证", "doc_ids": ids,
                            "status": "unresolved", "citations": citations, "resolution": None, "resolution_citations": []}
                sentences.append((read, sentence, template, numbers))

    def record(self, arguments):
        if not isinstance(arguments, dict) or set(arguments) - {"facts", "conflicts"}:
            raise ActionError("record_evidence 仅支持 facts 和 conflicts 数组。")
        facts, updates = arguments.get("facts", []), arguments.get("conflicts", [])
        if not isinstance(facts, list) or not isinstance(updates, list):
            raise ActionError("证据记录必须是数组。")
        new_facts, new_conflicts = copy.deepcopy(self.facts), copy.deepcopy(self.conflicts)
        for fact in facts:
            if not isinstance(fact, dict) or set(fact) != {"claim", "citation"} or not isinstance(fact["claim"], str) or not fact["claim"].strip():
                raise ActionError("fact 需要 claim 和 citation。")
            new_facts.append({"claim": fact["claim"], "citation": self.cite(fact["citation"])})
        for update in updates:
            required = {"conflict_id", "topic", "citations", "status", "resolution", "resolution_citations"}
            if not isinstance(update, dict) or set(update) != required:
                raise ActionError("冲突记录字段不正确。")
            if any(not isinstance(update[k], str) or not update[k].strip() for k in ("conflict_id", "topic")) or update["status"] not in ("resolved", "unresolved"):
                raise ActionError("冲突 ID、事项或状态不正确。")
            if not isinstance(update["citations"], list) or not isinstance(update["resolution_citations"], list):
                raise ActionError("冲突引用必须为数组。")
            citations = [self.cite(c) for c in update["citations"]]
            ids = sorted({c["doc_id"] for c in citations})
            if len(ids) < 2:
                raise ActionError("冲突需要至少两份已读文档的引用。")
            existing = new_conflicts.get(update["conflict_id"])
            if existing and existing["doc_ids"] != ids:
                raise ActionError("不能通过更换冲突来源清除已有冲突。")
            resolution_citations = [self.cite(c) for c in update["resolution_citations"]]
            if update["status"] == "resolved" and (not isinstance(update["resolution"], str) or not update["resolution"].strip() or not resolution_citations):
                raise ActionError("解决冲突必须说明适用条件并引用支持原文；日期或用户口头选择不是依据。")
            if update["status"] == "resolved" and not any(re.search("适用|替代|废止|优先|生效|仅限", c["quote"]) for c in resolution_citations):
                raise ActionError("解决依据须包含适用关系或替代条款原文，仅数字规则不支持优先关系。")
            if update["status"] == "resolved" and not any(c["doc_id"] in ids or all(doc_id in c["quote"] for doc_id in ids) for c in resolution_citations):
                raise ActionError("解决依据必须来自冲突文档或明确指向冲突双方，不能使用无关范围条款。")
            new_conflicts[update["conflict_id"]] = {**copy.deepcopy(update), "doc_ids": ids,
                "citations": citations, "resolution_citations": resolution_citations}
        self.facts, self.conflicts = new_facts, new_conflicts

    @property
    def unresolved(self):
        return copy.deepcopy([c for c in self.conflicts.values() if c["status"] == "unresolved"])

    def view(self):
        return {"facts": copy.deepcopy(self.facts), "conflicts": copy.deepcopy(list(self.conflicts.values()))}
