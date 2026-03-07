from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class ProductTemplate(models.Model):
    _inherit = "product.template"

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
        if not warehouse:
            warehouse = self.env["stock.warehouse"].search([], limit=1)
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
