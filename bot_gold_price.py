#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gold Price Bot – VN (PNJ, DOJI, SJC)
Chạy trên GitHub Actions, gửi thông báo qua Telegram.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

HISTORY_FILE = "gold_history.json"


# ==========================
# 0. XỬ LÝ GIÁ / ĐỊNH DẠNG
# ==========================

def _normalize_price_to_vnd(value: Any) -> Optional[int]:
    """
    Chuyển chuỗi giá (15280, 15,280, 15.280.000, …) về số VNĐ.
    - Nếu số có <= 6 chữ số (ví dụ: 15280) -> hiểu là 'nghìn', nhân 1.000.
    - Nếu số có > 6 chữ số (ví dụ: 150600000) -> hiểu là đã là VNĐ, giữ nguyên.
    """
    if value is None:
        return None

    s = str(value)
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None

    amount = int(digits)

    if len(digits) <= 6:
        amount *= 1000

    return amount


def _format_vnd_raw(amount: int) -> str:
    """Định dạng số VNĐ (int) thành 'xx.xxx.xxx VNĐ'."""
    return f"{amount:,}".replace(",", ".") + " VNĐ"


def _format_vnd_amount(value: Any) -> str:
    """
    Dùng cho dữ liệu lấy trực tiếp từ web (có thể đang là 'nghìn').
    Tự quy đổi về VNĐ rồi định dạng 'xx.xxx.xxx VNĐ'.
    """
    amount = _normalize_price_to_vnd(value)
    if amount is None:
        return ""
    return _format_vnd_raw(amount)


# ==========================
# 1. LẤY GIÁ TỪ WEB
# ==========================

def _parse_baomoi_gold_table(url: str, source_name: str) -> Dict[str, Any]:
    """
    Đọc bảng 'Loại vàng – Giá mua (VNĐ) – Giá bán (VNĐ)' trên trang tiện ích giá vàng của BaoMoi.
    Trả về dict: { 'Tên loại vàng': {'mua': '...', 'ban': '...'} }
    """
    try:
        tables = pd.read_html(url, flavor=["lxml", "html5lib"])
    except Exception as e:
        raise RuntimeError(f"{source_name}: Lỗi đọc HTML - {e}")

    if not tables:
        raise RuntimeError(f"{source_name}: Không tìm thấy bảng dữ liệu nào")

    df = tables[0]
    df.columns = [str(c).strip() for c in df.columns]

    col_map: Dict[str, str] = {}
    for col in df.columns:
        lower = str(col).lower()
        if "loại" in lower and "vàng" in lower:
            col_map["loai"] = col
        elif "giá mua" in lower or "mua" in lower:
            col_map["mua"] = col
        elif "giá bán" in lower or "bán" in lower:
            col_map["ban"] = col

    required = ["loai", "mua", "ban"]
    if not all(k in col_map for k in required):
        raise RuntimeError(
            f"{source_name}: Không nhận diện được đủ cột, columns={df.columns}"
        )

    result: Dict[str, Any] = {}
    for _, row in df.iterrows():
        loai = str(row[col_map["loai"]]).strip()
        if not loai or loai.lower() == "nan":
            continue
        result[loai] = {
            "mua": str(row[col_map["mua"]]).strip(),
            "ban": str(row[col_map["ban"]]).strip(),
        }
    return result


def get_pnj_prices() -> Dict[str, Any]:
    """
    Lấy giá PNJ từ tiện ích BaoMoi:
    https://baomoi.com/tien-ich-gia-vang-pnj.epi

    Bảng có thể chứa cả dòng SJC, nên filter các dòng có chữ 'PNJ'.
    """
    url = "https://baomoi.com/tien-ich-gia-vang-pnj.epi"
    raw = _parse_baomoi_gold_table(url, "PNJ (BaoMoi)")

    result: Dict[str, Any] = {}
    for loai, info in raw.items():
        name_upper = loai.upper()
        if "PNJ" not in name_upper:
            continue
        result[loai] = {
            "mua": info["mua"],
            "ban": info["ban"],
            "khu_vuc": "",
        }

    return result


def get_doji_prices() -> Dict[str, Any]:
    """
    Lấy bảng giá vàng từ DOJI trực tiếp trên https://giavang.doji.vn/.
    Chỉ lấy bảng có đủ 3 cột: Loại / Mua / Bán.
    """
    url = "https://giavang.doji.vn/"
    try:
        tables = pd.read_html(url, flavor=["lxml", "html5lib"])
    except Exception as e:
        raise RuntimeError(f"DOJI: Lỗi đọc HTML - {e}")

    if not tables:
        raise RuntimeError("DOJI: Không tìm thấy bảng dữ liệu nào")

    for df in tables:
        df.columns = [str(c).strip() for c in df.columns]
        col_map: Dict[str, str] = {}

        for col in df.columns:
            lower = str(col).lower()
            if "loại" in lower or "giá vàng trong nước" in lower:
                col_map["loai"] = col
            elif "mua" in lower:
                col_map["mua"] = col
            elif "bán" in lower:
                col_map["ban"] = col

        required = ["loai", "mua", "ban"]
        if all(key in col_map for key in required):
            result: Dict[str, Any] = {}
            for _, row in df.iterrows():
                loai = str(row[col_map["loai"]]).strip()
                if not loai or loai.lower() == "nan":
                    continue
                result[loai] = {
                    "mua": str(row[col_map["mua"]]).strip(),
                    "ban": str(row[col_map["ban"]]).strip(),
                    "khu_vuc": "Trong nước",
                }
            return result

    raise RuntimeError(f"DOJI: Đã duyệt {len(tables)} bảng nhưng không khớp cột.")


def get_sjc_prices() -> Dict[str, Any]:
    """
    Lấy bảng giá vàng SJC từ tiện ích BaoMoi:
    https://baomoi.com/tien-ich-gia-vang-sjc.epi
    """
    url = "https://baomoi.com/tien-ich-gia-vang-sjc.epi"
    raw = _parse_baomoi_gold_table(url, "SJC (BaoMoi)")

    result: Dict[str, Any] = {}
    for loai, info in raw.items():
        result[loai] = {
            "mua": info["mua"],
            "ban": info["ban"],
        }

    return result


def get_all_gold_prices() -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    errors: List[str] = []

    try:
        data["PNJ"] = get_pnj_prices()
    except Exception as exc:
        errors.append(f"PNJ: {exc}")

    try:
        data["DOJI"] = get_doji_prices()
    except Exception as exc:
        errors.append(f"DOJI: {exc}")

    try:
        data["SJC"] = get_sjc_prices()
    except Exception as exc:
        errors.append(f"SJC: {exc}")

    if errors:
        data["_errors"] = errors

    return data


# ==========================
# 2. FORMAT NỘI DUNG TIN NHẮN
# ==========================

def _format_header() -> List[str]:
    now_utc = datetime.utcnow()
    now_vn = now_utc + timedelta(hours=7)
    header_time = now_vn.strftime("%d/%m/%Y %H:%M")

    lines: List[str] = []
    lines.append("📊 BÁO CÁO GIÁ VÀNG VIỆT NAM (PNJ – DOJI – SJC)")
    lines.append(f"⏰ Cập nhật: {header_time} (giờ VN)")
    lines.append("Đơn vị: VNĐ (đã quy đổi nếu nguồn niêm yết nghìn đồng/chỉ)")
    lines.append("")
    return lines


def _append_pnj_section(lines: List[str], pnj_data: Optional[Dict[str, Any]]) -> None:
    if pnj_data is None:
        return

    lines.append("🟡 PNJ")
    if not pnj_data:
        lines.append("- Không có dữ liệu.")
        lines.append("")
        return

    for loai, info in pnj_data.items():
        khu_vuc = info.get("khu_vuc") or ""
        suffix = f" [{khu_vuc}]" if khu_vuc else ""

        mua = _format_vnd_amount(info.get("mua"))
        ban = _format_vnd_amount(info.get("ban"))

        lines.append(f"- {loai}{suffix}: Mua {mua} | Bán {ban}")

    lines.append("")


def _append_doji_section(lines: List[str], doji_data: Optional[Dict[str, Any]]) -> None:
    if doji_data is None:
        return

    lines.append("🟠 DOJI (Trong nước)")
    if not doji_data:
        lines.append("- Không có dữ liệu.")
        lines.append("")
        return

    for loai, info in doji_data.items():
        name_display = loai.replace("(nghìn/chỉ)", "").strip()

        mua = _format_vnd_amount(info.get("mua"))
        ban = _format_vnd_amount(info.get("ban"))
        lines.append(f"- {name_display}: Mua {mua} | Bán {ban}")

    lines.append("")


def _append_sjc_section(lines: List[str], sjc_data: Optional[Dict[str, Any]]) -> None:
    if sjc_data is None:
        return

    lines.append("🔵 SJC")
    if not sjc_data:
        lines.append("- Không có dữ liệu.")
        lines.append("")
        return

    for loai, info in sjc_data.items():
        name_display = loai.strip()
        mua = _format_vnd_amount(info.get("mua"))
        ban = _format_vnd_amount(info.get("ban"))
        lines.append(f"- {name_display}: Mua {mua} | Bán {ban}")

    lines.append("")


def _append_error_section(lines: List[str], errors: Optional[List[str]]) -> None:
    if not errors:
        return

    lines.append("⚠️ Lỗi trong quá trình lấy dữ liệu:")
    for err in errors:
        lines.append(f"- {err}")


# ==========================
# 3. PHÂN TÍCH / HISTORY
# ==========================

def _find_item_price(
    data: Dict[str, Any],
    brand_key: str,
    name_contains: str,
    field: str = "ban",
) -> Optional[int]:
    """
    Tìm giá (mua/bán) của 1 sản phẩm trong 1 thương hiệu, trả về VNĐ (int),
    tìm theo 'chứa chuỗi' (case-insensitive).
    """
    brand_data = data.get(brand_key) or {}
    for loai, info in brand_data.items():
        if name_contains.lower() in str(loai).lower():
            return _normalize_price_to_vnd(info.get(field))
    return None


def _choose_summary_item(
    brand_key: str,
    brand_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Chọn 1 dòng đại diện cho mỗi thương hiệu để theo dõi lịch sử.
    Trả về: {'name': <tên dòng>, 'ban': <giá bán VNĐ>}
    """
    if not brand_data:
        return None

    keys = list(brand_data.keys())
    if not keys:
        return None

    # Heuristic riêng cho từng brand
    chosen_name: Optional[str] = None

    if brand_key == "PNJ":
        # Ưu tiên dòng có HCM / TP.HCM
        candidates = [
            k for k in keys
            if "hcm" in k.lower() or "tp.hcm" in k.lower() or "tp hcm" in k.lower()
        ]
        if not candidates:
            candidates = [k for k in keys if "pnj" in k.lower()]
        chosen_name = (candidates or keys)[0]

    elif brand_key == "DOJI":
        # Ưu tiên dòng có AVPL/SJC hoặc SJC
        candidates = [
            k for k in keys
            if "avpl" in k.lower() or "sjc" in k.lower()
        ]
        chosen_name = (candidates or keys)[0]

    elif brand_key == "SJC":
        # Ưu tiên dòng có 1L, 10L, 1KG
        candidates = [
            k for k in keys
            if "1l" in k.lower() or "1kg" in k.lower() or "10l" in k.lower()
        ]
        chosen_name = (candidates or keys)[0]

    else:
        chosen_name = keys[0]

    ban_raw = brand_data[chosen_name].get("ban")
    ban_vnd = _normalize_price_to_vnd(ban_raw)
    if ban_vnd is None:
        return None

    return {"name": chosen_name, "ban": ban_vnd}


def _load_history() -> Dict[str, Any]:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"Không đọc được history: {exc}")
        return {}


def _build_history_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lưu lại các dòng đại diện (giá BÁN ra) để so sánh ở lần sau.
    Cấu trúc:
    {
      "_timestamp_utc": "...",
      "summary_items": {
        "PNJ": {"name": "...", "ban": 153600000},
        "DOJI": {"name": "...", "ban": 154800000},
        "SJC": {"name": "...", "ban": 154800000}
      }
    }
    """
    summary_items: Dict[str, Any] = {}

    for brand in ("PNJ", "DOJI", "SJC"):
        brand_data = data.get(brand) or {}
        chosen = _choose_summary_item(brand, brand_data)
        if chosen:
            summary_items[brand] = chosen

    snapshot: Dict[str, Any] = {
        "_timestamp_utc": datetime.utcnow().isoformat(),
        "summary_items": summary_items,
    }
    return snapshot


def _save_history(snapshot: Dict[str, Any]) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        print("Đã lưu history vào", HISTORY_FILE)
    except Exception as exc:
        print(f"Không lưu được history: {exc}")


def _format_change(current: Optional[int], previous: Optional[int]) -> str:
    """
    current, previous: giá VNĐ (int)
    Trả về câu:
    '▲ tăng 300.000 VNĐ (+0,20%) so với 153.300.000 VNĐ lần trước'
    """
    if current is None or previous is None or previous == 0:
        return "không có dữ liệu so sánh (lần chạy đầu hoặc thiếu history)"

    diff = current - previous
    if diff > 0:
        direction = "tăng"
        symbol = "▲"
    elif diff < 0:
        direction = "giảm"
        symbol = "▼"
    else:
        direction = "đứng giá"
        symbol = "▶"

    diff_abs = abs(diff)
    diff_str = _format_vnd_raw(diff_abs)
    prev_str = _format_vnd_raw(previous)

    pct = (diff / previous) * 100
    pct_str = f"{pct:+.2f}%".replace(".", ",")

    if diff == 0:
        return (
            f"{symbol} {direction}, không thay đổi so với {prev_str} "
            f"({pct_str})"
        )

    return (
        f"{symbol} {direction} {diff_str} ({pct_str}) "
        f"so với {prev_str} lần trước"
    )


def _get_brand_summary(
    data: Dict[str, Any],
    history: Dict[str, Any],
    brand_key: str,
) -> Optional[Dict[str, Any]]:
    """
    Lấy thông tin tóm tắt cho 1 brand:
    {
      "brand": "PNJ",
      "name": "tên dòng",
      "current_price": 153600000,
      "previous_price": 153300000 hoặc None
    }
    """
    brand_data = data.get(brand_key) or {}
    history_items = (history or {}).get("summary_items", {})
    prev_entry = history_items.get(brand_key)

    curr_name: Optional[str] = None
    curr_price: Optional[int] = None
    prev_price: Optional[int] = None

    if prev_entry and prev_entry.get("name"):
        # Đã từng có history -> cố gắng lấy đúng cùng dòng
        prev_name = prev_entry["name"]
        prev_price = prev_entry.get("ban")

        if prev_name in brand_data:
            curr_price = _normalize_price_to_vnd(
                brand_data[prev_name].get("ban")
            )
            curr_name = prev_name
        else:
            # không tìm thấy tên y hệt, thử contains
            for loai, info in brand_data.items():
                if prev_name.lower() in loai.lower():
                    curr_price = _normalize_price_to_vnd(info.get("ban"))
                    curr_name = loai
                    break

        # nếu vẫn không lấy được thì chọn lại dòng đại diện mới
        if curr_price is None:
            chosen = _choose_summary_item(brand_key, brand_data)
            if chosen:
                curr_name = chosen["name"]
                curr_price = chosen["ban"]
    else:
        # Chưa có history -> chọn dòng đại diện hiện tại
        chosen = _choose_summary_item(brand_key, brand_data)
        if chosen:
            curr_name = chosen["name"]
            curr_price = chosen["ban"]
            prev_price = None

    if curr_name is None or curr_price is None:
        return None

    return {
        "brand": brand_key,
        "name": curr_name,
        "current_price": curr_price,
        "previous_price": prev_price,
    }


def _append_quick_summary(
    lines: List[str],
    data: Dict[str, Any],
    history: Dict[str, Any],
) -> None:
    lines.append("📌 Tóm tắt nhanh – Giá BÁN ra (một số dòng chủ lực)")

    for brand in ("PNJ", "DOJI", "SJC"):
        info = _get_brand_summary(data, history, brand)
        if not info:
            continue

        display_name = info["name"]
        lines.append(
            f"- {display_name}: {_format_vnd_raw(info['current_price'])}"
        )

    lines.append("")


def _append_change_section(
    lines: List[str],
    data: Dict[str, Any],
    history: Dict[str, Any],
) -> None:
    lines.append("📈 Diễn biến so với lần cập nhật trước (theo giá BÁN ra)")

    any_prev = False
    for brand in ("PNJ", "DOJI", "SJC"):
        info = _get_brand_summary(data, history, brand)
        if not info:
            continue

        curr = info["current_price"]
        prev = info["previous_price"]
        if prev is None:
            continue  # brand này chưa có dữ liệu lịch sử

        any_prev = True
        display_name = info["name"]
        lines.append(
            f"- {display_name} (Bán): {_format_vnd_raw(curr)} – "
            f"{_format_change(curr, prev)}"
        )

    if not any_prev:
        lines.append(
            "- Chưa có dữ liệu so sánh (lần chạy đầu tiên hoặc mới đổi nguồn dữ liệu)."
        )

    lines.append("")


def format_gold_message(
    data: Dict[str, Any],
    history: Optional[Dict[str, Any]] = None,
) -> str:
    hist = history or {}
    lines = _format_header()

    _append_quick_summary(lines, data, hist)
    _append_change_section(lines, data, hist)
    lines.append("────────────────────")

    _append_pnj_section(lines, data.get("PNJ"))
    _append_doji_section(lines, data.get("DOJI"))
    _append_sjc_section(lines, data.get("SJC"))
    _append_error_section(lines, data.get("_errors"))
    return "\n".join(lines)


# ==========================
# 4. GỬI TELEGRAM
# ==========================

def send_telegram_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        print("Test mode: Không tìm thấy TELEGRAM_TOKEN, in message ra log:")
        print(text)
        return

    if not chat_id:
        raise RuntimeError("Thiếu TELEGRAM_CHAT_ID (env)")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    resp = requests.post(url, json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Telegram API lỗi: {resp.status_code} {resp.text}")


# ==========================
# 5. MAIN
# ==========================

def main() -> None:
    data: Optional[Dict[str, Any]] = None

    try:
        prev_history = _load_history()
        data = get_all_gold_prices()
        message = format_gold_message(data, prev_history)
        new_history = _build_history_snapshot(data)
        _save_history(new_history)
    except Exception as exc:
        message = f"⚠️ Gold Bot: lỗi nghiêm trọng – {exc}"

    send_telegram_message(message)


if __name__ == "__main__":
    main()
