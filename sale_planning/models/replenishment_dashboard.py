# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class SalePlanningReplenishmentDashboard(models.AbstractModel):
    _name = "sale.planning.replenishment"
    _description = "Demand & Supply Planning - Replenishment Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        PosConfig = env["pos.config"].sudo()
        configs = PosConfig.search([("active", "=", True)])
        selected_config = False
        if filters.get("pos_config_id"):
            selected_config = PosConfig.browse(int(filters["pos_config_id"])).exists()
        if not selected_config:
            selected_config = configs[:1]

        store_options = [{"id": config.id, "name": config.name} for config in configs]

        # ---- Products (storable, active) ----
        Product = env["product.product"].sudo()
        product_domain = [
            ("active", "=", True),
            ("type", "in", ["product", "consu"]),
        ]
        if "available_in_pos" in Product._fields:
            product_domain.append(("available_in_pos", "=", True))
        if selected_config and "swift_branch_config_ids" in env["product.template"]._fields:
            product_domain.append(("product_tmpl_id.swift_branch_config_ids", "in", selected_config.ids))
        if selected_config and getattr(selected_config, "limit_categories", False) and selected_config.iface_available_categ_ids:
            product_domain.append(("pos_categ_ids", "in", selected_config.iface_available_categ_ids.ids))

        all_products = Product.search(product_domain)

        if not all_products:
            return self._empty_payload(selected_config=selected_config, store_options=store_options)

        product_ids = all_products.ids

        # ---- Real stock quantities ----
        StockQuant = env["stock.quant"].sudo()
        location = selected_config.picking_type_id.default_location_src_id if selected_config and selected_config.picking_type_id else False
        wh_name = selected_config.name if selected_config else _("Main Warehouse")

        quant_domain = [
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
        ]
        if location:
            quant_domain.append(("location_id", "child_of", location.id))
        quants = StockQuant.search(quant_domain)
        stock_map = {}
        for q in quants:
            stock_map[q.product_id.id] = stock_map.get(q.product_id.id, 0.0) + q.quantity

        # ---- 30-day sales history (kept for context in the UI) ----
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

        # ---- Thresholds from Swift low-stock alerts when available ----
        threshold_default = 10.0
        threshold_map = {}
        active_alert_product_ids = set()
        if "swift.low.stock.alert" in env:
            Alert = env["swift.low.stock.alert"].sudo()
            active_alerts = Alert.search([("state", "=", "active")])
            for alert in active_alerts:
                threshold_map[alert.product_id.id] = alert.threshold or threshold_default
                active_alert_product_ids.add(alert.product_id.id)

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

        # ---- Build replenishment rows based on low-stock threshold ----
        rows = []
        for p in all_products:
            pid = p.id
            onhand_qty = stock_map.get(pid, 0.0)
            onhand = int(round(onhand_qty))
            threshold = threshold_map.get(pid, threshold_default)
            threshold_qty = int(round(threshold))
            shortage = max(0.0, threshold - onhand_qty)
            suggest_qty = int(round(shortage))

            if pid not in active_alert_product_ids and onhand_qty > threshold:
                continue

            # Determine state based on purchase orders
            if ordered_map.get(pid):
                state = "ordered"
            elif pending_map.get(pid):
                state = "approved"
            elif shortage > 0 or pid in active_alert_product_ids:
                state = "proposed"
            else:
                continue

            forecast_30d = int(demand_30d_map.get(pid, 0))
            if onhand_qty <= 0:
                reason = _("Out of stock - reorder immediately to reach threshold")
            elif shortage > 0:
                reason = _("Current stock is below threshold (%s)") % threshold_qty
            else:
                reason = _("Low-stock alert is active for threshold (%s)") % threshold_qty

            rows.append({
                "key": f"r_{pid}",
                "product_id": pid,
                "sku_name": p.display_name,
                "image_url": f"/web/image/product.product/{pid}/image_128",
                "category": p.categ_id.display_name if p.categ_id else _("Other"),
                "warehouse": wh_name,
                "onhand": onhand,
                "forecast_30d": forecast_30d,
                "threshold": threshold_qty,
                "suggest_qty": suggest_qty,
                "state": state,
                "reason": reason,
                "season": _("Current Period"),
            })

        # Sort: proposed first, then approved, then ordered
        state_order = {"proposed": 0, "approved": 1, "ordered": 2}
        rows.sort(key=lambda r: (state_order.get(r["state"], 9), r["onhand"] - r["threshold"], -r["suggest_qty"]))
        # ---- KPIs ----
        total = len(rows)
        risk_skus = len([r for r in rows if r["onhand"] <= 0])
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

        detail = {
            "product_id": False,
            "title": "",
            "category": "",
            "season": "",
            "warehouse": "",
            "image_url": "",
            "analysis": {
                "onhand": 0,
                "forecast_30d": 0,
                "reorder_point": 0,
                "suggest_qty": 0,
            },
            "reason": "",
            "state": "",
        }
        if selected:
            detail.update({
                "product_id": selected["product_id"],
                "title": selected["sku_name"],
                "category": selected["category"],
                "season": selected["season"],
                "warehouse": selected["warehouse"],
                "image_url": selected["image_url"],
                "analysis": {
                    "onhand": selected["onhand"],
                    "forecast_30d": selected["forecast_30d"],
                    "reorder_point": selected["threshold"],
                    "suggest_qty": selected["suggest_qty"],
                },
                "reason": selected["reason"],
                "state": selected["state"],
            })


        return {
            "filters_echo": filters,
            "store_options": store_options,
            "selected_store": {
                "id": selected_config.id,
                "name": selected_config.name,
            } if selected_config else False,
            "kpis": {
                "total_suggestions": total,
                "delta_vs_last_week": f"+{pending}",
                "risk_skus": risk_skus,
                "risk_hint": _("Already at or below the configured threshold"),
                "pending": pending,
                "pending_hint": _("Below threshold and waiting replenishment"),
                "ordered": ordered,
                "ordered_hint": _("Purchase orders already created"),
            },
            "spark": spark,
            "rows": rows,
            "detail": detail,
            "last_update": fields.Datetime.now(),
        }

    def _empty_payload(self, selected_config=False, store_options=None):
        return {
            "filters_echo": {},
            "store_options": store_options or [],
            "selected_store": {
                "id": selected_config.id,
                "name": selected_config.name,
            } if selected_config else False,
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
            "detail": {
                "product_id": False,
                "title": "",
                "category": "",
                "season": "",
                "warehouse": "",
                "image_url": "",
                "analysis": {
                    "onhand": 0,
                    "forecast_30d": 0,
                    "reorder_point": 0,
                    "suggest_qty": 0,
                },
                "reason": "",
                "state": "",
            },
            "last_update": fields.Datetime.now(),
        }
