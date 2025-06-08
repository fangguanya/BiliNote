from typing import Optional, Union

from openai import OpenAI
from app.utils.retry_utils import retry_on_rate_limit

class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str, model: Union[str, None]=None):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    @property
    def get_client(self):
        return self.client

    @retry_on_rate_limit(max_retries=3, delay=30.0, backoff_factor=1.5)
    def chat(self, model: str, messages: list, temperature: float = 0.7, **kwargs):
        """带重试功能的聊天完成方法"""
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs
        )

    def list_models(self):
        """获取模型列表"""
        return self.client.models.list()

    @staticmethod
    def test_connection(api_key: str, base_url: str) -> bool:
        print(api_key)
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            client.models.list()
            return True
        except Exception as e:
            print(f"Error connecting to OpenAI API: {e}")
            return False