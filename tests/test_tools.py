import json

import pytest

from knowledge_agent import KnowledgeTools, load_corpus
from knowledge_agent.schemas import Answer, TaskStatus
from knowledge_agent.tools import FaultInjection


@pytest.mark.parametrize("query,required", [
    ("报销期限多久？", {"D01", "D02"}),
    ("费用发生以后，最迟多久要在系统里申请报账？", {"D01", "D02"}),
    ("报销申请最晚几天内提交？", {"D01", "D02"}),
    ("花完这笔钱后，有多少天可以提交费用报销？", {"D01", "D02"}),
    ("报销需要哪些材料？", {"D03"}),
    ("云剪工作台网页版上传单个视频最大支持多大？", {"D07"}),
])
def test_recall_in_top_five(data_dir, query, required):
    result = KnowledgeTools(load_corpus(data_dir, "conflict")).search_docs(query)
    assert result.ok
    assert required <= {hit["doc_id"] for hit in result.data["hits"]}


def test_snippet_and_read_offsets_are_original_text(corpus):
    tools = KnowledgeTools(corpus)
    for hit in tools.search_docs("报销材料", 10).data["hits"]:
        read = tools.read_document(hit["doc_id"], hit["start"], hit["end"])
        assert read.data["content"] == hit["snippet"]
        assert read.data["version_date"] == hit["version_date"]
        assert read.data["snapshot_id"] == corpus.snapshot_id
    read = tools.read_document("D01", 2, 14)
    assert read.data["content"] == corpus.documents["D01"].content[2:14]


def test_empty_results_and_truncation(corpus):
    tools = KnowledgeTools(corpus)
    empty = tools.search_docs("xyzunfindable987")
    assert empty.ok and empty.data["hits"] == [] and empty.data["total_hits"] == 0
    short = tools.search_docs("报销", 1).data
    assert short["truncated"] and short["total_hits"] > len(short["hits"]) == 1
    assert tools.search_docs("报销", 10).data["truncated"] is False


@pytest.mark.parametrize("query,k", [("", 5), ("  ", 5), (None, 5), ("报销", 0), ("报销", 11), ("报销", True), ("报销", 1.5), ("文" * 2001, 5)])
def test_bad_search_parameters(corpus, query, k):
    result = KnowledgeTools(corpus).search_docs(query, k)
    assert not result.ok and result.error.code == "INVALID_ARGUMENT" and result.data is None


@pytest.mark.parametrize("doc,start,end,code", [
    (None, 0, None, "INVALID_ARGUMENT"), ("D999", 0, None, "DOCUMENT_NOT_FOUND"),
    ("../documents.json", 0, None, "DOCUMENT_NOT_FOUND"), ("D01", -1, 10, "INVALID_ARGUMENT"),
    ("D01", 5, 5, "INVALID_ARGUMENT"), ("D01", 0, 99999, "INVALID_ARGUMENT"),
    ("D01", True, None, "INVALID_ARGUMENT"), ("D01", 0, "10", "INVALID_ARGUMENT"),
])
def test_bad_reads(corpus, doc, start, end, code):
    assert KnowledgeTools(corpus).read_document(doc, start, end).error.code == code


@pytest.mark.parametrize("mode", ["first_matching_call", "all_matching_calls"])
def test_fault_counts_only_matching_calls_and_does_not_retry(corpus, mode):
    fault = FaultInjection("read_document", {"doc_id": "D01"}, mode, "TEMPORARY_FAILURE", True)
    tools = KnowledgeTools(corpus, fault=fault)
    assert tools.read_document("D03").ok
    assert tools.search_docs("报销").ok
    first = tools.read_document("D01")
    assert not first.ok and first.error.retryable and first.data is None
    assert fault._matches == 1
    second = tools.read_document("D01")
    assert second.ok == (mode == "first_matching_call")
    assert KnowledgeTools(corpus).read_document("D01").ok


def test_search_fault(corpus):
    tools = KnowledgeTools(corpus, fault=FaultInjection("search_docs", {}, "all_matching_calls", "TOOL_UNAVAILABLE", False))
    result = tools.search_docs("报销")
    assert result.error.code == "TOOL_UNAVAILABLE" and not result.error.retryable


def test_baseline_retained_and_contracts_serializable(corpus):
    tools = KnowledgeTools(corpus, "baseline")
    assert tools.search_docs("报销期限").data["hits"]
    json.dumps(tools.read_document("D01").to_dict(), ensure_ascii=False)
    assert Answer("尚未实现 Agent", TaskStatus.INCOMPLETE).to_dict()["status"] == "incomplete"
