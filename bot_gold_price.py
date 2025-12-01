import os
import requests
import pandas as pd

def get_pnj_prices():
    url = "https://giavang.pnj.com.vn/"
    tables = pd.read_html(url)  # lấy tất cả các bảng trên trang
    df = tables[0]  # thường bảng đầu tiên là bảng giá chính

    # Giả sử cột tên là: "Khu vực", "Loại vàng", "Giá mua", "Giá bán"
    df.columns = [c.strip() for c in df.columns]

    # Ví dụ: chỉ lấy khu vực TPHCM, loại PNJ và SJC
    mask = df["Khu vực"].str.contains("TPHCM", case=False, na=False)
    df_hcm = df[mask]

    result = {}
    for _, row in df_hcm.iterrows():
        loai = row["Loại vàng"]
        result[loai] = {
            "mua": row["Giá mua"],
            "ban": row["Giá bán"],
            "khu_vuc": row["Đà Nẵng"]
        }
    return result

def get_doji_prices():
    url = "https://giavang.doji.vn/"
    tables = pd.read_html(url)

    # bảng đầu tiên thường là "Bảng giá tại Hà Nội"
    df = tables[0]
    df.columns = [c.strip() for c in df.columns]

    # Giả sử cột là "Loại", "Mua vào", "Bán ra"
    result = {}
    for _, row in df.iterrows():
        loai = str(row["Loại"])
        result[loai] = {
            "mua": row["Mua vào"],
            "ban": row["Bán ra"],
            "khu_vuc": "Đà Nẵng"
        }
    return result
  
def get_sjc_prices():
    url = "https://sjc.com.vn/"
    tables = pd.read_html(url)

    # Tìm bảng nào có 3 cột "Loại vàng", "Mua vào", "Bán ra"
    df_target = None
    for df in tables:
        cols = [c.lower() for c in df.columns]
        if ("loại vàng" in " ".join(cols)) or ("mua vào" in " ".join(cols)):
            df_target = df
            break

    if df_target is None:
        raise RuntimeError("Không tìm được bảng giá vàng SJC trong trang")

    df = df_target
    df.columns = [str(c).strip() for c in df.columns]

    result = {}
    for _, row in df.iterrows():
        loai = str(row[df.columns[0]])
        gia_mua = row[df.columns[1]]
        gia_ban = row[df.columns[2]]
        result[loai] = {
            "mua": gia_mua,
            "ban": gia_ban
        }
    return result

def send_telegram_message(text: str):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    r = requests.post(url, json=payload)
    r.raise_for_status()

def main():
    data = get_all_gold_prices()
    message = format_gold_message(data)
    send_telegram_message(message)

if __name__ == "__main__":
    main()
