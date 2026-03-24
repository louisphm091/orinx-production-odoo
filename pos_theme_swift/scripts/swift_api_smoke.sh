#!/usr/bin/env bash

set -uo pipefail

BASE_URL="${BASE_URL:-https://group.orinx.com.vn/api/swift/v1}"
TOKEN="${TOKEN:-}"
BRANCH_ID="${BRANCH_ID:-1}"
PRODUCT_ID="${PRODUCT_ID:-123}"
BARCODE="${BARCODE:-8938544087398}"
IMAGE_ID="${IMAGE_ID:-456}"
IMAGE_FILE="${IMAGE_FILE:-}"
RUN_WRITE="${RUN_WRITE:-0}"
CREATE_ATTRIBUTE_NAME="${CREATE_ATTRIBUTE_NAME:-Lốc}"
CREATE_SERVICE_NAME="${CREATE_SERVICE_NAME:-Gói lắp đặt}"
CREATE_PRODUCT_NAME="${CREATE_PRODUCT_NAME:-Sữa chua Hy Lạp}"

if [[ -z "$TOKEN" ]]; then
  echo "Set TOKEN first, for example:"
  echo 'TOKEN="your_bearer_token" bash swift_api_smoke.sh'
  exit 1
fi

tmp_body_file() {
  mktemp 2>/dev/null || mktemp -t swift_api_smoke
}

call_json() {
  local label="$1"
  local method="$2"
  local url="$3"
  local payload="${4:-}"
  local body_file
  body_file="$(tmp_body_file)"

  echo "== ${label} =="
  local http_code
  if [[ -n "$payload" ]]; then
    http_code=$(curl -sS -o "$body_file" -w "%{http_code}" \
      -X "$method" "$url" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$payload" || true)
  else
    http_code=$(curl -sS -o "$body_file" -w "%{http_code}" \
      -X "$method" "$url" \
      -H "Authorization: Bearer $TOKEN" || true)
  fi
  echo "HTTP $http_code"
  cat "$body_file"
  rm -f "$body_file"
  echo
}

call_upload() {
  local label="$1"
  local url="$2"
  local file_path="$3"
  local body_file
  body_file="$(tmp_body_file)"

  echo "== ${label} =="
  if [[ ! -f "$file_path" ]]; then
    echo "Skip: file not found -> $file_path"
    echo
    rm -f "$body_file"
    return 0
  fi

  local http_code
  http_code=$(curl -sS -o "$body_file" -w "%{http_code}" \
    -X POST "$url" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@${file_path}" || true)
  echo "HTTP $http_code"
  cat "$body_file"
  rm -f "$body_file"
  echo
}

echo "Base URL: $BASE_URL"
echo "Branch ID: $BRANCH_ID"
echo

# Read-only smoke tests
call_json "Products list" "GET" "$BASE_URL/products?search=&categoryId=&sortBy=price&sortOrder=desc&page=1&pageSize=20&branchId=$BRANCH_ID"
call_json "Products summary" "GET" "$BASE_URL/products/summary?search=&categoryId=&branchId=$BRANCH_ID"
call_json "Product categories" "GET" "$BASE_URL/product-categories"
call_json "Barcode lookup" "GET" "$BASE_URL/products/by-barcode/$BARCODE?branchId=$BRANCH_ID"
call_json "Inventory items" "GET" "$BASE_URL/inventory/items?keyword=&branchId=$BRANCH_ID"
call_json "Inventory categories" "GET" "$BASE_URL/inventory/categories"
call_json "Stock checks" "GET" "$BASE_URL/stock-checks"
call_json "Transfers" "GET" "$BASE_URL/transfers?branchId=$BRANCH_ID"
call_json "Brands" "GET" "$BASE_URL/brands"
call_json "Product attributes" "GET" "$BASE_URL/product-attributes"
call_json "Current user" "GET" "$BASE_URL/auth/me"

if [[ "$RUN_WRITE" == "1" ]]; then
  call_json "Create attribute" "POST" "$BASE_URL/product-attributes" "{\"name\":\"$CREATE_ATTRIBUTE_NAME\"}"
  call_json "Create service" "POST" "$BASE_URL/services" "{\"name\":\"$CREATE_SERVICE_NAME\",\"salePrice\":50000,\"costPrice\":0}"
  call_json "Create product" "POST" "$BASE_URL/products" "{
    \"name\": \"$CREATE_PRODUCT_NAME\",
    \"barcode\": \"$BARCODE\",
    \"categoryId\": 1,
    \"brandId\": \"Vinamilk\",
    \"attributeIds\": [1, 2],
    \"costPrice\": 10000,
    \"salePrice\": 12000,
    \"stockQuantity\": 32,
    \"minStockThreshold\": 10,
    \"maxStockThreshold\": 100,
    \"branchId\": $BRANCH_ID
  }"
  call_json "Update product" "PATCH" "$BASE_URL/products/$PRODUCT_ID" "{
    \"name\": \"$CREATE_PRODUCT_NAME\",
    \"categoryId\": 1,
    \"brandId\": \"Vinamilk\",
    \"salePrice\": 12000,
    \"costPrice\": 10000,
    \"stockQuantity\": 32,
    \"minStockThreshold\": 10,
    \"maxStockThreshold\": 100,
    \"attributeIds\": [1, 2],
    \"branchId\": $BRANCH_ID
  }"
  call_json "Change status" "POST" "$BASE_URL/products/$PRODUCT_ID/change-status" "{\"status\":\"inactive\",\"branchId\":$BRANCH_ID}"
fi

call_upload "Upload image" "$BASE_URL/uploads/images" "${IMAGE_FILE}"
call_json "Product detail" "GET" "$BASE_URL/products/$PRODUCT_ID?branchId=$BRANCH_ID"
call_json "Stock history" "GET" "$BASE_URL/products/$PRODUCT_ID/stock-history"
call_json "Price history" "GET" "$BASE_URL/products/$PRODUCT_ID/price-history"

if [[ "$RUN_WRITE" == "1" ]]; then
  call_json "Delete product" "DELETE" "$BASE_URL/products/$PRODUCT_ID"
  call_json "Delete image" "DELETE" "$BASE_URL/uploads/images/$IMAGE_ID"
fi

echo "Done."
