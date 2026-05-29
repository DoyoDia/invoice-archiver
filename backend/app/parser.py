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

_NAME_MAX_X = 115.0   # 项目名称列右界
_SPEC_MAX_X = 188.0   # 规格型号列右界（之后为数值列）

_TAXID_RE = re.compile(r"^[0-9A-Z]{15,20}$")
_PCT_RE = re.compile(r"^-?\d+(?:\.\d+)?%$")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# 标准全电发票明细数值列的中心 x 坐标（模板固定，跨样本一致）
_COL_CENTERS = {"单位": 199.0, "数量": 272.0, "单价": 343.0, "金额": 415.0, "税率": 471.0, "税额": 565.0}


def _same_line(a: float, b: float) -> bool:
    return abs(a - b) <= _Y_TOL


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

    total_amount, total_tax, grand_upper, grand_lower = _parse_totals(words)
    inv["合计"] = {"金额": total_amount, "税额": total_tax}
    inv["价税合计"] = {"大写": grand_upper, "小写": grand_lower}

    inv["_rows"] = _item_rows(words)
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


def _parse_totals(words: List[Word]):
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
    total_amount = _num_in_col(words, _COL_CENTERS["金额"], hy) if hy is not None else None
    total_tax = _num_in_col(words, _COL_CENTERS["税额"], hy) if hy is not None else None
    return total_amount, total_tax, grand_upper, grand_lower


def _item_rows(words: List[Word]) -> List[dict]:
    """提取明细区域的原始行（不最终成条，留待跨页拼接后统一处理）。"""
    header_y = next((y0 for x0, y0, x1, y1, t in words if t == "项目名称"), 150.0)
    # 明细下界：金额列首个 ¥（合计行）或价税合计标签
    money_ys = [y0 for x0, y0, x1, y1, t in words if t.startswith("¥") and 390 <= x0 <= 430 and y0 > header_y]
    jy = next((y0 for x0, y0, x1, y1, t in words if "价税合计" in t and y0 > header_y), float("inf"))
    bottom = min([*money_ys, jy], default=float("inf"))

    buckets: "OrderedDict[float, List[Word]]" = OrderedDict()
    for w in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        x0, y0, x1, y1, t = w
        if header_y + _Y_TOL < y0 < bottom - 1:
            key = next((k for k in buckets if _same_line(k, y0)), y0)
            buckets.setdefault(key, []).append(w)

    rows = []
    for y in sorted(buckets):
        cells = sorted(buckets[y], key=lambda w: w[0])
        name = "".join(t for x0, y0, x1, y1, t in cells if x0 < _NAME_MAX_X)
        spec = "".join(t for x0, y0, x1, y1, t in cells if _NAME_MAX_X <= x0 < _SPEC_MAX_X)
        nums: Dict[str, str] = {}
        for x0, y0, x1, y1, t in cells:
            if x0 < _SPEC_MAX_X or t.startswith("¥"):
                continue
            col = min(_COL_CENTERS, key=lambda c: abs(_COL_CENTERS[c] - (x0 + x1) / 2))
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
