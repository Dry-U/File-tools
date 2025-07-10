# src/api/app.py
from fastapi import FastAPI
from src.api.routes import router
from src.utils.logger import setup_logger

logger = setup_logger()

app = FastAPI(title="DocAssistant API", version="1.0")

app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health_check():
    """健康检查端点（用于Docker等）"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


    # app.py
import subprocess

def start_api_server():
    """启动FastAPI服务器"""
    try:
        subprocess.Popen(["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080"])
        logger.info("API服务器启动")
    except Exception as e:
        logger.error(f"API启动失败: {e}")

# 在main()开头调用
if 'api_started' not in st.session_state:
    start_api_server()
    st.session_state.api_started = True