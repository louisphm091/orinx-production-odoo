from odoo import api, fields, models, _
import random


class SalePlanningAnalyticsDashboard(models.AbstractModel):
    _name = "sale.planning.analytics.dashboard"
    _description = "Sale Planning - Analytics Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = (kwargs or {}).get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        random.seed(19)

        # KPI top cards
        kpis = {
            "user_behavior": {"pv": 120000, "uu": 35000, "delta_percent": "+15%"},
            "revenue": {"value": 1250000000, "growth_percent": 12},
            "profit": {"value": 1250000000, "growth_percent": 12},  # demo
            "kpi_over": {"delta_percent": "+8%", "subtitle": _("Category exceeding KPI")},
        }

        # Line chart: PV/UU by month
        months = [_("Jan"), _("Feb"), _("Mar"), _("Apr"), _("May"), _("Jun")]
        pv = [22000, 28000, 31000, 33500, 36000, 42000]
        uu = [8200, 9800, 10500, 11200, 12800, 15000]

        behavior_chart = {
            "labels": months,
            "datasets": [
                {"label": "PV", "data": pv},
                {"label": "UU", "data": uu},
            ],
        }

        # Bar chart: Revenue by category
        revenue_by_category = [
            {"key": "c1", "name": _("Women's Jeans"), "value": 420, "color": "rgba(16,185,129,0.9)"},
            {"key": "c2", "name": _("Men's T-shirt"), "value": 310, "color": "rgba(59,130,246,0.85)"},
            {"key": "c3", "name": _("Office Dress"), "value": 180, "color": "rgba(245,158,11,0.85)"},
        ]
        revenue_bar = {
            "labels": [_("Apr"), _("May"), _("Jun")],
            "values": [280, 350, 420],
            "colors": ["rgba(16,185,129,0.35)", "rgba(16,185,129,0.6)", "rgba(16,185,129,0.9)"],
            "headline": _("420 M"),
        }

        # Donut: full price vs sale
        pricing_mix = {"full_price": 68, "sale": 32, "note": _("Office dresses have a higher than average sale rate – price strategy needs review")}

        # Table: Plan vs Actual
        plan_actual_rows = [
            {"key": "p1", "name": _("Women's Jeans"), "category": _("Women's Fashion"), "pv": 28000, "uu": 3200, "revenue": _("420 M"), "full_price": "27.79%"},
            {"key": "p2", "name": _("Men's T-shirt"), "category": _("Men's Fashion"), "pv": 18000, "uu": 6100, "revenue": _("310 M"), "full_price": "28.99%"},
            {"key": "p3", "name": _("Office Dress"), "category": _("Women's Fashion"), "pv": 14000, "uu": 5300, "revenue": _("180 M"), "full_price": "27.89%"},
        ]

        # Table: chart & data (search)
        data_table_rows = [
            {"key": "d1", "name": _("Women's Jeans"), "category": _("Women's Fashion"), "pv": 28000, "uu": 3200, "revenue": _("420 M"), "sale": 7.2},
            {"key": "d2", "name": _("Men's T-shirt"), "category": _("Men's Fashion"), "pv": 18000, "uu": 6100, "revenue": _("310 M"), "sale": 6.5},
            {"key": "d3", "name": _("Office Dress"), "category": _("Women's Fashion"), "pv": 14000, "uu": 5300, "revenue": _("180 M"), "sale": 4.8},
        ]

        return {
            "kpis": kpis,
            "behavior_chart": behavior_chart,
            "revenue_bar": revenue_bar,
            "revenue_by_category": revenue_by_category,
            "pricing_mix": pricing_mix,
            "plan_actual_rows": plan_actual_rows,
            "data_table_rows": data_table_rows,
        }
