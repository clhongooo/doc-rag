"""Chinese embedding function for ChromaDB"""
from pathlib import Path
from chromadb import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer

# 项目根目录下的本地模型
LOCAL_MODEL_PATH = str(Path(__file__).parent.parent / "models" / "text2vec-base-chinese")


class ChineseEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model_name: str = LOCAL_MODEL_PATH):
        self.model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self.model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()
