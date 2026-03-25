# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class MrpProductionPlanDashboard(models.AbstractModel):
    _name = "mrp.production.plan.dashboard"
    _description = "Master Production Schedule Dashboard Service"

    @api.model
    def get_dashboard_data(self, **kwargs):
        filters = kwargs.get("filters") or {}
        env = self.env
        
        # 1. Timeline: 6 months from today
        today = date.today()
        first_day = today.replace(day=1)
        months = []
        for i in range(12):
            d = first_day + relativedelta(months=i)
            months.append({
                "label": f"thg {d.month} {d.year}",
                "date_start": d,
                "date_end": d + relativedelta(months=1) - timedelta(days=1)
            })
            
        # 2. Products (from config line)
        plan_id = filters.get("plan_id")
        Line = env["production.plan.line"].sudo()
        if plan_id:
            domain = [("plan_id", "=", int(plan_id))]
            config_lines = Line.search(domain)
            products = config_lines.mapped("product_id")
        else:
            # Auto-detect most recent plan (fallback when planId wasn't passed from frontend)
            latest_plan = env["production.plan"].search([], order="id desc", limit=1)
            if latest_plan:
                config_lines = Line.search([("plan_id", "=", latest_plan.id)])
                products = config_lines.mapped("product_id")
            else:
                products = env["product.product"].browse()
        
        # 3. Build data rows
        rows = []
        for p in products:
            actual_stock = p.qty_available
            product_row = {
                "id": p.id,
                "name": p.display_name,
                "actual_stock": actual_stock,
                "values": [actual_stock if i == 0 else 0 for i in range(len(months))]
            }
            
            # Sub-rows data
            config_line = config_lines.filtered(lambda l: l.product_id == p)
            is_indirect = config_line[0].is_indirect_demand if config_line else False
            
            forecast_row = {"label": _("Nhu cầu được dự báo"), "icon": "-", "allow_edit": True, "values": []}
            indirect_row = {"label": _("Dự báo nhu cầu gián tiếp"), "icon": "-", "allow_edit": False, "values": []} if is_indirect else None
            replenish_row = {"label": _("Bổ sung hàng: Đơn hàng"), "icon": "+", "allow_edit": True, "values": []}
            stock_row = {"label": _("Tồn kho được dự báo"), "icon": "=", "allow_edit": False, "values": []}
            
            curr_stock = actual_stock
            
            for i, m in enumerate(months):
                f_qty = 0
                i_qty = 0
                r_qty = 0
                
                forecast_row["values"].append(f_qty)
                if indirect_row:
                    indirect_row["values"].append(i_qty)
                replenish_row["values"].append(r_qty)
                
                stock_row["values"].append(curr_stock)
                curr_stock = max(0, curr_stock + r_qty - f_qty - i_qty)
            
            sub_rows = [forecast_row]
            if indirect_row:
                sub_rows.append(indirect_row)
            sub_rows += [replenish_row, stock_row]
            
            product_row["sub_rows"] = sub_rows
            rows.append(product_row)
            
        return {
            "months": [m["label"] for m in months],
            "rows": rows,
            "filters": filters
        }
