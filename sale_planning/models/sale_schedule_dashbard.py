from odoo import api, fields, models
import random
from datetime import date


class SaleScheduleDashboard(models.AbstractModel):
    _name = "sale.schedule.dashboard"
    _description = "Sale Schedule Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        # deterministic seed theo company
        seed = (self.env.company.id or 1) * 1000 + (date.today().day)
        random.seed(seed)

        # --- KPIs (mock) ---
        kpis = {
            "wave_count": 5,
            "main_sku": "Quần jean nữ",
            "revenue": 820_000_000,
            "revenue_delta": 10,
            "risk_sku_count": 2,
            "need_review_count": 1,
        }

        # --- timeline header (tháng 4) ---
        cols = ["Th2", "Th3", "Th4", "Th5", "Th6", "Th7", "Th8", "Th9", "Th10"]
        # timeline rows
        rows = [
            {
                "key": "r1",
                "sku": "Quần jean nữ",
                "campaign": "Sale hè",
                "stock": 1200,
                "target": 420_000_000,
                # bar position: 0..8 (for cols) + width in cols
                "bars": [{"label": "01 – 30 Th4", "start": 2, "span": 7, "color": "green"}],
            },
            {
                "key": "r2",
                "sku": "Áo thun nam",
                "campaign": "Bán thường",
                "stock": 900,
                "target": 260_000_000,
                "bars": [{"label": "01 – 26 Th4", "start": 1, "span": 6, "color": "blue"}],
            },
            {
                "key": "r3",
                "sku": "Váy công sở",
                "campaign": "Clearance",
                "stock": 400,
                "target": 140_000_000,
                "bars": [{"label": "01 – 14 Th4", "start": 0, "span": 4, "color": "yellow"}],
            },
        ]

        # --- selected schedule detail (mock) ---
        selected = {
            "sku": "Quần jean nữ",
            "campaign": "Sale hè",
            "sku_code": "QJN-NU",
            "date_from": "01/04",
            "date_to": "30/04",
            "target_revenue": 420_000_000,
            "current_stock": 1200,
            "status": "Đang bán",
        }

        inventory_link = {
            "onhand": 1200,
            "daily_sell": 40,
            "out_of_stock_date": "18 Th4",
            "out_of_stock_in_days": 12,
        }

        # --- performance card (mini chart data) ---
        performance = {
            "title": "Quần jean nữ – Sale hè",
            "progress_percent": 92,
            "days": 20,
            "spark": [12, 18, 20, 28, 35, 40, 48, 55],  # mini columns
        }

        # --- risk alerts list ---
        risk_alerts = [
            {"key": "a1", "sku": "Váy công sở", "message": "Nguy cơ thiếu hàng sau 5 ngày", "trend": "up"},
            {"key": "a2", "sku": "Áo thun nam", "message": "Bán chậm hơn kế hoạch 16%", "trend": "down"},
        ]

        return {
            "kpis": kpis,
            "timeline": {
                "cols": cols,
                "rows": rows,
                "view_mode": filters.get("view_mode") or "timeline",  # timeline | calendar
            },
            "selected": selected,
            "inventory_link": inventory_link,
            "performance": performance,
            "risk_alerts": risk_alerts,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }
