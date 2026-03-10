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

    @api.constrains("active", "picking_type_id")
    def _check_swift_branch_source_location(self):
        active_configs = self.sudo().search([("active", "=", True)])
        location_to_configs = {}

        for config in active_configs:
            location = config.picking_type_id.default_location_src_id
            if not location:
                raise ValidationError(
                    _("POS branch '%s' must have its own source location.") % config.display_name
                )
            location_to_configs.setdefault(location.id, self.env["pos.config"])
            location_to_configs[location.id] |= config

        for configs in location_to_configs.values():
            if len(configs) > 1:
                raise ValidationError(
                    _(
                        "Each POS branch must use a different source location. These branches are sharing one location: %s"
                    )
                    % ", ".join(configs.mapped("display_name"))
                )
