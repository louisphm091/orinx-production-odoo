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
        for i in range(9):
            d = first_day + relativedelta(months=i)
            months.append({
                "label": f"thg {d.month} {d.year}",
                "date_start": d,
                "date_end": d + relativedelta(months=1) - timedelta(days=1)
            })
            
        # 2. Products (manufactured, storable)
        Product = env["product.product"].sudo()
        domain = [("active", "=", True), ("type", "=", "consu"), ("is_storable", "=", True)]
        # Filter products that are in the mock data or high demand
        products = Product.search(domain, limit=10)
        
        # 3. Build data rows
        rows = []
        for p in products:
            product_row = {
                "id": p.id,
                "name": p.display_name,
                "image_url": f"/web/image/product.product/{p.id}/image_128",
                "values": []
            }
            
            # Sub-rows data
            forecast_row = {"label": "Nhu cầu được dự báo", "icon": "-", "allow_edit": True, "values": []}
            indirect_row = {"label": "Dự báo nhu cầu gián tiếp", "icon": "-", "allow_edit": False, "values": []}
            replenish_row = {"label": "Bổ sung hàng", "icon": "+", "allow_edit": True, "values": []}
            stock_row = {"label": "Tồn kho được dự báo", "icon": "=", "allow_edit": False, "values": []}
            
            # Mock some data for 9 columns
            import random
            curr_stock = random.randint(50, 150)
            
            for m in months:
                # Column values
                f_qty = random.choice([0, 100, 150, 300, 50, 0])
                i_qty = random.choice([0, 0, 150, 300, 0, 0])
                r_qty = f_qty + i_qty
                
                forecast_row["values"].append(f_qty)
                indirect_row["values"].append(i_qty)
                replenish_row["values"].append(r_qty)
                stock_row["values"].append(curr_stock)
                
                curr_stock = max(0, curr_stock + r_qty - f_qty - i_qty)
            
            product_row["sub_rows"] = [forecast_row, indirect_row, replenish_row, stock_row]
            rows.append(product_row)
            
        return {
            "months": [m["label"] for m in months],
            "rows": rows,
            "filters": filters
        }
