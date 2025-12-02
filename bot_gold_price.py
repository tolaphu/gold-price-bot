#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gold Price Bot – VN (PNJ, DOJI, SJC)
Chạy trên GitHub Actions, gửi thông báo qua Telegram.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List

import pandas as pd
import requests


# ==========================
# 1. HÀM LẤY GIÁ PNJ, DOJI, SJC
# ==========================


def get_pnj_prices() -> Dict[str, Any]:
    """
    Lấy bảng giá vàng từ PNJ.
    Trả về dict: { 'Tên loại': {mua, ban, khu_vuc} }
    """
    url = "https://giavang.pnj.com.vn/"
    tables = pd.read_html(url)

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
        raise RuntimeError(
            f"PNJ: Không nhận diện được đủ cột, columns={df.columns}"
        )

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


# SỬA LẠI HÀM get_doji_prices
def get_doji_prices() -> Dict[str, Any]:
    url = "https://giavang.doji.vn/"
    try:
        # Thêm flavor='html5lib' hoặc 'lxml' để parse tốt hơn
        tables = pd.read_html(url, flavor=['lxml', 'html5lib'])
    except Exception as e:
        raise RuntimeError(f"DOJI: Lỗi read_html - {e}")

    if not tables:
        raise RuntimeError("DOJI: Không tìm thấy bảng dữ liệu nào")

    # Duyệt qua TẤT CẢ các bảng để tìm bảng đúng
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
        
        # Nếu tìm đủ cột thì xử lý bảng này và return ngay
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

    # Nếu chạy hết vòng lặp mà không return
    raise RuntimeError(f"DOJI: Đã duyệt {len(tables)} bảng nhưng không khớp cột.")



def _find_sjc_dataframe(tables: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """
    Tìm DataFrame chứa bảng 'Loại vàng / Mua vào / Bán ra' trong sjc.com.vn
    """
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        joined = " ".join(cols)
        has_loai = "loại vàng" in joined or "loại" in joined
        has_mua_ban = "mua" in joined and "bán" in joined
        if has_loai and has_mua_ban:
            return df

    raise RuntimeError("SJC: Không tìm được bảng giá phù hợp")


def _map_sjc_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    Map tên cột trong bảng SJC sang chuẩn: loai, mua, ban.
    """
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
        raise RuntimeError(
            f"SJC: Không nhận diện được đủ cột, columns={df.columns}"
        )
    return col_map


def _sjc_rows_to_dict(df: pd.DataFrame, col_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Chuyển từng dòng trong bảng SJC thành dict.
    """
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
    url = "https://sjc.com.vn/giavang/textContent.jsp"
    # SJC chặn bot rất gắt, cần giả lập Header giống hệt trình duyệt
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://sjc.com.vn/",
    }

    last_exc: Exception | None = None
    for _ in range(3): 
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            # Xử lý encoding nếu SJC trả về lỗi font
            resp.encoding = resp.apparent_encoding 
            tables = pd.read_html(resp.text)
            break
        except Exception as exc:
            last_exc = exc
            tables = None
            import time
            time.sleep(2) # Nghỉ 2s trước khi thử lại

    if not tables:
        raise RuntimeError(f"SJC: Lỗi kết nối - {last_exc}")

    df_raw = _find_sjc_dataframe(tables)
    # ... (phần còn lại giữ nguyên)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]
    col_map = _map_sjc_columns(df_raw)
    return _sjc_rows_to_dict(df_raw, col_map)


def get_all_gold_prices() -> Dict[str, Any]:
    """
    Gom dữ liệu từ PNJ, DOJI, SJC.
    """
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
    """
    Tạo phần header chung của message.
    """
    now_utc = datetime.utcnow()
    now_vn = now_utc + timedelta(hours=7)
    header_time = now_vn.strftime("%d/%m/%Y %H:%M")

    lines: List[str] = []
    lines.append("📊 Báo cáo giá vàng VN (PNJ – DOJI – SJC)")
    lines.append(f"⏰ Cập nhật: {header_time} (giờ VN)")
    lines.append("")
    return lines


def _append_pnj_section(lines: List[str], pnj_data: Dict[str, Any] | None) -> None:
    """
    Thêm section PNJ vào message.
    """
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
        mua = info.get("mua", "")
        ban = info.get("ban", "")
        lines.append(f"- {loai}{suffix}: Mua {mua} | Bán {ban}")

    lines.append("")


def _append_doji_section(lines: List[str], doji_data: Dict[str, Any] | None) -> None:
    """
    Thêm section DOJI vào message.
    """
    if doji_data is None:
        return

    lines.append("🟠 DOJI (Hà Nội)")
    if not doji_data:
        lines.append("- Không có dữ liệu.")
        lines.append("")
        return

    for loai, info in doji_data.items():
        mua = info.get("mua", "")
        ban = info.get("ban", "")
        lines.append(f"- {loai}: Mua {mua} | Bán {ban}")

    lines.append("")


def _append_sjc_section(lines: List[str], sjc_data: Dict[str, Any] | None) -> None:
    """
    Thêm section SJC vào message.
    """
    if sjc_data is None:
        return

    lines.append("🔵 SJC")
    if not sjc_data:
        lines.append("- Không có dữ liệu.")
        lines.append("")
        return

    for loai, info in sjc_data.items():
        mua = info.get("mua", "")
        ban = info.get("ban", "")
        lines.append(f"- {loai}: Mua {mua} | Bán {ban}")

    lines.append("")


def _append_error_section(lines: List[str], errors: List[str] | None) -> None:
    """
    Thêm phần lỗi (nếu có) vào message.
    """
    if not errors:
        return

    lines.append("⚠️ Lỗi trong quá trình lấy dữ liệu:")
    for err in errors:
        lines.append(f"- {err}")


def format_gold_message(data: Dict[str, Any]) -> str:
    """
    Format text gọn gàng để gửi Telegram.
    """
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
    """
    Gửi message tới Telegram qua BOT.
    Cần 2 biến env:
      - TELEGRAM_TOKEN
      - TELEGRAM_CHAT_ID
    """
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        raise RuntimeError("Thiếu TELEGRAM_TOKEN (env)")
    if not chat_id:
        raise RuntimeError("Thiếu TELEGRAM_CHAT_ID (env)")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    resp = requests.post(url, json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(
            f"Telegram API lỗi: {resp.status_code} {resp.text}"
        )


# ==========================
# 4. MAIN
# ==========================


def main() -> None:
    try:
        data = get_all_gold_prices()
        message = format_gold_message(data)
    except Exception as exc:
        message = f"⚠️ Gold Bot: lỗi khi lấy dữ liệu – {exc}"

    send_telegram_message(message)


if __name__ == "__main__":
    main()
