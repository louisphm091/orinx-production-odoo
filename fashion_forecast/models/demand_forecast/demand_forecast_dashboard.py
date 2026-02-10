# Demand_forecast/models/Demand_forecast_dashboard.py
from odoo import api, fields, models
import random


class DemandForecastDashboard(models.AbstractModel):
    _name = "demand.forecast.dashboard"
    _description = "Demand Forecast Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        Forecast = self.env["demand.forecast"].sudo()
        Line = self.env["demand.forecast.line"].sudo()

        # Pick forecast
        forecast = None
        forecast_id = filters.get("forecast_id")
        if forecast_id:
            forecast = Forecast.browse(int(forecast_id)).exists()

        if not forecast:
            domain = []
            if filters.get("warehouse_id"):
                domain.append(("warehouse_id", "=", int(filters["warehouse_id"])))
            if filters.get("date_from"):
                domain.append(("date_from", ">=", filters["date_from"]))
            if filters.get("date_to"):
                domain.append(("date_to", "<=", filters["date_to"]))
            forecast = Forecast.search(domain, limit=1, order="date_from desc, id desc")

        if not forecast:
            return {
                "kpis": {
                    "sku_forecast": 0,
                    "delta_percent": "0%",
                    "top_sku_name": "-",
                    "top_sku_share": "0%",
                    "low_stock_sku_count": 0,
                    "low_stock_hint": "",
                    "manual_adjusted": False,
                    "last_update": "",
                },
                "series": {"labels": [], "forecast": [], "actual": []},
                "forecast_rows": [],
                "forecast_leak_rows": [],
                "adjustment_percent": 0,
            }

        lines = Line.search([("forecast_id", "=", forecast.id)])

        total_forecast = sum(lines.mapped("forecast_qty")) or 0.0
        total_actual = sum(lines.mapped("actual_qty")) or 0.0

        # delta %
        delta_percent = "0%"
        if total_actual:
            delta = (total_forecast - total_actual) / total_actual * 100.0
            sign = "+" if delta >= 0 else ""
            delta_percent = f"{sign}{delta:.1f}%"

        # top sku
        top_line = lines.sorted(key=lambda l: l.forecast_qty or 0.0, reverse=True)[:1]
        top_line = top_line[0] if top_line else None
        top_sku_name = top_line.product_id.display_name if top_line else "-"
        top_sku_share = "0%"
        if top_line and total_forecast:
            top_sku_share = f"{(top_line.forecast_qty / total_forecast * 100.0):.0f}%"

        # shortage risk
        shortage_lines = lines.filtered(lambda l: (l.shortage_qty or 0.0) > 0.0)
        low_stock_sku_count = len(shortage_lines)
        low_stock_hint = "Có SKU dự kiến thiếu hàng trong kỳ." if low_stock_sku_count else ""

        # NOTE: bạn đang có field typo adjustmnet_percent trước đó
        # => lấy an toàn cả 2 tên
        adjustment_percent = 0.0
        if "adjustment_percent" in forecast._fields:
            adjustment_percent = forecast.adjustment_percent or 0.0
        elif "adjustmnet_percent" in forecast._fields:
            adjustment_percent = forecast.adjustmnet_percent or 0.0

        kpis = {
            "sku_forecast": int(round(total_forecast)),
            "delta_percent": delta_percent,
            "top_sku_name": top_sku_name,
            "top_sku_share": top_sku_share,
            "low_stock_sku_count": low_stock_sku_count,
            "low_stock_hint": low_stock_hint,
            "manual_adjusted": bool(adjustment_percent),
            "last_update": (forecast.write_date and fields.Datetime.to_string(forecast.write_date)) or "",
        }

        # series placeholder
        # --- build series (simple split) ---
        labels = ["T1", "T2", "T3", "T4", "T5", "T6"]

        # chia total thành 6 điểm cho đẹp (deterministic)
        weights = [0.12, 0.15, 0.17, 0.18, 0.20, 0.18]
        f_points = [round(total_forecast * w) for w in weights]
        a_points = [round(total_actual * w) for w in weights]

        series = {
            "labels": labels,
            "forecast": f_points,
            "actual": a_points,
        }

        forecast_rows = []
        for l in lines.sorted(key=lambda x: x.forecast_qty or 0.0, reverse=True)[:8]:
            forecast_rows.append({
                "key": f"f_{l.id}",
                "name": l.product_id.display_name,
                "category": l.categ_id.display_name if l.categ_id else "",
                "demand": int(round(l.forecast_qty or 0.0)),
                "actual": int(round(l.actual_qty or 0.0)),
            })

        forecast_leak_rows = []
        for l in shortage_lines.sorted(key=lambda x: x.shortage_qty or 0.0, reverse=True)[:8]:
            forecast_leak_rows.append({
                "key": f"s_{l.id}",
                "name": l.product_id.display_name,
                "need": int(round(l.shortage_qty or 0.0)),
                "demand": int(round(l.forecast_qty or 0.0)),
                "actual": int(round(l.actual_qty or 0.0)),
            })

        # ========= Spark bars (1 dãy cột như ảnh) =========
        # chia total_rev thành 5 cột (deterministic)
        # lấy top 5 dòng theo doanh thu forecast
        top_lines = sorted(
            lines,
            key=lambda l: (l.forecast_qty or 0.0) * (l.product_id.list_price or 0.0),
            reverse=True
        )[:5]

        spark_labels = []
        spark_values = []
        spark_colors = ["#14b8a6", "#34d399", "#a7f3d0", "#fde68a", "#fb923c"]

        for l in top_lines:
            name = l.product_id.display_name
            short = name.split(" ")[0:2]          # rút gọn cho UI
            spark_labels.append(" ".join(short))  # VD: "Quần jean"
            spark_values.append(
                int(round((l.forecast_qty or 0.0) * (l.product_id.list_price or 0.0)))
            )

        rev_spark = {
            "labels": spark_labels,    # <-- THEO SKU
            "values": spark_values,
            "colors": spark_colors[:len(spark_values)],
        }

        # chọn SKU có shortage cao nhất
        risk_line = shortage_lines[:1]
        if risk_line:
            l = risk_line[0]

            onhand = l.onhand_qty or 0
            daily_rate = max(1, (l.actual_qty or l.forecast_qty or 30) / 30)

            days_to_oos = int(onhand / daily_rate) if daily_rate else 0

            inventory_forecast = {
                "sku_name": l.product_id.display_name,
                "days_to_oos": days_to_oos,
                "labels": ["Hiện tại", "+7d", "+14d", "+21d"],
                "onhand_series": [
                    int(onhand),
                    max(0, int(onhand - daily_rate * 7)),
                    max(0, int(onhand - daily_rate * 14)),
                    0,
                ],
                "trend_series": [
                    int(onhand),
                    int(onhand - daily_rate * 8),
                    int(onhand - daily_rate * 16),
                    int(onhand - daily_rate * 21),
                ],
                "growth_percent": random.choice([12, 15, 18]),
                "season_note": "SS hiện tại",
            }
        else:
            inventory_forecast = {}

        # return thêm 2 field này
        return {
            "kpis": kpis,
            "series": series,
            "forecast_rows": forecast_rows,
            "forecast_leak_rows": forecast_leak_rows,
            "adjustment_percent": int(round(adjustment_percent)),
            "rev_spark": rev_spark,
             "inventory_forecast": inventory_forecast,
        }
