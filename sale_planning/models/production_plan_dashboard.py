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
        
        # 1. Timeline: 12 months from current month
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
                plan_id = latest_plan.id
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
            
            # Fetch stored values from DB
            value_records = env["production.plan.value"].sudo().search([
                ("plan_id", "=", int(plan_id)),
                ("product_id", "=", p.id)
            ])
            value_map = {v.date_start: v for v in value_records}

            forecast_row = {"label": _("Nhu cầu được dự báo"), "icon": "-", "allow_edit": True, "values": []}
            indirect_row = {"label": _("Dự báo nhu cầu gián tiếp"), "icon": "-", "allow_edit": False, "values": []} if is_indirect else None
            replenish_row = {"label": _("Bổ sung hàng: Đơn hàng"), "icon": "+", "allow_edit": True, "values": []}
            stock_row = {"label": _("Tồn kho được dự báo"), "icon": "=", "allow_edit": False, "values": []}
            
            # Identify current month index for main row stock display
            current_date = fields.Date.today().replace(day=1)
            current_month_idx = -1
            for idx, m in enumerate(months):
                if m["date_start"] == current_date:
                    current_month_idx = idx
                    break
            
            if current_month_idx != -1:
                product_row["values"][current_month_idx] = actual_stock

            curr_stock = actual_stock
            
            for i, m in enumerate(months):
                v_rec = value_map.get(m["date_start"])
                f_qty = v_rec.forecast_qty if v_rec else 0
                r_qty = v_rec.replenish_qty if v_rec else 0
                i_qty = 0 # Future: implement indirect logic
                
                forecast_row["values"].append(f_qty)
                if indirect_row:
                    indirect_row["values"].append(i_qty)
                replenish_row["values"].append(r_qty)
                
                # 3. Forecasted Inventory: Calculation only for the first month
                if i == 0:
                    curr_stock = curr_stock + r_qty - f_qty - i_qty
                else:
                    curr_stock = 0
                stock_row["values"].append(curr_stock)
            
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

    @api.model
    def save_cell_value(self, **kwargs):
        plan_id = kwargs.get("plan_id")
        product_id = kwargs.get("product_id")
        month_label = kwargs.get("month_label") # e.g. "thg 3 2026"
        row_label = kwargs.get("row_label") # e.g. "Nhu cầu được dự báo"
        value = kwargs.get("value")

        if not plan_id or not product_id or not month_label:
            return False

        # Parse date from label
        import datetime
        parts = month_label.split(" ")
        month = int(parts[1])
        year = int(parts[2])
        date_start = datetime.date(year, month, 1)

        Value = self.env["production.plan.value"].sudo()
        rec = Value.search([
            ("plan_id", "=", int(plan_id)),
            ("product_id", "=", int(product_id)),
            ("date_start", "=", date_start)
        ], limit=1)

        vals = {
            "plan_id": int(plan_id),
            "product_id": int(product_id),
            "date_start": date_start,
        }
        
        if row_label.startswith(_("Nhu cầu")):
            vals["forecast_qty"] = float(value)
        elif row_label.startswith(_("Bổ sung")):
            vals["replenish_qty"] = float(value)
        
        if rec:
            rec.write(vals)
        else:
            Value.create(vals)
        return True

    @api.model
    def create_manufacturing_orders(self, **kwargs):
        plan_id = kwargs.get("plan_id")
        product_id = kwargs.get("product_id")
        if not plan_id or not product_id:
            return {"error": "Thiếu mã kế hoạch hoặc sản phẩm."}
        
        # Get all replenish quantities for this product in this plan
        Value = self.env["production.plan.value"].sudo()
        values = Value.search([
            ("plan_id", "=", int(plan_id)),
            ("product_id", "=", int(product_id)),
            ("replenish_qty", ">", 0)
        ])
        
        if not values:
            return {"error": "Không có số lượng bổ sung nào (>0) cần đặt hàng cho sản phẩm này."}
        
        MO = self.env["mrp.production"].sudo()
        created_count = 0
        today = date.today()
        for v in values:
            # Determine start date: if it's for current or past month, use Now. Otherwise use month start.
            plan_date = v.date_start
            if plan_date <= today:
                mo_start_date = fields.Datetime.now()
            else:
                mo_start_date = fields.Datetime.to_string(plan_date)

            # Create MO
            mo_vals = {
                "product_id": v.product_id.id,
                "product_qty": v.replenish_qty,
                "date_start": mo_start_date,
                "user_id": self.env.user.id,
                "origin": f"Kế hoạch SX #{plan_id}",
            }
            # Try to get BOM
            bom = self.env["mrp.bom"]._bom_find(v.product_id)[v.product_id]
            if bom:
                mo_vals["bom_id"] = bom.id
                mo_vals["product_uom_id"] = bom.product_uom_id.id
            else:
                mo_vals["product_uom_id"] = v.product_id.uom_id.id
            
            MO_rec = MO.create(mo_vals)
            MO_rec.action_confirm()
            MO_rec.action_assign()
            if MO_rec.bom_id:
                MO_rec.button_plan()
            created_count += 1
            
        return {"success": True, "count": created_count}
