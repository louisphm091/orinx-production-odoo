# -*- coding: utf-8 -*-
from odoo import api, fields, models
import random


class SalePlanningReplenishmentDashboard(models.AbstractModel):
    _name = "sale.planning.replenishment"
    _description = "Sale Planning - Replenishment Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        random.seed(19)

        rows = [
            {
                "key": "r1",
                "sku_name": "Quần jean nữ – Form suông",
                "category": "Thời trang nữ",
                "warehouse": "Kho HCM",
                "onhand": 120,
                "forecast_30d": 350,
                "suggest_qty": 250,
                "state": "proposed",  # proposed / approved / ordered
                "reason": "Chuẩn bị chạy chiến dịch khuyến mãi hè – tăng lượt wishlist & đơn đặt trước",
                "season": "Hè 2025",
                "image_hint": "jeans",
            },
            {
                "key": "r2",
                "sku_name": "Áo thun nam",
                "category": "Thời trang nam",
                "warehouse": "Kho HCM",
                "onhand": 80,
                "forecast_30d": 190,
                "suggest_qty": 120,
                "state": "approved",
                "reason": "Nhu cầu ổn định, tồn kho thấp hơn ngưỡng an toàn",
                "season": "Hè 2025",
                "image_hint": "tshirt",
            },
            {
                "key": "r3",
                "sku_name": "Chân váy midi xếp ly",
                "category": "Thời trang nữ",
                "warehouse": "Kho HCM",
                "onhand": 50,
                "forecast_30d": 190,
                "suggest_qty": 190,
                "state": "approved",
                "reason": "Lead time dài, cần đặt sớm để kịp mùa",
                "season": "Hè 2025",
                "image_hint": "skirt",
            },
            {
                "key": "r4",
                "sku_name": "Đầm hoa nhí",
                "category": "Thời trang nữ",
                "warehouse": "Kho HCM",
                "onhand": 40,
                "forecast_30d": 150,
                "suggest_qty": 150,
                "state": "ordered",
                "reason": "Bán tốt 2 tuần gần đây",
                "season": "Hè 2025",
                "image_hint": "dress",
            },
            {
                "key": "r5",
                "sku_name": "Áo phông trắng",
                "category": "Thời trang nữ",
                "warehouse": "Kho HCM",
                "onhand": 140,
                "forecast_30d": 380,
                "suggest_qty": 300,
                "state": "ordered",
                "reason": "Sản phẩm nền tảng, độ phủ cao",
                "season": "Hè 2025",
                "image_hint": "white_tee",
            },
        ]

        total = len(rows)
        risk_skus = len([r for r in rows if (r["forecast_30d"] - r["onhand"]) > 150])
        pending = len([r for r in rows if r["state"] == "proposed"])
        ordered = len([r for r in rows if r["state"] == "ordered"])

        # sparkline mini (cho KPI 1)
        spark = {
            "labels": ["", "", "", "", ""],
            "values": [3, 6, 5, 8, 11],
        }

        selected_key = filters.get("selected_key") or rows[0]["key"]
        selected = next((r for r in rows if r["key"] == selected_key), rows[0])

        detail = {
            "title": selected["sku_name"],
            "category": selected["category"],
            "season": selected["season"],
            "warehouse": selected["warehouse"],
            "image_hint": selected.get("image_hint") or "product",
            "analysis": {
                "onhand": selected["onhand"],
                "forecast_30d": selected["forecast_30d"],
                "reorder_point": max(0, selected["forecast_30d"] - selected["onhand"]),
                "suggest_qty": selected["suggest_qty"],
            },
            "reason": selected["reason"],
            "state": selected["state"],
        }

        return {
            "filters_echo": filters,
            "kpis": {
                "total_suggestions": total,
                "delta_vs_last_week": "+3",
                "risk_skus": risk_skus,
                "risk_hint": "Dự kiến hết trong 14 ngày",
                "pending": pending,
                "pending_hint": "Cần xử lý trong hôm nay",
                "ordered": ordered,
                "ordered_hint": "Cập nhật hôm nay",
            },
            "spark": spark,
            "rows": rows,
            "detail": detail,
            "last_update": fields.Datetime.now(),
        }
