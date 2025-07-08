import streamlit as st
from backend.core.service import DocumentProcessor
from config import settings

# 初始化处理器
processor = DocumentProcessor(
    model_name=settings.nlp.model_name,
    faiss_index_path=settings.retrieval.faiss_index_path
)

# 应用标题
st.title("智能文件处理系统")

# 侧边栏设置
with st.sidebar:
    st.header("配置选项")
    upload_dir = st.text_input("监控目录", value="./docs")
    chunk_size = st.slider("分块大小", 128, 1024, 512)

# 文件上传区
uploaded_files = st.file_uploader(
    "上传文档", 
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True
)

if uploaded_files:
    with st.spinner("处理文件中..."):
        results = processor.process_files(uploaded_files)
        st.success(f"已处理 {len(results)} 个文档")

# 搜索功能区
query = st.text_input("输入搜索内容")
if query:
    with st.spinner("搜索中..."):
        results = processor.search(query, top_k=3)
        for doc in results:
            with st.expander(f"相似度: {doc.score:.2f}"):
                st.markdown(doc.page_content)