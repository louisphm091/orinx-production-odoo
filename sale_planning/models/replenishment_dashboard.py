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

        # --- Master Data for Filters ---
        warehouses = env["stock.warehouse"].sudo().search_read([], ["id", "name"])
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # --- Filter Processing ---
        wh_id = filters.get("warehouse_id")
        cat_id = filters.get("category_id")

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
        
        if cat_id:
            product_domain.append(("categ_id", "child_of", int(cat_id)))
            
        all_products = Product.search(product_domain)

        if not all_products:
            return self._empty_payload(selected_config=selected_config, store_options=store_options, warehouses=warehouses, categories=categories)

        product_ids = all_products.ids

        # ---- Real stock quantities ----
        StockQuant = env["stock.quant"].sudo()
        
        # Determine location from warehouse filter OR pos config
        Warehouse = env["stock.warehouse"].sudo()
        wh = None
        if wh_id:
            wh = Warehouse.browse(int(wh_id)).exists()
        
        location = False
        if wh:
            location = wh.view_location_id
            wh_name = wh.name
        else:
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

        # ---- 30-day sales history ----
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

        # ---- Thresholds ----
        threshold_default = 10.0
        threshold_map = {}
        active_alert_product_ids = set()
        if "swift.low.stock.alert" in env:
            Alert = env["swift.low.stock.alert"].sudo()
            active_alerts = Alert.search([("state", "=", "active")])
            for alert in active_alerts:
                threshold_map[alert.product_id.id] = alert.threshold or threshold_default
                active_alert_product_ids.add(alert.product_id.id)

        # ---- Purchase orders ----
        PurchaseLine = env["purchase.order.line"].sudo()
        pending_purchases = PurchaseLine.search([
            ("order_id.state", "in", ["draft", "sent"]),
            ("product_id", "in", product_ids),
        ])
        pending_map = {}
        for pl in pending_purchases:
            pid = pl.product_id.id
            pending_map[pid] = pending_map.get(pid, 0.0) + pl.product_qty

        ordered_purchases = PurchaseLine.search([
            ("order_id.state", "in", ["purchase"]),
            ("product_id", "in", product_ids),
        ])
        ordered_map = {}
        for pl in ordered_purchases:
            pid = pl.product_id.id
            ordered_map[pid] = ordered_map.get(pid, 0.0) + pl.product_qty

        # ---- Build rows ----
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
                reason = _("Out of stock - reorder immediately")
            elif shortage > 0:
                reason = _("Current stock below threshold (%s)") % threshold_qty
            else:
                reason = _("Low-stock alert active")

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

        rows.sort(key=lambda r: ({"proposed": 0, "approved": 1, "ordered": 2}.get(r["state"], 9), r["onhand"] - r["threshold"], -r["suggest_qty"]))
        
        # ---- Detail final ----
        selected_key = filters.get("selected_key")
        selected = next((r for r in rows if r["key"] == selected_key), rows[0] if rows else None)

        detail = {
            "product_id": selected["product_id"] if selected else False,
            "title": selected["sku_name"] if selected else "",
            "category": selected["category"] if selected else "",
            "season": selected["season"] if selected else "",
            "warehouse": selected["warehouse"] if selected else "",
            "image_url": selected["image_url"] if selected else "",
            "analysis": {
                "onhand": selected["onhand"] if selected else 0,
                "forecast_30d": selected["forecast_30d"] if selected else 0,
                "reorder_point": selected["threshold"] if selected else 0,
                "suggest_qty": selected["suggest_qty"] if selected else 0,
            },
            "reason": selected["reason"] if selected else "",
            "state": selected["state"] if selected else "",
        }

        return {
            "filters_echo": filters,
            "store_options": store_options,
            "selected_store": {"id": selected_config.id, "name": selected_config.name} if selected_config else False,
            "kpis": {
                "total_suggestions": len(rows),
                "delta_vs_last_week": f"+{len([r for r in rows if r['state'] == 'proposed'])}",
                "risk_skus": len([r for r in rows if r["onhand"] <= 0]),
                "pending": len([r for r in rows if r["state"] == "proposed"]),
                "ordered": len([r for r in rows if r["state"] == "ordered"]),
            },
            "rows": rows,
            "detail": detail,
            "warehouses": warehouses,
            "categories": categories,
            "last_update": fields.Datetime.now(),
        }

    @api.model
    def action_approve_replenishment(self, params=None, **kwargs):
        """
        Create a draft Purchase Order for the selected product and quantity.
        """
        env = self.env
        try:
            if not params:
                params = kwargs
            
            product_id = params.get("product_id")
            qty = params.get("qty")
            wh_id = params.get("warehouse_id")

            if not product_id or not qty:
                return {"ok": False, "message": _("Missing product or quantity.")}

            PurchaseOrder = env["purchase.order"].sudo()
            PurchaseLine = env["purchase.order.line"].sudo()
            Product = env["product.product"].sudo().browse(int(product_id))

            if not Product.exists():
                return {"ok": False, "message": _("Product not found.")}

            # Find supplier
            partner = Product.seller_ids[:1].partner_id
            if not partner:
                partner = env["res.partner"].sudo().search([("supplier_rank", ">", 0)], limit=1)
            if not partner:
                partner = env.company.partner_id

            # Create PO
            po_vals = {
                "partner_id": partner.id,
                "date_order": fields.Datetime.now(),
                "company_id": env.company.id,
                "origin": _("Manual Replenishment Dashboard"),
            }
            # Handle warehouse if provided
            if wh_id:
                wh = env["stock.warehouse"].sudo().browse(int(wh_id))
                if wh.exists():
                    picking_type = env["stock.picking.type"].sudo().search([
                        ("code", "=", "incoming"),
                        ("warehouse_id", "=", wh.id)
                    ], limit=1)
                    if picking_type:
                        po_vals["picking_type_id"] = picking_type.id

            po = PurchaseOrder.create(po_vals)

            # Create line
            seller = Product.seller_ids[:1]
            price = seller.price if seller else Product.standard_price or 0.0

            PurchaseLine.create({
                "order_id": po.id,
                "product_id": Product.id,
                "product_qty": float(qty or 0),
                "price_unit": price,
                "name": Product.display_name,
                "product_uom_id": getattr(Product, 'uom_po_id', Product.uom_id).id or Product.uom_id.id,
                "date_planned": fields.Datetime.now(),
            })

            return {
                "ok": True,
                "res_id": po.id,
                "name": po.name,
                "message": _("Draft PO %s created for %s") % (po.name, Product.display_name),
            }
        except Exception as e:
            _logger.error("action_approve_replenishment error: %s", e)
            return {"ok": False, "message": str(e)}

    def _empty_payload(self, selected_config=False, store_options=None, warehouses=None, categories=None):
        return {
            "filters_echo": {},
            "store_options": store_options or [],
            "selected_store": {"id": selected_config.id, "name": selected_config.name} if selected_config else False,
            "kpis": {
                "total_suggestions": 0,
                "delta_vs_last_week": "+0",
                "risk_skus": 0,
                "pending": 0,
                "ordered": 0,
            },
            "rows": [],
            "detail": {},
            "warehouses": warehouses or [],
            "categories": categories or [],
            "last_update": fields.Datetime.now(),
        }
