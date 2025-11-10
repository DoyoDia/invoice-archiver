import re

def parse_invoice_from_ocr(text: str) -> dict:
    """
    解析 OCR 返回的发票文本
    OCR 文本特点：格式相对规整，表格用 | 分隔，或者空格分隔
    """
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
    
    # OCR 格式：购买方/销售方通常在表格中或同一行
    buyer_seller_line = re.search(
        r"\|\s*购买方信息\s*\|\s*名称[:：]\s*([^\|]+?)\s*\|\s*销售方信息\s*\|\s*名称[:：]\s*([^\|]+?)\s*\|", 
        text
    )
    if buyer_seller_line:
        invoice["购买方信息"]["名称"] = buyer_seller_line.group(1).strip()
        invoice["销售方信息"]["名称"] = buyer_seller_line.group(2).strip()
    else:
        # 尝试分开匹配
        buyer_name = search(r"购买方信息[\s\S]{0,200}?名称[:：]\s*([^\n]+)")
        if buyer_name:
            invoice["购买方信息"]["名称"] = buyer_name
        seller_name = search(r"销售方信息[\s\S]{0,200}?名称[:：]\s*([^\n]+)")
        if seller_name:
            invoice["销售方信息"]["名称"] = seller_name
    
    # 提取纳税人识别号
    tax_ids = re.findall(r"统一社会信用代码/纳税人识别号[:：]\s*([0-9A-Z]+)", text)
    if len(tax_ids) >= 2:
        invoice["购买方信息"]["纳税人识别号"] = tax_ids[0]
        invoice["销售方信息"]["纳税人识别号"] = tax_ids[1]
    elif len(tax_ids) == 1:
        invoice["购买方信息"]["纳税人识别号"] = tax_ids[0]

    items = []
    
    # 格式1: 空格分隔 - *项目名称*规格型号 单位 数量 单价 金额 税率 税额
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
    
    # 格式2: 表格格式 - | 项目名称 | 规格型号 | 单位 | ...
    if not items:
        text_normalized = re.sub(r'\|\s*\|', '|\n|', text)
        all_table_rows = re.findall(r"\|([^\n]+)\|", text_normalized)
        
        for row in all_table_rows:
            cols = [c.strip() for c in row.split('|')]
            if not cols or not cols[0]:
                continue
            if any(kw in '|'.join(cols) for kw in ["项目名称", "规格型号", "合计", "价税", "购买方", "销售方"]):
                continue
            
            if len(cols) >= 6 and any(re.match(r'^\d+(\.\d+)?$', c) for c in cols):
                # 找到税率列 (xx%)
                tax_rate_idx = -1
                for i in range(len(cols)-1, -1, -1):
                    if re.match(r'^\d+%$', cols[i]):
                        tax_rate_idx = i
                        break
                
                if tax_rate_idx >= 5:
                    item = {
                        "单位": cols[tax_rate_idx - 4],
                        "数量": cols[tax_rate_idx - 3],
                        "单价": cols[tax_rate_idx - 2],
                        "金额": cols[tax_rate_idx - 1],
                        "税率": cols[tax_rate_idx],
                        "税额": cols[tax_rate_idx + 1] if tax_rate_idx + 1 < len(cols) else ""
                    }
                    
                    name_cols = cols[:tax_rate_idx - 4]
                    if len(name_cols) >= 2:
                        item["项目名称"] = name_cols[0]
                        item["规格型号"] = name_cols[1]
                    elif len(name_cols) == 1:
                        item["项目名称"] = name_cols[0]
                        item["规格型号"] = ""
                    else:
                        continue
                    
                    items.append(item)
    
    # 格式3: 垂直布局（OCR 有时也会这样）
    if not items:
        m = re.search(r"\*([^\*]+)\*([^\n\r]*)", text)
        if m:
            pname = m.group(1).strip() if m.group(1) else ""
            pspec = m.group(2).strip() if m.group(2) else ""
            after = text[m.end():]
            lines = [ln.strip() for ln in re.split(r"[\r\n]+", after) if ln.strip()]
            vals = []
            
            for ln in lines:
                if re.search(r"合计|价税合计|开票人", ln):
                    break
                clean = ln.replace('¥', '').strip()
                if re.match(r'^\d+(\.\d+)?%?$', clean):
                    vals.append(clean)
            
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


def parse_invoice_from_pdf_text(text: str) -> dict:
    """
    解析 pypdf 提取的 PDF 文本
    PDF 文本特点：
    1. 标签和值经常分行
    2. 单字可能被拆散（如"购\n买\n方"）
    3. 垂直布局更常见
    4. 数据按行顺序排列而非表格格式
    """
    def search(pattern, flags=0):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else None
    
    # 先清理文本：移除单字换行造成的干扰
    # 将 "购\n买\n方" 这种拆分合并，但保留正常换行
    lines = text.split('\n')
    cleaned_lines = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 如果是单字行，尝试与下一行合并
        if len(line) == 1 and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if len(next_line) == 1:
                # 连续的单字行，合并它们
                merged = line
                j = i + 1
                while j < len(lines) and len(lines[j].strip()) == 1:
                    merged += lines[j].strip()
                    j += 1
                cleaned_lines.append(merged)
                i = j
                continue
        cleaned_lines.append(line)
        i += 1
    
    cleaned_text = '\n'.join(cleaned_lines)
    text = cleaned_text

    invoice = {
        "发票类型": "电子发票（普通发票）",
        "发票号码": search(r"发票号码[:：]\s*\n?\s*(\d+)"),
        "开票日期": search(r"开票日期[:：]\s*\n?\s*([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)"),
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
            "金额": None,
            "税额": None
        },
        "价税合计": {
            "大写": search(r"价税合计[（\(]大写[）\)]\s*¥?([^\s（\(]+)"),
            "小写": search(r"[（\(]小写[）\)][:：]?\s*\n?\s*¥?([\d.]+)")
        },
        "备注": search(r"备\s*注\s*([\s\S]*?)开票人") or "",
        "开票人": search(r"开票人[:：]\s*\n?\s*([^\n\s]+)")
    }
    
    # PDF 格式：合计可能垂直布局
    合计_match = re.search(r"合\s*计\s*¥?([\d.]+)\s*¥?([\d.]+)", text)
    if 合计_match:
        invoice["合计"]["金额"] = 合计_match.group(1)
        invoice["合计"]["税额"] = 合计_match.group(2)
    else:
        合计_section = re.search(r"合\s*计[\s\S]{0,50}", text)
        if 合计_section:
            amounts = re.findall(r"¥?([\d.]+)", 合计_section.group(0))
            if len(amounts) >= 2:
                invoice["合计"]["金额"] = amounts[0]
                invoice["合计"]["税额"] = amounts[1]
    
    # PDF 格式：购买方/销售方名称处理
    # 策略：按顺序查找"名称："，第一个是购买方，第二个是销售方
    name_pattern = r"名称[:：]\s*\n?\s*([^\n]+)"
    all_matches = list(re.finditer(name_pattern, text))
    
    if len(all_matches) >= 1:
        name1 = all_matches[0].group(1).strip()
        name1 = re.sub(r'[购买方销售信息户）\)]+$', '', name1).strip()
        if name1 and len(name1) >= 2:
            invoice["购买方信息"]["名称"] = name1
    
    if len(all_matches) >= 2:
        name2 = all_matches[1].group(1).strip()
        name2 = re.sub(r'[购买方销售信息户）\)]+$', '', name2).strip()
        
        # 如果第二个名称无效，尝试在后续行查找
        if not name2 or len(name2) < 2:
            pos = all_matches[1].end()
            remaining = text[pos:pos+200]
            for line in remaining.split('\n'):
                line = line.strip()
                if len(line) >= 4 and re.search(r'[\u4e00-\u9fa5]', line):
                    line = re.sub(r'[户）\)]+$', '', line).strip()
                    if not any(kw in line for kw in ['统一', '社会', '信用', '代码', '识别号']):
                        invoice["销售方信息"]["名称"] = line
                        break
        else:
            invoice["销售方信息"]["名称"] = name2
    
    # 提取纳税人识别号
    tax_ids = re.findall(r"统一社会信用代码/纳税人识别号[:：]\s*\n?\s*([0-9A-Z]+)", text)
    if len(tax_ids) >= 2:
        invoice["购买方信息"]["纳税人识别号"] = tax_ids[0]
        invoice["销售方信息"]["纳税人识别号"] = tax_ids[1]
    elif len(tax_ids) == 1:
        invoice["购买方信息"]["纳税人识别号"] = tax_ids[0]

    # PDF 格式：项目通常是垂直布局
    items = []
    m = re.search(r"\*([^\*]+)\*([^\n\r]*)", text)
    if m:
        pname = m.group(1).strip() if m.group(1) else ""
        pspec = m.group(2).strip() if m.group(2) else ""
        after = text[m.end():]
        
        lines = [ln.strip() for ln in re.split(r"[\r\n]+", after) if ln.strip()]
        vals = []
        unit = ""
        
        for ln in lines:
            if re.search(r"合\s*计|价税合计|开票人|备\s*注", ln):
                break
            
            # 跳过标签行
            if re.search(r"规格型号|单\s*位|数\s*量|单\s*价|金\s*额|税率|税\s*额|征收率", ln):
                continue
            
            clean = ln.replace('¥', '').strip()
            
            # 收集单位（短文本，排除关键字）
            if not unit and len(clean) <= 3 and not re.match(r'^\d', clean) and clean:
                if clean not in ['合', '计', '税', '额', '率']:
                    unit = clean
                    continue
            
            # 收集数字
            if re.match(r'^\d+(\.\d+)?%?$', clean):
                vals.append(clean)
        
        # 找到税率位置
        if len(vals) >= 5:
            tax_rate_idx = -1
            for i, v in enumerate(vals):
                if '%' in v:
                    tax_rate_idx = i
                    break
            
            if tax_rate_idx >= 3:
                items.append({
                    "项目名称": pname,
                    "规格型号": pspec or "",
                    "单位": unit,
                    "数量": vals[0],
                    "单价": vals[1],
                    "金额": vals[2],
                    "税率": vals[tax_rate_idx],
                    "税额": vals[tax_rate_idx + 1] if tax_rate_idx + 1 < len(vals) else ""
                })

    invoice["项目"] = items
    return invoice
