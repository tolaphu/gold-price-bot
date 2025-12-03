#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gold Price Bot – VN (PNJ, DOJI, SJC)
Chạy trên GitHub Actions, gửi thông báo qua Telegram.
"""

import os
import time
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

import matplotlib
matplotlib.use("Agg")  # dùng backend không cần GUI
import matplotlib.pyplot as plt

HISTORY_FILE = "gold_history.json"

# ==========================
# 0. HÀM XỬ LÝ GIÁ / ĐỊNH DẠNG
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
    # Lấy toàn bộ chữ số trong chuỗi
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None

    amount = int(digits)

    # 15280 -> 5 chữ số -> 15.280.000 VNĐ
    # 150600000 -> 9 chữ số -> 150.600.000 VNĐ (không nhân nữa)
    if len(digits) <= 6:
        amount *= 1000

    return amount


def _format_vnd_amount(value: Any) -> str:
    """
    Trả về chuỗi dạng '15.280.000 VNĐ' từ nguồn string/int gốc.
    Nếu không parse được -> trả về chuỗi rỗng.
    """
    amount = _normalize_price_to_vnd(value)
    if amount is None:
        return ""
    # 15280000 -> '15,280,000' -> '15.280.000 VNĐ'
    return f"{amount:,}".replace(",", ".") + " VNĐ"


# ==========================
# 1. HÀM LẤY GIÁ TỪ WEB
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
    """Lấy bảng giá vàng từ DOJI trực tiếp trên https://giavang.doji.vn/."""
    url = "https://giavang.doji.vn/"
    try:
        tables = pd.read_html(url, flavor=["lxml", "html5lib"])
    except Exception as e:
        raise RuntimeError(f"DOJI: Lỗi đọc HTML - {e}")

    if not tables:
        raise RuntimeError("DOJI: Không tìm thấy bảng dữ liệu nào")

    # Duyệt qua tất cả bảng để tìm bảng có cột Loại / Mua / Bán
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
        # Làm sạch tên: bỏ ' (nghìn/chỉ)' nếu có
        name_display = (
            loai.replace("(nghìn/chỉ)", "")
            .replace("(nghìn/chỉ)", "")
            .strip()
        )

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
# 3. HỖ TRỢ PHÂN TÍCH / HISTORY
# ==========================

def _find_item_price(
    data: Dict[str, Any],
    brand_key: str,
    name_contains: str,
    field: str = "ban",
) -> Optional[int]:
    """
    Tìm giá (mua/bán) của 1 sản phẩm trong 1 thương hiệu, trả về VNĐ (int).
    brand_key: 'PNJ', 'DOJI', 'SJC'
    name_contains: chuỗi con để match tên sản phẩm (không phân biệt hoa/thường)
    field: 'mua' hoặc 'ban'
    """
    brand_data = data.get(brand_key) or {}
    for loai, info in brand_data.items():
        if name_contains.lower() in str(loai).lower():
            return _normalize_price_to_vnd(info.get(field))
    return None


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
    Lưu lại một số giá 'key' để so sánh ở lần sau.
    Lưu giá bán (ban) dưới dạng VNĐ (int).
    """
    snapshot: Dict[str, Any] = {
        "_timestamp_utc": datetime.utcnow().isoformat(),
        "PNJ_HCM_BAN": _find_item_price(data, "PNJ", "PNJ HCM", "ban"),
        "DOJI_AVPL_BAN": _find_item_price(data, "DOJI", "AVPL/SJC", "ban"),
        "SJC_1L_BAN": _find_item_price(data, "SJC", "SJC 1L", "ban"),
    }
    return snapshot


def _save_history(snapshot: Dict[str, Any]) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        print(f"Không lưu được history: {exc}")


def _format_change(current: Optional[int], previous: Optional[int]) -> str:
    """
    current, previous: giá VNĐ (int)
    Trả về câu kiểu: '▲ tăng 300.000 VNĐ (+0,20%)'
    """
    if current is None or previous is None or previous == 0:
        return "không có dữ liệu so sánh"

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
    diff_str = f"{diff_abs:,}".replace(",", ".") + " VNĐ"

    pct = (diff / previous) * 100
    pct_str = f"{pct:+.2f}%".replace(".", ",")

    if diff == 0:
        return f"{symbol} {direction} 0 VNĐ ({pct_str})"
    return f"{symbol} {direction} {diff_str} ({pct_str})"


def _append_quick_summary(lines: List[str], data: Dict[str, Any]) -> None:
    pnj_hcm = _find_item_price(data, "PNJ", "PNJ HCM", "ban")
    doji_avpl = _find_item_price(data, "DOJI", "AVPL/SJC", "ban")
    sjc_1l = _find_item_price(data, "SJC", "SJC 1L", "ban")

    lines.append("📌 Tóm tắt nhanh – Giá bán")
    if pnj_hcm is not None:
        lines.append(f"- PNJ HCM: {_format_vnd_amount(pnj_hcm)}")
    if doji_avpl is not None:
        lines.append(f"- DOJI AVPL/SJC: {_format_vnd_amount(doji_avpl)}")
    if sjc_1l is not None:
        lines.append(f"- SJC 1L/10L/1KG: {_format_vnd_amount(sjc_1l)}")
    lines.append("")


def _append_change_section(
    lines: List[str],
    data: Dict[str, Any],
    history: Dict[str, Any],
) -> None:
    pnj_curr = _find_item_price(data, "PNJ", "PNJ HCM", "ban")
    doji_curr = _find_item_price(data, "DOJI", "AVPL/SJC", "ban")
    sjc_curr = _find_item_price(data, "SJC", "SJC 1L", "ban")

    pnj_prev = history.get("PNJ_HCM_BAN")
    doji_prev = history.get("DOJI_AVPL_BAN")
    sjc_prev = history.get("SJC_1L_BAN")

    lines.append("📈 Diễn biến so với lần cập nhật trước")

    if not any([pnj_prev, doji_prev, sjc_prev]):
        lines.append("- Chưa có dữ liệu so sánh (lần chạy đầu tiên).")
        lines.append("")
        return

    if pnj_curr is not None:
        lines.append(
            f"- PNJ HCM (Bán): {_format_vnd_amount(pnj_curr)} – "
            f"{_format_change(pnj_curr, pnj_prev)}"
        )
    if doji_curr is not None:
        lines.append(
            f"- DOJI AVPL/SJC (Bán): {_format_vnd_amount(doji_curr)} – "
            f"{_format_change(doji_curr, doji_prev)}"
        )
    if sjc_curr is not None:
        lines.append(
            f"- SJC 1L/10L/1KG (Bán): {_format_vnd_amount(sjc_curr)} – "
            f"{_format_change(sjc_curr, sjc_prev)}"
        )

    lines.append("")


def format_gold_message(
    data: Dict[str, Any],
    history: Optional[Dict[str, Any]] = None,
) -> str:
    lines = _format_header()

    _append_quick_summary(lines, data)
    _append_change_section(lines, data, history or {})
    lines.append("────────────────────")

    _append_pnj_section(lines, data.get("PNJ"))
    _append_doji_section(lines, data.get("DOJI"))
    _append_sjc_section(lines, data.get("SJC"))
    _append_error_section(lines, data.get("_errors"))
    return "\n".join(lines)


# ==========================
# 4. GỬI TELEGRAM + BIỂU ĐỒ
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


def send_telegram_photo(path: str, caption: Optional[str] = None) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(
            "Test mode: Thiếu TELEGRAM_TOKEN hoặc TELEGRAM_CHAT_ID, "
            "bỏ qua gửi ảnh."
        )
        return

    if not os.path.exists(path):
        print(f"Không tìm thấy file ảnh để gửi: {path}")
        return

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(path, "rb") as img_file:
        files = {"photo": img_file}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption

        resp = requests.post(url, data=data, files=files, timeout=60)
        if not resp.ok:
            raise RuntimeError(
                f"Telegram sendPhoto lỗi: {resp.status_code} {resp.text}"
            )


def generate_current_price_chart(
    data: Dict[str, Any],
    output_path: str = "gold_chart.png",
) -> None:
    """
    Vẽ biểu đồ cột giá bán hiện tại của 3 dòng chủ lực:
    PNJ HCM, DOJI AVPL/SJC, SJC 1L/10L/1KG
    """
    labels: List[str] = []
    values: List[int] = []

    pnj = _find_item_price(data, "PNJ", "PNJ HCM", "ban")
    doji = _find_item_price(data, "DOJI", "AVPL/SJC", "ban")
    sjc = _find_item_price(data, "SJC", "SJC 1L", "ban")

    if pnj is not None:
        labels.append("PNJ HCM")
        values.append(pnj)
    if doji is not None:
        labels.append("DOJI AVPL/SJC")
        values.append(doji)
    if sjc is not None:
        labels.append("SJC 1L/10L/1KG")
        values.append(sjc)

    if not labels:
        print("Không có dữ liệu để vẽ biểu đồ.")
        return

    plt.figure()
    plt.bar(labels, values)
    plt.ylabel("Giá bán (VNĐ)")
    plt.title("So sánh giá bán hiện tại")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


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

    # Gửi message text
    send_telegram_message(message)

    # Nếu có dữ liệu thì vẽ biểu đồ và gửi ảnh
    if data is not None:
        try:
            generate_current_price_chart(data)
            send_telegram_photo(
                "gold_chart.png",
                caption="Biểu đồ so sánh giá bán hiện tại",
            )
        except Exception as exc:
            print(f"Không gửi được biểu đồ: {exc}")


if __name__ == "__main__":
    main()
