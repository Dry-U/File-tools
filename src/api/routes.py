# src/api/routes.py
from fastapi import APIRouter, Depends, HTTPException
from src.api.models import QueryRequest, QueryResponse
from src.api.auth import verify_token, create_access_token
from src.core.rag_pipeline import RAGPipeline
from src.core.security_manager import SecurityManager
from src.utils.config_loader import ConfigLoader

router = APIRouter()
config = ConfigLoader()  # 全局配置；实际可注入
security = SecurityManager(config)
rag = RAGPipeline(...)  # 注入完整依赖（ModelManager等）；假设从main注入

class LoginRequest(BaseModel):
    username: str
    password: str  # 简化；生产中使用hash


@router.post("/token")
def login(request: LoginRequest):
    # 模拟验证（实际使用数据库）
    if request.username == "admin" and request.password == "password":
        token = create_access_token({"sub": request.username, "role": "admin"})
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="无效凭证")


@router.post("/query", response_model=QueryResponse)
def execute_query(request: QueryRequest, token_data: dict = Depends(verify_token)):
    """执行智能查询（基于文档9.1）"""
    if not security.check_permission('query', token_data.get('role')):
        raise HTTPException(status_code=403, detail="权限不足")
    
    try:
        result = rag.query(request.query)
        # 可选：应用文件过滤（如果request.file_filter，过滤sources）
        if request.file_filter:
            result['sources'] = [s for s in result['sources'] if any(f in s for f in request.file_filter)]
        
        security.log_audit("api_query", {"query": request.query, "user": token_data['username']})
        return QueryResponse(answer=result['answer'], sources=result['sources'])
    except Exception as e:
        logger.error(f"API查询失败: {e}")
        raise HTTPException(status_code=500, detail="内部服务器错误")


