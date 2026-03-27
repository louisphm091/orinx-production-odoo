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

        # --- Master Data for Filters ---
        pos_configs = env["pos.config"].sudo().search([
            ("active", "=", True),
            ("company_id", "=", env.company.id),
            ("swift_warehouse_id", "!=", False),
            '|',
            ("swift_warehouse_id.name", "ilike", "AN PHU THINH"),
            ("swift_warehouse_id.name", "ilike", "TRUNG TAM")
        ])
        warehouses_data = []
        for config in pos_configs:
            name = config.name.replace('KHO ', '').strip()
            warehouses_data.append({
                "id": config.id, 
                "name": name, 
                "warehouse_id": config.swift_warehouse_id.id
            })
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        # --- Filter Processing ---
        branch_id = self._safe_int(filters.get("warehouse_id"))
        cat_id = self._safe_int(filters.get("category_id"))

        selected_config = pos_configs.filtered(lambda c: c.id == branch_id)[:1] if branch_id else False
        target_warehouse_id = selected_config.swift_warehouse_id.id if selected_config and selected_config.swift_warehouse_id else False
        
        # Determine allowed warehouse IDs
        allowed_warehouse_ids = [config.swift_warehouse_id.id for config in pos_configs if config.swift_warehouse_id]

        # ---- Top products to track ----
        Product = env['product.product'].sudo()
        SaleLine = env['sale.order.line'].sudo()
        
        product_domain = [('active', '=', True), ('type', '=', 'consu')]
        if cat_id:
            product_domain.append(('categ_id', 'child_of', cat_id))
            
        all_products = Product.search(product_domain)
        product_ids = all_products.ids

        # Common Line Domain
        line_domain = [
            ('state', 'in', ['sale', 'done']),
            ('product_id', 'in', product_ids),
        ]
        if 'warehouse_id' in env['sale.order']._fields:
            if target_warehouse_id:
                line_domain.append(('order_id.warehouse_id', '=', target_warehouse_id))
            else:
                line_domain.append(('order_id.warehouse_id', 'in', allowed_warehouse_ids))

        top_lines = SaleLine._read_group(
            line_domain + [('order_id.date_order', '>=', str(today - timedelta(days=60)))],
            ['product_id'],
            ['product_uom_qty:sum'],
            limit=10,
            order='product_uom_qty:sum desc'
        )

        final_product_pids = [l[0].id for l in top_lines if l[0]]
        products = Product.browse(final_product_pids)

        # planned vs actual (planned = last month, actual = this month)
        overall = []
        for p in products:
            # Query this month
            this_month_qty = sum(SaleLine.search(line_domain + [
                ('product_id', '=', p.id),
                ('order_id.date_order', '>=', str(first_day_month))
            ]).mapped('product_uom_qty'))

            # Query last month (as 'Plan')
            last_month_qty = sum(SaleLine.search(line_domain + [
                ('product_id', '=', p.id),
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

        progress_percent = int(total_actual / total_planned * 100) or 0
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
            this_month_lines = SaleLine.search(line_domain + [
                ('product_id', '=', p.id),
                ('order_id.date_order', '>=', str(first_day_month))
            ])
            rev = sum(this_month_lines.mapped('price_subtotal'))
            qty = sum(this_month_lines.mapped('product_uom_qty'))

            last_month_qty = sum(SaleLine.search(line_domain + [
                ('product_id', '=', p.id),
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
            week_qty = sum(SaleLine.search(line_domain + [
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
            "warehouses": warehouses_data,
            "categories": categories,
            "last_update": fields.Datetime.now(),
        }

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return False
