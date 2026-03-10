# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class SwiftBranchProductWizard(models.TransientModel):
    _name = "swift.branch.product.wizard"
    _description = "Swift Branch Product Assignment Wizard"

    operation = fields.Selection(
        [
            ("add", "Add Branches"),
            ("remove", "Remove Branches"),
            ("replace", "Replace Branches"),
        ],
        default="replace",
        required=True,
    )
    branch_config_ids = fields.Many2many(
        "pos.config",
        string="POS Branches",
        domain=[("active", "=", True)],
        required=True,
    )
    product_tmpl_ids = fields.Many2many(
        "product.template",
        string="POS Products",
        domain=[("available_in_pos", "=", True)],
        required=True,
    )
    product_count = fields.Integer(compute="_compute_counts")
    branch_count = fields.Integer(compute="_compute_counts")

    def _compute_counts(self):
        for wizard in self:
            wizard.product_count = len(wizard.product_tmpl_ids)
            wizard.branch_count = len(wizard.branch_config_ids)

    def action_apply(self):
        self.ensure_one()
        if not self.product_tmpl_ids:
            raise UserError(_("Please select at least one POS product."))
        if not self.branch_config_ids:
            raise UserError(_("Please select at least one POS branch."))

        commands = [(6, 0, self.branch_config_ids.ids)]
        for product in self.product_tmpl_ids:
            if self.operation == "replace":
                product.swift_branch_config_ids = commands
            elif self.operation == "add":
                product.swift_branch_config_ids = [(4, branch_id) for branch_id in self.branch_config_ids.ids]
            elif self.operation == "remove":
                product.swift_branch_config_ids = [(3, branch_id) for branch_id in self.branch_config_ids.ids]

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Branch assignment updated"),
                "message": _("Updated %s POS product(s).") % len(self.product_tmpl_ids),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
