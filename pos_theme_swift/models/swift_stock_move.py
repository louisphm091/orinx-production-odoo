# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import ValidationError


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        """Check high stock threshold before completing the move."""
        res = super(StockMove, self)._action_done(cancel_backorder=cancel_backorder)

        # After move is done, we check actual stock in the destination location.
        # If any moved product exceeds the threshold in its POS warehouse, we raise error.
        # Note: We do this POST-move to get accurate 'on-hand' including the new items.

        for move in res:
            if move.state != 'done' or not move.product_id or move.product_id.type != 'product':
                continue

            dest_location = move.location_dest_id
            if dest_location.usage != 'internal':
                continue

            # Find if this location belongs to a POS warehouse
            warehouse = move.env['stock.warehouse'].sudo().search([
                '|', ('lot_stock_id', 'child_of', dest_location.id),
                ('lot_stock_id', '=', dest_location.id)
            ], limit=1)

            # Actually, it's safer to check if dest_location is child of a warehouse's lot_stock_id
            # Let's find all POS configs that have a warehouse
            pos_configs = move.env['pos.config'].sudo().search([
                ('active', '=', True),
                ('swift_warehouse_id', '!=', False)
            ])

            for config in pos_configs:
                branch_location = config.swift_warehouse_id.lot_stock_id
                if not branch_location:
                    continue

                # If destination is within this branch's territory
                if dest_location.id == branch_location.id or dest_location.parent_path.startswith(branch_location.parent_path or ''):
                    threshold = config.swift_high_stock_threshold
                    if threshold <= 0:
                        continue

                    # Calculate total on-hand in this branch for this product template
                    # The user said "số lượng sản phẩm... không được > max".
                    # Usually this refers to the specific product being moved.

                    product = move.product_id
                    # We check the template's total in this branch (matching the alert logic)
                    total_qty = product.product_tmpl_id.with_context(pos_config_id=config.id).qty_available

                    # Wait, product.template.qty_available is usually global.
                    # We need the qty in this specific location.

                    branch_qty = product.with_context(location=branch_location.id).qty_available

                    if branch_qty > threshold:
                        raise ValidationError(_(
                            "Cannot move goods to branch '%s'. "
                            "Product '%s' would exceed the maximum stock threshold (Current: %s, Max: %s)."
                        ) % (config.name, product.display_name, branch_qty, threshold))

        return res
