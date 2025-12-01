#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gold Price Bot – VN (PNJ, DOJI, SJC)
Chạy trên GitHub Actions, gửi thông báo qua Telegram.
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any


# ==========================
# 1. HÀM LẤY GIÁ TỪ CÁC WEBSITE
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

    # Thường bảng đầu là bảng giá chính
    df = tables[0]
    df.columns = [str(c).strip() for c in df.columns]

    # Thử đoán tên cột (tùy trang, có thể thay đổi)
    # Ví dụ: "Khu vực", "Loại vàng", "Giá mua", "Giá bán"
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "khu" in cl and "vực" in cl:
            col_map["khu_vuc"] = c
        elif ("loại" in cl and "vàng" in cl) or "sản phẩm" in cl:
            col_map["loai"] = c
        elif "mua" in cl:
            col_map["mua"] = c
        elif "bán" in cl:
            col_map["ban"] = c

    required = ["khu_vuc", "loai", "mua", "ban"]
    if not all(k in col_map for k in required):
        raise RuntimeError(f"PNJ: Không nhận diện được đủ cột, columns={df.columns}")

    result: Dict[str, Any] = {}

    # Bạn có thể lọc theo khu vực, ví dụ chỉ TP.HCM
    # Ở đây mình giữ nguyên tất cả khu vực
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
    """
    Lấy bảng giá vàng từ DOJI.
    Mặc định lấy bảng đầu tiên (thường là Hà Nội).
    Trả về dict: { 'Tên loại': {mua, ban, khu_vuc} }
    """
    url = "https://giavang.doji.vn/"
    tables = pd.read_html(url)

    if not tables:
        raise RuntimeError("DOJI: Không tìm thấy bảng dữ liệu nào")

    df = tables[0]  # Bảng đầu: Bảng giá tại Hà Nội (thường là vậy)
    df.columns = [str(c).strip() for c in df.columns]

    # Thử map cột: "Loại", "Mua vào", "Bán ra"
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "loại" in cl:
            col_map["loai"] = c
        elif "mua" in cl:
            col_map["mua"] = c
        elif "bán" in cl:
            col_map["ban"] = c

    required = ["loai", "mua", "ban"]
    if not all(k in col_map for k in required):
        raise RuntimeError(f"DOJI: Không nhận diện được đủ cột, columns={df.columns}")

    result: Dict[str, Any] = {}

    for _, row in df.iterrows():
        loai = str(row[col_map["loai"]]).strip()
        if not loai or loai.lower() == "nan":
            continue

        result[loai] = {
            "mua": str(row[col_map["mua"]]).strip(),
            "ban": str(row[col_map["ban"]]).strip(),
            "khu_vuc": "Hà Nội",
        }

    return result


def get_sjc_prices() -> Dict[str, Any]:
    """
    Lấy bảng giá vàng SJC từ website sjc.com.vn.
    Trả về dict: { 'Loại vàng': {mua, ban} }
    """
    url = "https://sjc.com.vn/"
    tables = pd.read_html(url)

    if not tables:
        raise RuntimeError("SJC: Không tìm thấy bảng dữ liệu nào")

    df_target = None
    for df in tables:
        cols = [str(c).lower() for c in df.columns]
        joined = " ".join(cols)
        # Thường bảng giá SJC có các cột chứa "loại vàng", "mua vào", "bán ra"
        if ("loại vàng" in joined or "loại" in joined) and ("mua" in joined and "bán" in joined):
            df_target = df
            break

    if df_target is None:
        raise RuntimeError("SJC: Không tìm được bảng giá phù hợp")

    df = df_target
    df.columns = [str(c).strip() for c in df.columns]

    # Map cột
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "loại" in cl:
            col_map["loai"] = c
        elif "mua" in cl:
            col_map["mua"] = c
        elif "bán" in cl:
            col_map["ban"] = c

    required = ["loai", "mua", "ban"]
    if not all(k in col_map for k in required):
        raise RuntimeError(f"SJC: Không nhận diện được đủ cột, columns={df.columns}")

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


def get_all_gold_prices() -> Dict[str, Any]:
    """
    Gom dữ liệu từ PNJ, DOJI, SJC.
    """
    data: Dict[str, Any] = {}
    errors = []

    try:
        data["PNJ"] = get_pnj_prices()
    except Exception as e:
        errors.append(f"PNJ: {e}")

    try:
        data["DOJI"] = get_doji_prices()
    except Exception as e:
        errors.append(f"DOJI: {e}")

    try:
        data["SJC"] = get_sjc_prices()
    except Exception as e:
        errors.append(f"SJC: {e}")

    if errors:
        data["_errors"] = errors

    return data


# ==========================
# 2. FORMAT NỘI DUNG TIN NHẮN
# ==========================

def format_gold_message(data: Dict[str, Any]) -> str:
    """
    Format text gọn gàng để gửi Telegram.
    """
    # Thời gian VN (UTC+7)
    now_utc = datetime.utcnow()
    now_vn = now_utc + timedelta(hours=7)
    header_time = now_vn.strftime("%d/%m/%Y %H:%M")

    lines = []
    lines.append(f"📊 Báo cáo giá vàng VN (PNJ – DOJI – SJC)")
    lines.append(f"⏰ Cập nhật: {header_time} (giờ VN)")
    lines.append("")

    # PNJ
    if "PNJ" in data:
        lines.append("🟡 PNJ")
        if data["PNJ"]:
            for loai, info in data["PNJ"].items():
                khu_vuc = info.get("khu_vuc", "")
                kv = f" [{khu_vuc}]" if khu_vuc else ""
                lines.append(
                    f"- {loai}{kv}: Mua {info['mua']} | Bán {info['ban']}"
                )
        else:
            lines.append("- Không có dữ liệu.")
        lines.append("")

    # DOJI
    if "DOJI" in data:
        lines.append("🟠 DOJI (Hà Nội)")
        if data["DOJI"]:
            for loai, info in data["DOJI"].items():
                lines.append(
                    f"- {loai}: Mua {info['mua']} | Bán {info['ban']}"
                )
        else:
            lines.append("- Không có dữ liệu.")
        lines.append("")

    # SJC
    if "SJC" in data:
        lines.append("🔵 SJC")
        if data["SJC"]:
            for loai, info in data["SJC"].items():
                lines.append(
                    f"- {loai}: Mua {info['mua']} | Bán {info['ban']}"
                )
        else:
            lines.append("- Không có dữ liệu.")
        lines.append("")

    # Lỗi (nếu có)
    if "_errors" in data and data["_errors"]:
        lines.append("⚠️ Lỗi trong quá trình lấy dữ liệu:")
        for err in data["_errors"]:
            lines.append(f"- {err}")

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
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

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
    except Exception as e:
        # Nếu lỗi nặng (không lấy được data), vẫn gửi báo lỗi
        message = f"⚠️ Gold Bot: lỗi khi lấy dữ liệu – {e}"

    send_telegram_message(message)


if __name__ == "__main__":
    main()
