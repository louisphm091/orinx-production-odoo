# Hướng Dẫn Cài Đặt Module Odoo - Orinx Production

Tài liệu này hướng dẫn chi tiết các bước để cài đặt bộ module tùy chỉnh từ kho lưu trữ `orinx-production-odoo` vào một hệ thống Odoo mới.

## Thông tin Repository
- **GitLab URL:** [https://github.com/louisphm091/orinx-production-odoo](https://github.com/louisphm091/orinx-production-odoo)

Danh sách các module có trong bộ mã nguồn này:
- `pos_theme_swift` (Cấu hình và giao diện cho POS Swift)
- `dms` / `dms_field` / `dms_user_role` (Tích hợp quản lý tài liệu)
- `fashion_forecast`
- `product_images_import`
- `sale_planning`
- `web_editor_media_dialog_dms`

---

## Các Bước Triển Khai

### Bước 1: Clone mã nguồn về máy chủ Odoo

Hãy ssh vào máy chủ chứa source code Odoo của bạn. Chuyển đến thư mục chứa các module tùy chỉnh (custom addons) và tiến hành clone repo. 

Ví dụ, nếu bạn muốn lưu source code vào thư mục `/home/ubuntu/orinx/`, hãy chạy lệnh:

```bash
cd /home/ubuntu/orinx/
git clone https://github.com/louisphm091/orinx-production-odoo.git
```

*(Lưu ý: Nếu repo ở chế độ private, bạn sẽ cần nhập Username và Password (hoặc Access Token) của GitLab).*

### Bước 2: Cài đặt các thư viện Python (Nếu có)

Trước khi khởi động, hãy kiểm tra xem các module này có yêu cầu cài thêm thư viện Python đặc thù nào không (thường được list trong file `requirements.txt`).
Nếu có, hãy chạy:
```bash
pip3 install -r /home/ubuntu/orinx/orinx-production-odoo/requirements.txt
```

### Bước 3: Khai báo thư mục cho Odoo bằng `addons_path`

Odoo cần biết thư mục chứa code của bạn ở đâu để nạp lên hệ thống. Mở file cấu hình Odoo của bạn (thường là `odoo.conf` hoặc `/etc/odoo/odoo.conf`) bằng trình soạn thảo (vi/nano).

Tìm đến dòng `addons_path` và **thêm đường dẫn tuyệt đối** tới thư mục `orinx-production-odoo` mà bạn vừa clone về. Các đường dẫn được cách nhau bởi dấu phẩy `,`.

Ví dụ:
```ini
[options]
; ... các cấu hình khác
addons_path = /home/ubuntu/orinx/odoo/addons,/home/ubuntu/orinx/orinx-production-odoo
```

### Bước 4: Khởi động lại dịch vụ Odoo

Sau khi thay đổi file config, bạn phải khởi động lại Odoo để nó nhận diện đường dẫn thư mục mới.
Tùy vào cách bạn đang chạy Odoo, lệnh khởi động lại có thể là:

- **Chạy bằng systemd:**
  ```bash
  sudo systemctl restart odoo
  ```
- **Chạy trực tiếp từ command line / tmux:**
  Nhấn `Ctrl+C` để tắt tiến trình và chạy lại lệnh start Odoo (đảm bảo truyền file config):
  ```bash
  ./odoo-bin -c /đường_dẫn_tới/odoo.conf
  ```

### Bước 5: Cập nhật danh sách Ứng dụng (Update App List)

Sau khi Odoo chạy lại, Odoo vẫn chưa cài đặt ngay module của bạn. Hãy thao tác trên trình duyệt:

1. Đăng nhập vào Odoo bằng tài khoản có quyền Quản trị cao nhất (vd: `admin`).
2. Bật chế độ **Developer Mode** (Chế độ nhà phát triển) bằng cách vào *Settings (Cài đặt)* > kéo xuống dưới cùng và click *Activate the developer mode*.
3. Mở menu **Apps (Ứng dụng)**.
4. Trên thanh menu ngang (Top Bar), nhấn vào mục **Update Apps List (Cập nhật Danh sách Ứng dụng)**.
5. Một popup hiện lên, nhấn nút **Update (Cập nhật)**.

### Bước 6: Tìm và Cài Đặt (Install)

1. Vẫn ở màn hình **Apps (Ứng dụng)**, tắt bộ lọc *Apps (Ứng dụng)* trên thanh tìm kiếm (bấm dấu x để xóa chữ *Apps*).
2. Nhập tên các module có trong `orinx-production-odoo` để tìm kiếm. Ví dụ: nhập `pos_theme_swift` hoặc `fashion_forecast`.
3. Giao diện sẽ hiển thị kết quả. Nhấn **Install (Cài đặt)** hoặc **Activate (Kích hoạt)** trên thẻ module tương ứng.
4. Quá trình cài đặt sẽ chạy và hệ thống có thể tự làm mới trang khi cài xong. Lặp lại bước này cho các module khác nếu cần thiết.

> [!TIP]
> Nếu bạn muốn cài thông qua giao diện dòng lệnh (Command Line Interface - CLI) cho nhanh và chuẩn xác hơn, bạn có thể chạy cờ `-i` hoặc `-u` lúc khởi động lệnh Odoo.  Ví dụ: Cài đặt mới module `pos_theme_swift`:
> ```bash
> ./odoo-bin -c /đường_dẫn/odoo.conf -i pos_theme_swift -d name_of_db
> ```

---

## Xử lý sự cố thường gặp (Troubleshooting)

- **Module không xuất hiện trong danh sách:** Đảm bảo đường dẫn trong `addons_path` ở `odoo.conf` là chính xác, khởi động lại Odoo, và **chắc chắn** đã làm thao tác *Update Apps List*.
- **Lỗi permission denied khi clone mã nguồn:** Kiểm tra phân quyền truy cập repo git, hoặc cấu hình SSH keys trên server.
- **Lỗi ImportError khi cài đặt hoặc chạy Odoo:** Do server đang thiếu thư viện Python. Hãy xem module đó cần import thư viện gì (ví dụ: `requests`, `pytz`, v.v) và sử dụng lệnh `pip3 install tên_thư_viện` để sửa.
- **Quyền đọc/ghi file log:** Hãy đảm bảo user hệ điều hành dùng để chạy Odoo (ví dụ `odoo` hoặc `ubuntu`) có toàn quyền truy xuất vô folder `orinx-production-odoo`. Dùng `sudo chown -R ubuntu:ubuntu /home/ubuntu/orinx/orinx-production-odoo` nếu cần.
