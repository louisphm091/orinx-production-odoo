# Transfer API (Swift V1) - Hướng dẫn sử dụng

Tài liệu này hướng dẫn chi tiết cách sử dụng bộ API Chuyển hàng (Transfer API) đã được tích hợp vào hệ thống Orinx Odoo.

## 1. Authentication (Xác thực)

Tất cả các API yêu cầu xác thực qua **Authorization header** (Bearer token). Hệ thống sẽ tự động map token này vào session tương ứng.

- **Header**: `Authorization: Bearer <accessToken>`
- **Language**: `frontend_lang=vi_VN` (Mặc định nếu không gửi)

> [!NOTE]
> Bạn chỉ cần dùng duy nhất `Authorization` header tương tự như các bộ API Swift khác trong hệ thống.

## 2. Danh sách Endpoint

### 2.1. Lấy danh sách phiếu chuyển
`GET /api/swift/v1/transfers`

**Query Parameters:**
- `branchId`: ID chi nhánh (ví dụ: `1`)
- `period`: Khoảng thời gian (`today`, `last_7_days`, `this_month`, `last_month`)
- `status`: Trạng thái phiếu (`draft`, `shipped`, `done`, `cancel`)
- `receiptState`: Trạng thái nhận hàng (`pending`, `partial`, `full`)
- `keyword`: Tìm kiếm theo mã phiếu hoặc ghi chú
- `page`, `pageSize`: Phân trang

**Sample Request:**
```bash
curl -X GET "https://api.orinx.com/api/swift/v1/transfers?branchId=1&period=this_month&status=shipped&page=1&pageSize=20" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

**Response Shape:**
```json
{
  "error": 0,
  "message": "OK",
  "data": {
    "items": [
      {
        "id": "13",
        "code": "TRF00013",
        "status": "shipped",
        "fromBranch": { "id": "1", "name": "TRUNG TÂM" },
        "toBranch": { "id": "4", "name": "AN PHÚ THỊNH" },
        "createdAt": 1773326331000,
        "amount": 14519988,
        "preview": "Nước khoáng Aquarius 390ml x12 (+2)",
        "totalItems": 3,
        "totalQuantity": 24,
        "receivedQuantity": 0,
        "receiptState": "pending"
      }
    ],
    "summary": { "count": 1 }
  }
}
```

---

### 2.2. Chi tiết phiếu chuyển
`GET /api/swift/v1/transfers/{transferId}`

**Sample Request:**
```bash
curl -X GET "https://api.orinx.com/api/swift/v1/transfers/13?branchId=1" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 2.3. Tạo phiếu chuyển mới
`POST /api/swift/v1/transfers`

**Request Body:**
```json
{
  "fromBranchId": "1",
  "toBranchId": "4",
  "note": "Giao gấp trong ngày",
  "status": "draft",
  "lines": [
    { "productId": "1882", "qty": 2 },
    { "productId": "1883", "qty": 5 }
  ]
}
```

---

### 2.4. Cập nhật phiếu nháp
`PATCH /api/swift/v1/transfers/{transferId}`

**Request Body:**
```json
{
  "toBranchId": "4",
  "note": "Cập nhật lại ghi chú",
  "lines": [
    { "productId": "1882", "qty": 3 }
  ]
}
```

---

### 2.5. Nhận hàng
`POST /api/swift/v1/transfers/{transferId}/receive`

**Request Body:**
```json
{
  "note": "Nhận thiếu 1 sản phẩm",
  "lines": [
    { "lineId": "16", "receivedQty": 5 }
  ]
}
```

---

### 2.6. Hủy phiếu
`POST /api/swift/v1/transfers/{transferId}/cancel`

---

### 2.7. Tìm kiếm sản phẩm
`GET /api/swift/v1/products?keyword=aquarius&branchId=1`

Response đã bao gồm `itemCode` và `uom` hỗ trợ map DTO.

## 3. Options Filter
`GET /api/swift/v1/transfers/filter-options`

Dùng để lấy danh sách các tùy chọn cho dropdown filter trên UI.

## 4. Mapping Status
| Odoo State | Flutter UI Status | Label |
|------------|-------------------|-------|
| `draft`    | `draft`           | Phiếu tạm |
| `shipped`  | `in_transit`      | Đang chuyển |
| `done`     | `received`        | Đã nhận |
| `cancel`   | `cancelled`       | Đã huỷ |

## 5. Script Test (Odoo Shell)
Dùng để kiểm tra logic nội bộ branch/product:
```python
dashboard = env['pos.dashboard.swift']
# Lấy danh sách chi nhánh
branches = env['pos.config'].sudo().search([('active', '=', True)])
# Lấy danh sách hàng
products = env['product.product'].sudo().search([('sale_ok', '=', True)], limit=5)
# Test tạo transfer
res = dashboard.create_or_update_transfer({
    'config_id': branches[0].id,
    'dest_config_id': branches[1].id,
    'lines': [{'product_id': products[0].id, 'qty': 1}]
})
print(res)
```
