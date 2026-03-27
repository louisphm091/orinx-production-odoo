# Hướng dẫn tích hợp API Đăng nhập cho Nhân viên (Mobile)

Tài liệu này hướng dẫn lập trình viên Frontend cách sử dụng API đăng nhập trên ứng dụng Mobile cho nhân viên của hệ thống ORINX.

## 1. Thông tin Endpoint
- **URL**: `https://group.orinx.com.vn/api/swift/v1/auth/login`
- **Method**: `POST`
- **Content-Type**: `application/json`

## 2. Request Body
Frontend gửi thông tin đăng nhập với các trường sau:

```json
{
  "username": "0934773489", 
  "password": "mật_khẩu_đã_thiết_lập",
  "db": "orinx-manufacturing"
}
```

*Ghi chú:*
- `username`: Có thể là **Số điện thoại** hoặc **Tên đăng nhập** của nhân viên.
- `password`: Mật khẩu được Admin thiết lập trong mục **Nhân viên > Chỉnh sửa nhân viên**.
- `db`: Luôn để mặc định là `orinx-manufacturing`.

## 3. Quy trình thiết lập phía Admin (Backend)
Để một nhân viên có thể đăng nhập, Admin cần làm các bước sau:
1. Vào mục **Nhân viên**.
2. Tìm nhân viên bằng Số điện thoại hoặc Tên.
3. Nhấn **Chỉnh sửa nhân viên**.
4. Nhập mật khẩu vào ô **Password** (ví dụ: `123456`) và nhấn **Update Employee**.
   - Tại bước này, hệ thống sẽ tự động gán **Số điện thoại** làm tên đăng nhập chính thức cho nhân viên đó.

## 4. Response
### Thành công (HTTP 200)
```json
{
  "error": 0,
  "message": "Success",
  "data": {
    "session_id": "8b9cad0e1f20...",
    "user_id": 20,
    "name": "BÙI THỊ TUYẾT TRÂM",
    "db": "orinx-manufacturing"
  }
}
```

### Thất bại (HTTP 401)
```json
{
  "error": -1,
  "message": "Wrong login/password",
  "data": null
}
```

## 5. Lưu ý quan trọng
- Hệ thống hỗ trợ tìm kiếm linh hoạt: Lập trình viên có thể gửi định dạng số điện thoại `0934...` hoặc `+84934...`, hệ thống sẽ tự động ánh xạ đúng tài khoản.
- Mỗi lần Admin "Update Employee", hệ thống sẽ dọn dẹp các tài khoản rác trùng lặp để đảm bảo nhân viên luôn đăng nhập đúng vào hồ sơ hiện tại.
