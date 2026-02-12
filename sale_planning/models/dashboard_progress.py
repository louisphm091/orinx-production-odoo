# -*- coding: utf-8 -*-
from odoo import api, fields, models
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
            {"sku": "Quần jean nữ", "cat": "Thời trang nữ"},
            {"sku": "Váy công sở", "cat": "Thời trang nữ"},
            {"sku": "Áo thun nam", "cat": "Thời trang nam"},
            {"sku": "Áo khoác nữ", "cat": "Thời trang nữ"},
            {"sku": "Áo sơ mi nam", "cat": "Thời trang nam"},
            {"sku": "Chân váy", "cat": "Thời trang nữ"},
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
            {"name": "Váy công sở", "hint": "Chậm 15% so kế hoạch tuần", "level": "high"},
            {"name": "Áo khoác nữ", "hint": "Nguy cơ trễ do tồn kho thấp", "level": "medium"},
        ]

        # Mini cards (theo SKU/đơn)
        sku_cards = [
            {
                "key": "c1",
                "name": "Quần jean nữ",
                "status": "Đúng tiến độ",
                "status_type": "ok",
                "percent": 92,
                "revenue": 420_000_000,
                "tags": ["Bán chạy", "Ổn định"],
            },
            {
                "key": "c2",
                "name": "Váy công sở",
                "status": "Chậm tiến độ",
                "status_type": "bad",
                "percent": 70,
                "reasons": ["Tồn kho thấp", "Nhu cầu giảm"],
            },
            {
                "key": "c3",
                "name": "Áo thun nam",
                "status": "Đúng tiến độ",
                "status_type": "ok",
                "percent": 78,
                "revenue": 310_000_000,
                "tags": ["Ổn định"],
            },
        ]

        # Lịch sử thực hiện & xu hướng (line)
        hist_labels = ["Tuần 1", "Tuần 2", "Tuần 3", "Tuần 4", "Tuần 5", "Tuần 6"]
        hist_values = [85, 83, 79, 82, 76, 74]

        note = "Tiến độ giảm do nhóm Váy công sở bán chậm trong 2 tuần liên tiếp"

        return {
            "filters_echo": filters,
            "kpis": {
                "progress_percent": progress_percent,
                "late_sku_count": len(late_skus),
                "late_sku_names": ", ".join([x["name"] for x in late_skus[:2]]) or "-",
                "ontrack_sku_count": len(ontrack_skus),
                "ontrack_sku_names": ", ".join([x["name"] for x in ontrack_skus[:2]]) or "-",
                "critical_count": 1,
                "critical_hint": "1 vấn đề nghiêm trọng",
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
