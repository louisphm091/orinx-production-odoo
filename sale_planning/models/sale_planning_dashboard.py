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
        last_month_start = (first_day_month - timedelta(days=1)).replace(day=1)

        # ---- Warehouse ----
        Warehouse = env["stock.warehouse"].sudo()
        wh = None
        if filters.get("warehouse_id"):
            wh = Warehouse.browse(int(filters["warehouse_id"])).exists()
        if not wh:
            wh = Warehouse.search([("company_id", "=", env.company.id)], limit=1)

        # ---- Products (storable, active) ----
        Product = env["product.product"].sudo()
        all_products = Product.search([
            ("active", "=", True),
            ("type", "in", ["product", "consu"]),
        ], limit=200)

        if not all_products:
            return self._empty_payload()

        # ---- Real stock quantities ----
        StockQuant = env["stock.quant"].sudo()
        product_ids = all_products.ids
        quants = StockQuant.search([
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
        ])
        stock_map = {}
        for q in quants:
            stock_map[q.product_id.id] = stock_map.get(q.product_id.id, 0.0) + q.quantity

        # ---- Real sale demand (this month) ----
        SaleLine = env["sale.order.line"].sudo()
        sale_domain = [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", str(first_day_month)),
            ("product_id", "in", product_ids),
        ]
        sale_lines = SaleLine.search(sale_domain)
        demand_map = {}
        for sl in sale_lines:
            pid = sl.product_id.id
            demand_map[pid] = demand_map.get(pid, 0.0) + sl.product_uom_qty

        # ---- Real purchase orders (planned purchases this month) ----
        PurchaseLine = env["purchase.order.line"].sudo()
        purchase_domain = [
            ("order_id.state", "in", ["purchase", "done", "draft"]),
            ("order_id.date_order", ">=", str(first_day_month)),
            ("product_id", "in", product_ids),
        ]
        purchase_lines = PurchaseLine.search(purchase_domain)
        purchase_map = {}
        for pl in purchase_lines:
            pid = pl.product_id.id
            purchase_map[pid] = purchase_map.get(pid, 0.0) + pl.product_qty

        # ---- Waiting purchase orders (state = draft/sent) ----
        PurchaseOrder = env["purchase.order"].sudo()
        waiting_orders = PurchaseOrder.search_count([
            ("state", "in", ["draft", "sent"]),
            ("company_id", "=", env.company.id),
        ])

        # ---- Build SKU rows (top 8 by demand) ----
        demand_total = 0
        purchase_plan_total = 0
        risk_sku = 0
        sku_rows = []

        # Sort by demand descending, take top 8 with demand > 0
        products_with_demand = sorted(
            [(p, demand_map.get(p.id, 0)) for p in all_products],
            key=lambda x: x[1], reverse=True
        )[:8]

        # If no demand data, fallback to stock-based top products
        if all(d == 0 for _, d in products_with_demand):
            products_with_demand = [
                (p, stock_map.get(p.id, 0) * 2) for p in all_products[:8]
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

        # ---- Growth vs last month ----
        last_month_domain = [
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", str(last_month_start)),
            ("order_id.date_order", "<", str(first_day_month)),
        ]
        last_month_lines = SaleLine.search(last_month_domain)
        last_month_demand = sum(last_month_lines.mapped("product_uom_qty"))
        if last_month_demand > 0 and demand_total > 0:
            growth_percent = int(round((demand_total - last_month_demand) / last_month_demand * 100))
        else:
            growth_percent = 0

        kpis = {
            "total_supply_need": demand_total,
            "purchase_plan_qty": purchase_plan_total,
            "risk_sku_count": risk_sku,
            "waiting_orders": waiting_orders,
            "growth_percent": growth_percent,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }

        # ---- Main chart: demand vs plan by last 6 months ----
        labels = []
        demand_series = []
        plan_series = []
        risk_band = []

        for i in range(5, -1, -1):
            month_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            label = month_start.strftime("%b")
            labels.append(label)

            m_sale_domain = [
                ("order_id.state", "in", ["sale", "done"]),
                ("order_id.date_order", ">=", str(month_start)),
                ("order_id.date_order", "<=", str(month_end)),
            ]
            m_lines = SaleLine.search(m_sale_domain)
            m_demand = int(sum(m_lines.mapped("product_uom_qty")))
            demand_series.append(m_demand)

            m_purchase_domain = [
                ("order_id.state", "in", ["purchase", "done", "draft"]),
                ("order_id.date_order", ">=", str(month_start)),
                ("order_id.date_order", "<=", str(month_end)),
            ]
            m_plines = PurchaseLine.search(m_purchase_domain)
            m_plan = int(sum(m_plines.mapped("product_qty")))
            plan_series.append(m_plan)

            # Risk = shortage estimate
            risk_band.append(max(0, int((m_demand - m_plan) * 0.1)))

        main_chart = {
            "labels": labels,
            "demand": demand_series,
            "plan": plan_series,
            "risk": risk_band,
        }

        # ---- Revenue by category (from real sales) ----
        cat_map = {}
        sale_lines_all = SaleLine.search([
            ("order_id.state", "in", ["sale", "done"]),
            ("order_id.date_order", ">=", str(first_day_month)),
        ])
        for sl in sale_lines_all:
            cat_name = sl.product_id.categ_id.name if sl.product_id.categ_id else _("Other")
            cat_map[cat_name] = cat_map.get(cat_name, 0) + sl.price_subtotal

        top_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)[:3]
        if not top_cats:
            # fallback to product categories with stock
            cat_stock = {}
            for p in all_products:
                cn = p.categ_id.name if p.categ_id else _("Other")
                cat_stock[cn] = cat_stock.get(cn, 0) + stock_map.get(p.id, 0)
            top_cats = sorted(cat_stock.items(), key=lambda x: x[1], reverse=True)[:3]

        palette = ["#10b981", "#60a5fa", "#fb923c"]
        rev_rows = []
        for i, (name, val) in enumerate(top_cats):
            rev_rows.append({
                "key": f"cat_{i}",
                "name": name,
                "value": round(val / 1_000_000, 1) if val >= 1_000_000 else round(val, 0),
                "color": palette[i % len(palette)],
            })

        rev_spark = {
            "labels": [r["name"] for r in rev_rows],
            "values": [r["value"] for r in rev_rows],
            "colors": [r["color"] for r in rev_rows],
        }

        # ---- Inventory forecast card (top risk SKU) ----
        risk_skus = [r for r in sku_rows if r["risk"]]
        focus = risk_skus[0] if risk_skus else (sku_rows[0] if sku_rows else None)
        inventory_forecast = None
        if focus:
            onhand_val = focus["onhand"]
            demand_val = focus["demand"] or 1
            daily_consumption = demand_val / 30 if demand_val > 0 else 1
            days_left = int(onhand_val / daily_consumption) if daily_consumption > 0 else 999

            inventory_forecast = {
                "labels": ["", "", "", "", ""],
                "onhand_series": [
                    max(0, int(onhand_val * f)) for f in [1.0, 0.75, 0.5, 0.25, 0.0]
                ],
                "trend_series": [
                    int(demand_val * f / 5) for f in [1, 2, 3, 4, 5]
                ],
                "hint": {
                    "sku_name": focus["sku_name"],
                    "days_left": days_left,
                    "message": _("Out of stock in %s days if current trend continues") % days_left,
                },
                "growth_note": _("Increase %s%% vs previous period") % abs(growth_percent),
            }

        # ---- Order suggestions table ----
        order_suggestions = []
        for i, r in enumerate(sku_rows[:5], start=1):
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
            "rev_spark": rev_spark,
            "inventory_forecast": inventory_forecast,
            "order_suggestions": order_suggestions,
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
                    "product_uom": products.uom_po_id.id or products.uom_id.id,
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
                    "product_uom": products.uom_po_id.id or products.uom_id.id,
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
