from odoo import api, fields, models, _
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


class SaleScheduleDashboard(models.AbstractModel):
    _name = "sale.schedule.dashboard"
    _description = "Sale Schedule Dashboard Service"

    @api.model
    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)

        # --- Master Data for Filters ---
        warehouses = env["stock.warehouse"].sudo().search_read([], ["id", "name"])
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # --- Warehouse Handling ---
        Warehouse = env["stock.warehouse"].sudo()
        wh = None
        if filters.get("warehouse_id"):
            wh = Warehouse.browse(int(filters["warehouse_id"])).exists()
        if not wh:
            wh = Warehouse.search([("company_id", "=", env.company.id)], limit=1)

        # --- KPIs ---
        SaleLine = env['sale.order.line'].sudo()
        
        # Product Domain
        product_domain = [('active', '=', True), ('type', 'in', ['product', 'consu'])]
        if filters.get("category_id"):
            product_domain.append(('categ_id', 'child_of', int(filters["category_id"])))
        
        all_products = env['product.product'].sudo().search(product_domain)
        product_ids = all_products.ids

        sale_domain = [
            ('state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', str(first_day_month)),
            ('product_id', 'in', product_ids)
        ]
        this_month_rev = sum(SaleLine.search(sale_domain).mapped('price_subtotal'))

        last_month_start = first_day_month - relativedelta(months=1)
        last_month_domain = [
            ('state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', str(last_month_start)),
            ('order_id.date_order', '<', str(first_day_month)),
            ('product_id', 'in', product_ids)
        ]
        last_month_rev = sum(SaleLine.search(last_month_domain).mapped('price_subtotal')) or 1

        rev_delta = int((this_month_rev - last_month_rev) / last_month_rev * 100)

        # Top products for timeline (filtered)
        top_lines = SaleLine.read_group(
            [('state', 'in', ['sale', 'done']), 
             ('order_id.date_order', '>=', str(today - timedelta(days=30))),
             ('product_id', 'in', product_ids)],
            ['product_id', 'price_subtotal'],
            ['product_id'],
            limit=5
        )
        products_pids = [l['product_id'][0] for l in top_lines if l['product_id']]
        products = env['product.product'].browse(products_pids).sudo()

        kpis = {
            "wave_count": len(products),
            "main_sku": products[0].display_name if products else "-",
            "revenue": this_month_rev,
            "revenue_delta": rev_delta,
            "risk_sku_count": 0,
            "need_review_count": 0,
        }

        # --- timeline header ---
        cols = []
        for i in range(-3, 6):
            m_date = first_day_month + relativedelta(months=i)
            cols.append(m_date.strftime("%b"))

        # timeline rows
        rows = []
        risk_sku_count = 0
        for i, p in enumerate(products):
            q_domain = [('product_id', '=', p.id), ('location_id.usage', '=', 'internal')]
            if wh:
                q_domain.append(('location_id', 'child_of', wh.view_location_id.id))
            p_onhand = sum(env['stock.quant'].search(q_domain).mapped('quantity'))
            
            p_last_rev = sum(SaleLine.search([('product_id', '=', p.id), ('state', 'in', ['sale', 'done']), ('order_id.date_order', '>=', str(last_month_start)), ('order_id.date_order', '<', str(first_day_month))]).mapped('price_subtotal'))
            p_target = p_last_rev * 1.1 if p_last_rev else 10_000_000

            is_risk = p_onhand < 10
            if is_risk: risk_sku_count += 1

            rows.append({
                "key": f"r{p.id}",
                "sku": p.display_name,
                "campaign": _("Monthly Plan") if i % 2 == 0 else _("Seasonal Sales"),
                "stock": int(p_onhand),
                "target": p_target,
                "bars": [{"label": _("Current Period"), "start": 3, "span": 2, "color": "green" if not is_risk else "yellow"}],
            })

        kpis["risk_sku_count"] = risk_sku_count

        return {
            "kpis": kpis,
            "timeline": {
                "cols": cols,
                "rows": rows,
                "view_mode": filters.get("view_mode") or "timeline",
            },
            "selected": {}, # Truncated for brevity as requested by user's focus on filters
            "inventory_link": {},
            "performance": {},
            "risk_alerts": [],
            "warehouses": warehouses,
            "categories": categories,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }

