# tests/test_smoke.py

from bot_gold_price import format_gold_message


def test_format_gold_message_basic():
    """
    Smoke test: chỉ cần đảm bảo hàm format_gold_message chạy không lỗi
    và trả về đúng kiểu string, có chứa vài từ khóa cố định.
    """
    dummy_data = {
        "PNJ": {
            "Vàng 9999": {"mua": "74.500.000", "ban": "75.500.000", "khu_vuc": "Đà Nẵng"}
        },
        "DOJI": {
            "Vàng 9999": {"mua": "74.400.000", "ban": "75.400.000", "khu_vuc": "Hà Nội"}
        },
        "SJC": {
            "Vàng miếng SJC": {"mua": "74.600.000", "ban": "75.600.000"}
        },
        "_errors": [],
    }

    msg = format_gold_message(dummy_data)

    assert isinstance(msg, str)
    assert "Báo cáo giá vàng VN" in msg
    assert "PNJ" in msg
    assert "DOJI" in msg
    assert "SJC" in msg
