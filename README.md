HCMUE News Fetcher

Ứng dụng desktop (GUI) và dòng lệnh (CLI) giúp sinh viên tự động thu thập tin tức, thông báo mới nhất từ nhiều trang web của trường đại học. Chương trình lọc Top N bài mới nhất, hỗ trợ phân trang, multiple date formats, và trích xuất đoạn trích (excerpt) mà không cần API.

Tính năng chính
Top N bài mới nhất: Lấy N bài mới nhất tính từ thời điểm chạy (mặc định 10), dựa trên ngày thật đã parse (không bị lừa bởi thứ tự hiển thị hay bài được pin).
Đa nguồn (Multi-source): Dễ dàng thêm/xóa nguồn qua file sources.json hoặc trực tiếp trên GUI.

Chiến lược scrape thông minh:
    Dò RSS/Atom feed (ổn định nhất).
    Dùng CSS Selectors nếu người dùng tự khai báo.
    Dùng Heuristic (tìm thẻ <a> và chuỗi ngày tháng gần đó).
    Fallback sang Playwright (headless browser) nếu trang cần JavaScript để render (ví dụ: Wix).
    
Xử lý ngày tháng phức tạp: Hiểu ISO 8601, dd/mm/yyyy, tên tháng tiếng Anh (có/không năm, tự lùi năm nếu ra tương lai), và dạng tương đối ("2 days ago", "2 ngày trước").

Tránh trùng lặp: Lưu trạng thái "đã xem" vào seen.json, chỉ lấy excerpt cho bài mới để tiết kiệm băng thông.

Giao diện đồ hoạ (Tkinter): Chạy nền bằng threading không bị treo UI, double-click hoặc click nút [Link] để mở trình duyệt.

Thân thiện với Server: Tự kiểm tra robots.txt, delay 1-2s giữa các request, có User-Agent riêng.

Yêu cầu hệ thống
Python 3.10+
Linux
Windows
Gói tk cho GUI (Trên Arch: sudo pacman -S tk)

Cài đặt

Trên các distro Arch-based, bắt buộc phải dùng môi trường ảo (venv) để tránh lỗi externally-managed-environment.
```
# 1. Clone repository
git clone https://github.com/longme179/hcmueFetch.git
cd hcmueFetch
python -m venv venv
# 2. Tạo và kích hoạt venv
source venv/bin/activate  
# Nếu dùng fish shell: 
source venv/bin/activate.fish
# 3. Cài đặt dependencies
pip install -r requirements.txt
# 4. (Optional) Cài Playwright cho các trang cần JS-render (Wix)
pip install playwright && playwright install chromium
```
Sử dụng
Cài đặt lệnh tắt vào hệ thống (Linux)

Chạy script sau để có thể gọi hcmueFetch từ bất kỳ đâu trong terminal hoặc mở từ App Launcher (GNOME/KDE):
bash
```
chmod +x install.sh
./install.sh
```

Sau khi chạy, bạn có thể nhấn phím Super (Windows key) gõ "HCMUE Fetch" để mở GUI, hoặc gõ hcmueFetch trong terminal.
Chạy bằng GUI

``` bash
hcmueFetch
```
# Hoặc chạy bằng Python:

```
python main.py
``` 
 
Chạy bằng CLI
```bash
 
# Lấy 10 bài mới nhất của từng nguồn
python main.py run --count 10

# Lấy 20 bài mới nhất gộp chung tất cả các nguồn, không lấy excerpt
python main.py run --count 20 --mode combined --no-excerpt

# Quản lý nguồn
python main.py add "Tên nguồn" "https://example.com/news"
python main.py remove "Tên nguồn"
python main.py list
 ```
Đóng góp (Contributions)

Dự án này được phát triển với sự hỗ trợ kỹ thuật toàn diện từ GLM-5.2 và Claude.

Vai trò của Trợ lý AI trong quá trình phát triển:

     Kiến trúc & Thiết kế: Tách biệt logic lõi (core.py) khỏi giao diện (cli.py, gui.py) để đảm bảo dễ bảo trì.
     Xử lý dữ liệu (Data Parsing): Viết bộ regex và dùng dateutil để chuẩn hoá các định dạng ngày tháng hỗn loạn (ISO, tiếng Anh không năm, dạng tương đối) về chuẩn UTC+7.
     Tối ưu ho thuật toán: Đóng góp logic deduplicate trong quá trình phân trang (tránh dừng sớm do bài trùng lặp) và heuristic trích xuất thẻ HTML.
     Đa luồng (Concurrency): Triển khai threading và queue.Queue an toàn cho Tkinter GUI, đảm bảo giao diện không bị đóng băng khi fetch mạng.
     Tối ưu code (Refactoring): Áp dụng triết lý "Lazy Developer" để rút gọn codebase, loại bỏ dependencies thừa, tận dụng tối đa standard library.

Mọi đóng góp hoặc báo lỗi (issues) vui lòng tạo pull request hoặc liên hệ trực tiếp.
