import sys
import os
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd

# Thêm thư mục gốc vào path để import được bot_gold_price
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import bot_gold_price

class TestGoldBot(unittest.TestCase):

    @patch('bot_gold_price.pd.read_html')
    @patch('bot_gold_price.requests.get')
    def test_format_message_mocked(self, mock_requests_get, mock_read_html):
        """
        Test logic format tin nhắn mà KHÔNG gọi internet.
        """
        print("\n--- Đang chạy Test Giả Lập (Mock) ---")

        # 1. Giả lập dữ liệu PNJ (trả về từ pd.read_html)
        # Tạo DataFrame giả giống cấu trúc PNJ
        df_pnj = pd.DataFrame({
            'Khu vực': ['TP.HCM', 'Hà Nội'],
            'Loại vàng': ['Vàng miếng PNJ', 'Nhẫn trơn'],
            'Giá mua': ['70000', '60000'],
            'Giá bán': ['71000', '61000']
        })
        
        # 2. Giả lập dữ liệu DOJI
        df_doji = pd.DataFrame({
            'Giá vàng trong nước': ['DOJI Hưng Thịnh Vượng', 'Vàng Nữ Trang'],
            'Mua': ['68000', '50000'],
            'Bán': ['69000', '51000']
        })

        # 3. Giả lập dữ liệu SJC (SJC dùng requests.get rồi mới read_html)
        # Giả lập response của requests
        mock_response = MagicMock()
        mock_response.text = "<html>Bảng giá SJC</html>"
        mock_response.status_code = 200
        mock_requests_get.return_value = mock_response
        
        df_sjc = pd.DataFrame({
            'Loại vàng': ['SJC 1L', 'SJC 5c'],
            'Mua vào': ['72000', '72000'],
            'Bán ra': ['74000', '74000']
        })

        # Cấu hình mock_read_html trả về lần lượt cho PNJ, DOJI, và SJC
        # Lưu ý: get_sjc_prices gọi pd.read_html(resp.text)
        mock_read_html.side_effect = [[df_pnj], [df_doji], [df_sjc]]

        # Chạy hàm chính lấy dữ liệu
        data = bot_gold_price.get_all_gold_prices()

        # Kiểm tra không có lỗi
        self.assertNotIn("_errors", data, "Không được có lỗi khi lấy dữ liệu giả lập")
        
        # Kiểm tra dữ liệu lấy được
        self.assertIn("Vàng miếng PNJ", data["PNJ"])
        self.assertIn("DOJI Hưng Thịnh Vượng", data["DOJI"])
        
        # Format tin nhắn
        msg = bot_gold_price.format_gold_message(data)
        
        print(f"Nội dung tin nhắn test:\n{msg}")
        
        # Assert các từ khóa quan trọng
        self.assertIn("PNJ", msg)
        self.assertIn("DOJI", msg)
        self.assertIn("SJC", msg)

if __name__ == '__main__':
    unittest.main()
