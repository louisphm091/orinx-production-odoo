# -*- coding: utf-8 -*-
from odoo import api, fields, models
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
            "kpi_over": {"delta_percent": "+8%", "subtitle": "Danh mục vượt KPI"},
        }

        # Line chart: PV/UU theo tháng
        months = ["Tháng 01", "Tháng 02", "Tháng 03", "Tháng 04", "Tháng 05", "Tháng 06"]
        pv = [22000, 28000, 31000, 33500, 36000, 42000]
        uu = [8200, 9800, 10500, 11200, 12800, 15000]

        behavior_chart = {
            "labels": months,
            "datasets": [
                {"label": "PV", "data": pv},
                {"label": "UU", "data": uu},
            ],
        }

        # Bar chart: Doanh thu theo danh mục
        revenue_by_category = [
            {"key": "c1", "name": "Quần jean nữ", "value": 420, "color": "rgba(16,185,129,0.9)"},
            {"key": "c2", "name": "Áo thun nam", "value": 310, "color": "rgba(59,130,246,0.85)"},
            {"key": "c3", "name": "Váy công sở", "value": 180, "color": "rgba(245,158,11,0.85)"},
        ]
        revenue_bar = {
            "labels": ["Tháng 04", "Tháng 05", "Tháng 06"],
            "values": [280, 350, 420],
            "colors": ["rgba(16,185,129,0.35)", "rgba(16,185,129,0.6)", "rgba(16,185,129,0.9)"],
            "headline": "420 triệu",
        }

        # Donut: nguyên giá vs sale
        pricing_mix = {"full_price": 68, "sale": 32, "note": "Váy công sở có tỷ lệ sale cao hơn trung bình – cần xem lại chiến lược giá"}

        # Table: Plan vs Actual
        plan_actual_rows = [
            {"key": "p1", "name": "Quần jean nữ", "category": "Thời trang nữ", "pv": 28000, "uu": 3200, "revenue": "420 triệu", "full_price": "27.79%"},
            {"key": "p2", "name": "Áo thun nam", "category": "Thời trang nam", "pv": 18000, "uu": 6100, "revenue": "310 triệu", "full_price": "28.99%"},
            {"key": "p3", "name": "Váy công sở", "category": "Thời trang nữ", "pv": 14000, "uu": 5300, "revenue": "180 triệu", "full_price": "27.89%"},
        ]

        # Table: chart & data (search)
        data_table_rows = [
            {"key": "d1", "name": "Quần jean nữ", "category": "Thời trang nữ", "pv": 28000, "uu": 3200, "revenue": "420 triệu", "sale": 7.2},
            {"key": "d2", "name": "Áo thun nam", "category": "Thời trang nam", "pv": 18000, "uu": 6100, "revenue": "310 triệu", "sale": 6.5},
            {"key": "d3", "name": "Váy công sở", "category": "Thời trang nữ", "pv": 14000, "uu": 5300, "revenue": "180 triệu", "sale": 4.8},
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
