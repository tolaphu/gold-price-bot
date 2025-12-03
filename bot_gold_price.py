#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gold Price Bot – VN (PNJ, DOJI, SJC)
Chạy trên GitHub Actions, gửi thông báo qua Telegram.
"""

import os
import time
from datetime import datetime, timedelta
# Import Optional để tương thích với Python < 3.10
from typing import Any, Dict, Iterable, List, Optional 

import pandas as pd
import requests

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
    digits = ''.join(ch for ch in s if ch.isdigit())
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
    Trả về chuỗi dạng '15.280.000 VNĐ' từ nguồn string gốc.
    Nếu không parse được -> trả về chuỗi rỗng.
    """
    amount = _normalize_price_to_vnd(value)
    if amount is None:
        return ""
    # Format kiểu 15.280.000 VNĐ
    return f"{amount:,}".replace(",", ".") + " VNĐ"

# ==========================
# 1. HÀM LẤY GIÁ PNJ, DOJI, SJC
# ==========================

def get_pnj_prices() -> Dict[str, Any]:
    """Lấy bảng giá vàng từ PNJ."""
    url = "https://giavang.pnj.com.vn/"
    try:
        # Thêm flavor để tránh lỗi thiếu thư viện parse
        tables = pd.read_html(url, flavor=['lxml', 'html5lib'])
    except Exception as e:
        raise RuntimeError(f"PNJ: Lỗi đọc HTML - {e}")

    if not tables:
        raise RuntimeError("PNJ: Không tìm thấy bảng dữ liệu nào")

    df = tables[0]
    df.columns = [str(c).strip() for c in df.columns]

    col_map: Dict[str, str] = {}
    for col in df.columns:
        lower = str(col).lower()
        if "khu" in lower and "vực" in lower:
            col_map["khu_vuc"] = col
        elif ("loại" in lower and "vàng" in lower) or "sản phẩm" in lower:
            col_map["loai"] = col
        elif "mua" in lower:
            col_map["mua"] = col
        elif "bán" in lower:
            col_map["ban"] = col

    required = ["khu_vuc", "loai", "mua", "ban"]
    if not all(key in col_map for key in required):
        raise RuntimeError(f"PNJ: Không nhận diện được đủ cột, columns={df.columns}")

    result: Dict[str, Any] = {}
    for _, row in df.iterrows():
        loai = str(row[col_map["loai"]]).strip()
        if not loai or loai.lower() == "nan":
            continue
        result[loai] = {
            "mua": str(row[col_map["mua"]]).strip(),
            "ban": str(row[col_map["ban"]]).strip(),
            "khu_vuc": str(row[col_map["khu_vuc"]]).strip(),
        }

    return result


def get_doji_prices() -> Dict[str, Any]:
    """Lấy bảng giá vàng từ DOJI."""
    url = "https://giavang.doji.vn/"
    try:
        tables = pd.read_html(url, flavor=['lxml', 'html5lib'])
    except Exception as e:
        raise RuntimeError(f"DOJI: Lỗi đọc HTML - {e}")

    if not tables:
        raise RuntimeError("DOJI: Không tìm thấy bảng dữ liệu nào")

    # SỬA LỖI: Duyệt qua TẤT CẢ các bảng để tìm bảng đúng (tránh bảng quảng cáo/ngoại tệ)
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
        # Nếu bảng này đủ cột thì dùng luôn
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


def _find_sjc_dataframe(tables: Iterable[pd.DataFrame]) -> pd.DataFrame:
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        joined = " ".join(cols)
        has_loai = "loại vàng" in joined or "loại" in joined
        has_mua_ban = "mua" in joined and "bán" in joined
        if has_loai and has_mua_ban:
            return df
    raise RuntimeError("SJC: Không tìm được bảng giá phù hợp")


def _map_sjc_columns(df: pd.DataFrame) -> Dict[str, str]:
    col_map: Dict[str, str] = {}
    for col in df.columns:
        lower = str(col).lower()
        if "loại" in lower:
            col_map["loai"] = col
        elif "mua" in lower:
            col_map["mua"] = col
        elif "bán" in lower:
            col_map["ban"] = col

    required = ["loai", "mua", "ban"]
    if not all(key in col_map for key in required):
        raise RuntimeError(f"SJC: Không nhận diện được đủ cột, columns={df.columns}")
    return col_map


def _sjc_rows_to_dict(df: pd.DataFrame, col_map: Dict[str, str]) -> Dict[str, Any]:
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


def get_sjc_prices() -> Dict[str, Any]:
    """Lấy bảng giá vàng SJC từ website sjc.com.vn (URL mới)."""
    # URL mới của SJC, có bảng Loại vàng / Mua / Bán
    url = "https://sjc.com.vn/gia-vang-online"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://sjc.com.vn/",
    }

    last_exc: Optional[Exception] = None
    tables = None

    for _ in range(3):  # Thử 3 lần
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            # Fix encoding
            resp.encoding = resp.apparent_encoding
            tables = pd.read_html(resp.text)
            break
        except Exception as exc:
            last_exc = exc
            time.sleep(2)

    if not tables:
        raise RuntimeError(f"SJC: Lỗi kết nối hoặc không tìm thấy bảng - {last_exc}")

    # Tận dụng lại hàm lọc bảng & map cột bạn đã có
    df_raw = _find_sjc_dataframe(tables)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    col_map = _map_sjc_columns(df_raw)
    return _sjc_rows_to_dict(df_raw, col_map)



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
    lines.append("📊 Báo cáo giá vàng VN (PNJ – DOJI – SJC)")
    lines.append(f"⏰ Cập nhật: {header_time} (giờ VN)")
    lines.append("")
    return lines

# SỬA: Dùng Optional[...] thay vì ... | None
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

        # Dùng format VNĐ
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
        mua = _format_vnd_amount(info.get("mua"))
        ban = _format_vnd_amount(info.get("ban"))
        lines.append(f"- {loai}: Mua {mua} | Bán {ban}")

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
        mua = _format_vnd_amount(info.get("mua"))
        ban = _format_vnd_amount(info.get("ban"))
        lines.append(f"- {loai}: Mua {mua} | Bán {ban}")

    lines.append("")



def _append_error_section(lines: List[str], errors: Optional[List[str]]) -> None:
    if not errors:
        return

    lines.append("⚠️ Lỗi trong quá trình lấy dữ liệu:")
    for err in errors:
        lines.append(f"- {err}")


def format_gold_message(data: Dict[str, Any]) -> str:
    lines = _format_header()
    _append_pnj_section(lines, data.get("PNJ"))
    _append_doji_section(lines, data.get("DOJI"))
    _append_sjc_section(lines, data.get("SJC"))
    _append_error_section(lines, data.get("_errors"))
    return "\n".join(lines)


# ==========================
# 3. GỬI TELEGRAM
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
# 4. MAIN
# ==========================

def main() -> None:
    try:
        data = get_all_gold_prices()
        message = format_gold_message(data)
    except Exception as exc:
        message = f"⚠️ Gold Bot: lỗi nghiêm trọng – {exc}"

    send_telegram_message(message)


if __name__ == "__main__":
    main()
