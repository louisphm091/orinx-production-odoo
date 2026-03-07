from odoo import api, fields, models, _
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
            "main_sku": _("Women's Jeans"),
            "revenue": 820_000_000,
            "revenue_delta": 10,
            "risk_sku_count": 2,
            "need_review_count": 1,
        }

        # --- timeline header (April) ---
        cols = [_("Feb"), _("Mar"), _("Apr"), _("May"), _("Jun"), _("Jul"), _("Aug"), _("Sep"), _("Oct")]
        # timeline rows
        rows = [
            {
                "key": "r1",
                "sku": _("Women's Jeans"),
                "campaign": _("Summer Sale"),
                "stock": 1200,
                "target": 420_000_000,
                # bar position: 0..8 (for cols) + width in cols
                "bars": [{"label": _("01 – 30 Apr"), "start": 2, "span": 7, "color": "green"}],
            },
            {
                "key": "r2",
                "sku": _("Men's T-shirt"),
                "campaign": _("Regular Sale"),
                "stock": 900,
                "target": 260_000_000,
                "bars": [{"label": _("01 – 26 Apr"), "start": 1, "span": 6, "color": "blue"}],
            },
            {
                "key": "r3",
                "sku": _("Office Dress"),
                "campaign": "Clearance",
                "stock": 400,
                "target": 140_000_000,
                "bars": [{"label": _("01 – 14 Apr"), "start": 0, "span": 4, "color": "yellow"}],
            },
        ]

        # --- selected schedule detail (mock) ---
        selected = {
            "sku": _("Women's Jeans"),
            "campaign": _("Summer Sale"),
            "sku_code": "QJN-NU",
            "date_from": "01/04",
            "date_to": "30/04",
            "target_revenue": 420_000_000,
            "current_stock": 1200,
            "status": _("On Sale"),
        }

        inventory_link = {
            "onhand": 1200,
            "daily_sell": 40,
            "out_of_stock_date": _("18 Apr"),
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
            {"key": "a1", "sku": _("Office Dress"), "message": _("Risk of shortage in 5 days"), "trend": "up"},
            {"key": "a2", "sku": _("Men's T-shirt"), "message": _("Sales 16%% slower than plan"), "trend": "down"},
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
