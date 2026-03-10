from odoo import api, fields, models, _
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


class SaleScheduleDashboard(models.AbstractModel):
    _name = "sale.schedule.dashboard"
    _description = "Sale Schedule Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)

        # --- KPIs ---
        SaleLine = env['sale.order.line']
        this_month_rev = sum(SaleLine.search([
            ('state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', str(first_day_month))
        ]).mapped('price_subtotal'))

        last_month_start = first_day_month - relativedelta(months=1)
        last_month_rev = sum(SaleLine.search([
            ('state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', str(last_month_start)),
            ('order_id.date_order', '<', str(first_day_month))
        ]).mapped('price_subtotal')) or 1

        rev_delta = int((this_month_rev - last_month_rev) / last_month_rev * 100)

        # Top products for timeline
        top_lines = SaleLine.read_group(
            [('state', 'in', ['sale', 'done']), ('order_id.date_order', '>=', str(today - timedelta(days=30)))],
            ['product_id', 'price_subtotal'],
            ['product_id'],
            limit=5
        )
        product_ids = [l['product_id'][0] for l in top_lines if l['product_id']]
        products = env['product.product'].browse(product_ids)

        kpis = {
            "wave_count": len(products),
            "main_sku": products[0].display_name if products else "-",
            "revenue": this_month_rev,
            "revenue_delta": rev_delta,
            "risk_sku_count": 0, # To be calculated
            "need_review_count": 0,
        }

        # --- timeline header (last 3, next 5 months) ---
        cols = []
        for i in range(-3, 6):
            m_date = first_day_month + relativedelta(months=i)
            cols.append(m_date.strftime("%b"))

        # timeline rows
        rows = []
        risk_sku_count = 0
        for i, p in enumerate(products):
            p_onhand = sum(env['stock.quant'].search([('product_id', '=', p.id), ('location_id.usage', '=', 'internal')]).mapped('quantity'))
            p_last_rev = sum(SaleLine.search([('product_id', '=', p.id), ('state', 'in', ['sale', 'done']), ('order_id.date_order', '>=', str(last_month_start)), ('order_id.date_order', '<', str(first_day_month))]).mapped('price_subtotal'))

            p_target = p_last_rev * 1.1 if p_last_rev else 10_000_000

            # Risk if stock is low vs sales
            is_risk = p_onhand < 10 # Dummy threshold
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

        # --- selected schedule detail (first one) ---
        selected = {}
        inventory_link = {}
        performance = {}
        if products:
            p = products[0]
            p_onhand = sum(env['stock.quant'].search([('product_id', '=', p.id), ('location_id.usage', '=', 'internal')]).mapped('quantity'))

            selected = {
                "sku": p.display_name,
                "campaign": _("Current Plan"),
                "sku_code": p.default_code or "-",
                "date_from": first_day_month.strftime("%d/%m"),
                "date_to": (first_day_month + relativedelta(months=1) - timedelta(days=1)).strftime("%d/%m"),
                "target_revenue": rows[0]["target"] if rows else 0,
                "current_stock": int(p_onhand),
                "status": _("Active"),
            }

            inventory_link = {
                "onhand": int(p_onhand),
                "daily_sell": int(sum(SaleLine.search([('product_id', '=', p.id), ('state', 'in', ['sale', 'done']), ('order_id.date_order', '>=', str(today - timedelta(days=30)))]).mapped('product_uom_qty')) / 30) or 1,
                "out_of_stock_date": (today + timedelta(days=30)).strftime("%d %b"),
                "out_of_stock_in_days": 30,
            }

            performance = {
                "title": p.display_name,
                "progress_percent": 85, # Dummy
                "days": (today - first_day_month).days,
                "spark": [12, 18, 20, 28, 35, 40, 48, 55],
            }

        # --- risk alerts list ---
        risk_alerts = []
        for r in rows:
            if r["bars"][0]["color"] == "yellow":
                risk_alerts.append({
                    "key": f"a{r['key']}",
                    "sku": r["sku"],
                    "message": _("Low stock alert for current planning period"),
                    "trend": "down"
                })

        return {
            "kpis": kpis,
            "timeline": {
                "cols": cols,
                "rows": rows,
                "view_mode": filters.get("view_mode") or "timeline",
            },
            "selected": selected,
            "inventory_link": inventory_link,
            "performance": performance,
            "risk_alerts": risk_alerts,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
        }

