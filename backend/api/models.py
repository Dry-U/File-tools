"""
API 请求/响应模型定义
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """搜索请求模型"""

    query: str
    filters: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    """搜索结果模型"""

    file_name: str
    path: str
    score: float
    snippet: str


class ChatRequest(BaseModel):
    """对话请求模型"""

    query: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """对话响应模型"""

    answer: str
    sources: List[Dict[str, Any]]


class PreviewRequest(BaseModel):
    """文件预览请求模型"""

    path: str


class PreviewResponse(BaseModel):
    """文件预览响应模型"""

    content: str


class ConfigUpdateRequest(BaseModel):
    """配置更新请求模型"""

    ai_model: Optional[Dict[str, Any]] = None
    rag: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    """健康检查响应模型"""

    status: str
    initialized: bool
    timestamp: float
    components: Dict[str, Any]


class DirectoryPath(BaseModel):
    """目录路径请求模型"""

    path: str


class DirectoryResponse(BaseModel):
    """目录响应模型"""

    status: str
    message: str
    path: Optional[str] = None
    needs_rebuild: bool = False


class BrowseResponse(BaseModel):
    """浏览目录响应模型"""

    status: str
    path: Optional[str] = None
    canceled: bool = False


class DirectoryInfo(BaseModel):
    """目录信息模型"""

    path: str
    exists: bool
    is_scanning: bool
    is_monitoring: bool
    file_count: int


class DirectoriesListResponse(BaseModel):
    """目录列表响应模型"""

    directories: List[DirectoryInfo]


class AIModelSecurityValidator(BaseModel):
    """AI模型安全配置验证"""

    verify_ssl: bool = True
    timeout: int = 120
    retry_count: int = 2


class AIModelSamplingValidator(BaseModel):
    """AI模型采样参数验证"""

    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    min_p: float = 0.05
    max_tokens: int = 2048
    seed: int = -1


class AIModelPenaltiesValidator(BaseModel):
    """AI模型惩罚参数验证"""

    repeat_penalty: float = 1.1
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


class AIModelLocalValidator(BaseModel):
    """AI模型本地模式配置验证"""

    api_url: str = "http://localhost:8000/v1/chat/completions"
    max_context: int = 4096
    max_tokens: int = 512


class AIModelAPIValidator(BaseModel):
    """AI模型API模式配置验证"""

    provider: str = "siliconflow"
    api_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    api_key: str = ""
    keys: Dict[str, str] = Field(default_factory=dict)
    model_name: str = "deepseek-ai/DeepSeek-V2.5"
    max_context: int = 8192
    max_tokens: int = 2048


class AIModelConfigValidator(BaseModel):
    """AI模型完整配置验证"""

    enabled: bool = False
    mode: str = "local"
    system_prompt: str = ""
    local: AIModelLocalValidator = AIModelLocalValidator()
    api: AIModelAPIValidator = AIModelAPIValidator()
    security: AIModelSecurityValidator = AIModelSecurityValidator()
    sampling: AIModelSamplingValidator = AIModelSamplingValidator()
    penalties: AIModelPenaltiesValidator = AIModelPenaltiesValidator()


class RAGConfigValidator(BaseModel):
    """RAG配置验证"""

    max_history_turns: int = 3
    max_history_chars: int = 1000


class SearchConfigValidator(BaseModel):
    """搜索配置验证"""

    text_weight: float = 0.6
    vector_weight: float = 0.4
    max_results: int = 50
    snippet_length: int = 200
