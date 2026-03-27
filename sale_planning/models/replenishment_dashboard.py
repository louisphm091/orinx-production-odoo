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
        warehouses_objs = env["stock.warehouse"].sudo().search(
            ['|', ('name', 'ilike', 'AN PHU THINH'), ('name', 'ilike', 'TRUNG TAM')]
        )
        allowed_wh_ids = warehouses_objs.ids
        warehouses = [
            {"id": w.id, "name": w.name.replace('KHO ', '').strip()}
            for w in warehouses_objs
        ]
            
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # --- Filter Processing ---
        wh_id = self._safe_int(filters.get("warehouse_id"))
        cat_id = self._safe_int(filters.get("category_id"))

        selected_config = False

        # ---- Products (storable, active) ----
        Product = env["product.product"].sudo()
        product_domain = [
            ("active", "=", True),
            ("type", "=", "consu"),
            ("is_storable", "=", True),
        ]
        if "available_in_pos" in Product._fields:
            product_domain.append(("available_in_pos", "=", True))
        
        if cat_id:
            product_domain.append(("categ_id", "child_of", int(cat_id)))
            
        all_products = Product.search(product_domain)

        if not all_products:
            return self._empty_payload(store_options=[], warehouses=warehouses, categories=categories)

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
        elif selected_config:
            location = selected_config.picking_type_id.default_location_src_id if selected_config.picking_type_id else False
            wh_name = selected_config.name
        else:
            # All allowed warehouses
            view_locations = warehouses_objs.mapped('view_location_id').ids
            if view_locations:
                location = view_locations # This will be used in 'child_of' domain
            wh_name = _("All Branches")

        quant_domain = [
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
        ]
        if location:
            if isinstance(location, list):
                quant_domain.append(("location_id", "child_of", location))
            else:
                quant_domain.append(("location_id", "child_of", location.id))
        quants = StockQuant.search(quant_domain)
        stock_map = {}
        for q in quants:
            stock_map[q.product_id.id] = stock_map.get(q.product_id.id, 0.0) + q.quantity

        # ---- 30-day sales history ----
        SaleLine = env["sale.order.line"].sudo()
        thirty_days_ago = today - timedelta(days=30)
        # ---- Demand Forecast (Integrate from Forecast module) ----
        forecast_id = self._safe_int(filters.get("forecast_id"))
        forecast_map = {}
        if forecast_id:
            ForecastLine = env["demand.forecast.line"].sudo()
            flines = ForecastLine.search([
                ("forecast_id", "=", forecast_id),
                ("product_id", "in", product_ids)
            ])
            for fl in flines:
                forecast_map[fl.product_id.id] = forecast_map.get(fl.product_id.id, 0.0) + (fl.forecast_qty or 0.0)

        # ---- Sale History (Past 30d) ----
        thirty_days_ago = today - timedelta(days=30)
        SaleLine = env["sale.order.line"].sudo()
        
        sale_history_domain = [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", str(thirty_days_ago)),
            ("product_id", "in", product_ids),
        ]
        if "warehouse_id" in env["sale.order"]._fields:
            if wh:
                sale_history_domain.append(("order_id.warehouse_id", "=", wh.id))
            elif selected_config:
                sale_history_domain.append(("order_id.warehouse_id", "=", selected_config.swift_warehouse_id.id))
            else:
                sale_history_domain.append(("order_id.warehouse_id", "in", allowed_wh_ids))
        
        sale_lines = SaleLine.search(sale_history_domain)
        demand_30d_map = {}
        for sl in sale_lines:
            pid = sl.product_id.id
            demand_30d_map[pid] = demand_30d_map.get(pid, 0.0) + sl.product_uom_qty

        # ---- Thresholds (Reordering Rules) ----
        # Use Odoo standard stock.warehouse.orderpoint
        threshold_map = {}
        orderpoints = env["stock.warehouse.orderpoint"].sudo().search([
            ("product_id", "in", product_ids),
            ("warehouse_id", "in", allowed_wh_ids),
            ("active", "=", True),
        ])
        for op in orderpoints:
            pid = op.product_id.id
            # If multiple rules exist (for different locations), we use the one with the highest product_min_qty
            threshold_map[pid] = max(threshold_map.get(pid, 0.0), op.product_min_qty)

        threshold_default = 0.0 # Default to 0 if no rule is found

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
            forecast_qty = forecast_map.get(pid, 0.0)
            # Shortage = Threshold + Forecast - Onhand
            # This follows the user logic: "bring all forecasted values here to create supply plan"
            shortage_val = (threshold + forecast_qty) - onhand_qty
            shortage = max(0.0, shortage_val)
            suggest_qty = int(round(shortage))

            if shortage <= 0 and not ordered_map.get(pid) and not pending_map.get(pid):
                continue

            if ordered_map.get(pid):
                state = "ordered"
            elif pending_map.get(pid):
                state = "approved"
            elif shortage > 0:
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
            "store_options": [],
            "selected_store": False,
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

    @api.model
    def action_batch_manufacturing(self, items, filters=None):
        """
        Create Manufacturing Orders (mrp.production) in bulk.
        items: list of {'product_id': int, 'qty': float, 'warehouse_id': int}
        """
        env = self.env
        try:
            Production = env["mrp.production"].sudo()
            Bom = env["mrp.bom"].sudo()
            ProductObj = env["product.product"].sudo()
            Warehouse = env["stock.warehouse"].sudo()

            created_count = 0
            errors = []
            mo_ids = []

            for item in items:
                pid = self._safe_int(item.get("product_id"))
                qty = float(item.get("qty") or 0)
                wh_id = self._safe_int(item.get("warehouse_id"))

                if not pid or qty <= 0:
                    continue

                Product = ProductObj.browse(pid)
                if not Product.exists():
                    errors.append(_("Product ID %s not found.") % pid)
                    continue

                # Find BOM
                wh = Warehouse.browse(wh_id) if wh_id else Warehouse.search([], limit=1)
                bom = Bom._bom_find(product=Product, warehouse_id=wh.id if wh else False)
                if not bom:
                    # Fallback to any bom for this product
                    bom = Bom.search([
                        '|',
                        ("product_id", "=", Product.id),
                        "&",
                        ("product_tmpl_id", "=", Product.product_tmpl_id.id),
                        ("product_id", "=", False)
                    ], limit=1)

                if not bom:
                    errors.append(_("No BoM found for product %s") % Product.display_name)
                    continue

                # Picking type (Manufacturing)
                picking_type = env["stock.picking.type"].sudo().search([
                    ("code", "=", "mrp_operation"),
                    ("warehouse_id", "=", wh.id)
                ], limit=1)
                if not picking_type:
                    # Fallback
                    picking_type = env["stock.picking.type"].sudo().search([("code", "=", "mrp_operation")], limit=1)

                mo_vals = {
                    "product_id": Product.id,
                    "product_qty": qty,
                    "product_uom_id": Product.uom_id.id,
                    "bom_id": bom.id,
                    "date_planned_start": fields.Datetime.now(),
                    "user_id": env.user.id,
                    "origin": _("Bulk Plan: Replenishment Dashboard"),
                }
                if picking_type:
                    mo_vals["picking_type_id"] = picking_type.id
                
                mo = Production.create(mo_vals)
                mo_ids.append(mo.id)
                created_count += 1

            message = _("Successfully created %s Manufacturing Orders.") % created_count
            if errors:
                message += " " + _("Skipped: %s") % "; ".join(errors[:5])

            return {
                "ok": True,
                "message": message,
                "mo_ids": mo_ids,
                "created_count": created_count
            }
        except Exception as e:
            _logger.error("action_batch_manufacturing error: %s", e)
            return {"ok": False, "message": str(e)}

    def _empty_payload(self, store_options=None, warehouses=None, categories=None):
        return {
            "filters_echo": {},
            "store_options": store_options or [],
            "selected_store": False,
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

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return False
