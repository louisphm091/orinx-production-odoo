# Demand_forecast/models/Demand_forecast_line.py
from odoo import api, fields, models


class DemandForecastLine(models.Model):
    _name = "demand.forecast.line"
    _description = "Demand Forecast Line"
    _order = "forecast_qty desc, id desc"

    forecast_id = fields.Many2one("demand.forecast", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="forecast_id.company_id", store=True, readonly=True)

    warehouse_id = fields.Many2one(related="forecast_id.warehouse_id", store=True, readonly=True)
    date_from = fields.Date(related="forecast_id.date_from", store=True, readonly=True)
    date_to = fields.Date(related="forecast_id.date_to", store=True, readonly=True)

    product_id = fields.Many2one("product.product", required=True)
    product_uom_id = fields.Many2one(related="product_id.uom_id", store=True, readonly=True)
    categ_id = fields.Many2one(related="product_id.categ_id", store=True, readonly=True)

    # forecast/actual
    forecast_qty = fields.Float(default=0.0)
    adjusted_forecast_qty = fields.Float(default=0.0)  # optional: if you call action_apply_adjustment
    actual_qty = fields.Float(default=0.0)

    delta_qty = fields.Float(compute="_compute_delta", store=False)
    share_percent = fields.Float(compute="_compute_share", store=False)

    # stock snapshot (context by warehouse)
    onhand_qty = fields.Float(compute="_compute_stock_snapshot", store=False)
    incoming_qty = fields.Float(compute="_compute_stock_snapshot", store=False)
    outgoing_qty = fields.Float(compute="_compute_stock_snapshot", store=False)
    virtual_available = fields.Float(compute="_compute_stock_snapshot", store=False)

    shortage_qty = fields.Float(compute="_compute_shortage", store=False)

    # MRP links (optional)
    bom_id = fields.Many2one("mrp.bom")
    suggest_mo_qty = fields.Float(default=0.0)

    @api.constrains
    def _check_unique_product(self):
        for rec in self:
            domain = [
                ("forecast_id", "=", rec.forecast_id.id),
                ("product_id", "=", rec.product_id.id),
                ("id", "!=", rec.id),
            ]
            if self.search_count(domain):
                raise ValueError("Product already exists in this forecast.")

    @api.depends("forecast_qty", "actual_qty")
    def _compute_delta(self):
        for rec in self:
            rec.delta_qty = (rec.forecast_qty or 0.0) - (rec.actual_qty or 0.0)

    @api.depends("forecast_id", "forecast_qty")
    def _compute_share(self):
        for rec in self:
            total = sum(rec.forecast_id.line_ids.mapped("forecast_qty")) if rec.forecast_id else 0.0
            rec.share_percent = (rec.forecast_qty / total * 100.0) if total else 0.0

    @api.depends("product_id", "warehouse_id")
    def _compute_stock_snapshot(self):
        """
        Uses product quantities with warehouse context.
        Works well in stock module; gives quantities for that warehouse.
        """
        for rec in self:
            rec.onhand_qty = 0.0
            rec.incoming_qty = 0.0
            rec.outgoing_qty = 0.0
            rec.virtual_available = 0.0

            if not rec.product_id or not rec.warehouse_id:
                continue

            p = rec.product_id.with_context(warehouse=rec.warehouse_id.id)
            # These are standard product fields provided by stock:
            rec.onhand_qty = p.qty_available
            rec.incoming_qty = p.incoming_qty
            rec.outgoing_qty = p.outgoing_qty
            rec.virtual_available = p.virtual_available

    @api.depends("forecast_qty", "onhand_qty", "incoming_qty", "outgoing_qty")
    def _compute_shortage(self):
        for rec in self:
            supply = (rec.onhand_qty or 0.0) + (rec.incoming_qty or 0.0) - (rec.outgoing_qty or 0.0)
            need = rec.forecast_qty or 0.0
            rec.shortage_qty = max(0.0, need - supply)
