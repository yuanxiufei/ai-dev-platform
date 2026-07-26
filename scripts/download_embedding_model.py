"""预下载 embedding 模型到 HuggingFace 缓存目录"""
import os
import sys

cache_dir = r"D:\app\LLM\models\huggingface\hub"
os.makedirs(cache_dir, exist_ok=True)
os.environ["HF_HOME"] = cache_dir
os.environ["XDG_CACHE_HOME"] = cache_dir

print(f"缓存目录: {cache_dir}")
print("下载 all-MiniLM-L6-v2 (约 80MB)...")

from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=cache_dir, device="cpu")
dim = model.get_sentence_embedding_dimension()
print(f"模型下载完成, 维度: {dim}")
