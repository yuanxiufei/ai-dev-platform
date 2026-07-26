#!/bin/bash
set -e

# 确保 pip 可用
if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null 2>&1; then
    echo "=== 安装 python3-pip ==="
    sudo apt update -qq && sudo apt install -y -qq python3-pip
fi

PIP="python3 -m pip"
echo "=== 安装 sentence-transformers ==="
$PIP install sentence-transformers -q --break-system-packages

echo ""
echo "=== 下载 all-MiniLM-L6-v2 模型 ==="
HF_DIR=/mnt/d/app/LLM/models/huggingface/hub
mkdir -p "$HF_DIR"

python3 -c "
import os
os.environ['HF_HOME'] = '$HF_DIR'
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('all-MiniLM-L6-v2', cache_folder='$HF_DIR', device='cpu')
print(f'维度: {m.get_sentence_embedding_dimension()}')
print('下载完成!')
"

echo ""
echo "=== 缓存文件 ==="
ls -lh "$HF_DIR"/models--sentence-transformers--all-MiniLM-L6-v2/ 2>/dev/null || echo "(新模型，检查 snapshots)"
ls "$HF_DIR"/ | grep -i mini
