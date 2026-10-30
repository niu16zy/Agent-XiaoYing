"""Small-corpus lexical retrieval. Scores indicate relevance, never authority."""

import math
import re
import unicodedata
from collections import Counter

from .corpus import Corpus


SYNONYMS = {"报账": "报销", "报帐": "报销", "截止时间": "期限", "最迟": "期限", "最晚": "期限", "多久": "期限", "多少天": "期限", "凭据": "凭证"}


def normalize(text: str, improved: bool) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    if improved:
        for source, target in SYNONYMS.items():
            text = text.replace(source, target)
    return text


def terms(text: str, improved: bool) -> Counter:
    result = Counter()
    for token in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", normalize(text, improved)):
        if improved and re.fullmatch(r"[\u4e00-\u9fff]+", token):
            result.update(token[i:i + 2] for i in range(len(token) - 1))
        else:
            result[token] += 1
    return result


class Retriever:
    def __init__(self, corpus: Corpus, mode: str = "improved"):
        if mode not in {"baseline", "improved"}:
            raise ValueError("Unknown retrieval mode")
        self.corpus = corpus
        self.improved = mode == "improved"
        self.index = {}
        frequency = Counter()
        for key, doc in corpus.documents.items():
            body = terms(doc.content, self.improved)
            title = terms(doc.title, self.improved)
            weights = body + Counter({term: count * 2 for term, count in title.items()})
            self.index[key] = weights
            frequency.update(weights.keys())
        self.idf = {term: math.log(1 + len(self.index) / count) for term, count in frequency.items()}

    def search(self, query: str, top_k: int) -> dict:
        query_terms = terms(query, self.improved)
        ranked = []
        for key, weights in self.index.items():
            if self.improved:
                score = sum(self.idf.get(t, 0) * (1 + math.log(weights[t])) for t in query_terms if weights[t])
            else:
                # Deliberately simple literal-match comparator for retrieval experiments.
                doc = self.corpus.documents[key]
                literal = normalize(query.strip(), False)
                score = normalize(doc.content, False).count(literal) + 2 * normalize(doc.title, False).count(literal)
            if score > 0:
                ranked.append((key, score))
        ranked.sort(key=lambda row: (-row[1], row[0]))
        hits = []
        for key, score in ranked[:top_k]:
            doc = self.corpus.documents[key]
            # Select an original paragraph; normalization never changes the returned text.
            paragraphs = doc.content.split("\n\n")
            snippet = max(paragraphs, key=lambda p: sum(
                self.idf.get(t, 0) for t in query_terms.keys() & terms(p, self.improved).keys()
            ))
            start = doc.content.index(snippet)
            hits.append({"doc_id": key, "title": doc.title, "version_date": doc.version_date,
                         "snippet": snippet, "start": start, "end": start + len(snippet),
                         "score": round(score, 6)})
        return {"hits": hits, "total_hits": len(ranked), "truncated": len(ranked) > top_k,
                "snapshot_id": self.corpus.snapshot_id}
