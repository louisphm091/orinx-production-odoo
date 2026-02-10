# models/dashboard.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FashionForecast(models.Model):
    _name = "fashion.forecast"
    _description = "Fashion Forecast Dashboard"
    _order = "date_from desc, id desc"

    name = fields.Char(required = True, default = lambda self: _("New Forecast"))
    company_id = fields.Many2one("res.company", required = True, default = lambda self: self.env.company)
    currency_id = fields.Many2one(related = "company_id.currency_id", store = False, readonly = True)

    warehouse_id = fields.Many2one("stock.warehouse", required = True)
    date_from = fields.Date(required = True, default = fields.Date.context_today)
    date_to = fields.Date(required = True, default = fields.Date.context_today)


    # Time Period of forecast
    time_grain = fields.Selection(
        [("month", "Month"), ("week", "Week"), ("quarter", "Quarter")],
        default = "month",
        required = True
    )


    # Fashion Forecast Status
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Done"), ("cancel", "Cancelled")],
        default = "draft",
        required = True
    )

    # Manual Adjustment
    adjustment_percent = fields.Float(default = 0.0)
    adjustment_reason = fields.Text()
    adjusted_by = fields.Many2one("res.users", readonly = True)
    adjusted_at = fields.Datetime(readonly = True)

    line_ids = fields.One2many("fashion.forecast.line", "forecast_id", string="Lines")

    # quick totals
    total_forecast_qty = fields.Float(compute="_compute_totals", store=False)
    total_actual_qty = fields.Float(compute="_compute_totals", store=False)


    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("date_from must be <= date_to"))

    def action_mark_done(self):
        for rec in self:
            rec.state = "done"

    def action_apply_adjustment(self):
        """Apply adjustment_percent to forecast_qty into adjusted_forecast_qty on each line."""
        for rec in self:
            percent = rec.adjustment_percent or 0.0
            factor = 1.0 + (percent / 100.0)
            for line in rec.line_ids:
                line.adjusted_forecast_qty = line.forecast_qty * factor
            rec.adjusted_by = self.env.user
            rec.adjusted_at = fields.Datetime.now()

    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.total_forecast_qty = sum(lines.mapped("forecast_qty"))
            rec.total_actual_qty = sum(lines.mapped("actual_qty"))
