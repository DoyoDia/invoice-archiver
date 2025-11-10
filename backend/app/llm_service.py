from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import pymupdf4llm
import fitz  # PyMuPDF

from .config import Settings
from .llm_client import LLMClient


SYSTEM_PROMPT = """你是一个专业的发票数据提取机器人。你的唯一任务是从文本中提取发票字段,输出JSON,不做任何解释。/no_think"""

INVOICE_PROMPT_TEMPLATE = """从以下文本提取发票信息:

{source_text}

示例输出格式:
{{"发票类型":"电子发票（普通发票）","发票号码":"25312000000190830857","开票日期":"2025年06月20日","购买方信息":{{"名称":"上海杉达学院","纳税人识别号":"523100004251652819"}},"销售方信息":{{"名称":"上海市浦东新区曹路镇印德好图文广告经营部","纳税人识别号":"92310115MAEK8M5Q97"}},"项目":[{{"项目名称":"广告服务*广告制作费","规格型号":null,"单位":"个","数量":"1","单价":"128.71","金额":"128.71","税率":"1%","税额":"1.29"}}],"合计":{{"金额":"128.71","税额":"1.29"}},"价税合计":{{"大写":null,"小写":"130.00"}},"备注":null,"开票人":null}}

规则: 数字去除¥符号,日期保持中文,缺失字段用null,只输出JSON不要解释
"""


@dataclass(slots=True)
class LLMParseResult:
    data: dict
    source_markdown: str
    raw_response: dict
    fallback_used: Optional[str] = None  # "direct" | "ocr" | None
    failure_logs: Optional[dict] = None  # 失败时记录的日志


@dataclass(slots=True)
class LLMService:
    settings: Settings
    llm_client: LLMClient

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMService":
        stop_tokens = tuple(settings.llm_stop_tokens) if settings.llm_stop_tokens else None
        llm_client = LLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            stop=stop_tokens,
            temperature=settings.llm_temperature,
            min_p=settings.llm_min_p,
            repeat_penalty=settings.llm_repeat_penalty,
            top_k=settings.llm_top_k,
            top_p=settings.llm_top_p,
            timeout=float(settings.llm_request_timeout),
        )
        return cls(settings=settings, llm_client=llm_client)

    def _amount_to_chinese(self, amount: float) -> str:
        """将金额转换为中文大写"""
        if amount == 0:
            return "零圆整"
        
        # 数字对应的中文
        digits = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"]
        units = ["", "拾", "佰", "仟"]
        big_units = ["", "万", "亿"]
        
        # 分离整数和小数部分
        int_part = int(amount)
        decimal_part = round((amount - int_part) * 100)
        
        if int_part == 0:
            result = "零圆"
        else:
            # 转换整数部分
            int_str = str(int_part)
            result = ""
            zero_flag = False
            section_has_value = [False, False, False]  # 亿、万、个 三节是否有值
            
            for i, digit in enumerate(int_str):
                n = int(digit)
                pos = len(int_str) - i - 1
                section = pos // 4  # 0=个, 1=万, 2=亿
                
                if n == 0:
                    zero_flag = True
                else:
                    if zero_flag and result:
                        result += "零"
                    result += digits[n] + units[pos % 4]
                    zero_flag = False
                    section_has_value[section] = True
                
                # 添加万、亿单位
                if pos % 4 == 0 and pos > 0:
                    if section_has_value[section]:
                        result += big_units[section]
                    zero_flag = False
            
            result += "圆"
        
        # 处理小数部分
        if decimal_part == 0:
            result += "整"
        else:
            jiao = decimal_part // 10
            fen = decimal_part % 10
            if jiao > 0:
                result += digits[jiao] + "角"
            elif fen > 0:
                result += "零"
            if fen > 0:
                result += digits[fen] + "分"
        
        return result

    def _validate_parsed_data(self, data: dict) -> bool:
        """验证解析结果是否有效（发票号码或项目名称不为null）并校验金额"""
        # 检查发票号码
        invoice_no = data.get("发票号码")
        if not (invoice_no is not None and str(invoice_no).strip()):
            # 检查项目列表
            items = data.get("项目", [])
            if not items or not isinstance(items, list):
                return False
            
            # 至少有一个项目有名称或规格
            has_valid_item = False
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("项目名称")
                spec = item.get("规格型号")
                if (name is not None and str(name).strip()) or (spec is not None and str(spec).strip()):
                    has_valid_item = True
                    break
            
            if not has_valid_item:
                return False
        
        # 校验价税合计
        try:
            total_info = data.get("合计", {})
            price_tax_total = data.get("价税合计", {})
            
            if not isinstance(total_info, dict) or not isinstance(price_tax_total, dict):
                print("[DEBUG] 合计或价税合计字段格式错误")
                return False
            
            amount_str = total_info.get("金额")
            tax_str = total_info.get("税额")
            expected_chinese = price_tax_total.get("大写")
            actual_total_str = price_tax_total.get("小写")
            
            # 如果有价税合计信息,进行校验
            if expected_chinese or actual_total_str:
                if not amount_str or not tax_str:
                    print("[DEBUG] 缺少金额或税额信息,无法校验")
                    return False
                
                # 计算实际的价税合计
                amount = float(str(amount_str).replace(",", ""))
                tax = float(str(tax_str).replace(",", ""))
                calculated_total = amount + tax
                
                # 校验小写金额
                if actual_total_str:
                    actual_total = float(str(actual_total_str).replace(",", ""))
                    if abs(calculated_total - actual_total) > 0.01:
                        print(f"[DEBUG] 价税合计小写不符: 计算值 {calculated_total:.2f} != 实际值 {actual_total:.2f}")
                        return False
                
                # 校验大写金额
                if expected_chinese:
                    calculated_chinese = self._amount_to_chinese(calculated_total)
                    # 去除可能的空格和标点差异
                    expected_clean = str(expected_chinese).replace(" ", "").replace("¥", "")
                    calculated_clean = calculated_chinese.replace(" ", "")
                    
                    if expected_clean != calculated_clean:
                        print(f"[DEBUG] 价税合计大写不符: 计算值 '{calculated_chinese}' != 实际值 '{expected_chinese}'")
                        return False
                    
                    print(f"[DEBUG] 价税合计校验通过: {calculated_total:.2f} = {calculated_chinese}")
        
        except (ValueError, TypeError) as e:
            print(f"[DEBUG] 金额校验异常: {e}")
            return False
        
        return True
    
    async def _parse_with_llm(self, source_text: str) -> Optional[dict]:
        """使用 LLM 解析文本,返回解析结果或 None"""
        prompt = INVOICE_PROMPT_TEMPLATE.format(source_text=source_text)
        try:
            print(f"[DEBUG] 正在调用 LLM (超时设置: {self.settings.llm_request_timeout}秒)...")
            # 使用 system prompt 强制角色定位
            response = await self.llm_client.generate(prompt, system=SYSTEM_PROMPT)
            print(f"[DEBUG] LLM 响应长度: {len(response.text)} 字符")
            
            # 提取 JSON 部分（去除前后的说明文字和 markdown 标记）
            response_text = response.text.strip()
            
            # 尝试找到 JSON 的开始位置
            json_start = response_text.find('{')
            json_end = response_text.rfind('}')
            
            if json_start == -1 or json_end == -1:
                print(f"[DEBUG] 响应中未找到 JSON 对象")
                print(f"[DEBUG] 原始响应: {response_text[:500]}...")
                return None
            
            json_text = response_text[json_start:json_end+1]
            print(f"[DEBUG] 提取的 JSON 长度: {len(json_text)} 字符")
            print(f"[DEBUG] JSON 前500字符: {json_text[:500]}...")
            
            parsed = json.loads(json_text)
            if not isinstance(parsed, dict):
                print(f"[DEBUG] LLM 返回类型错误: {type(parsed)}")
                return None
            print(f"[DEBUG] JSON 解析成功,包含 {len(parsed)} 个字段")
            return parsed
        except json.JSONDecodeError as e:
            print(f"[DEBUG] JSON 解析失败: {e}")
            if 'json_text' in locals():
                print(f"[DEBUG] 尝试解析的文本: {json_text[:500]}...")
            return None
        except Exception as e:
            print(f"[DEBUG] LLM 调用异常: {type(e).__name__}: {e}")
            return None
    
    async def parse_invoice(self, pdf_path: Path) -> LLMParseResult:
        """解析 PDF 发票,多页逐页处理,直接提取失败自动转 OCR"""
        failure_logs = {}
        
        # 第一步: 尝试直接提取每一页的 Markdown
        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            doc.close()
            
            # 逐页提取 Markdown 并拼接
            all_markdown = []
            for page_num in range(page_count):
                page_md = pymupdf4llm.to_markdown(str(pdf_path), pages=[page_num])
                all_markdown.append(f"\n--- 第 {page_num + 1} 页 ---\n{page_md}")
            
            markdown_text = "\n".join(all_markdown)
            
            # 尝试用 LLM 解析直接提取的文本
            parsed = await self._parse_with_llm(markdown_text)
            if parsed and self._validate_parsed_data(parsed):
                return LLMParseResult(
                    data=parsed,
                    source_markdown=markdown_text,
                    raw_response={},
                    fallback_used="direct"
                )
            
            # 直接提取结果无效,记录日志
            failure_logs["direct_extract"] = {
                "text": markdown_text[:1000],  # 保留前1000字符
                "llm_result": parsed
            }
        
        except Exception as e:
            failure_logs["direct_extract_error"] = str(e)
        
        # 第二步: 直接提取失败,尝试 OCR 每一页再给 LLM
        try:
            from .ocr import OCRClient
            
            ocr_client = OCRClient(self.settings)
            ocr_result = await ocr_client.recognize_pdf(pdf_path)
            await ocr_client.aclose()
            
            ocr_text = ocr_result.text
            
            # 尝试用 LLM 解析 OCR 文本
            parsed = await self._parse_with_llm(ocr_text)
            if parsed and self._validate_parsed_data(parsed):
                return LLMParseResult(
                    data=parsed,
                    source_markdown=ocr_text,
                    raw_response={},
                    fallback_used="ocr",
                    failure_logs=failure_logs
                )
            
            # OCR 结果也无效,记录日志
            failure_logs["ocr_extract"] = {
                "text": ocr_text[:1000],
                "llm_result": parsed
            }
        
        except Exception as e:
            failure_logs["ocr_extract_error"] = str(e)
        
        # 两种方式都失败,抛出异常并附带日志
        raise ValueError(f"LLM 解析失败（直接提取和 OCR 均失败）。日志: {json.dumps(failure_logs, ensure_ascii=False, indent=2)}")

    async def aclose(self) -> None:
        await self.llm_client.aclose()
