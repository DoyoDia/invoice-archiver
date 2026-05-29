"""可选的 LLM 兜底解析（OpenAI 兼容接口）。

仅当配置了 LLM_API_KEY 时启用：正则解析失败时，把 PDF 文本交给
OpenAI 兼容的对话补全接口抽取字段。预设 DeepSeek，平时不触发此路径。
"""
from __future__ import annotations

import json
from typing import Optional

import httpx

from .config import Settings

_SYSTEM_PROMPT = "你是发票数据提取机器人，只输出JSON，不解释。"

_PROMPT = """从以下发票文本提取信息，只输出 JSON：

{source_text}

格式示例：
{{"发票类型":"电子发票（普通发票）","发票号码":"...","开票日期":"2025年06月20日","购买方信息":{{"名称":"...","纳税人识别号":"..."}},"销售方信息":{{"名称":"...","纳税人识别号":"..."}},"项目":[{{"项目名称":"...","规格型号":null,"单位":"个","数量":"1","单价":"100","金额":"100","税率":"1%","税额":"1"}}],"合计":{{"金额":"100","税额":"1"}},"价税合计":{{"大写":null,"小写":"101"}},"备注":null,"开票人":null}}

规则：数字去除¥符号，日期保持中文，缺失字段用null，只输出 JSON。
"""


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = float(settings.llm_request_timeout)

    def parse(self, source_text: str) -> Optional[dict]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _PROMPT.format(source_text=source_text)},
            ],
            "temperature": 0,
            "stream": False,
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            parsed = json.loads(content[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
