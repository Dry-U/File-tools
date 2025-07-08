# 使用带CUDA的基础镜像
FROM nvidia/cuda:12.1.0-base-ubuntu22.04

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y \
    python3.9 \
    python3-pip \
    openjdk-11-jre \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装FAISS GPU版本
RUN pip uninstall -y faiss-cpu && \
    pip install faiss-gpu==1.7.4

# 复制项目文件
COPY . .

# 暴露端口
EXPOSE 8000 8501

# 预下载模型
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# 启动命令
CMD ["sh", "-c", "uvicorn backend.api.routes:app --host 0.0.0.0 --port 8000 --workers 4 & streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false && wait"]