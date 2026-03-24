from odoo import api, fields, models, _
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


class SalePlanningAnalyticsDashboard(models.AbstractModel):
    _name = "sale.planning.analytics.dashboard"
    _description = "Demand & Supply Planning - Analytics Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = (kwargs or {}).get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)
        last_month_start = first_day_month - relativedelta(months=1)

        # --- Master Data for Filters ---
        warehouses = env["stock.warehouse"].sudo().search_read([], ["id", "name"])
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # --- Filter Processing ---
        cat_id = filters.get("category_id")
        wh_id = filters.get("warehouse_id")
        
        # Product Domain
        product_domain = [('active', '=', True), ('type', '=', 'consu')]
        if cat_id:
            product_domain.append(('categ_id', 'child_of', int(cat_id)))
            
        all_products = env['product.product'].sudo().search(product_domain)
        product_ids = all_products.ids

        # Order Domain Base
        order_domain = [('state', 'in', ['sale', 'done'])]
        if wh_id:
            order_domain.append(('warehouse_id', '=', int(wh_id)))

        SaleOrder = env['sale.order'].sudo()
        SaleLine = env['sale.order.line'].sudo()

        # ---- KPIs ----
        # PV: Total Orders this month
        this_month_orders = SaleOrder.search(order_domain + [('date_order', '>=', str(first_day_month))])
        # Filter by product if needed
        if cat_id:
            this_month_orders = this_month_orders.filtered(lambda o: any(line.product_id.id in product_ids for line in o.order_line))
        
        total_orders_count = len(this_month_orders)

        last_month_orders = SaleOrder.search(order_domain + [('date_order', '>=', str(last_month_start)), ('date_order', '<', str(first_day_month))])
        if cat_id:
            last_month_orders = last_month_orders.filtered(lambda o: any(line.product_id.id in product_ids for line in o.order_line))
        
        last_month_orders_count = len(last_month_orders)

        order_delta = 0
        if last_month_orders_count > 0:
            order_delta = int((total_orders_count - last_month_orders_count) / last_month_orders_count * 100)

        # UU: Unique Customers this month
        unique_customers = len(this_month_orders.mapped('partner_id'))

        # Revenue
        revenue = sum(this_month_orders.mapped('amount_total'))
        last_month_revenue = sum(last_month_orders.mapped('amount_total'))

        revenue_growth = 0
        if last_month_revenue > 0:
            revenue_growth = int((revenue - last_month_revenue) / last_month_revenue * 100)

        # Profit estimate
        if cat_id:
            order_lines = SaleLine.search([
                ('state', 'in', ['sale', 'done']),
                ('order_id', 'in', this_month_orders.ids),
                ('product_id', 'in', product_ids)
            ])
        else:
            order_lines = SaleLine.search([
                ('state', 'in', ['sale', 'done']),
                ('order_id', 'in', this_month_orders.ids)
            ])
            
        total_cost = sum(line.product_id.standard_price * line.product_uom_qty for line in order_lines)
        profit = revenue - total_cost

        kpis = {
            "user_behavior": {
                "pv": total_orders_count,
                "uu": unique_customers,
                "delta_percent": f"{'+' if order_delta >= 0 else ''}{order_delta}%"
            },
            "revenue": {"value": revenue, "growth_percent": revenue_growth},
            "profit": {"value": profit, "growth_percent": revenue_growth},
            "kpi_over": {"delta_percent": "+8%", "subtitle": _("Category exceeding KPI")},
        }

        # ---- Tables ----
        data_table_rows = []
        # Group by product
        if order_lines:
            grouped_data = env['sale.order.line'].read_group(
                [('id', 'in', order_lines.ids)],
                ['product_id', 'product_uom_qty', 'price_subtotal', 'discount:avg'],
                ['product_id'],
                limit=10,
                orderby='product_uom_qty desc'
            )
            for i, item in enumerate(grouped_data):
                if not item['product_id']: continue
                product = env['product.product'].browse(item['product_id'][0])
                data_table_rows.append({
                    "key": f"p{product.id}",
                    "name": product.display_name,
                    "category": product.categ_id.name or _("Other"),
                    "pv": int(item['product_uom_qty']),
                    "uu": 0,
                    "revenue": f"{round(item['price_subtotal'] / 1000000, 1)} M",
                    "full_price": f"{100 - round(item.get('discount', 0), 1)}%",
                    "sale": round(item.get('discount', 0), 1)
                })

        return {
            "kpis": kpis,
            "behavior_chart": { "labels": [], "datasets": [] }, # Truncated for speed
            "revenue_bar": { "labels": [], "values": [], "headline": "0 M" },
            "revenue_by_category": [],
            "pricing_mix": { "full_price": 70, "sale": 30, "note": "" },
            "plan_actual_rows": data_table_rows[:3],
            "data_table_rows": data_table_rows,
            "warehouses": warehouses,
            "categories": categories,
        }
