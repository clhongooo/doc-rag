from rank_bm25 import BM25Okapi

from storage.vector_store import VectorStore


class HybridRetriever:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.bm25 = None
        self.chunk_ids = []
        self.chunk_texts = []

    def build_index(self, chunks: list[dict]) -> None:
        self.chunk_ids = [c["id"] for c in chunks]
        self.chunk_texts = [c["text"] for c in chunks]

        tokenized = [text.lower().split() for text in self.chunk_texts]
        self.bm25 = BM25Okapi(tokenized)

    def retrieve(self, query: str, top_k: int = 5, vector_weight: float = 0.7) -> list[dict]:
        vector_results = self.vector_store.query(query, n_results=top_k * 2)
        vector_scores = {r["id"]: 1 - r["distance"] for r in vector_results if r.get("distance") is not None}

        bm25_scores = {}
        if self.bm25:
            tokenized_query = query.lower().split()
            scores = self.bm25.get_scores(tokenized_query)
            for i, score in enumerate(scores):
                bm25_scores[self.chunk_ids[i]] = float(score)

        combined = {}
        all_ids = set(vector_scores.keys()) | set(bm25_scores.keys())

        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1
        for cid in all_ids:
            v_score = vector_scores.get(cid, 0)
            b_score = bm25_scores.get(cid, 0) / max_bm25 if max_bm25 > 0 else 0
            combined[cid] = vector_weight * v_score + (1 - vector_weight) * b_score

        sorted_ids = sorted(combined.keys(), key=lambda x: combined[x], reverse=True)[:top_k]

        results = []
        for cid in sorted_ids:
            for r in vector_results:
                if r["id"] == cid:
                    r["score"] = combined[cid]
                    results.append(r)
                    break
            else:
                idx = self.chunk_ids.index(cid) if cid in self.chunk_ids else -1
                if idx >= 0:
                    results.append({
                        "id": cid,
                        "text": self.chunk_texts[idx],
                        "metadata": {},
                        "score": combined[cid],
                    })

        return results
