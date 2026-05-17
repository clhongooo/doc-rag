from typing import Optional

import chromadb
from chromadb.config import Settings
from chromadb import EmbeddingFunction


class VectorStore:
    def __init__(self, persist_dir: str = "data/chroma", collection_name: str = "doc_chunks",
                 embedding_function: Optional[EmbeddingFunction] = None):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        kwargs = {"metadata": {"hnsw:space": "cosine"}}
        if embedding_function:
            kwargs["embedding_function"] = embedding_function
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            **kwargs,
        )

    def add(self, chunks: list) -> None:
        if not chunks:
            return

        ids = []
        documents = []
        metadatas = []
        seen_ids = set()

        for chunk in chunks:
            chunk_id = chunk.id
            if chunk_id in seen_ids:
                i = 1
                while f"{chunk_id}_{i}" in seen_ids:
                    i += 1
                chunk_id = f"{chunk_id}_{i}"
            seen_ids.add(chunk_id)

            ids.append(chunk_id)
            documents.append(chunk.text)
            metadatas.append({
                "url": chunk.metadata.url,
                "title": chunk.metadata.title,
                "section": chunk.metadata.section,
                "chunk_type": chunk.metadata.chunk_type.value,
            })

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, query_text: str, n_results: int = 5) -> list[dict]:
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )

        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
        return output

    def count(self) -> int:
        return self.collection.count()

    def delete(self, ids: Optional[list[str]] = None) -> None:
        if ids:
            self.collection.delete(ids=ids)
        else:
            self.client.delete_collection(self.collection.name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection.name,
                metadata={"hnsw:space": "cosine"},
            )
