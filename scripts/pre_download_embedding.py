"""一次性预下载 embedding 模型（国内 hf-mirror 镜像）"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from sentence_transformers import SentenceTransformer

model_name = "all-MiniLM-L6-v2"
print(f"Downloading {model_name} (~80MB) from hf-mirror.com ...")
m = SentenceTransformer(model_name)
print(f"Done! Dimension: {m.get_embedding_dimension()}")
