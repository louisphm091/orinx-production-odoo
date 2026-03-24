# -*- coding: utf-8 -*-

from odoo import fields, models


class SwiftPosOrder(models.Model):
    _inherit = "pos.order"

    swift_mode = fields.Selection(
        [("sell", "Sell"), ("order", "Order")],
        string="Swift Mode",
        default="sell",
        index=True,
    )
    swift_discount_percent = fields.Float(string="Swift Discount (%)", default=0.0)
    swift_extra_charge = fields.Monetary(string="Swift Extra Charge", currency_field="currency_id", default=0.0)
    swift_note = fields.Char(string="Swift Note")
