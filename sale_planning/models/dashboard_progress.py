# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import random


class SalePlanningDashboardProgressService(models.AbstractModel):
    _name = "sale.planning.dashboard.progress"
    _description = "Sale Planning - Dashboard Progress Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        """
        JS gọi:
          orm.call("sale.planning.dashboard.progress", "get_dashboard_data", [], {filters:{...}})
        """
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        random.seed(19)

        # ---- Fashion SKU demo ----
        skus = [
            {"sku": _("Women's Jeans"), "cat": _("Women's Fashion")},
            {"sku": _("Office Dress"), "cat": _("Women's Fashion")},
            {"sku": _("Men's T-shirt"), "cat": _("Men's Fashion")},
            {"sku": _("Women's Jacket"), "cat": _("Women's Fashion")},
            {"sku": _("Men's Shirt"), "cat": _("Men's Fashion")},
            {"sku": _("Skirt"), "cat": _("Women's Fashion")},
        ]

        # planned vs actual (tổng quan)
        overall = []
        for s in skus:
            planned = random.randint(600, 980)
            actual = int(planned * random.choice([0.7, 0.78, 0.85, 0.92, 1.02]))
            overall.append({
                "name": s["sku"],
                "planned": planned,
                "actual": actual,
            })

        total_planned = sum(x["planned"] for x in overall) or 1
        total_actual = sum(x["actual"] for x in overall)

        progress_percent = int(round(total_actual / total_planned * 100))
        late_skus = [x for x in overall if x["actual"] < x["planned"] * 0.8]
        ontrack_skus = [x for x in overall if x["actual"] >= x["planned"] * 0.95]

        # Alerts / risks
        risks = [
            {"name": _("Office Dress"), "hint": _("15%% behind weekly plan"), "level": "high"},
            {"name": _("Women's Jacket"), "hint": _("Risk of delay due to low inventory"), "level": "medium"},
        ]

        # Mini cards (theo SKU/đơn)
        sku_cards = [
            {
                "key": "c1",
                "name": _("Women's Jeans"),
                "status": _("On track"),
                "status_type": "ok",
                "percent": 92,
                "revenue": 420_000_000,
                "tags": [_("Top seller"), _("Stable")],
            },
            {
                "key": "c2",
                "name": _("Office Dress"),
                "status": _("Behind schedule"),
                "status_type": "bad",
                "percent": 70,
                "reasons": [_("Low inventory"), _("Decreased demand")],
            },
            {
                "key": "c3",
                "name": _("Men's T-shirt"),
                "status": _("On track"),
                "status_type": "ok",
                "percent": 78,
                "revenue": 310_000_000,
                "tags": [_("Stable")],
            },
        ]

        # Execution history & trend (line)
        hist_labels = [_("Week 1"), _("Week 2"), _("Week 3"), _("Week 4"), _("Week 5"), _("Week 6")]
        hist_values = [85, 83, 79, 82, 76, 74]

        note = _("Progress decreased due to slow sales of Office Dress group for 2 consecutive weeks")

        return {
            "filters_echo": filters,
            "kpis": {
                "progress_percent": progress_percent,
                "late_sku_count": len(late_skus),
                "late_sku_names": ", ".join([x["name"] for x in late_skus[:2]]) or "-",
                "ontrack_sku_count": len(ontrack_skus),
                "ontrack_sku_names": ", ".join([x["name"] for x in ontrack_skus[:2]]) or "-",
                "critical_count": 1,
                "critical_hint": _("1 critical issue"),
            },
            "overall_chart": {
                "labels": [x["name"] for x in overall],
                "planned": [x["planned"] for x in overall],
                "actual": [x["actual"] for x in overall],
                # trend line (mock)
                "trend": [int(x["actual"] * random.choice([0.95, 1.0, 1.03])) for x in overall],
            },
            "risks": risks,
            "sku_cards": sku_cards,
            "history": {
                "labels": hist_labels,
                "values": hist_values,
                "note": note,
            },
            "last_update": fields.Datetime.now(),
        }
