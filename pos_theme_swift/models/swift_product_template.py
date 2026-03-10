from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class ProductTemplate(models.Model):
    _inherit = "product.template"

    swift_branch_config_ids = fields.Many2many(
        "pos.config",
        "swift_product_template_pos_config_rel",
        "product_tmpl_id",
        "config_id",
        string="POS Branches",
        help="Only products assigned to selected POS branches are available in those branches. Leave empty to keep the product hidden from branch-specific POS flows.",
    )

    def action_swift_import_goods_filtered(self):
        """Import goods for all products in current filtered result (low stock <= 10)."""
        ctx = self.env.context
        domain = ctx.get("active_domain") or ctx.get("search_domain") or ctx.get("domain") or []
        if isinstance(domain, str):
            domain = safe_eval(domain)
        if not isinstance(domain, list):
            domain = []

        if domain:
            products = self.search(domain)
        elif self:
            products = self
        else:
            products = self.search([("available_in_pos", "=", True)])

        # Force low-stock behavior for this button so it imports what the user expects.
        products = products.filtered(lambda p: p.is_storable and p.qty_available <= 10)
        if not products:
            raise UserError(_("No low-stock products (<= 10) found in current filter."))

        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        if not warehouse or not warehouse.lot_stock_id:
            raise UserError(_("No warehouse stock location found."))

        target_qty = 20.0
        location = warehouse.lot_stock_id
        variants = products.mapped("product_variant_id").filtered(lambda p: p.is_storable)
        if not variants:
            raise UserError(_("No inventory-managed product variants found."))

        Quant = self.env["stock.quant"].sudo().with_context(inventory_mode=True)
        StockQuant = self.env["stock.quant"].sudo()
        updated = 0
        total_added = 0.0
        for product in variants:
            current_qty = StockQuant._get_available_quantity(product, location)
            if current_qty >= target_qty:
                continue
            needed_qty = target_qty - current_qty
            quant = Quant.search([
                ("product_id", "=", product.id),
                ("location_id", "=", location.id),
            ], limit=1)
            if quant:
                quant.write({"inventory_quantity_auto_apply": target_qty})
            else:
                Quant.create({
                    "product_id": product.id,
                    "location_id": location.id,
                    "inventory_quantity_auto_apply": target_qty,
                })
            updated += 1
            total_added += needed_qty

        message = _(
            "Imported goods for %s product(s). Added %s units, target stock is 20."
        ) % (updated, round(total_added, 2))
        if updated == 0:
            message = _("No products needed import (all already >= 20).")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Import Goods"),
                "message": message,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    def action_open_swift_branch_assignment_wizard(self):
        products = self
        if not products:
            active_ids = self.env.context.get("active_ids", [])
            products = self.browse(active_ids)
        products = products.filtered(lambda product: product.available_in_pos)
        if not products:
            raise UserError(_("Please select at least one POS product."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Gán chi nhánh POS"),
            "res_model": "swift.branch.product.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_product_tmpl_ids": [(6, 0, products.ids)],
            },
        }
