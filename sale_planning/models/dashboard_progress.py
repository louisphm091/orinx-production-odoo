from odoo import api, fields, models, _
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta


class SalePlanningDashboardProgressService(models.AbstractModel):
    _name = "sale.planning.dashboard.progress"
    _description = "Demand & Supply Planning - Dashboard Progress Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {}

        env = self.env
        today = date.today()
        first_day_month = today.replace(day=1)
        prev_month_start = first_day_month - relativedelta(months=1)
        prev_month_end = first_day_month - timedelta(days=1)

        # ---- Top products to track ----
        # Get top 10 products by qty in the last 60 days
        SaleLine = env['sale.order.line']
        top_lines = SaleLine.read_group(
            [('state', 'in', ['sale', 'done']), ('order_id.date_order', '>=', str(today - timedelta(days=60)))],
            ['product_id', 'product_uom_qty'],
            ['product_id'],
            limit=10
        )

        product_ids = [l['product_id'][0] for l in top_lines if l['product_id']]
        products = env['product.product'].browse(product_ids)

        # planned vs actual (planned = last month, actual = this month)
        overall = []
        for p in products:
            # Query this month
            this_month_qty = sum(SaleLine.search([
                ('product_id', '=', p.id),
                ('state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', str(first_day_month))
            ]).mapped('product_uom_qty'))

            # Query last month (as 'Plan')
            last_month_qty = sum(SaleLine.search([
                ('product_id', '=', p.id),
                ('state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', str(prev_month_start)),
                ('order_id.date_order', '<=', str(prev_month_end))
            ]).mapped('product_uom_qty'))

            # Fallback if no last month data, use a default target
            planned = last_month_qty or 100
            actual = this_month_qty

            overall.append({
                "name": p.display_name,
                "planned": int(planned),
                "actual": int(actual),
            })

        total_planned = sum(x["planned"] for x in overall) or 1
        total_actual = sum(x["actual"] for x in overall)

        progress_percent = int(round(total_actual / total_planned * 100))
        late_skus = [x for x in overall if x["actual"] < x["planned"] * 0.8]
        ontrack_skus = [x for x in overall if x["actual"] >= x["planned"] * 0.95]

        # Alerts / risks
        risks = []
        for ls in late_skus[:2]:
            gap = int((1 - ls["actual"] / (ls["planned"] or 1)) * 100)
            risks.append({
                "name": ls["name"],
                "hint": _("%s%% behind monthly target") % gap,
                "level": "high" if gap > 30 else "medium"
            })

        # Mini cards
        sku_cards = []
        for i, p in enumerate(products[:3]):
            this_month_lines = SaleLine.search([
                ('product_id', '=', p.id),
                ('state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', str(first_day_month))
            ])
            rev = sum(this_month_lines.mapped('price_subtotal'))
            qty = sum(this_month_lines.mapped('product_uom_qty'))

            last_month_qty = sum(SaleLine.search([
                ('product_id', '=', p.id),
                ('state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', str(prev_month_start)),
                ('order_id.date_order', '<=', str(prev_month_end))
            ]).mapped('product_uom_qty')) or 1

            percent = int(qty / last_month_qty * 100)

            sku_cards.append({
                "key": f"c{p.id}",
                "name": p.display_name,
                "status": _("On track") if percent >= 95 else (_("Behind schedule") if percent < 80 else _("Progressing")),
                "status_type": "ok" if percent >= 95 else ("bad" if percent < 80 else "warn"),
                "percent": percent,
                "revenue": rev,
                "tags": [_("Top Seller")] if i == 0 else []
            })

        # Execution history (last 6 weeks)
        hist_labels = []
        hist_values = []
        for i in range(5, -1, -1):
            w_start = today - timedelta(weeks=i+1)
            w_end = today - timedelta(weeks=i)
            hist_labels.append(_("Week %s") % (6-i))

            # Total qty across all top products for this week
            week_qty = sum(SaleLine.search([
                ('product_id', 'in', product_ids),
                ('state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', str(w_start)),
                ('order_id.date_order', '<', str(w_end))
            ]).mapped('product_uom_qty')) or 0

            # Target for week (avg of total_planned/4)
            week_target = (total_planned / 4) or 1
            hist_values.append(int(week_qty / week_target * 100))

        note = _("Progress is tracked against previous month's performance as a baseline target.")

        return {
            "filters_echo": filters,
            "kpis": {
                "progress_percent": progress_percent,
                "late_sku_count": len(late_skus),
                "late_sku_names": ", ".join([x["name"] for x in late_skus[:2]]) or "-",
                "ontrack_sku_count": len(ontrack_skus),
                "ontrack_sku_names": ", ".join([x["name"] for x in ontrack_skus[:2]]) or "-",
                "critical_count": len(risks),
                "critical_hint": _("%s issues identified") % len(risks),
            },
            "overall_chart": {
                "labels": [x["name"] for x in overall],
                "planned": [x["planned"] for x in overall],
                "actual": [x["actual"] for x in overall],
                "trend": [int(x["actual"] * 1.05) for x in overall], # Projection
            },
            "risks": risks,
            "sku_cards": sku_cards,
            "history": {
                "labels": hist_labels,
                "values": hist_values,
                "note": note,
            },
            "last_update": fields.Datetime.now(),
        }
