from odoo import api, fields, models
import random
from datetime import date


class SalePlanningDashboard(models.AbstractModel):
    _name = "sale.planning.dashboard"
    _description = "Sale Planning Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        Product = env["product.product"].sudo()
        Category = env["product.category"].sudo()
        Warehouse = env["stock.warehouse"].sudo()

        # --- pick warehouse (optional filter) ---
        wh = None
        if filters.get("warehouse_id"):
            wh = Warehouse.browse(int(filters["warehouse_id"])).exists()
        if not wh:
            wh = Warehouse.search([("company_id", "=", env.company.id)], limit=1)

        # --- pick products (prefer fashion-ish names/categories) ---
        # Nếu DB bạn chưa có, nó vẫn lấy random products có sẵn.
        all_products = Product.search([("active", "=", True)], limit=200)
        if not all_products:
            return self._empty_payload()

        def is_fashionish(p):
            name = (p.display_name or "").lower()
            cat = (p.categ_id.display_name or "").lower() if p.categ_id else ""
            keywords = ["áo", "quan", "quần", "vay", "váy", "dam", "đầm", "hoodie", "shirt", "jean", "fashion"]
            return any(k in name for k in keywords) or ("fashion" in cat) or ("thời trang" in cat)

        fashion_products = all_products.filtered(is_fashionish)
        products = fashion_products if len(fashion_products) >= 10 else all_products
        products = products[:30]

        # --- quantities with warehouse context ---
        # Chú ý: qty_available theo warehouse context
        def qty_onhand(p):
            if not wh:
                return p.qty_available or 0.0
            pp = p.with_context(warehouse=wh.id)
            return float(pp.qty_available or 0.0)

        # deterministic random
        seed = (env.company.id or 1) * 1000 + (wh.id if wh else 1)
        random.seed(seed)

        # ---------- KPI (mock theo logic supply planning) ----------
        # "Nhu cầu cần cung ứng" ~ demand
        demand_total = 0
        purchase_plan_total = 0
        risk_sku = 0
        waiting_orders = random.randint(3, 12)

        sku_rows = []
        for p in products[:8]:
            demand = random.randint(800, 4200)
            onhand = int(qty_onhand(p))
            plan_buy = max(0, int(demand * random.uniform(0.5, 0.9)))
            shortage = max(0, demand - (onhand + plan_buy))

            demand_total += demand
            purchase_plan_total += plan_buy
            if shortage > 0:
                risk_sku += 1

            sku_rows.append({
                "key": f"sku_{p.id}",
                "sku_name": p.display_name,
                "category": p.categ_id.display_name if p.categ_id else "",
                "demand": demand,
                "onhand": onhand,
                "plan_buy": plan_buy,
                "risk": shortage > 0,
            })

        growth_percent = random.choice([10, 12, 15, 18])

        kpis = {
            "total_supply_need": demand_total,
            "purchase_plan_qty": purchase_plan_total,
            "risk_sku_count": risk_sku,
            "waiting_orders": waiting_orders,
            "growth_percent": growth_percent,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }

        # ---------- MAIN LINE CHART (trend theo tháng) ----------
        labels = ["Tháng 01", "Tháng 02", "Tháng 03", "Tháng 04", "Tháng 05", "Tháng 06"]
        base = max(2000, int(demand_total / 6))
        demand_series = [int(base * f) for f in [0.75, 0.82, 0.90, 0.95, 1.02, 1.08]]
        plan_series = [int(v * random.uniform(0.75, 0.92)) for v in demand_series]
        risk_band = [int(v * 0.12) for v in demand_series]  # “rủi ro thiếu”

        main_chart = {
            "labels": labels,
            "demand": demand_series,
            "plan": plan_series,
            "risk": risk_band,
        }

        # ---------- CATEGORY BAR (Doanh thu dự báo theo danh mục) ----------
        # Mock "triệu" (tr)
        # lấy 3 category chính từ product line
        cat_map = {}
        for p in products:
            cat_name = (p.categ_id.name if p.categ_id else "Khác")
            cat_map.setdefault(cat_name, 0)
            cat_map[cat_name] += random.randint(40, 180)

        # pick top 3
        top_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)[:3]
        if not top_cats:
            top_cats = [("Quần jean nữ", 420), ("Áo thun nam", 310), ("Váy công sở", 180)]

        rev_rows = []
        palette = ["#10b981", "#60a5fa", "#fb923c"]
        for i, (name, val) in enumerate(top_cats):
            rev_rows.append({
                "key": f"cat_{i}",
                "name": name,
                "value": int(val),
                "color": palette[i % len(palette)],
            })

        rev_spark = {
            "labels": [r["name"] for r in rev_rows],   # ✅ theo danh mục/SKU, không phải theo tháng
            "values": [r["value"] for r in rev_rows],
            "colors": [r["color"] for r in rev_rows],
        }

        # ---------- INVENTORY FORECAST CARD ----------
        focus = sku_rows[0] if sku_rows else None
        if focus:
            days_left = random.randint(10, 25)
            inv_labels = ["", "", "", "", ""]
            onhand_bars = [random.randint(800, 5000) for _ in range(2)] + [0, 0, 0]
            trend_line = [random.randint(800, 1200), random.randint(1400, 2200), random.randint(2000, 3200),
                          random.randint(2600, 3800), random.randint(2800, 4200)]
            inventory_forecast = {
                "labels": inv_labels,
                "onhand_series": onhand_bars,
                "trend_series": trend_line,
                "hint": {
                    "sku_name": focus["sku_name"],
                    "days_left": days_left,
                    "message": f"Hết hàng sau {days_left} ngày nếu hiện tại",
                },
                "growth_note": f"Tăng {random.choice([16,18,20])}% so với hiện tại",
            }
        else:
            inventory_forecast = None

        # ---------- table: đề xuất đặt hàng ----------
        order_suggestions = []
        for i, r in enumerate(sku_rows[:5], start=1):
            order_suggestions.append({
                "stt": i,
                "sku": r["sku_name"],
                "category": r["category"],
                "demand": r["demand"],
                "onhand": r["onhand"],
                "plan_buy": r["plan_buy"],
                "status": "Nguy cơ thiếu hàng" if r["risk"] else "Ổn định",
            })

        return {
            "kpis": kpis,
            "main_chart": main_chart,
            "rev_by_category": rev_rows,
            "rev_spark": rev_spark,
            "inventory_forecast": inventory_forecast,
            "order_suggestions": order_suggestions,
        }

    def _empty_payload(self):
        return {
            "kpis": {
                "total_supply_need": 0,
                "purchase_plan_qty": 0,
                "risk_sku_count": 0,
                "waiting_orders": 0,
                "growth_percent": 0,
                "last_update": "",
            },
            "main_chart": {"labels": [], "demand": [], "plan": [], "risk": []},
            "rev_by_category": [],
            "rev_spark": {"labels": [], "values": [], "colors": []},
            "inventory_forecast": None,
            "order_suggestions": [],
        }
