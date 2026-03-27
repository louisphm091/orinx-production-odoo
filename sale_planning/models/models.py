# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class ProductionPlan(models.Model):
    _name = "production.plan"
    _description = "Production Plan"
    _order = "date desc, id desc"

    name = fields.Char(string="Tên kế hoạch", required=True, default=lambda self: self._get_default_name())
    date = fields.Date(string="Ngày lập", default=fields.Date.today, required=True)
    user_id = fields.Many2one("res.users", string="Người lập", default=lambda self: self.env.user)
    state = fields.Selection([
        ("draft", "Dự thảo"),
        ("done", "Hoàn tất")
    ], string="Trạng thái", default="draft")
    line_ids = fields.One2many("production.plan.line", "plan_id", string="Chi tiết sản phẩm")

    def _get_default_name(self):
        count = self.search_count([])
        return f"Kế hoạch #{count + 1}"

    def action_done(self):
        self.write({"state": "done"})

    def action_draft(self):
        self.write({"state": "draft"})

    @api.model
    def create_from_forecast(self, **kwargs):
        forecast_id = kwargs.get("forecast_id")
        product_ids = kwargs.get("product_ids")
        forecast_values = kwargs.get("forecast_values", {}) or {}
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("CREATING PLAN FROM FORECAST: id=%s, products=%s, values=%s", forecast_id, product_ids, forecast_values)
        
        plan = self.create({
            "name": f"Kế hoạch #{self.search_count([]) + 1}",
        })
        
        final_product_ids = []
        forecast_lines = self.env["demand.forecast.line"]
        if forecast_id and forecast_id != 0:
            forecast_lines = self.env["demand.forecast.line"].search([("forecast_id", "=", int(forecast_id))])
            final_product_ids = forecast_lines.mapped("product_id").ids
        
        if product_ids is not None and len(product_ids) > 0:
            final_product_ids = list(set(final_product_ids) | set(product_ids))
            
        _logger.info("FINAL PRODUCT IDS: %s", final_product_ids)
        for p_id_raw in final_product_ids:
            try:
                p_id = int(p_id_raw)
                # check if line already exists for this product in this plan
                if not self.env["production.plan.line"].search([("plan_id", "=", plan.id), ("product_id", "=", p_id)]):
                    self.env["production.plan.line"].create({
                        "plan_id": plan.id,
                        "product_id": p_id,
                    })
                
                # Initialize values
                qty = 0.0
                repl_qty = 0.0
                start_date = fields.Date.today().replace(day=1)
                end_date = fields.Date.today().replace(day=1) # Placeholder, will be updated if forecast line exists

                # Import forecast values if coming from a forecast
                # Case 1: Forecast records in DB
                f_line = forecast_lines.filtered(lambda l: l.product_id.id == p_id)
                if f_line:
                    qty = f_line[0].forecast_qty
                    onhand = f_line[0].product_id.qty_available
                    repl_qty = max(0, qty - onhand)
                    start_date = f_line[0].date_from or fields.Date.today().replace(day=1)
                    end_date = f_line[0].date_to or fields.Date.today().replace(day=1)
                # Case 2: Forecast data passed directly from dynamic dashboard or needs to be re-calculated
                else:
                    # Try to get quantity from passed forecast_values
                    qty_from_kwargs = forecast_values.get(str(p_id)) or forecast_values.get(p_id)
                    if qty_from_kwargs:
                        qty = float(qty_from_kwargs)
                    else:
                        # Re-calculate dynamically if nothing was passed (most robust)
                        dynamic_data = self.env["demand.forecast.dashboard"].get_dashboard_data(filters={})
                        rows = dynamic_data.get("forecast_rows") or []
                        matched = next((r for r in rows if r.get("product_id") == p_id), None)
                        if matched:
                            qty = matched.get("demand")
                    
                        # Calculate replenishment based on user rule: Replenish = Demand - Actual Stock
                        product = self.env["product.product"].browse(p_id)
                        actual_stock = product.qty_available
                        repl_qty = max(0, float(qty) - actual_stock)
                        
                        self.env["production.plan.value"].create({
                            "plan_id": plan.id,
                            "product_id": p_id,
                            "date_start": fields.Date.today().replace(day=1),
                            "forecast_qty": float(qty),
                            "replenish_qty": repl_qty,
                        })

            except Exception as e:
                _logger.error("Error creating plan line for product %s: %s", p_id_raw, e)
        return {
            "type": "ir.actions.client",
            "tag": "mrp_production_plan.dashboard",
            "name": "Lập kế hoạch sản xuất",
            "context": {"plan_id": plan.id},
        }

class ProductionPlanLine(models.Model):
    _name = "production.plan.line"
    _description = "Production Plan Configuration Row"
    _order = "id desc"

    plan_id = fields.Many2one("production.plan", string="Kế hoạch", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    is_indirect_demand = fields.Boolean(string="Nhu cầu gián tiếp")
    material_category_id = fields.Many2one("mrp.bom", string="Danh mục vật tư")
    route_id = fields.Many2one("stock.route", string="Tuyến cung ứng")
    safety_stock_target = fields.Float(string="Mục tiêu tồn kho an toàn")
    min_replenish_qty = fields.Float(string="Số lượng bổ sung tối thiểu")
    activation_type = fields.Selection([
        ("manual", "Thủ công"),
        ("auto", "Tự động")
    ], string="Kích hoạt bổ sung", default="manual")

class ProductionPlanWizard(models.TransientModel):
    _name = "production.plan.wizard"
    _description = "Add Product to Production Plan Wizard"

    plan_id = fields.Many2one("production.plan", string="Kế hoạch")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    is_indirect_demand = fields.Boolean(string="Nhu cầu gián tiếp")
    material_category_id = fields.Many2one("mrp.bom", string="Danh mục vật tư")
    route_id = fields.Many2one("stock.route", string="Tuyến cung ứng")
    safety_stock_target = fields.Float(string="Mục tiêu tồn kho an toàn")
    min_replenish_qty = fields.Float(string="Số lượng bổ sung tối thiểu")
    activation_type = fields.Selection([
        ("manual", "Thủ công"),
        ("auto", "Tự động")
    ], string="Kích hoạt bổ sung", default="manual")

    def action_save(self):
        self.env["production.plan.line"].create({
            "plan_id": self.plan_id.id,
            "product_id": self.product_id.id,
            "is_indirect_demand": self.is_indirect_demand,
            "material_category_id": self.material_category_id.id,
            "route_id": self.route_id.id,
            "safety_stock_target": self.safety_stock_target,
            "min_replenish_qty": self.min_replenish_qty,
            "activation_type": self.activation_type,
        })
        return {"type": "ir.actions.client", "tag": "reload_context"}
class ProductionPlanValue(models.Model):
    _name = "production.plan.value"
    _description = "Production Plan Value (Monthly)"

    plan_id = fields.Many2one("production.plan", string="Kế hoạch", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Sản phẩm", required=True)
    date_start = fields.Date(string="Tháng", required=True)
    forecast_qty = fields.Float(string="Nhu cầu dự báo")
    replenish_qty = fields.Float(string="Bổ sung hàng")

    _sql_constraints = [
        ("plan_product_date_unique", "unique(plan_id, product_id, date_start)", "Product/Month combination must be unique per plan."),
    ]
