"""坐标感知的电子发票解析。

电子发票（全电）PDF 的文本层里标签与数值是分离的，纯文本顺序错乱，
因此按词的坐标重建版面：左右半区分购销方，按列顺序还原明细行。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import pymupdf


Word = tuple[float, float, float, float, str]  # x0, y0, x1, y1, text

_HALF_X = 300.0  # 左(购买方) / 右(销售方) 分界
_Y_TOL = 4.0     # 同一行的 y 容差
_TAXID_RE = re.compile(r"^[0-9A-Z]{15,20}$")
_PCT_RE = re.compile(r"^\d+(?:\.\d+)?%$")
_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


def _words(pdf_path: Path) -> List[Word]:
    out: List[Word] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for page in doc:
            for x0, y0, x1, y1, text, *_ in page.get_text("words"):
                t = text.strip()
                if t:
                    out.append((x0, y0, x1, y1, t))
    return out


def _same_line(a: float, b: float) -> bool:
    return abs(a - b) <= _Y_TOL


def _value_right_of(words: List[Word], label: str, *, half: Optional[str] = None) -> Optional[str]:
    """返回标签同一行、位于标签右侧的第一个词。half='left'/'right' 可限定半区。

    标签框较宽时其右边界可能盖过数值起点，故用标签起点而非终点判断右侧。
    """
    for x0, y0, x1, y1, t in words:
        if not t.startswith(label):
            continue
        if half == "left" and x0 >= _HALF_X:
            continue
        if half == "right" and x0 < _HALF_X:
            continue
        candidates = [
            (cx0, ct)
            for cx0, cy0, cx1, cy1, ct in words
            if _same_line(cy0, y0) and cx0 > x0 + 5 and ct != t
        ]
        if half == "left":
            candidates = [c for c in candidates if c[0] < _HALF_X]
        elif half == "right":
            candidates = [c for c in candidates if c[0] >= _HALF_X]
        if candidates:
            candidates.sort(key=lambda c: c[0])
            return candidates[0][1]
    return None


def _strip_money(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return text.replace("¥", "").replace(",", "").strip() or None


def parse_invoice(pdf_path: Path) -> dict:
    """从 PDF 解析出发票字典（中文键，与下游映射一致）。"""
    words = _words(pdf_path)

    invoice_no = _value_right_of(words, "发票号码")
    invoice_date = _value_right_of(words, "开票日期")
    drawer = _value_right_of(words, "开票人")

    buyer_name = _value_right_of(words, "名称", half="left")
    seller_name = _value_right_of(words, "名称", half="right")

    # 税号：版面中部、社会信用代码/纳税人识别号区域
    buyer_tax_id = seller_tax_id = None
    for x0, y0, x1, y1, t in words:
        if 110.0 <= y0 <= 145.0 and _TAXID_RE.match(t) and t != invoice_no:
            if x0 < _HALF_X and buyer_tax_id is None:
                buyer_tax_id = t
            elif x0 >= _HALF_X and seller_tax_id is None:
                seller_tax_id = t

    items = _parse_line_items(words)
    total_amount, total_tax = _parse_totals(words)
    grand_upper, grand_lower = _parse_grand_total(words)

    return {
        "发票类型": "电子发票（普通发票）",
        "发票号码": invoice_no,
        "开票日期": invoice_date,
        "购买方信息": {"名称": buyer_name, "纳税人识别号": buyer_tax_id},
        "销售方信息": {"名称": seller_name, "纳税人识别号": seller_tax_id},
        "项目": items,
        "合计": {"金额": total_amount, "税额": total_tax},
        "价税合计": {"大写": grand_upper, "小写": grand_lower},
        "备注": "",
        "开票人": drawer,
    }


def _items_region(words: List[Word]) -> tuple[float, float]:
    header_y = next((y0 for x0, y0, x1, y1, t in words if t == "项目名称"), 150.0)
    total_y = min(
        (y0 for x0, y0, x1, y1, t in words if t in ("合", "合计") and y0 > header_y),
        default=header_y + 120.0,
    )
    return header_y, total_y


# 标准全电发票明细列的中心 x 坐标（模板固定，跨样本一致）。
_COL_CENTERS = {
    "单位": 199.0,
    "数量": 272.0,
    "单价": 343.0,
    "金额": 415.0,
    "税率": 471.0,
    "税额": 565.0,
}


def _assign_column(center_x: float) -> str:
    return min(_COL_CENTERS, key=lambda c: abs(_COL_CENTERS[c] - center_x))


def _parse_line_items(words: List[Word]) -> List[dict]:
    header_y, total_y = _items_region(words)
    rows: dict[float, List[Word]] = {}
    for w in words:
        x0, y0, x1, y1, t = w
        if header_y + _Y_TOL < y0 < total_y - _Y_TOL:
            key = next((k for k in rows if _same_line(k, y0)), y0)
            rows.setdefault(key, []).append(w)

    items: List[dict] = []
    for y in sorted(rows):
        cells = sorted(rows[y], key=lambda w: w[0])
        name_token = next((t for x0, y0, x1, y1, t in cells if x0 < 150), None)
        right = [(x0, x1, t) for x0, y0, x1, y1, t in cells if x0 >= 150]

        if name_token and not right:
            # 项目名称续行：并入上一条
            if items:
                items[-1]["项目名称"] = (items[-1]["项目名称"] or "") + name_token
            continue
        if not right:
            continue

        cols: dict[str, str] = {}
        for x0, x1, t in right:
            col = _assign_column((x0 + x1) / 2)
            cols.setdefault(col, t)

        items.append({
            "项目名称": name_token,
            "规格型号": None,
            "单位": cols.get("单位"),
            "数量": cols.get("数量"),
            "单价": cols.get("单价"),
            "金额": cols.get("金额"),
            "税率": cols.get("税率"),
            "税额": cols.get("税额"),
        })
    return items


def _parse_totals(words: List[Word]) -> tuple[Optional[str], Optional[str]]:
    """合计行：两个 ¥ 金额，小 x 为金额，大 x 为税额。"""
    money = sorted(
        ((x0, t) for x0, y0, x1, y1, t in words if 250.0 <= y0 <= 270.0 and t.startswith("¥")),
        key=lambda c: c[0],
    )
    amount = _strip_money(money[0][1]) if money else None
    tax = _strip_money(money[-1][1]) if len(money) >= 2 else None
    return amount, tax


def _parse_grand_total(words: List[Word]) -> tuple[Optional[str], Optional[str]]:
    upper = next(
        (t for x0, y0, x1, y1, t in words if 270.0 <= y0 <= 290.0 and ("圆" in t or "元" in t) and not t.startswith("¥")),
        None,
    )
    lower = _strip_money(
        next((t for x0, y0, x1, y1, t in words if 270.0 <= y0 <= 290.0 and t.startswith("¥")), None)
    )
    return upper, lower
