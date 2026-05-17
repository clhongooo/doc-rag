import re
from storage.vector_store import VectorStore


class SemanticRetriever:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        # 语义检索（多取一些用于重排）
        semantic_results = self.vector_store.query(query, n_results=top_k * 3)

        # 标题匹配检索：用文档标题来匹配查询意图
        title_results = self._title_search(query, top_k * 2)

        # 合并去重
        seen_ids = set()
        merged = []
        for r in semantic_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                merged.append(r)

        for r in title_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                merged.append(r)

        # 重排：优先返回标题匹配度高的 chunk
        merged = self._rerank(query, merged)
        return merged[:top_k]

    def _title_search(self, query: str, limit: int) -> list[dict]:
        """根据文档标题匹配查询意图"""
        all_data = self.vector_store.collection.get(
            include=["documents", "metadatas"]
        )

        # 提取中文二元组和英文词作为查询特征
        features = set()
        cn_chars = re.findall(r'[一-鿿]', query)
        for i in range(len(cn_chars) - 1):
            features.add(cn_chars[i] + cn_chars[i + 1])
        for match in re.finditer(r'[a-zA-Z]{2,}', query):
            features.add(match.group().lower())

        if not features:
            return []

        # 检测是否在问 API/接口相关问题
        is_api_query = any(w in query for w in ["接口", "API", "api", "调用", "请求", "参数", "SDK"])

        scored = []
        for i, doc_id in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            title = meta.get("title", "").lower()
            section = meta.get("section", "").lower()

            score = 0
            for f in features:
                fl = f.lower()
                if fl in title:
                    score += 5
                if fl in section:
                    score += 3

            # API 文档在 API 查询时大幅加分
            if is_api_query:
                if any(kw in title for kw in ["单发推送", "全员/标签推送", "模板推送", "推送撤回", "推送记录"]):
                    score += 10
                if any(kw in section for kw in ["功能说明", "请求参数", "请求包", "应答包", "错误码"]):
                    score += 5

            if score >= 3:
                scored.append({
                    "id": doc_id,
                    "text": all_data["documents"][i],
                    "metadata": meta,
                    "distance": 1.0 / (score + 1),
                })

        scored.sort(key=lambda x: x["distance"])
        return scored[:limit]

    def _rerank(self, query: str, results: list[dict]) -> list[dict]:
        """基于文档标题的相关性重排结果"""
        cn_chars = re.findall(r'[一-鿿]', query)
        features = set()
        for i in range(len(cn_chars) - 1):
            features.add(cn_chars[i] + cn_chars[i + 1])

        for r in results:
            title = r["metadata"].get("title", "").lower()
            title_boost = sum(1 for f in features if f.lower() in title)
            r["_final_score"] = r.get("distance", 1.0) - title_boost * 0.1

        results.sort(key=lambda x: x.get("_final_score", x.get("distance", 1.0)))
        return results
