# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class SalePlanningReplenishmentDashboard(models.AbstractModel):
    _name = "sale.planning.replenishment"
    _description = "Sale Planning - Replenishment Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)

        # ---- Products (storable, active) ----
        Product = env["product.product"].sudo()
        all_products = Product.search([
            ("active", "=", True),
            ("type", "in", ["product", "consu"]),
        ], limit=100)

        if not all_products:
            return self._empty_payload()

        product_ids = all_products.ids

        # ---- Real stock quantities ----
        StockQuant = env["stock.quant"].sudo()
        Warehouse = env["stock.warehouse"].sudo()
        wh = Warehouse.search([("company_id", "=", env.company.id)], limit=1)
        wh_name = wh.name if wh else _("Main Warehouse")

        quants = StockQuant.search([
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
        ])
        stock_map = {}
        for q in quants:
            stock_map[q.product_id.id] = stock_map.get(q.product_id.id, 0.0) + q.quantity

        # ---- 30-day sales forecast (based on last 30-day sales) ----
        SaleLine = env["sale.order.line"].sudo()
        thirty_days_ago = today - timedelta(days=30)
        sale_lines = SaleLine.search([
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", str(thirty_days_ago)),
            ("product_id", "in", product_ids),
        ])
        demand_30d_map = {}
        for sl in sale_lines:
            pid = sl.product_id.id
            demand_30d_map[pid] = demand_30d_map.get(pid, 0.0) + sl.product_uom_qty

        # ---- Pending purchase orders ----
        PurchaseLine = env["purchase.order.line"].sudo()
        pending_purchases = PurchaseLine.search([
            ("order_id.state", "in", ["draft", "sent"]),
            ("product_id", "in", product_ids),
        ])
        pending_map = {}
        for pl in pending_purchases:
            pid = pl.product_id.id
            pending_map[pid] = pending_map.get(pid, 0.0) + pl.product_qty

        # ---- Approved purchase orders (ordered/confirmed) ----
        ordered_purchases = PurchaseLine.search([
            ("order_id.state", "in", ["purchase"]),
            ("product_id", "in", product_ids),
        ])
        ordered_map = {}
        for pl in ordered_purchases:
            pid = pl.product_id.id
            ordered_map[pid] = ordered_map.get(pid, 0.0) + pl.product_qty

        # ---- Build replenishment rows ----
        rows = []
        for p in all_products:
            pid = p.id
            onhand = int(stock_map.get(pid, 0))
            forecast_30d = int(demand_30d_map.get(pid, 0))
            if forecast_30d == 0:
                continue  # skip products with no demand

            shortage = max(0, forecast_30d - onhand)
            suggest_qty = shortage

            # Determine state based on purchase orders
            if ordered_map.get(pid):
                state = "ordered"
            elif pending_map.get(pid):
                state = "approved"
            elif shortage > 0:
                state = "proposed"
            else:
                continue  # skip products with sufficient stock and no activity

            # Reason
            if shortage > forecast_30d * 0.5:
                reason = _("Critical shortage – stock covers less than 50%% of 30-day forecast")
            elif shortage > 0:
                reason = _("Stock below safety level – reorder required before stockout")
            else:
                reason = _("Stable demand, inventory within safety threshold")

            rows.append({
                "key": f"r_{pid}",
                "sku_name": p.display_name,
                "category": p.categ_id.display_name if p.categ_id else _("Other"),
                "warehouse": wh_name,
                "onhand": onhand,
                "forecast_30d": forecast_30d,
                "suggest_qty": suggest_qty,
                "state": state,
                "reason": reason,
                "season": _("Current Period"),
            })

        # Sort: proposed first, then approved, then ordered
        state_order = {"proposed": 0, "approved": 1, "ordered": 2}
        rows.sort(key=lambda r: (state_order.get(r["state"], 9), -r["forecast_30d"]))
        rows = rows[:20]

        # ---- KPIs ----
        total = len(rows)
        risk_skus = len([r for r in rows if (r["forecast_30d"] - r["onhand"]) > r["forecast_30d"] * 0.5])
        pending = len([r for r in rows if r["state"] == "proposed"])
        ordered = len([r for r in rows if r["state"] == "ordered"])

        # Sparkline (weekly demand trend – last 5 weeks)
        spark_values = []
        for i in range(4, -1, -1):
            w_start = today - timedelta(days=(i + 1) * 7)
            w_end = today - timedelta(days=i * 7)
            w_lines = SaleLine.search([
                ("order_id.state", "in", ["sale", "done"]),
                ("order_id.date_order", ">=", str(w_start)),
                ("order_id.date_order", "<", str(w_end)),
            ])
            spark_values.append(int(sum(w_lines.mapped("product_uom_qty"))))

        spark = {
            "labels": ["", "", "", "", ""],
            "values": spark_values,
        }

        # ---- Detail panel ----
        selected_key = filters.get("selected_key")
        if selected_key:
            selected = next((r for r in rows if r["key"] == selected_key), rows[0] if rows else None)
        else:
            selected = rows[0] if rows else None

        detail = {}
        if selected:
            detail = {
                "title": selected["sku_name"],
                "category": selected["category"],
                "season": selected["season"],
                "warehouse": selected["warehouse"],
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
                "delta_vs_last_week": f"+{pending}",
                "risk_skus": risk_skus,
                "risk_hint": _("Expected to run out within 30 days"),
                "pending": pending,
                "pending_hint": _("Needs approval today"),
                "ordered": ordered,
                "ordered_hint": _("Updated today"),
            },
            "spark": spark,
            "rows": rows,
            "detail": detail,
            "last_update": fields.Datetime.now(),
        }

    def _empty_payload(self):
        return {
            "filters_echo": {},
            "kpis": {
                "total_suggestions": 0,
                "delta_vs_last_week": "+0",
                "risk_skus": 0,
                "risk_hint": "",
                "pending": 0,
                "pending_hint": "",
                "ordered": 0,
                "ordered_hint": "",
            },
            "spark": {"labels": [], "values": []},
            "rows": [],
            "detail": {},
            "last_update": fields.Datetime.now(),
        }
