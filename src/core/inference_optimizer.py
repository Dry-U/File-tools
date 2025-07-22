from typing import Generator, Dict
import time
from collections import deque
from src.utils.logger import setup_logger

logger = setup_logger()

class InferenceOptimizer:
    """推理加速器：KV Cache和批处理（基于文档4.2）"""

    def __init__(self, model_manager: Any):  # model_manager: ModelManager
        self.model_manager = model_manager
        self.kv_cache: Dict[str, Any] = {}  # {session_id: past_key_values}
        self.batch_queue: deque = deque(maxlen=50)  # 批处理队列
        self.batch_size: int = 32  # 可配置

    def generate(self, prompt: str, session_id: str = None, max_tokens: int = 512, temperature: float = 0.7) -> Generator[str, None, None]:
        """优化生成：使用KV Cache或批处理"""
        if session_id and session_id in self.kv_cache:
            yield from self._generate_with_cache(prompt, session_id, max_tokens, temperature)
        elif self._can_batch():
            self.batch_queue.append((prompt, max_tokens, temperature))
            yield from self._process_batch()
        else:
            yield from self.model_manager.generate(prompt, max_tokens, temperature)

    def _generate_with_cache(self, prompt: str, session_id: str, max_tokens: int, temperature: float) -> Generator[str, None, None]:
        """使用KV Cache生成（保持上下文）"""
        cache = self.kv_cache[session_id]
        model = self.model_manager.get_model()
        if not model:
            yield "错误：模型未加载。"
            return
        
        try:
            output = model.create_completion(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                past_key_values=cache,
                use_cache=True,
                stream=True
            )
            full_response = ''
            for token in output:
                text = token['choices'][0]['text']
                full_response += text
                yield text
            
            # 更新KV Cache
            self.kv_cache[session_id] = model.current_key_values  # 假设llama.cpp支持
        except Exception as e:
            logger.error(f"KV Cache生成失败: {e}")
            yield "错误：生成失败。"

    def _can_batch(self) -> bool:
        """检查是否可以批处理"""
        return len(self.batch_queue) >= self.batch_size or time.time() - self._last_batch_time > 5  # 超时5s

    def _process_batch(self) -> Generator[str, None, None]:
        """批处理多个请求（简化：顺序处理；实际可并行）"""
        while self.batch_queue:
            prompt, max_tokens, temperature = self.batch_queue.popleft()
            yield from self.model_manager.generate(prompt, max_tokens, temperature)
        self._last_batch_time = time.time()

    _last_batch_time = time.time()