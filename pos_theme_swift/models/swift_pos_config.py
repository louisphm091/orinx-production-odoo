# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    swift_low_stock_threshold = fields.Float(
        string="Low Stock Threshold",
        default=10.0,
        help="Send low stock alerts when on hand quantity is less than or equal to this value.",
    )

    swift_high_stock_threshold = fields.Float(
        string="High Stock Threshold",
        default=100.0,
        help="Maximum desired stock level for this POS branch.",
    )

    swift_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse (Swift)",
        help="The warehouse associated with this POS branch for inventory management.",
    )

    swift_branch_address = fields.Char(
        related="swift_warehouse_id.partner_id.contact_address",
        string="Branch Address",
        readonly=True,
    )

    swift_branch_phone = fields.Char(
        related="swift_warehouse_id.partner_id.phone",
        string="Branch Phone",
        readonly=True,
    )

    @api.constrains("active", "swift_warehouse_id")
    def _check_swift_branch_warehouse(self):
        active_configs = self.sudo().search([("active", "=", True)])
        warehouse_to_configs = {}

        for config in active_configs:
            warehouse = config.swift_warehouse_id
            if not warehouse:
                continue
            warehouse_to_configs.setdefault(warehouse.id, self.env["pos.config"])
            warehouse_to_configs[warehouse.id] |= config

        for configs in warehouse_to_configs.values():
            if len(configs) > 1:
                raise ValidationError(
                    _(
                        "Each POS branch must have its own Warehouse. These branches are sharing one Warehouse: %s"
                    )
                    % ", ".join(configs.mapped("display_name"))
                )
