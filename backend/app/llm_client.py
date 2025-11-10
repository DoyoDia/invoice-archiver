from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    raw: Dict[str, Any]


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        stop: Optional[Sequence[str]] = None,
        temperature: float = 0.7,
        min_p: float = 0.0,
        repeat_penalty: float = 1.05,
        top_k: int = 20,
        top_p: float = 0.8,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_options = {
            "temperature": temperature,
            "min_p": min_p,
            "repeat_penalty": repeat_penalty,
            "top_k": top_k,
            "top_p": top_p,
        }
        if stop:
            self.default_options["stop"] = list(stop)
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def generate(
        self, 
        prompt: str, 
        *, 
        system: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        client = await self._get_client()
        
        # 使用 chat 接口,Qwen3 需要 role 格式
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "options": {**self.default_options, **(options or {})},
            "stream": True,  # 使用流式输出
        }
        url = f"{self.base_url}/api/chat"
        
        accumulated_text = ""
        stop_tokens = self.default_options.get("stop", [])
        
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                
                try:
                    chunk = json.loads(line)
                    
                    # chat 接口返回的是 message.content
                    if "message" in chunk and "content" in chunk["message"]:
                        accumulated_text += chunk["message"]["content"]
                        
                        # 检查是否遇到停止符
                        should_stop = False
                        for stop_token in stop_tokens:
                            if stop_token in accumulated_text:
                                # 移除停止符及其后的内容
                                accumulated_text = accumulated_text.split(stop_token)[0]
                                should_stop = True
                                break
                        
                        if should_stop:
                            break
                        
                        # 检查 JSON 是否完整(找到最后的 })
                        if accumulated_text.strip().endswith("}"):
                            # 尝试验证 JSON 完整性
                            open_braces = accumulated_text.count("{")
                            close_braces = accumulated_text.count("}")
                            if open_braces > 0 and open_braces == close_braces:
                                # JSON 可能已完整,停止接收
                                break
                    
                    # 检查是否完成
                    if chunk.get("done", False):
                        break
                        
                except Exception:
                    continue
        
        if not accumulated_text:
            raise ValueError("LLM response missing text content")

        return LLMResponse(text=accumulated_text.strip(), raw={"response": accumulated_text})

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
