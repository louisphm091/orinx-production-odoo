# fashion_forecast/models/fashion_forecast_dashboard.py
from odoo import api, fields, models
import logging
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class FashionForecastDashboard(models.AbstractModel):
    _name = "fashion.forecast.dashboard"
    _description = "Fashion Forecast Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        Forecast = self.env["fashion.forecast"].sudo()
        Line = self.env["fashion.forecast.line"].sudo()

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
            return self._get_dynamic_historical_forecast(filters)

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

        return {
            "kpis": kpis,
            "series": series,
            "forecast_rows": forecast_rows,
            "forecast_leak_rows": forecast_leak_rows,
            "adjustment_percent": int(round(adjustment_percent)),
        }

    def _get_dynamic_historical_forecast(self, filters):
        """Generate forecast based on 3-month average of revenue/sales."""
        env = self.env
        today = fields.Date.today()
        date_start = today - relativedelta(months=3)
        
        _logger.info("Generating dynamic forecast (fashion): filters=%s", filters)
        
        SaleLine = env["sale.order.line"].sudo()
        # Find model if exists - handle different module names if any
        PosLine = env["pos.order.line"].sudo() if "pos.order.line" in env.registry else False
        
        # 1. Sale Line Aggregation
        sale_domain = [
            ("state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", fields.Datetime.to_string(date_start)),
        ]
        
        wh_id = filters.get("warehouse_id")
        if wh_id:
            # Similar to dashboard_progress logic
            config = env["pos.config"].sudo().browse(int(wh_id)).exists()
            if config and config.swift_warehouse_id:
                sale_domain.append(("order_id.warehouse_id", "=", config.swift_warehouse_id.id))
            else:
                sale_domain.append(("order_id.warehouse_id", "=", int(wh_id)))

        sale_grouped = SaleLine._read_group(
            sale_domain, ["product_id"], ["price_subtotal:sum", "product_uom_qty:sum"]
        )
        
        metrics = {}
        for product, subtotal_sum, qty_sum in sale_grouped:
            if not product: continue
            metrics[product.id] = {
                "id": product.id,
                "name": product.display_name,
                "category": product.categ_id.name or "",
                "revenue": subtotal_sum or 0.0,
                "qty": qty_sum or 0.0
            }
            
        # 2. POS Line Aggregation
        if PosLine:
            pos_domain = [
                ("order_id.state", "in", ["paid", "done", "invoiced"]),
                ("order_id.date_order", ">=", fields.Datetime.to_string(date_start)),
            ]
            if wh_id:
                config = env["pos.config"].sudo().browse(int(wh_id)).exists()
                if config:
                    pos_domain.append(("order_id.config_id", "=", config.id))
                
            pos_grouped = PosLine._read_group(
                pos_domain, ["product_id"], ["price_subtotal_incl:sum", "qty:sum"]
            )
            for product, subtotal_sum, qty_sum in pos_grouped:
                if not product: continue
                m = metrics.get(product.id)
                if not m:
                    metrics[product.id] = {
                        "id": product.id,
                        "name": product.display_name,
                        "category": product.categ_id.name or "",
                        "revenue": subtotal_sum or 0.0,
                        "qty": qty_sum or 0.0
                    }
                else:
                    m["revenue"] += subtotal_sum or 0.0
                    m["qty"] += qty_sum or 0.0
                
        # 3. Calculate 30-day average
        product_list = list(metrics.values())
        
        # Category Filter check
        cat_id = filters.get("category_id")
        if cat_id:
            valid_pids = env['product.product'].sudo().search([('categ_id', 'child_of', int(cat_id))]).ids
            product_list = [p for p in product_list if p['id'] in valid_pids]

        total_monthly_revenue = 0.0
        for m in product_list:
            m["avg_revenue"] = m["revenue"] / 3.0
            m["avg_qty"] = m["qty"] / 3.0
            total_monthly_revenue += m["avg_revenue"]
            
        top_skus = sorted(product_list, key=lambda x: x["avg_revenue"], reverse=True)
        top_sku = top_skus[0] if top_skus else None
        top_sku_name = top_sku["name"] if top_sku else "-"
        top_sku_share = f"{(top_sku['avg_revenue'] / total_monthly_revenue * 100.0):.0f}%" if top_sku and total_monthly_revenue else "0%"
        
        # Series (deterministic split)
        labels = ["T1", "T2", "T3", "T4", "T5", "T6"]
        f_total = sum(m["avg_qty"] for m in product_list)
        weights = [0.12, 0.15, 0.17, 0.18, 0.20, 0.18]
        
        return {
            "kpis": {
                "sku_forecast": int(round(f_total)),
                "delta_percent": "0%",
                "top_sku_name": top_sku_name,
                "top_sku_share": top_sku_share,
                "low_stock_sku_count": 0,
                "low_stock_hint": "",
                "manual_adjusted": False,
                "last_update": "",
            },
            "series": {
                "labels": labels,
                "forecast": [round(f_total * w) for w in weights],
                "actual": [0] * 6 # No actual vs historical yet
            },
            "forecast_rows": [
                {
                    "key": f"p_{m['id']}",
                    "name": m["name"],
                    "category": m["category"],
                    "demand": int(round(m["avg_qty"])),
                    "actual": 0
                } for m in top_skus[:8]
            ],
            "forecast_leak_rows": [],
            "adjustment_percent": 0,
        }
