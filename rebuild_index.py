"""重建向量索引：从英文 embedding 切换到中文 embedding"""
import chromadb
from chromadb.config import Settings
from storage.embedding import ChineseEmbeddingFunction

PERSIST_DIR = "data/chroma"
COLLECTION_NAME = "doc_chunks"

def rebuild():
    print("1. 加载中文 embedding 模型...")
    embedding_fn = ChineseEmbeddingFunction()

    print("2. 读取旧数据...")
    old_client = chromadb.PersistentClient(
        path=PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    old_col = old_client.get_collection(COLLECTION_NAME)
    total = old_col.count()
    print(f"   旧 collection 有 {total} 个 chunks")

    # 分批取出所有数据
    batch_size = 100
    all_ids = []
    all_docs = []
    all_metas = []
    offset = 0
    while offset < total:
        batch = old_col.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas"],
        )
        all_ids.extend(batch["ids"])
        all_docs.extend(batch["documents"])
        all_metas.extend(batch["metadatas"])
        offset += batch_size
    print(f"   读取完成: {len(all_ids)} 个 chunks")

    print("3. 删除旧 collection...")
    old_client.delete_collection(COLLECTION_NAME)
    del old_client

    print("4. 创建新 collection 并写入中文 embedding...")
    new_client = chromadb.PersistentClient(
        path=PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    new_col = new_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # 分批写入（embedding 计算需要时间）
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i:i+batch_size]
        batch_docs = all_docs[i:i+batch_size]
        batch_metas = all_metas[i:i+batch_size]
        print(f"   写入 {i+1}-{min(i+batch_size, len(all_ids))}...")
        new_col.upsert(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_metas,
        )

    final_count = new_col.count()
    print(f"\n完成！新 collection 有 {final_count} 个 chunks（中文 embedding）")

    # 验证：测试一条中文查询
    print("\n5. 验证查询...")
    results = new_col.query(
        query_texts=["如何调用推送接口"],
        n_results=3,
    )
    for i, (doc_id, dist) in enumerate(zip(results["ids"][0], results["distances"][0])):
        meta = results["metadatas"][0][i]
        title = meta.get("title", "?")[:30]
        print(f"   {i+1}. [{dist:.4f}] {title}")


if __name__ == "__main__":
    rebuild()
