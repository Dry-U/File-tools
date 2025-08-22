# app.py (完整更新，焦点在聊天输入部分)
import streamlit as st
import subprocess
import time
import requests  # 新增：用于API调用
from src.utils.logger import setup_logger
from src.utils.config_loader import ConfigLoader
from src.core.model_manager import ModelManager
from src.core.rag_pipeline import RAGPipeline  # 保持导入，但现在不直接用
from src.core.file_scanner import FileScanner

logger = setup_logger()

def start_wsl_model():
    """自动启动WSL中的llama.cpp模型服务器（从Part 1）"""
    config = ConfigLoader()
    wsl_path = config.get('system', 'wsl_model_path')
    try:
        subprocess.Popen(['wsl', '-d', 'Ubuntu', 'bash', '-c', f'cd {wsl_path} && ~/my-projects/repo_llama.cpp/bin/llama-server --model ~/models/YiLin.gguf --host 0.0.0.0 --port 9090'])
        time.sleep(5)
        logger.info("WSL model server started successfully.")
    except Exception as e:
        logger.error(f"Failed to start WSL model: {e}")
        st.error("模型启动失败，请检查WSL配置。")

def start_api_server():
    """启动FastAPI服务器（从Part 9）"""
    try:
        subprocess.Popen(["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080"])
        logger.info("API服务器启动")
    except Exception as e:
        logger.error(f"API启动失败: {e}")

def main():
    st.title("本地文档智能问答系统")
    
    # 自动启动WSL模型和API服务器（仅一次）
    if 'model_started' not in st.session_state:
        start_wsl_model()
        st.session_state.model_started = True
    if 'api_started' not in st.session_state:
        start_api_server()
        st.session_state.api_started = True
    
    # 初始化核心组件（保持，但RAG现在通过API间接使用）
    config = ConfigLoader()
    model_manager = ModelManager(config)
    scanner = FileScanner(config)
    # rag = RAGPipeline(model_manager, config)  # 可注释掉，不再直接用
    
    # 侧边栏：设置（保持不变）
    with st.sidebar:
        st.header("设置")
        scan_button = st.button("扫描文件")
        if scan_button:
            with st.spinner("正在扫描文件..."):
                scanner.scan_and_index()
            st.success("扫描完成！")
    
    # 主界面：聊天对话
    st.header("AI问答")
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    
    if prompt := st.chat_input("输入您的查询"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                # 修改：调用API代替直接rag.query (您的代码片段)
                api_url = "http://localhost:9090/api/v1/query"
                token = st.session_state.get('jwt_token', "your-jwt-token")  # 从session_state获取；fallback到默认（测试用）
                response = requests.post(
                    api_url,
                    json={"query": prompt},
                    headers={"Authorization": f"Bearer {token}"}
                )
                if response.status_code == 200:
                    result = response.json()
                    st.markdown(result['answer'])
                    st.markdown("**来源：** " + ", ".join(result['sources']))
                    st.session_state.messages.append({"role": "assistant", "content": result['answer']})
                else:
                    st.error("API调用失败")
                    st.session_state.messages.append({"role": "assistant", "content": "错误：API调用失败"})

if __name__ == "__main__":
    main(scanner = FileScanner(config))
# 在按钮或启动时调用 scanner.scan_and_index())