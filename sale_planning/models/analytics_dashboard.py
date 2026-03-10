from odoo import api, fields, models, _
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


class SalePlanningAnalyticsDashboard(models.AbstractModel):
    _name = "sale.planning.analytics.dashboard"
    _description = "Sale Planning - Analytics Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = (kwargs or {}).get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)
        last_month_start = first_day_month - relativedelta(months=1)

        # ---- KPIs ----
        # PV: Total Orders this month
        total_orders = env['sale.order'].search_count([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', str(first_day_month))
        ])
        last_month_orders = env['sale.order'].search_count([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', str(last_month_start)),
            ('date_order', '<', str(first_day_month))
        ])

        order_delta = 0
        if last_month_orders > 0:
            order_delta = int((total_orders - last_month_orders) / last_month_orders * 100)

        # UU: Unique Customers this month
        unique_customers = len(env['sale.order'].read_group([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', str(first_day_month))
        ], ['partner_id'], ['partner_id']))

        # Revenue
        revenue_data = env['sale.order'].read_group([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', str(first_day_month))
        ], ['amount_total'], [])
        revenue = revenue_data[0]['amount_total'] if revenue_data and revenue_data[0]['amount_total'] else 0

        last_month_revenue_data = env['sale.order'].read_group([
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', str(last_month_start)),
            ('date_order', '<', str(first_day_month))
        ], ['amount_total'], [])
        last_month_revenue = last_month_revenue_data[0]['amount_total'] if last_month_revenue_data and last_month_revenue_data[0]['amount_total'] else 0

        revenue_growth = 0
        if last_month_revenue > 0:
            revenue_growth = int((revenue - last_month_revenue) / last_month_revenue * 100)

        # Profit estimate
        order_lines = env['sale.order.line'].search([
            ('state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', str(first_day_month))
        ])
        total_cost = sum(line.product_id.standard_price * line.product_uom_qty for line in order_lines)
        profit = revenue - total_cost

        kpis = {
            "user_behavior": {
                "pv": total_orders,
                "uu": unique_customers,
                "delta_percent": f"{'+' if order_delta >= 0 else ''}{order_delta}%"
            },
            "revenue": {"value": revenue, "growth_percent": revenue_growth},
            "profit": {"value": profit, "growth_percent": revenue_growth},
            "kpi_over": {"delta_percent": "+8%", "subtitle": _("Category exceeding KPI")},
        }

        # ---- Line chart: Orders/Customers by month (last 6 months) ----
        months_labels = []
        pv_series = []
        uu_series = []
        for i in range(5, -1, -1):
            m_start = first_day_month - relativedelta(months=i)
            m_end = m_start + relativedelta(months=1) - timedelta(days=1)
            months_labels.append(m_start.strftime("%b"))

            m_orders = env['sale.order'].search_count([
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', str(m_start)),
                ('date_order', '<=', str(m_end))
            ])
            pv_series.append(m_orders)

            m_customers = len(env['sale.order'].read_group([
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', str(m_start)),
                ('date_order', '<=', str(m_end))
            ], ['partner_id'], ['partner_id']))
            uu_series.append(m_customers)

        behavior_chart = {
            "labels": months_labels,
            "datasets": [
                {"label": _("Orders"), "data": pv_series},
                {"label": _("Customers"), "data": uu_series},
            ],
        }

        # ---- Revenue by category ----
        cat_revenue_data = env['sale.order.line'].read_group(
            [('state', 'in', ['sale', 'done']), ('order_id.date_order', '>=', str(first_day_month))],
            ['price_subtotal', 'product_id', 'product_uom_qty', 'discount:avg'],
            ['product_id']
        )

        cat_map = {}
        for item in cat_revenue_data:
            if not item['product_id']:
                continue
            product = env['product.product'].browse(item['product_id'][0])
            cat_name = product.categ_id.name or _("Other")
            cat_map[cat_name] = cat_map.get(cat_name, 0) + item['price_subtotal']

        top_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)[:3]
        palette = ["rgba(16,185,129,0.9)", "rgba(59,130,246,0.85)", "rgba(245,158,11,0.85)"]
        revenue_by_category = []
        for i, (name, val) in enumerate(top_cats):
            revenue_by_category.append({
                "key": f"c{i+1}",
                "name": name,
                "value": round(val / 1_000_000, 1),
                "color": palette[i % len(palette)]
            })

        # Bar chart: revenue (last 3 months)
        rev_bar_labels = months_labels[-3:]
        rev_bar_values = []
        for i in range(2, -1, -1):
            m_start = first_day_month - relativedelta(months=i)
            m_end = m_start + relativedelta(months=1) - timedelta(days=1)
            m_rev_data = env['sale.order'].read_group([
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', str(m_start)),
                ('date_order', '<=', str(m_end))
            ], ['amount_total'], [])
            m_rev = m_rev_data[0]['amount_total'] if m_rev_data and m_rev_data[0]['amount_total'] else 0
            rev_bar_values.append(int(m_rev / 1_000_000))

        revenue_bar = {
            "labels": rev_bar_labels,
            "values": rev_bar_values,
            "colors": ["rgba(16,185,129,0.35)", "rgba(16,185,129,0.6)", "rgba(16,185,129,0.9)"],
            "headline": f"{rev_bar_values[-1]} M" if rev_bar_values else "0 M",
        }

        # Pricing mix: Full Price vs Discounted
        discount_lines = env['sale.order.line'].search_count([
            ('state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', str(first_day_month)),
            ('discount', '>', 0)
        ])
        total_lines = len(order_lines) or 1
        sale_rate = int(discount_lines / total_lines * 100)

        pricing_mix = {
            "full_price": 100 - sale_rate,
            "sale": sale_rate,
            "note": _("Discount rate: %s%% of total sale lines") % sale_rate
        }

        # ---- Tables ----
        # product_stats from read_group above
        plan_actual_rows = []
        data_table_rows = []
        for i, item in enumerate(cat_revenue_data[:10]):
            if not item['product_id']:
                continue
            product = env['product.product'].browse(item['product_id'][0])
            row = {
                "key": f"p{product.id}",
                "name": product.display_name,
                "category": product.categ_id.name or _("Other"),
                "pv": int(item['product_uom_qty']),
                "uu": 0, # N/A
                "revenue": f"{round(item['price_subtotal'] / 1000000, 1)} M",
                "full_price": f"{100 - round(item.get('discount', 0), 1)}%",
                "sale": round(item.get('discount', 0), 1)
            }
            data_table_rows.append(row)
            if i < 3:
                plan_actual_rows.append(row)


        return {
            "kpis": kpis,
            "behavior_chart": behavior_chart,
            "revenue_bar": revenue_bar,
            "revenue_by_category": revenue_by_category,
            "pricing_mix": pricing_mix,
            "plan_actual_rows": plan_actual_rows,
            "data_table_rows": data_table_rows,
        }

