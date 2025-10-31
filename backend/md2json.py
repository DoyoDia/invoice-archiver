import re
import json

def parse_invoice_text(text: str) -> dict:
    # 定义辅助函数
    def search(pattern, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else None

    invoice = {
        "发票类型": "电子发票（普通发票）",
        "发票号码": search(r"发票号码[:：]\s*(\d+)"),
        "开票日期": search(r"开票日期[:：]\s*([0-9]{4}年[0-9]{2}月[0-9]{2}日)"),
        "购买方信息": {
            "名称": search(r"购买方信息[\s\S]*?名称[:：]\s*([^\n统]+)"),
            "纳税人识别号": search(r"购买方[\s\S]*?识别号[:：]\s*([0-9A-Z]+)")
        },
        "销售方信息": {
            "名称": search(r"销售方信息[\s\S]*?名称[:：]\s*([^\n统]+)"),
            "纳税人识别号": search(r"销售方[\s\S]*?识别号[:：]\s*([0-9A-Z]+)")
        },
        "项目": [],
        "合计": {
            "金额": search(r"合计\s*¥?([\d.]+)"),
            "税额": search(r"合计\s*¥?[\d.]+\s*¥?([\d.]+)")
        },
        "价税合计": {
            "大写": search(r"价税合计（大写）\s*⊗?([^\s（]+)"),
            "小写": search(r"（小写）¥([\d.]+)")
        },
        "备注": search(r"备注\s*([\s\S]*?)开票人") or "",
        "开票人": search(r"开票人[:：]\s*([^\n]+)")
    }

    # 提取项目行（以"项目名称"开头）
    items_pattern = r"\*([^\*]+)\*([^\s]*)\s+([^\s]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+%)\s+([\d.]+)"
    items = re.findall(items_pattern, text)
    for item in items:
        invoice["项目"].append({
            "项目名称": item[0],
            "规格型号": item[1],
            "单位": item[2],
            "数量": item[3],
            "单价": item[4],
            "金额": item[5],
            "税率": item[6],
            "税额": item[7]
        })

    return invoice
