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
        warehouses = env["stock.warehouse"].sudo().search_read([], ["id", "name"])
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # ---- Filter Processing ----
        Warehouse = env["stock.warehouse"].sudo()
        wh = None
        if filters.get("warehouse_id"):
            wh = Warehouse.browse(int(filters["warehouse_id"])).exists()
        if not wh:
            wh = Warehouse.search([("company_id", "=", env.company.id)], limit=1)

        # ---- Products (storable, active) ----
        Product = env["product.product"].sudo()
        domain = [
            ("active", "=", True),
            ("type", "=", "consu"),
            ("is_storable", "=", True),
        ]
        if filters.get("category_id"):
            domain.append(("categ_id", "child_of", int(filters["category_id"])))
        if filters.get("product_id"):
            domain.append(("id", "=", int(filters["product_id"])))

        all_products = Product.search(domain, limit=200)

        if not all_products:
            return {
                "kpis": {}, "main_chart": {}, "rev_by_category": [], "rev_spark": {},
                "inventory_forecast": None, "order_suggestions": [],
                "warehouses": warehouses, "categories": categories,
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
        sku_rows = []

        products_with_demand = sorted(
            [(p, demand_map.get(p.id, 0)) for p in all_products],
            key=lambda x: x[1], reverse=True
        )[:15]

        if all(d == 0 for _, d in products_with_demand):
            products_with_demand = [
                (p, stock_map.get(p.id, 0) * 1.5) for p in all_products[:15]
            ]

        for p, demand in products_with_demand:
            demand = int(demand) if demand else 0
            onhand = int(stock_map.get(p.id, 0))
            plan_buy = int(purchase_map.get(p.id, 0))
            shortage = max(0, demand - (onhand + plan_buy))

            demand_total += demand
            purchase_plan_total += plan_buy
            if shortage > 0 and demand > 0:
                risk_sku += 1

            sku_rows.append({
                "key": f"sku_{p.id}",
                "sku_name": p.display_name,
                "category": p.categ_id.display_name if p.categ_id else _("Uncategorized"),
                "demand": demand,
                "onhand": onhand,
                "plan_buy": plan_buy,
                "risk": shortage > 0 and demand > 0,
            })

        # KPI construction simplified, growth vs last month always compared same span
        kpis = {
            "total_supply_need": demand_total,
            "purchase_plan_qty": purchase_plan_total,
            "risk_sku_count": risk_sku,
            "waiting_orders": waiting_orders,
            "growth_percent": 12, # Static for now or recalculate
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

        order_suggestions = []
        for i, r in enumerate(sku_rows[:8], start=1):
            order_suggestions.append({
                "stt": i,
                "sku": r["sku_name"],
                "category": r["category"],
                "demand": r["demand"],
                "onhand": r["onhand"],
                "plan_buy": r["plan_buy"],
                "status": _("Out of Stock Risk") if r["risk"] else _("Stable"),
            })

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
