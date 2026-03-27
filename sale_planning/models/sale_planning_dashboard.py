# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class SalePlanningDashboard(models.AbstractModel):
    _name = "sale.planning.dashboard"
    _description = "Demand & Supply Planning Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)
        
        # --- Date Range Handling ---
        time_range = filters.get("time_range", "this_month")
        if time_range == "today":
            start_date = today
            end_date = today
        elif time_range == "this_week":
            start_date = today - timedelta(days=today.weekday())
            end_date = today + timedelta(days=6 - today.weekday())
        elif time_range == "this_month":
            start_date = first_day_month
            # end of month
            next_month = today.replace(day=28) + timedelta(days=4)
            end_date = next_month - timedelta(days=next_month.day)
        else:
            start_date = first_day_month
            end_date = today

        # ---- Master Data for Filters ----
        warehouses_objs = env["stock.warehouse"].sudo().search(
            ['|', ('name', 'ilike', 'AN PHU THINH'), ('name', 'ilike', 'TRUNG TAM')]
        )
        allowed_wh_ids = warehouses_objs.ids
        warehouses = [
            {"id": w.id, "name": w.name.replace('KHO ', '').strip()}
            for w in warehouses_objs
        ]
        
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # ---- Filter Processing ----
        wh_id = self._safe_int(filters.get("warehouse_id"))
        wh = env["stock.warehouse"].sudo().browse(wh_id) if wh_id else False

        # ---- Products (storable, active) ----
        Product = env["product.product"].sudo()
        
        # ---- Forecast Demand Handling ----
        forecast_id = self._safe_int(filters.get("forecast_id"))
        forecast_map = {}
        all_products = Product.browse([])

        if not forecast_id:
            # Fallback: Find latest forecast record
            f_domain = []
            if wh:
                f_domain.append(("warehouse_id", "=", wh.id))
            LatestForecast = env["demand.forecast"].sudo().search(f_domain, limit=1, order="date_from desc, id desc")
            if LatestForecast:
                forecast_id = LatestForecast.id

        if forecast_id:
            Forecast = env["demand.forecast"].sudo().browse(int(forecast_id))
            if Forecast.exists():
                flines = Forecast.line_ids
                # Sum up forecast quantities per product
                for fl in flines:
                    pid = fl.product_id.id
                    forecast_map[pid] = forecast_map.get(pid, 0.0) + (fl.forecast_qty or 0.0)
                
                # Fetch products directly from forecast lines
                all_products = flines.mapped("product_id").filtered(lambda p: p.active)
        
        if not all_products:
            # Fallback: Traditional storable products + historical demand logic
            domain = [("active", "=", True)]
            if "is_storable" in Product._fields:
                domain.append("|")
                domain.append(("is_storable", "=", True))
                domain.append(("type", "=", "product"))
            else:
                domain.append(("type", "=", "product"))
                
            if filters.get("category_id"):
                domain.append(("categ_id", "child_of", int(filters["category_id"])))
            
            all_products = Product.search(domain, limit=200)
            
            # Populate forecast_map with historical average demand (as a baseline)
            # Fetch it now since it's used as fallback
            thirty_days_ago = today - timedelta(days=30)
            SaleLine = env["sale.order.line"].sudo()
            sale_domain = [
                ("order_id.state", "in", ["sale", "done"]),
                ("order_id.date_order", ">=", str(thirty_days_ago)),
                ("product_id", "in", all_products.ids),
            ]
            if wh:
                sale_domain.append(("order_id.warehouse_id", "=", wh.id))
            
            s_lines = SaleLine.search(sale_domain)
            d_hist_map = {}
            for sl in s_lines:
                pid = sl.product_id.id
                d_hist_map[pid] = d_hist_map.get(pid, 0.0) + sl.product_uom_qty

            for p in all_products:
                if p.id in d_hist_map:
                    forecast_map[p.id] = d_hist_map[p.id]

        if not all_products:
            return {
                "kpis": {
                    "total_supply_need": 0,
                    "purchase_plan_qty": 0,
                    "risk_sku_count": 0,
                    "waiting_orders": 0,
                    "growth_percent": 0,
                    "last_update": fields.Datetime.to_string(fields.Datetime.now()),
                },
                "main_chart": {}, 
                "rev_by_category": [], 
                "rev_spark": {},
                "inventory_forecast": None, 
                "order_suggestions": [],
                "warehouses": warehouses, 
                "categories": categories,
            }

        # ---- Real stock quantities ----
        StockQuant = env["stock.quant"].sudo()
        product_ids = all_products.ids
        quant_domain = [
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
        ]
        if wh:
            quant_domain.append(("location_id", "child_of", wh.view_location_id.id))
        else:
            # All allowed warehouses
            view_locations = warehouses_objs.mapped('view_location_id').ids
            if view_locations:
                quant_domain.append(("location_id", "child_of", view_locations))
        
        quants = StockQuant.search(quant_domain)
        stock_map = {}
        for q in quants:
            stock_map[q.product_id.id] = stock_map.get(q.product_id.id, 0.0) + q.quantity

        # ---- Real sale demand (filtered by date) ----
        SaleLine = env["sale.order.line"].sudo()
        sale_domain = [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", str(start_date)),
            ("order_id.date_order", "<=", str(end_date)),
            ("product_id", "in", product_ids),
        ]
        if "warehouse_id" in env["sale.order"]._fields:
            if wh:
                sale_domain.append(("order_id.warehouse_id", "=", wh.id))
            else:
                sale_domain.append(("order_id.warehouse_id", "in", allowed_wh_ids))
        
        sale_lines = SaleLine.search(sale_domain)
        demand_map = {}
        for sl in sale_lines:
            pid = sl.product_id.id
            demand_map[pid] = demand_map.get(pid, 0.0) + sl.product_uom_qty

        # ---- Real purchase orders ----
        PurchaseLine = env["purchase.order.line"].sudo()
        purchase_domain = [
            ("order_id.state", "in", ["purchase", "done", "draft"]),
            ("order_id.date_order", ">=", str(start_date)),
            ("order_id.date_order", "<=", str(end_date)),
            ("product_id", "in", product_ids),
        ]
        purchase_lines = PurchaseLine.search(purchase_domain)
        purchase_map = {}
        for pl in purchase_lines:
            pid = pl.product_id.id
            purchase_map[pid] = purchase_map.get(pid, 0.0) + pl.product_qty

        # ---- Waiting purchase orders ----
        PurchaseOrder = env["purchase.order"].sudo()
        waiting_orders = PurchaseOrder.search_count([
            ("state", "in", ["draft", "sent"]),
            ("company_id", "=", env.company.id),
        ])

        # ---- Build SKU rows (top 15) ----
        demand_total = 0
        purchase_plan_total = 0
        risk_sku = 0
        # ---- Dashboard Stats ----
        sku_rows = []
        demand_total = 0.0
        purchase_plan_total = 0.0
        risk_sku = 0

        # Build data rows
        for p in all_products:
            onhand_qty = stock_map.get(p.id, 0.0)
            forecast_qty = forecast_map.get(p.id, 0.0)
            # Threshold from reordering rules
            threshold = 0.0
            orderpoint = env["stock.warehouse.orderpoint"].sudo().search([
                ("product_id", "=", p.id),
                ("warehouse_id", "in", allowed_wh_ids),
                ("active", "=", True)
            ], limit=1)
            if orderpoint:
                threshold = orderpoint.product_min_qty
            
            # Simple demand = Forecast
            demand = forecast_qty
            # Shortage calculation
            shortage = max(0.0, (threshold + demand) - onhand_qty)
            
            # If we select a forecast, show everything in it even if 0 shortage
            # If not using forecast, skip empty/boring rows
            if not forecast_id and demand <= 0 and shortage <= 0 and onhand_qty <= 0:
                continue
            
            demand_total += demand
            purchase_plan_total += shortage # Suggested purchase

            sku_rows.append({
                "key": f"p_{p.id}",
                "stt": len(sku_rows) + 1,
                "sku": p.display_name,
                "category": p.categ_id.name if p.categ_id else _("Uncategorized"),
                "demand": int(round(demand)),
                "onhand": int(round(onhand_qty)),
                "plan_buy": int(round(shortage)),
                "status": _("Out of Stock Risk") if (onhand_qty < threshold or shortage > 0) else _("Stable"),
            })

        kpis = {
            "total_supply_need": demand_total,
            "purchase_plan_qty": purchase_plan_total,
            "risk_sku_count": len([r for r in sku_rows if r["plan_buy"] > 0]),
            "waiting_orders": len(PurchaseOrder.search([("state", "in", ["draft", "sent"])])),
            "growth_percent": 0,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }

        # Charts
        labels = [d.strftime("%b %d") for d in [start_date + timedelta(days=i) for i in range(7)]]
        main_chart = {
            "labels": labels,
            "demand": [int(demand_total * f) for f in [0.7, 0.8, 1.0, 0.9, 1.1, 1.0, 1.2]],
            "plan": [int(purchase_plan_total * f) for f in [0.6, 0.8, 0.9, 0.9, 1.0, 0.9, 1.1]],
            "risk": [int(demand_total * 0.05) for _ in range(len(labels))],
        }

        # Revenue by Category
        rev_rows = []
        palette = ["#10b981", "#60a5fa", "#fb923c"]
        for i, cat in enumerate(categories[:3]):
            rev_rows.append({
                "key": f"cat_{cat['id']}",
                "name": cat["name"],
                "value": round(demand_total * (0.5 - i * 0.1), 1),
                "color": palette[i % len(palette)],
            })

        order_suggestions = sku_rows

        return {
            "kpis": kpis,
            "main_chart": main_chart,
            "rev_by_category": rev_rows,
            "rev_spark": {
                "labels": [r["name"] for r in rev_rows],
                "values": [r["value"] for r in rev_rows],
                "colors": [r["color"] for r in rev_rows],
            },
            "inventory_forecast": None, # Will be computed in JS if needed
            "order_suggestions": order_suggestions,
            "warehouses": warehouses,
            "categories": categories,
        }

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return False

    @api.model
    def create_supply_plan(self, **kwargs):
        """
        Create a draft Purchase Order as a supply plan from the dashboard suggestions.
        Returns the new purchase order ID and name.
        """
        env = self.env
        try:
            PurchaseOrder = env["purchase.order"].sudo()
            PurchaseLine = env["purchase.order.line"].sudo()
            Product = env["product.product"].sudo()

            # Get order suggestions data
            data = self.get_dashboard_data()
            suggestions = data.get("order_suggestions") or []

            if not suggestions:
                return {"ok": False, "message": _("No supply suggestions available.")}

            # Find or use company default supplier
            partner = env["res.partner"].sudo().search(
                [("supplier_rank", ">", 0)], limit=1
            )
            if not partner:
                partner = env.company.partner_id

            # Create purchase order
            po = PurchaseOrder.create({
                "partner_id": partner.id,
                "date_order": fields.Datetime.now(),
                "note": _("Auto-generated supply plan from Sale Planning dashboard"),
                "company_id": env.company.id,
            })

            # Add lines for each suggested SKU
            for row in suggestions:
                if not row.get("plan_buy") or row["plan_buy"] <= 0:
                    continue
                # Find product by name (best effort)
                products = Product.search([("display_name", "=", row["sku"])], limit=1)
                if not products:
                    products = Product.search([("name", "ilike", row["sku"])], limit=1)
                if not products:
                    continue

                # Get seller info for price
                seller = products.seller_ids[:1]
                price = seller.price if seller else products.standard_price or 0.0

                PurchaseLine.create({
                    "order_id": po.id,
                    "product_id": products.id,
                    "product_qty": row["plan_buy"],
                    "price_unit": price,
                    "name": products.display_name,
                    "product_uom_id": getattr(products, 'uom_po_id', products.uom_id).id or products.uom_id.id,
                    "date_planned": fields.Datetime.now(),
                })

            return {
                "ok": True,
                "id": po.id,
                "name": po.name,
                "message": _("Supply plan '%s' created successfully.") % po.name,
            }
        except Exception as e:
            _logger.error("create_supply_plan error: %s", e)
            return {"ok": False, "message": str(e)}

    @api.model
    def create_purchase_recommendation(self, **kwargs):
        """
        Create a draft Purchase Order as a purchase recommendation
        for only risk/shortage SKUs.
        Returns the new purchase order ID and name.
        """
        env = self.env
        try:
            PurchaseOrder = env["purchase.order"].sudo()
            PurchaseLine = env["purchase.order.line"].sudo()
            Product = env["product.product"].sudo()

            data = self.get_dashboard_data()
            suggestions = data.get("order_suggestions") or []

            # Only include risk SKUs
            risk_rows = [r for r in suggestions if r.get("status") == _("Out of Stock Risk")]
            if not risk_rows:
                risk_rows = suggestions  # fallback to all if no risk

            if not risk_rows:
                return {"ok": False, "message": _("No purchase recommendations available.")}

            partner = env["res.partner"].sudo().search(
                [("supplier_rank", ">", 0)], limit=1
            )
            if not partner:
                partner = env.company.partner_id

            po = PurchaseOrder.create({
                "partner_id": partner.id,
                "date_order": fields.Datetime.now(),
                "note": _("Purchase recommendation – out of stock risk SKUs"),
                "company_id": env.company.id,
            })

            for row in risk_rows:
                qty = row.get("plan_buy") or max(0, row.get("demand", 0) - row.get("onhand", 0))
                if qty <= 0:
                    continue

                products = Product.search([("display_name", "=", row["sku"])], limit=1)
                if not products:
                    products = Product.search([("name", "ilike", row["sku"])], limit=1)
                if not products:
                    continue

                seller = products.seller_ids[:1]
                price = seller.price if seller else products.standard_price or 0.0

                PurchaseLine.create({
                    "order_id": po.id,
                    "product_id": products.id,
                    "product_qty": qty,
                    "price_unit": price,
                    "name": products.display_name,
                    "product_uom_id": getattr(products, 'uom_po_id', products.uom_id).id or products.uom_id.id,
                    "date_planned": fields.Datetime.now(),
                })

            return {
                "ok": True,
                "id": po.id,
                "name": po.name,
                "message": _("Purchase recommendation '%s' created successfully.") % po.name,
            }
        except Exception as e:
            _logger.error("create_purchase_recommendation error: %s", e)
            return {"ok": False, "message": str(e)}

    def _empty_payload(self):
        return {
            "kpis": {
                "total_supply_need": 0,
                "purchase_plan_qty": 0,
                "risk_sku_count": 0,
                "waiting_orders": 0,
                "growth_percent": 0,
                "last_update": "",
            },
            "main_chart": {"labels": [], "demand": [], "plan": [], "risk": []},
            "rev_by_category": [],
            "rev_spark": {"labels": [], "values": [], "colors": []},
            "inventory_forecast": None,
            "order_suggestions": [],
        }
