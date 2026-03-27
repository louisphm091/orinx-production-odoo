from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
        this_period_start = today - timedelta(days=29)
        previous_period_start = this_period_start - timedelta(days=30)

        pos_configs, branch_options, selected_config, warehouse, allowed_warehouse_ids = self._get_branch_context(filters)
        categories = env["product.category"].sudo().search_read([], ["id", "name"])

        product_domain = [
            ("active", "=", True),
            ("type", "=", "consu"),
            ("sale_ok", "=", True),
        ]
        category_id = self._safe_int(filters.get("category_id"))
        if category_id:
            product_domain.append(("categ_id", "child_of", category_id))

        Product = env["product.product"].sudo()
        products = Product.search(product_domain)
        if not products:
            return self._empty_payload(branch_options, categories, selected_config, filters)

        product_ids = products.ids
        sale_line_domain = [
            ("state", "in", ["sale", "done"]),
            ("product_id", "in", product_ids),
        ]
        if "warehouse_id" in env["sale.order"]._fields:
            if warehouse:
                sale_line_domain.append(("order_id.warehouse_id", "=", warehouse.id))
            else:
                sale_line_domain.append(("order_id.warehouse_id", "in", allowed_warehouse_ids))

        SaleLine = env["sale.order.line"].sudo()

        current_month_domain = sale_line_domain + [
            ("order_id.date_order", ">=", fields.Datetime.to_string(first_day_month)),
        ]
        previous_month_start = first_day_month - relativedelta(months=1)
        previous_month_domain = sale_line_domain + [
            ("order_id.date_order", ">=", fields.Datetime.to_string(previous_month_start)),
            ("order_id.date_order", "<", fields.Datetime.to_string(first_day_month)),
        ]

        current_month_revenue = sum(SaleLine.search(current_month_domain).mapped("price_subtotal"))
        previous_month_revenue = sum(SaleLine.search(previous_month_domain).mapped("price_subtotal"))
        revenue_delta = self._compute_delta(current_month_revenue, previous_month_revenue)

        current_period_lines = SaleLine.search(
            sale_line_domain + [("order_id.date_order", ">=", fields.Datetime.to_string(this_period_start))]
        )
        previous_period_lines = SaleLine.search(
            sale_line_domain
            + [
                ("order_id.date_order", ">=", fields.Datetime.to_string(previous_period_start)),
                ("order_id.date_order", "<", fields.Datetime.to_string(this_period_start)),
            ]
        )

        if not current_period_lines and not previous_period_lines:
            return self._empty_payload(branch_options, categories, selected_config, filters)

        metrics_map = self._collect_product_metrics(
            products,
            current_period_lines,
            previous_period_lines,
            warehouse,
            today,
        )

        rows = self._build_rows(metrics_map, today, filters)
        selected_key = filters.get("selected_key")
        selected_row = next((row for row in rows if row["key"] == selected_key), rows[0] if rows else None)
        selected_product = metrics_map.get(selected_row["product_id"]) if selected_row else None

        risk_rows = [row for row in rows if row["is_risk"] or row["needs_review"]]
        risk_alerts = [
            {
                "key": row["key"],
                "sku": row["sku"],
                "message": row["risk_message"],
                "trend": "up" if row["growth_percent"] >= 0 else "down",
            }
            for row in risk_rows[:4]
        ]

        kpis = {
            "wave_count": len(rows),
            "main_sku": rows[0]["sku"] if rows else "-",
            "revenue": current_month_revenue,
            "revenue_delta": revenue_delta,
            "risk_sku_count": len([row for row in rows if row["is_risk"]]),
            "need_review_count": len([row for row in rows if row["needs_review"]]),
        }

        return {
            "kpis": kpis,
            "timeline": {
                "cols": self._build_timeline_columns(today),
                "rows": rows,
                "view_mode": filters.get("view_mode") or "timeline",
            },
            "selected": self._build_selected_payload(selected_row, selected_product),
            "inventory_link": self._build_inventory_payload(selected_product, today),
            "performance": self._build_performance_payload(selected_row, selected_product),
            "risk_alerts": risk_alerts,
            "warehouses": branch_options,
            "categories": categories,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
            "selected_branch": {
                "id": selected_config.id,
                "name": selected_config.name,
            }
            if selected_config
            else False,
        }

    @api.model
    def action_open_sale_orders(self, **kwargs):
        filters = kwargs.get("filters") or {}
        selected_key = kwargs.get("selected_key")
        _pos_configs, _branch_options, _selected_config, warehouse, allowed_warehouse_ids = self._get_branch_context(filters)
        product = self._get_selected_product(selected_key)

        domain = [("state", "in", ["sale", "done"])]
        if "warehouse_id" in self.env["sale.order"]._fields:
            if warehouse:
                domain.append(("warehouse_id", "=", warehouse.id))
            else:
                domain.append(("warehouse_id", "in", allowed_warehouse_ids))
        if product:
            domain.append(("order_line.product_id", "=", product.id))

        return {
            "type": "ir.actions.act_window",
            "name": _("Sales Orders"),
            "res_model": "sale.order",
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "domain": domain,
        }

    @api.model
    def action_open_product(self, **kwargs):
        product = self._get_selected_product(kwargs.get("selected_key"))
        if not product:
            raise UserError(_("Please select a product from the schedule first."))
        return {
            "type": "ir.actions.act_window",
            "name": product.display_name,
            "res_model": "product.product",
            "res_id": product.id,
            "views": [[False, "form"]],
            "target": "current",
        }

    @api.model
    def action_open_inventory(self, **kwargs):
        filters = kwargs.get("filters") or {}
        _pos_configs, _branch_options, _selected_config, warehouse, allowed_warehouse_ids = self._get_branch_context(filters)
        product = self._get_selected_product(kwargs.get("selected_key"))

        domain = [("location_id.usage", "=", "internal")]
        if product:
            domain.append(("product_id", "=", product.id))
        if warehouse:
            if warehouse.view_location_id:
                domain.append(("location_id", "child_of", warehouse.view_location_id.id))
        else:
            # Filter by all allowed warehouses
            ws = self.env['stock.warehouse'].sudo().browse(allowed_warehouse_ids)
            loc_ids = ws.mapped('view_location_id').ids
            if loc_ids:
                domain.append(("location_id", "child_of", loc_ids))

        return {
            "type": "ir.actions.act_window",
            "name": _("Inventory"),
            "res_model": "stock.quant",
            "views": [[False, "list"], [False, "form"]],
            "target": "current",
            "domain": domain,
        }

    def _get_branch_context(self, filters):
        env = self.env
        pos_configs = env["pos.config"].sudo().search(
            [
                ("active", "=", True),
                ("company_id", "=", env.company.id),
                ("swift_warehouse_id", "!=", False),
                '|',
                ("swift_warehouse_id.name", "ilike", "AN PHU THINH"),
                ("swift_warehouse_id.name", "ilike", "TRUNG TAM")
            ]
        )
        branch_options = []
        for config in pos_configs:
            name = config.name.replace('KHO ', '').strip()
            branch_options.append({
                "id": config.id,
                "name": name,
                "warehouse_id": config.swift_warehouse_id.id,
            })

        selected_config = False
        branch_id = self._safe_int(filters.get("warehouse_id"))
        selected_config = False
        if branch_id:
            selected_config = pos_configs.filtered(lambda config: config.id == branch_id)[:1]

        warehouse = selected_config.swift_warehouse_id if selected_config and selected_config.swift_warehouse_id else False
        
        # Determine allowed warehouse IDs
        allowed_warehouse_ids = [config.swift_warehouse_id.id for config in pos_configs if config.swift_warehouse_id]
        
        return pos_configs, branch_options, selected_config, warehouse, allowed_warehouse_ids

    def _collect_product_metrics(self, products, current_lines, previous_lines, warehouse, today):
        env = self.env
        current_qty_map = {}
        current_rev_map = {}
        previous_qty_map = {}

        for line in current_lines:
            pid = line.product_id.id
            current_qty_map[pid] = current_qty_map.get(pid, 0.0) + line.product_uom_qty
            current_rev_map[pid] = current_rev_map.get(pid, 0.0) + line.price_subtotal

        for line in previous_lines:
            pid = line.product_id.id
            previous_qty_map[pid] = previous_qty_map.get(pid, 0.0) + line.product_uom_qty

        quant_domain = [
            ("product_id", "in", products.ids),
            ("location_id.usage", "=", "internal"),
        ]
        if warehouse and warehouse.view_location_id:
            quant_domain.append(("location_id", "child_of", warehouse.view_location_id.id))

        onhand_map = {}
        for quant in env["stock.quant"].sudo().search(quant_domain):
            onhand_map[quant.product_id.id] = onhand_map.get(quant.product_id.id, 0.0) + quant.quantity

        purchase_domain = [
            ("product_id", "in", products.ids),
            ("order_id.state", "in", ["draft", "sent", "to approve", "purchase"]),
        ]
        incoming_map = {}
        for line in env["purchase.order.line"].sudo().search(purchase_domain):
            incoming_map[line.product_id.id] = incoming_map.get(line.product_id.id, 0.0) + line.product_qty

        metrics_map = {}
        for product in products:
            current_qty = current_qty_map.get(product.id, 0.0)
            previous_qty = previous_qty_map.get(product.id, 0.0)
            onhand_qty = onhand_map.get(product.id, 0.0)
            daily_sell = round(current_qty / 30.0, 2) if current_qty else 0.0
            cover_days = round(onhand_qty / daily_sell, 1) if daily_sell else 999.0
            target_qty = max(current_qty * 1.15, 1.0)
            forecast_end = today + timedelta(days=int(cover_days)) if daily_sell else False

            metrics_map[product.id] = {
                "product": product,
                "current_qty": current_qty,
                "current_revenue": current_rev_map.get(product.id, 0.0),
                "previous_qty": previous_qty,
                "onhand_qty": onhand_qty,
                "daily_sell": daily_sell,
                "cover_days": cover_days,
                "incoming_qty": incoming_map.get(product.id, 0.0),
                "target_qty": target_qty,
                "growth_percent": self._compute_delta(current_qty, previous_qty),
                "forecast_end": forecast_end,
            }

        return metrics_map

    def _build_rows(self, metrics_map, today, filters):
        rows = []
        base_start = 3
        for index, metric in enumerate(
            sorted(
                metrics_map.values(),
                key=lambda item: (
                    -item["current_qty"],
                    -item["current_revenue"],
                    item["cover_days"],
                ),
            )[:8]
        ):
            product = metric["product"]
            is_risk = metric["cover_days"] <= 7 or metric["onhand_qty"] <= 0
            needs_review = not is_risk and (
                metric["cover_days"] <= 14 or abs(metric["growth_percent"]) >= 20
            )

            if is_risk:
                campaign = _("Restock Priority")
                bar_color = "yellow"
                risk_message = _("Projected stock-out within %s days") % max(int(metric["cover_days"]), 0)
            elif metric["growth_percent"] >= 15:
                campaign = _("Growth Campaign")
                bar_color = "green"
                risk_message = _("Demand increased %s%% over the previous period") % metric["growth_percent"]
            else:
                campaign = _("Steady Demand")
                bar_color = "green"
                risk_message = _("Monitor replenishment to keep sales stable")

            span = 2 if filters.get("view_mode") != "calendar" else 1
            if needs_review and not is_risk:
                review_bar = {
                    "label": _("Review"),
                    "start": min(base_start + span, 7),
                    "span": 1,
                    "color": "yellow",
                }
            else:
                review_bar = False

            row = {
                "key": f"r{product.id}",
                "product_id": product.id,
                "sku": product.display_name,
                "sku_code": product.default_code or product.barcode or f"SKU-{product.id}",
                "image_url": self._get_product_image_url(product),
                "campaign": campaign,
                "stock": int(round(metric["onhand_qty"])),
                "target": metric["target_qty"] * product.standard_price,
                "current_qty": int(round(metric["current_qty"])),
                "growth_percent": metric["growth_percent"],
                "date_from": fields.Date.to_string(today),
                "date_to": fields.Date.to_string(today + timedelta(days=14 if is_risk else 30)),
                "daily_sell": metric["daily_sell"],
                "cover_days": metric["cover_days"],
                "incoming_qty": int(round(metric["incoming_qty"])),
                "progress_percent": min(
                    int(round((metric["current_qty"] / metric["target_qty"]) * 100)),
                    999,
                ),
                "days_running": 30,
                "is_risk": is_risk,
                "needs_review": needs_review,
                "risk_message": risk_message,
                "bars": [
                    {
                        "label": _("Current Period"),
                        "start": base_start,
                        "span": span,
                        "color": bar_color,
                    }
                ],
            }
            if review_bar:
                row["bars"].append(review_bar)
            rows.append(row)

        return rows

    def _build_timeline_columns(self, today):
        first_day_month = today.replace(day=1)
        return [
            (first_day_month + relativedelta(months=offset)).strftime("%b")
            for offset in range(-3, 6)
        ]

    def _build_selected_payload(self, row, metric):
        if not row or not metric:
            return {
                "sku": "-",
                "campaign": "-",
                "sku_code": "-",
                "image_url": False,
                "date_from": "",
                "date_to": "",
                "badges": [],
            }

        badges = [
            {
                "label": _("In Branch"),
                "className": "bg-light text-dark",
            }
        ]
        badges.append(
            {
                "label": _("At Risk") if row["is_risk"] else _("On Plan"),
                "className": "bg-danger" if row["is_risk"] else "bg-success",
            }
        )
        if row["needs_review"]:
            badges.append(
                {
                    "label": _("Review"),
                    "className": "bg-warning text-dark",
                }
            )

        return {
            "sku": row["sku"],
            "campaign": row["campaign"],
            "sku_code": row["sku_code"],
            "image_url": row.get("image_url"),
            "date_from": row["date_from"],
            "date_to": row["date_to"],
            "badges": badges,
        }

    def _build_inventory_payload(self, metric, today):
        if not metric:
            return {
                "onhand": 0,
                "daily_sell": 0,
                "out_of_stock_date": "-",
                "out_of_stock_in_days": "-",
            }

        forecast_end = metric["forecast_end"]
        out_of_stock_days = max(int(metric["cover_days"]), 0) if metric["daily_sell"] else "-"
        return {
            "onhand": int(round(metric["onhand_qty"])),
            "daily_sell": metric["daily_sell"],
            "out_of_stock_date": fields.Date.to_string(forecast_end) if forecast_end else _("Stable"),
            "out_of_stock_in_days": out_of_stock_days,
        }

    def _build_performance_payload(self, row, metric):
        if not row or not metric:
            return {
                "title": _("No active schedule"),
                "image_url": False,
                "progress_percent": 0,
                "days": 0,
            }

        return {
            "title": row["sku"],
            "image_url": row.get("image_url"),
            "progress_percent": min(row["progress_percent"], 100),
            "days": row["days_running"],
        }

    def _empty_payload(self, branch_options, categories, selected_config, filters):
        return {
            "kpis": {
                "wave_count": 0,
                "main_sku": "-",
                "revenue": 0,
                "revenue_delta": 0,
                "risk_sku_count": 0,
                "need_review_count": 0,
            },
            "timeline": {
                "cols": self._build_timeline_columns(date.today()),
                "rows": [],
                "view_mode": filters.get("view_mode") or "timeline",
            },
            "selected": self._build_selected_payload(False, False),
            "inventory_link": self._build_inventory_payload(False, date.today()),
            "performance": self._build_performance_payload(False, False),
            "risk_alerts": [],
            "warehouses": branch_options,
            "categories": categories,
            "last_update": fields.Datetime.to_string(fields.Datetime.now()),
            "selected_branch": {
                "id": selected_config.id,
                "name": selected_config.name,
            }
            if selected_config
            else False,
        }

    def _get_selected_product(self, selected_key):
        product_id = self._safe_int((selected_key or "").replace("r", ""))
        if not product_id:
            return False
        return self.env["product.product"].sudo().browse(product_id).exists()

    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return False

    def _compute_delta(self, current_value, previous_value):
        if not previous_value:
            return 100 if current_value else 0
        return int(round(((current_value - previous_value) / previous_value) * 100))

    def _get_product_image_url(self, product):
        return f"/web/image/product.product/{product.id}/image_128"
