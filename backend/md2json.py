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
        "开票日期": search(r"开票日期[:：]\s*([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)"),
        "购买方信息": {
            "名称": None,
            "纳税人识别号": None
        },
        "销售方信息": {
            "名称": None,
            "纳税人识别号": None
        },
        "项目": [],
        "合计": {
            "金额": search(r"合计\s*¥?([\d.]+)"),
            "税额": search(r"合计\s*¥?[\d.]+\s*¥?([\d.]+)")
        },
        "价税合计": {
            "大写": search(r"价税合计[（\(]大写[）\)]\s*¥?([^\s（\(]+)"),
            "小写": search(r"[（\(]小写[）\)][:：]?\s*¥?([\d.]+)")
        },
        "备注": search(r"备\s*注\s*([\s\S]*?)开票人") or "",
        "开票人": search(r"开票人[:：]\s*([^\n\s]+)")
    }
    
    # 解析购买方和销售方信息（表格格式优先）
    # | 购买方信息 | 名称：xxx | 销售方信息 | 名称：yyy |
    buyer_seller_line = re.search(r"\|\s*购买方信息\s*\|\s*名称[:：]\s*([^\|]+?)\s*\|\s*销售方信息\s*\|\s*名称[:：]\s*([^\|]+?)\s*\|", text)
    if buyer_seller_line:
        invoice["购买方信息"]["名称"] = buyer_seller_line.group(1).strip()
        invoice["销售方信息"]["名称"] = buyer_seller_line.group(2).strip()
    else:
        # 兼容换行格式：
        # 购买方信息\n名称：上海杉达学院\n统一社会信用代码/纳税人识别号：...
        buyer_name_line = re.search(r"购买方信息[\s\S]{0,200}?名称[:：]\s*([^\n]+)", text)
        if buyer_name_line:
            invoice["购买方信息"]["名称"] = buyer_name_line.group(1).strip()
        seller_name_line = re.search(r"销售方信息[\s\S]{0,200}?名称[:：]\s*([^\n]+)", text)
        if seller_name_line:
            invoice["销售方信息"]["名称"] = seller_name_line.group(1).strip()
    
    # 提取纳税人识别号 - 第一个是购买方，第二个是销售方
    tax_ids = re.findall(r"统一社会信用代码/纳税人识别号[:：]\s*([0-9A-Z]+)", text)
    if len(tax_ids) >= 2:
        invoice["购买方信息"]["纳税人识别号"] = tax_ids[0]
        invoice["销售方信息"]["纳税人识别号"] = tax_ids[1]
    elif len(tax_ids) == 1:
        # 兼容只有一个识别号的情况
        invoice["购买方信息"]["纳税人识别号"] = tax_ids[0]

    # 提取项目行 - 支持两种格式:
    # 格式1: 空格分隔 - *项目名称*规格型号 单位 数量 单价 金额 税率 税额
    # 格式2: 表格分隔 - | 项目名称 | 规格型号 | 单位 | ...
    items = []
    
    # 尝试格式1: 空格分隔格式 (保持原有逻辑不变)
    items_pattern = r"\*([^\*]+)\*([^\s]*)\s+([^\s]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+%)\s+([\d.]+)"
    matches = re.findall(items_pattern, text)
    for item in matches:
        items.append({
            "项目名称": item[0],
            "规格型号": item[1],
            "单位": item[2],
            "数量": item[3],
            "单价": item[4],
            "金额": item[5],
            "税率": item[6],
            "税额": item[7]
        })
    
    # 如果空格分隔格式没匹配到，尝试格式2: 表格格式
    if not items:
        # 先分割所有表格行 - 注意有些发票标题和数据在同一行，用 |  | (中间可能有空格) 分隔
        # 将 |\s*| 替换为换行，然后再提取表格行
        text_normalized = re.sub(r'\|\s*\|', '|\n|', text)
        all_table_rows = re.findall(r"\|([^\n]+)\|", text_normalized)
        
        for row in all_table_rows:
            cols = [c.strip() for c in row.split('|')]
            # 跳过标题行、空行、汇总行
            if not cols or not cols[0]:
                continue
            if any(kw in '|'.join(cols) for kw in ["项目名称", "规格型号", "合计", "价税", "购买方", "销售方"]):
                continue
            
            # 只处理包含数字的数据行 (必须有数量、单价、金额等)
            if len(cols) >= 6 and any(re.match(r'^\d+(\.\d+)?$', c) for c in cols):
                # 智能识别列结构 - 从后往前匹配固定格式: 税额|税率|金额|单价|数量|单位
                # 找到最后一个税率列 (xx%)
                tax_rate_idx = -1
                for i in range(len(cols)-1, -1, -1):
                    if re.match(r'^\d+%$', cols[i]):
                        tax_rate_idx = i
                        break
                
                if tax_rate_idx >= 5:  # 至少需要6列数据
                    # 标准结构: ... | 单位 | 数量 | 单价 | 金额 | 税率 | 税额
                    item = {
                        "单位": cols[tax_rate_idx - 4],
                        "数量": cols[tax_rate_idx - 3],
                        "单价": cols[tax_rate_idx - 2],
                        "金额": cols[tax_rate_idx - 1],
                        "税率": cols[tax_rate_idx],
                        "税额": cols[tax_rate_idx + 1] if tax_rate_idx + 1 < len(cols) else ""
                    }
                    
                    # 项目名称和规格型号在前面，可能是1列或2列
                    name_cols = cols[:tax_rate_idx - 4]
                    if len(name_cols) >= 2:
                        item["项目名称"] = name_cols[0]
                        item["规格型号"] = name_cols[1]
                    elif len(name_cols) == 1:
                        item["项目名称"] = name_cols[0]
                        item["规格型号"] = ""
                    else:
                        continue  # 无效行
                    
                    items.append(item)

    # 如果仍然没有匹配到，尝试垂直布局（标签一列、值在后续多行）
    if not items:
        # 找到以 *name*spec 这样的行
        m = re.search(r"\*([^\*]+)\*([^\n\r]*)", text)
        if m:
            pname = m.group(1).strip() if m.group(1) else ""
            pspec = m.group(2).strip() if m.group(2) else ""
            after = text[m.end():]
            # 收集后续非空行，直到遇到合计/价税合计等终止关键词
            lines = [ln.strip() for ln in re.split(r"[\r\n]+", after) if ln.strip()]
            vals = []
            for ln in lines:
                if re.search(r"合计|价税合计|开票人", ln):
                    break
                # 金额前可能有 ¥ 前缀，去掉
                clean = ln.replace('¥', '').strip()
                # 匹配数字或带% 的税率
                if re.match(r'^\d+(\.\d+)?%?$', clean):
                    vals.append(clean)
                # 有时金额写成 1% 或 0.13 等，这里尽量收集
            # 期望序列: 数量, 单价, 金额, 税率, 税额 (至少需5项)
            if len(vals) >= 5:
                items.append({
                    "项目名称": pname,
                    "规格型号": pspec or "",
                    "单位": "",
                    "数量": vals[0],
                    "单价": vals[1],
                    "金额": vals[2],
                    "税率": vals[3],
                    "税额": vals[4]
                })

    invoice["项目"] = items

    return invoice
