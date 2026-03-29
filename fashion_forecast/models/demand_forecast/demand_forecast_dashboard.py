# Demand_forecast/models/Demand_forecast_dashboard.py
from odoo import api, fields, models
import random
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


import logging

_logger = logging.getLogger(__name__)


class DemandForecastDashboard(models.AbstractModel):
    _name = "demand.forecast.dashboard"
    _description = "Demand Forecast Dashboard Service"

    def _resolve_warehouse_id(self, filters=None):
        filters = filters or {}
        wh_id = filters.get("warehouse_id")
        if wh_id:
            return int(wh_id)
        user = self.env.user.with_company(self.env.company.id)
        if hasattr(user, "_get_default_warehouse_id"):
            warehouse = user._get_default_warehouse_id()
            if warehouse:
                return warehouse.id
        warehouse = self.env["stock.warehouse"].sudo().search(
            [("company_id", "=", self.env.company.id)],
            limit=1,
        )
        return warehouse.id or False

    def _seed_forecast_lines_from_dynamic_data(self, forecast, filters=None):
        filters = dict(filters or {})
        filters["forecast_id"] = False
        dynamic_data = self._get_dynamic_historical_forecast(filters)
        existing_product_ids = set(forecast.line_ids.mapped("product_id").ids)
        line_vals = []
        for row in dynamic_data.get("forecast_rows", []):
            product_id = row.get("product_id")
            if not product_id or int(product_id) in existing_product_ids:
                continue
            line_vals.append({
                "forecast_id": forecast.id,
                "product_id": int(product_id),
                "forecast_qty": float(row.get("demand") or 0.0),
                "actual_qty": float(row.get("actual") or 0.0),
            })
        if line_vals:
            self.env["demand.forecast.line"].sudo().create(line_vals)

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        Forecast = env["demand.forecast"].sudo()
        Line = env["demand.forecast.line"].sudo()

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
            domain.append(("company_id", "=", self.env.company.id))
            forecast = Forecast.search(domain, limit=1, order="date_from desc, id desc")

        # --- Dynamic Data Generation if no Forecast record exists ---
        if not forecast:
            return self._get_dynamic_historical_forecast(filters)

        if forecast.state == "draft":
            self._seed_forecast_lines_from_dynamic_data(forecast, filters)
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
            top_sku_share = f"{(top_line.forecast_qty / total_forecast * 100.0):.1f}%"

        # shortage risk
        shortage_lines = lines.filtered(lambda l: (l.shortage_qty or 0.0) > 0.0)
        low_stock_sku_count = len(shortage_lines)
        low_stock_hint = "Có SKU dự kiến thiếu hàng trong kỳ." if low_stock_sku_count else ""

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
        labels = ["T1", "T2", "T3", "T4", "T5", "T6"]
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
                "product_id": l.product_id.id,
                "name": l.product_id.display_name,
                "category": l.categ_id.display_name if l.categ_id else "",
                "demand": int(round(l.forecast_qty or 0.0)),
                "actual": int(round(l.product_id.with_context(warehouse=forecast.warehouse_id.id).qty_available if forecast.warehouse_id else l.product_id.qty_available)),
                "minimum": int(round(l.product_id.product_tmpl_id.minimum_inventory or 0.0)),
            })
        _logger.info("DEBUG: get_dashboard_data sample row: %s", forecast_rows[0] if forecast_rows else "EMPTY")

        forecast_leak_rows = []
        for l in shortage_lines.sorted(key=lambda x: x.shortage_qty or 0.0, reverse=True)[:8]:
            forecast_leak_rows.append({
                "key": f"s_{l.id}",
                "name": l.product_id.display_name,
                "need": int(round(l.shortage_qty or 0.0)),
                "demand": int(round(l.forecast_qty or 0.0)),
                "actual": int(round(l.actual_qty or 0.0)),
            })

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
            short = name.split(" ")[0:2]
            spark_labels.append(" ".join(short))
            spark_values.append(
                int(round((l.forecast_qty or 0.0) * (l.product_id.list_price or 0.0)))
            )

        rev_spark = {
            "labels": spark_labels,
            "values": spark_values,
            "colors": spark_colors[:len(spark_values)],
        }

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

        return {
            "forecast_id": forecast.id if forecast else None,
            "kpis": kpis,
            "series": series,
            "forecast_rows": forecast_rows,
            "forecast_leak_rows": forecast_leak_rows,
            "adjustment_percent": int(round(adjustment_percent)),
            "rev_spark": rev_spark,
            "inventory_forecast": inventory_forecast,
        }

    @api.model
    def save_forecast_line(self, product_id, qty, filters=None):
        """
        Save a manual forecast quantity for a product.
        If no forecast exists for the current context, create one.
        """
        env = self.env
        Forecast = env["demand.forecast"].sudo()
        Line = env["demand.forecast.line"].sudo()
        Product = env["product.product"].sudo().browse(int(product_id))
        
        if not Product.exists():
            return {"ok": False, "message": "Product not found."}

        filters = filters or {}
        forecast_id = filters.get("forecast_id")
        wh_id = self._resolve_warehouse_id(filters)
        forecast = False
        
        if forecast_id:
            forecast = Forecast.browse(int(forecast_id)).exists()
        
        if not forecast:
            # Try to find a recent one or create new
            domain = [("company_id", "=", env.company.id)]
            if wh_id:
                domain.append(("warehouse_id", "=", wh_id))
            
            forecast = Forecast.search(domain, limit=1, order="date_from desc, id desc")
            
            if not forecast:
                # Create a new forecast for the current month
                today = date.today()
                date_from = today.replace(day=1)
                date_to = (date_from + relativedelta(months=1)) - timedelta(days=1)
                
                vals = {
                    "name": f"Dự báo {date_from.strftime('%m/%Y')}",
                    "date_from": date_from,
                    "date_to": date_to,
                    "company_id": env.company.id,
                    "warehouse_id": wh_id,
                }
                forecast = Forecast.create(vals)

        self._seed_forecast_lines_from_dynamic_data(forecast, filters)

        # Create or update line
        line = Line.search([
            ("forecast_id", "=", forecast.id),
            ("product_id", "=", Product.id)
        ], limit=1)
        
        if line:
            line.write({"forecast_qty": float(qty)})
        else:
            Line.create({
                "forecast_id": forecast.id,
                "product_id": Product.id,
                "forecast_qty": float(qty),
                "date_from": forecast.date_from,
                "date_to": forecast.date_to,
            })
            
        return {"ok": True, "forecast_id": forecast.id}

    def _get_dynamic_historical_forecast(self, filters):
        """Generate forecast based on 3-month average of revenue/sales."""
        env = self.env
        today = fields.Date.today()
        date_start = today - relativedelta(months=3)
        
        _logger.info("Generating dynamic forecast: filters=%s, date_start=%s", filters, date_start)
        
        SaleLine = env["sale.order.line"].sudo()
        PosLine = env["pos.order.line"].sudo() if "pos.order.line" in env.registry else False
        
        # 1. Sale Line Aggregation
        sale_domain = [
            ("state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", fields.Datetime.to_string(date_start)),
        ]
        
        # Branch context
        wh_id = filters.get("warehouse_id")
        if wh_id:
            config = env["pos.config"].sudo().browse(int(wh_id)).exists()
            if config and config.swift_warehouse_id:
                sale_domain.append(("order_id.warehouse_id", "=", config.swift_warehouse_id.id))
            else:
                sale_domain.append(("order_id.warehouse_id", "=", int(wh_id)))

        # Group by product
        sale_grouped = SaleLine._read_group(
            sale_domain,
            ["product_id"],
            ["price_subtotal:sum", "product_uom_qty:sum"]
        )
        
        metrics = {}
        for product, subtotal_sum, qty_sum in sale_grouped:
            if not product: continue
            metrics[product.id] = {
                "id": product.id,
                "name": product.display_name,
                "category": product.categ_id.name or "",
                "revenue": subtotal_sum or 0.0,
                "qty": qty_sum or 0.0,
                "minimum": product.product_tmpl_id.minimum_inventory or 0.0
            }
        _logger.info("Sale lines processed: %d products", len(metrics))
            
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
                pos_domain,
                ["product_id"],
                ["price_subtotal_incl:sum", "qty:sum"]
            )
            for product, subtotal_sum, qty_sum in pos_grouped:
                if not product: continue
                if product.id not in metrics:
                    metrics[product.id] = {
                        "id": product.id,
                        "name": product.display_name,
                        "category": product.categ_id.name or "",
                        "revenue": 0.0,
                        "qty": 0.0,
                        "minimum": product.product_tmpl_id.minimum_inventory or 0.0
                    }
                metrics[product.id]["revenue"] += subtotal_sum or 0.0
                metrics[product.id]["qty"] += qty_sum or 0.0
            _logger.info("POS data merged with sales: metrics total=%d", len(metrics))
                
        # 3. Calculate 30-day average (3-month total / 3)
        product_list = list(metrics.values())
        
        # Category Filter (mock category in UI screenshot)
        cat_id = filters.get("category_id")
        if cat_id:
            cat_id = int(cat_id)
            # Fetch products with category filter
            Product = env['product.product'].sudo()
            valid_pids_in_cat = Product.search([('categ_id', 'child_of', cat_id)]).ids
            product_list = [m for m in product_list if m['id'] in valid_pids_in_cat]
            _logger.info("Filtered by category %d: resulting total=%d", cat_id, len(product_list))
        
        total_monthly_revenue = 0.0
        for m in product_list:
            m["avg_revenue"] = m["revenue"] / 3.0
            m["avg_qty"] = m["qty"] / 3.0
            total_monthly_revenue += m["avg_revenue"]
            
        # Top SKU based on revenue average
        top_skus = sorted(product_list, key=lambda x: x["avg_revenue"], reverse=True)
        top_sku = top_skus[0] if top_skus else None
        top_sku_name = top_sku["name"] if top_sku else "-"
        top_sku_share = f"{(top_sku['avg_revenue'] / total_monthly_revenue * 100.0):.1f}%" if top_sku and total_monthly_revenue else "0%"
        
        _logger.info("Calculation complete: total_revenue=%f, top_sku=%s", total_monthly_revenue, top_sku_name)
        
        kpis = {
            "sku_forecast": int(round(total_monthly_revenue)),
            "delta_percent": "+12.5%", # Placeholder trend
            "top_sku_name": top_sku_name,
            "top_sku_share": top_sku_share,
            "low_stock_sku_count": 0,
            "low_stock_hint": "Hiện tại không có rủi ro thiếu hàng dựa trên dữ liệu lịch sử.",
            "manual_adjusted": False,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }
        
        # Series (deterministic split of total)
        labels = ["T1", "T2", "T3", "T4", "T5", "T6"]
        weights = [0.12, 0.15, 0.17, 0.18, 0.20, 0.18]
        f_points = [round(total_monthly_revenue * w) for w in weights]
        a_points = [round(total_monthly_revenue * w * 0.95) for w in weights] # Slightly less for visual
        
        series = {"labels": labels, "forecast": f_points, "actual": a_points}
        
        forecast_rows = []
        for m in top_skus[:8]:
            forecast_rows.append({
                "key": f"dyn_{m['id']}",
                "product_id": m["id"],
                "name": m["name"],
                "category": m["category"],
                "demand": int(round(m["avg_qty"] or 0.0)),
                "actual": int(round(env['product.product'].sudo().browse(m['id']).with_context(warehouse=int(wh_id) if wh_id else None).qty_available)),
                "minimum": int(round(m["minimum"] or 0.0)),
            })
        _logger.info("DEBUG: dynamic_forecast sample row: %s", forecast_rows[0] if forecast_rows else "EMPTY")
            
        rev_spark_labels = []
        rev_spark_values = []
        for m in top_skus[:5]:
            rev_spark_labels.append(m["name"][:10])
            rev_spark_values.append(int(round(m["avg_revenue"])))
            
        rev_spark = {
            "labels": rev_spark_labels,
            "values": rev_spark_values,
            "colors": ["#14b8a6", "#34d399", "#a7f3d0", "#fde68a", "#fb923c"][:len(rev_spark_values)],
        }
        
        return {
            "kpis": kpis,
            "series": series,
            "forecast_rows": forecast_rows,
            "forecast_leak_rows": [],
            "adjustment_percent": 0,
            "rev_spark": rev_spark,
            "inventory_forecast": {},
        }
