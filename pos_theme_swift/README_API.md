# Zalo Mini App Backend API Documentation

Hệ thống API backend phục vụ tích hợp cho dự án Zalo Mini App (Project Orinx Odoo).

## 📌 Quy ước chung

### Base URL
`https://group.orinx.com.vn/api/swift/v1` (hoặc `http://localhost:8081/api/swift/v1` khi chạy local)

### Authentication
Sau khi gọi API `/auth/login`, frontend sẽ nhận được `accessToken`.
Tất cả các API tiếp theo (ngoại trừ Login) đều yêu cầu Client gửi kèm chứng thực theo một trong hai cách:
1.  **Cookie:** Trình duyệt tự động đính kèm `sid` nhận được.
2.  **Header:** `Authorization: Bearer <accessToken>` (nếu dùng trên các client không hỗ trợ cookie).

### Request Format
Các API hỗ trợ cả JSON phẳng (flat) và cấu trúc `params` của Odoo:
```json
{
  "params": {
    "username": "admin",
    "password": "..."
  }
}
```

### Response Envelope (Chuẩn đầu ra)
Mọi phản hồi đều trả về một JSON bọc trong `error/message/data`:
*   **Success:** `{ "error": 0, "message": "OK", "data": { ... } }`
*   **Error:** `{ "error": -1, "message": "Thông báo lỗi", "data": null }`

---

## 🔑 1. Xác thực & Nhân viên (Authentication)

### POST `/auth/login`
Đăng nhập nhân viên.
*   **Request Body:** `{"username": "...", "password": "...", "db": "your_database"}` (Tham số `db` có thể bỏ qua nếu Odoo chỉ chạy 1 database hoặc thông qua db-filter).
*   **Response Data:** `{ "accessToken": "...", "expiresAt": 1741165200000, "user": { "id": "2", "name": "...", "code": "NV001", "branchId": "..." } }`

### GET `/auth/me`
Kiểm tra thông tin phiên đăng nhập hiện tại.
*   **Response Data:** `{ "id": "2", "name": "...", "code": "NV001", ... }`

### POST `/auth/logout`
Đăng xuất.

### GET `/staff/me`
Hồ sơ chi tiết của nhân viên (bao gồm chi nhánh thực nhận lương và chi nhánh đang làm việc).
*   **Response Data:** `{ "id": "...", "name": "...", "salaryBranch": { "id": "...", "name": "..." }, "workingBranch": { ... }, "avatarUrl": "..." }`

---

## 🛒 2. Nhóm Bán hàng (Core Sales)

### GET `/merchant`
Thông tin Merchant và danh sách các chi nhánh của cửa hàng.
*   **Response Data:** `{ "merchant": { "name": "...", "address": "...", "logoUrl": "...", "branches": [{ "id": "1", "name": "Clothes Shop" }, ...] } }`

### GET `/menu-items`
Lấy toàn bộ thực đơn cửa hàng. Sản phẩm được **gộp theo Nhóm (Category)**.
*   **Query Params:** `config_id` (để lọc sản phẩm theo chi nhánh).
*   **Response Data:** `[ { "category": { "id": 1, "name": "Đồ uống" }, "products": [{ "id": 101, "name": "Trà sữa", "price": 45000, "imageUrl": "..." }] }, ... ]`

### POST `/orders`
Tạo đơn hàng mới (Draft order).
*   **Request Body:** `{ "orderSessionId": "...", "items": [{ "productId": 101, "quantity": 2 }] }`

---

## ⏰ 3. Ca làm việc & Chấm công (Shifts)

### GET `/shifts/current`
Lấy thông tin ca làm việc hiện tại của nhân viên.

### POST `/shifts/check-in`
Nhân viên vào ca làm việc.
*   **Request Body:** `{ "note": "Ghi chú nếu có" }`
*   **Response Data:** `{ "id": 4, "state": "active" }`

### POST `/shifts/check-out`
Kết thúc ca làm việc.

### POST `/shifts/close`
**Chốt ca tài chính** (Lưu tiền mặt/chuyển khoản đã nhận).
*   **Request Body:** `{ "shiftId": 4, "closingTotal": 1000000, "cashAmount": 400000, "transferAmount": 600000 }`

### GET `/timesheets`
Lấy danh sách lịch sử chấm công/giờ làm của nhân viên.

---

## 📦 4. Vận hành kho (Inventory & Transfers)

### GET `/inventory/items`
Danh sách hàng tồn kho.
*   **Query Params:** `keyword` (search tên/SKU), `branchId` (lọc theo chi nhánh).

### GET `/inventory/categories`
Danh sách danh mục sản phẩm.

### GET `/transfers`
Danh sách các phiếu chuyển hàng.
*   **Query Params:** `branchId` (lọc phiếu của chi nhánh).

### POST `/transfers`
Tạo/Cập nhật phiếu chuyển hàng mới.
*   **Request Body:** `{ "loc_src_id": "...", "loc_dest_id": "...", "lines": [...] }`

### POST `/transfers/<id>/receive`
**Xác nhận đã nhận hàng** từ phiếu chuyển khác.
*   **Request Body:** `{ "items": [{ "product_id": "...", "qty_done": 10 }] }`

---

## ⏰ 5. Kiểm kê kho (Stock Checks)

### GET `/stock-checks`
Danh sách các phiếu kiểm kê.

### POST `/stock-checks`
Tạo phiếu kiểm kê mới.

---

## 🛠️ 6. Dữ liệu nền (Common Data)
*   **GET `/branches`:** Danh sách chi nhánh.
*   **GET `/users`:** Danh sách toàn bộ nhân viên (dùng cho filter).
*   **GET `/customers/search`:** Tìm kiếm khách hàng (Query: `keyword`).
*   **GET `/price-books`:** Danh sách các bảng giá (Pricelists).
*   **GET `/payment-methods`:** Danh sách các phương thức thanh toán.

---
**Note:** Nếu có bất kỳ lỗi 500 nào phát sinh, vui lòng báo lại Backend để kiểm tra Logs server Odoo.
