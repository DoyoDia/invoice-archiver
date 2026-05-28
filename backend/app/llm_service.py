"""可选的 LLM 兜底解析。

仅当配置了 LLM_BASE_URL 时启用：正则解析失败时，把 PDF 文本交给本地
Ollama 模型抽取字段。平时这条路径不会被触发。
"""
from __future__ import annotations

import json
from typing import Optional

import httpx

from .config import Settings

_SYSTEM_PROMPT = "你是发票数据提取机器人，只输出JSON，不解释。/no_think"

_PROMPT = """从以下发票文本提取信息，只输出JSON：

{source_text}

格式示例：
{{"发票类型":"电子发票（普通发票）","发票号码":"...","开票日期":"2025年06月20日","购买方信息":{{"名称":"...","纳税人识别号":"..."}},"销售方信息":{{"名称":"...","纳税人识别号":"..."}},"项目":[{{"项目名称":"...","规格型号":null,"单位":"个","数量":"1","单价":"100","金额":"100","税率":"1%","税额":"1"}}],"合计":{{"金额":"100","税额":"1"}},"价税合计":{{"大写":null,"小写":"101"}},"备注":null,"开票人":null}}

规则：数字去除¥符号，日期保持中文，缺失字段用null，只输出JSON。
"""


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout = float(settings.llm_request_timeout)

    def parse(self, source_text: str) -> Optional[dict]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _PROMPT.format(source_text=source_text)},
            ],
            "stream": False,
            "options": {"temperature": 0.0},
        }
        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
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
