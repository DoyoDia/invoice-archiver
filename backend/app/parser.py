"""坐标感知的电子发票解析。

电子发票（全电）PDF 的文本层里标签与数值是分离的，纯文本顺序错乱，
因此按词的坐标重建版面。支持三种结构：
- 单张单页发票
- 单张多页发票（明细溢出到次页，各页号码相同 → 合并）
- 合并发票（一个 PDF 含多张不同号码的发票，可能一页两张 → 拆分）

`parse_invoices()` 返回发票字典列表（中文键，与下游映射一致）。
"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymupdf

Word = Tuple[float, float, float, float, str]  # x0, y0, x1, y1, text

_HALF_X = 300.0       # 左(购买方) / 右(销售方) 分界
_Y_TOL = 4.0          # 同一行的 y 容差
_BASE_HEADER_Y = 22.7  # 标准模板中“电子发票”表头的 y，块平移到此对齐

_TAXID_RE = re.compile(r"^[0-9A-Z]{15,20}$")
_PCT_RE = re.compile(r"^-?\d+(?:\.\d+)?%$")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# 标准全电发票的列中心（找不到表头时的兜底；不同模板列数/位置会变）
_DEFAULT_COLS = {"单位": 199.0, "数量": 272.0, "单价": 343.0, "金额": 415.0, "税率": 471.0, "税额": 565.0}
_HEADER_LABELS = {"项目名称", "规格型号", "单位", "数量", "单价", "金额", "税额"}


def _same_line(a: float, b: float) -> bool:
    return abs(a - b) <= _Y_TOL


def _derive_columns(words: List[Word]) -> Tuple[Dict[str, float], float]:
    """从表头行推导各列中心 x（不同发票模板列数与位置不同，如客运发票无规格/单位）。

    表头里“单 位”“数 量”等会被拆成单字，按相邻间距合并还原为整列标签。
    """
    hy = next((y0 for x0, y0, x1, y1, t in words if t == "项目名称"), None)
    if hy is None:
        return dict(_DEFAULT_COLS), 150.0

    row = sorted(((x0, x1, t) for x0, y0, x1, y1, t in words if _same_line(y0, hy)), key=lambda w: w[0])
    groups: List[List] = []
    for x0, x1, t in row:
        if groups and x0 - groups[-1][1] < 12:  # 相邻单字 → 同一列标签
            groups[-1][1], groups[-1][2] = x1, groups[-1][2] + t
        else:
            groups.append([x0, x1, t])

    cols: Dict[str, float] = {}
    for x0, x1, label in groups:
        center = (x0 + x1) / 2
        if "税率" in label or "征收率" in label:
            cols["税率"] = center
        elif label in _HEADER_LABELS:
            cols[label] = center
    return cols, hy


def parse_invoices(pdf_path: Path) -> List[dict]:
    """解析 PDF，返回其中所有发票（合并发票拆分、多页发票合并）。"""
    with pymupdf.open(str(pdf_path)) as doc:
        pages: List[List[Word]] = [
            [(x0, y0, x1, y1, t.strip()) for x0, y0, x1, y1, t, *_ in page.get_text("words") if t.strip()]
            for page in doc
        ]

    blocks = _segment_blocks(pages)
    parsed = [_parse_block(b) for b in blocks]

    # 按发票号码分组：相同号码=多页溢出，合并；号码缺失则各自独立
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for idx, blk in enumerate(parsed):
        no = blk["发票号码"] or f"__unkeyed_{idx}"
        if no in groups:
            _merge_block(groups[no], blk)
        else:
            groups[no] = blk

    invoices = []
    for blk in groups.values():
        blk["项目"] = _finalize_items(blk.pop("_rows"))
        blk["_raw_text"] = blk.pop("_raw_text")
        invoices.append(blk)
    return invoices


def parse_invoice(pdf_path: Path) -> dict:
    """兼容入口：返回第一张发票（无则返回空结构）。"""
    out = parse_invoices(pdf_path)
    return out[0] if out else _empty_invoice()


# --- 分块：按“电子发票”表头切分，平移到模板坐标系 ---

def _segment_blocks(pages: List[List[Word]]) -> List[List[Word]]:
    blocks: List[List[Word]] = []
    for words in pages:
        headers = sorted(y0 for x0, y0, x1, y1, t in words if "电子发票" in t)
        if not headers:
            if words:
                blocks.append(words)
            continue
        for i, hy in enumerate(headers):
            y_end = headers[i + 1] if i + 1 < len(headers) else float("inf")
            shift = _BASE_HEADER_Y - hy
            block = [
                (x0, y0 + shift, x1, y1 + shift, t)
                for x0, y0, x1, y1, t in words
                if hy - 2 <= y0 < y_end
            ]
            blocks.append(block)
    return blocks


# --- 单块解析 ---

def _parse_block(words: List[Word]) -> dict:
    invoice_no = _value_right_of(words, "发票号码")
    inv = {
        "发票类型": "电子发票（普通发票）",
        "发票号码": invoice_no,
        "开票日期": _value_right_of(words, "开票日期"),
        "购买方信息": {"名称": _value_right_of(words, "名称", half="left"), "纳税人识别号": None},
        "销售方信息": {"名称": _value_right_of(words, "名称", half="right"), "纳税人识别号": None},
        "备注": "",
        "开票人": _value_right_of(words, "开票人"),
    }

    # 税号：版面中部、社会信用代码区域，按左右半区归属
    for x0, y0, x1, y1, t in words:
        if 110.0 <= y0 <= 145.0 and _TAXID_RE.match(t) and t != invoice_no:
            side = "购买方信息" if x0 < _HALF_X else "销售方信息"
            if inv[side]["纳税人识别号"] is None:
                inv[side]["纳税人识别号"] = t

    cols, header_y = _derive_columns(words)
    total_amount, total_tax, grand_upper, grand_lower = _parse_totals(words, cols)
    inv["合计"] = {"金额": total_amount, "税额": total_tax}
    inv["价税合计"] = {"大写": grand_upper, "小写": grand_lower}

    inv["_rows"] = _item_rows(words, cols, header_y)
    inv["_raw_text"] = " ".join(t for *_, t in sorted(words, key=lambda w: (round(w[1]), w[0])))
    return inv


def _value_right_of(words: List[Word], label: str, *, half: Optional[str] = None) -> Optional[str]:
    """标签同行、其右侧的第一个词。half='left'/'right' 限定半区。"""
    for x0, y0, x1, y1, t in words:
        if not t.startswith(label):
            continue
        if half == "left" and x0 >= _HALF_X:
            continue
        if half == "right" and x0 < _HALF_X:
            continue
        cands = [(cx0, ct) for cx0, cy0, cx1, cy1, ct in words if _same_line(cy0, y0) and cx0 > x0 + 5 and ct != t]
        if half == "left":
            cands = [c for c in cands if c[0] < _HALF_X]
        elif half == "right":
            cands = [c for c in cands if c[0] >= _HALF_X]
        if cands:
            return min(cands, key=lambda c: c[0])[1]
    return None


def _strip_money(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return text.replace("¥", "").replace(",", "").strip() or None


_MONEY_RE = re.compile(r"^¥?-?[\d,]+(?:\.\d+)?$")


def _num_in_col(words: List[Word], center_x: float, row_y: float) -> Optional[str]:
    """合计行某列里的数值（¥ 可能与数字分离，故按列中心 + 同行定位）。"""
    for x0, y0, x1, y1, t in words:
        if abs(y0 - row_y) <= 6 and abs((x0 + x1) / 2 - center_x) <= 35 and _MONEY_RE.match(t) and any(c.isdigit() for c in t):
            return _strip_money(t)
    return None


def _parse_totals(words: List[Word], cols: Dict[str, float]):
    """以标签为锚定位合计/价税合计，兼容 ¥ 与数字分离、含小计行、版面高度变化。"""
    jy = next((y0 for x0, y0, x1, y1, t in words if "价税合计" in t), None)
    if jy is None:
        return None, None, None, None

    grand_upper = next(
        (t for x0, y0, x1, y1, t in words if abs(y0 - jy) <= 10 and not t.startswith("¥") and ("圆" in t or "元" in t)),
        None,
    )
    grand_lower = next(
        (_strip_money(t) for x0, y0, x1, y1, t in words
         if abs(y0 - jy) <= 10 and x0 > 350 and _MONEY_RE.match(t) and any(c.isdigit() for c in t)),
        None,
    )

    # 合计行：定位“合”/“合计”标签（区别于“小计”），再读金额/税额两列
    hy = next((y0 for x0, y0, x1, y1, t in words if x0 < 150 and t in ("合", "合计")), None)
    amt_cx = cols.get("金额", _DEFAULT_COLS["金额"])
    tax_cx = cols.get("税额", _DEFAULT_COLS["税额"])
    total_amount = _num_in_col(words, amt_cx, hy) if hy is not None else None
    total_tax = _num_in_col(words, tax_cx, hy) if hy is not None else None
    return total_amount, total_tax, grand_upper, grand_lower


def _item_rows(words: List[Word], cols: Dict[str, float], header_y: float) -> List[dict]:
    """提取明细区域的原始行（不最终成条，留待跨页拼接后统一处理）。"""
    amt_cx = cols.get("金额", _DEFAULT_COLS["金额"])
    # 明细下界：金额列首个 ¥（合计/小计行）、“合”标签、或价税合计，取最靠上者
    money_ys = [y0 for x0, y0, x1, y1, t in words if t.startswith("¥") and abs((x0 + x1) / 2 - amt_cx) <= 30 and y0 > header_y]
    hj_y = next((y0 for x0, y0, x1, y1, t in words if x0 < 150 and t in ("合", "合计", "小") and y0 > header_y), float("inf"))
    jy = next((y0 for x0, y0, x1, y1, t in words if "价税合计" in t and y0 > header_y), float("inf"))
    bottom = min([*money_ys, hj_y, jy], default=float("inf"))

    buckets: "OrderedDict[float, List[Word]]" = OrderedDict()
    for w in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        x0, y0, x1, y1, t = w
        if header_y + _Y_TOL < y0 < bottom - 1:
            key = next((k for k in buckets if _same_line(k, y0)), y0)
            buckets.setdefault(key, []).append(w)

    rows = []
    for y in sorted(buckets):
        cells = sorted(buckets[y], key=lambda w: w[0])
        name = spec = ""
        nums: Dict[str, str] = {}
        for x0, y0, x1, y1, t in cells:
            if t.startswith("¥"):
                continue
            col = min(cols, key=lambda c: abs(cols[c] - (x0 + x1) / 2))
            if col == "项目名称":
                name += t
            elif col == "规格型号":
                spec += t
            else:
                nums.setdefault(col, t)
        rows.append({"name": name, "spec": spec, "nums": nums})
    return rows


def _finalize_items(rows: List[dict]) -> List[dict]:
    """把原始行拼成明细：带金额的行是锚点，其后无金额的行并入其名称/规格。"""
    items: List[dict] = []
    for row in rows:
        amount = row["nums"].get("金额")
        is_anchor = amount is not None and _NUM_RE.match(amount)
        if is_anchor:
            items.append({
                "项目名称": row["name"] or None,
                "规格型号": row["spec"] or None,
                "单位": row["nums"].get("单位"),
                "数量": row["nums"].get("数量"),
                "单价": row["nums"].get("单价"),
                "金额": amount,
                "税率": row["nums"].get("税率"),
                "税额": row["nums"].get("税额"),
            })
        elif items and (row["name"] or row["spec"]):
            items[-1]["项目名称"] = (items[-1]["项目名称"] or "") + row["name"]
            items[-1]["规格型号"] = (items[-1]["规格型号"] or "") + row["spec"] or None
    return items


def _merge_block(base: dict, extra: dict) -> None:
    """同号码多页合并：标量取非空（合计/价税取后出现的有效值），明细按页序拼接。"""
    for key in ("发票号码", "开票日期", "备注", "开票人"):
        if not base.get(key) and extra.get(key):
            base[key] = extra[key]
    for side in ("购买方信息", "销售方信息"):
        for k in ("名称", "纳税人识别号"):
            if not base[side].get(k) and extra[side].get(k):
                base[side][k] = extra[side][k]
    # 合计 / 价税合计：以最后出现的有效值为准（末页才有总计）
    for grp in ("合计", "价税合计"):
        for k, v in extra[grp].items():
            if v is not None:
                base[grp][k] = v
    base["_rows"].extend(extra["_rows"])
    base["_raw_text"] += "\n" + extra["_raw_text"]


def _empty_invoice() -> dict:
    return {
        "发票类型": "电子发票（普通发票）",
        "发票号码": None,
        "开票日期": None,
        "购买方信息": {"名称": None, "纳税人识别号": None},
        "销售方信息": {"名称": None, "纳税人识别号": None},
        "项目": [],
        "合计": {"金额": None, "税额": None},
        "价税合计": {"大写": None, "小写": None},
        "备注": "",
        "开票人": None,
        "_raw_text": "",
    }
