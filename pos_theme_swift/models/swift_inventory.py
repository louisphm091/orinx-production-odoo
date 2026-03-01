from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class SwiftStockInventory(models.Model):
    _name = 'swift.stock.inventory'
    _description = 'Swift POS Inventory Sheet'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    date = fields.Datetime(string='Inventory Date', default=fields.Datetime.now, required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Validated'),
    ], string='Status', default='draft', index=True, copy=False)
    note = fields.Text(string='Note')
    line_ids = fields.One2many('swift.stock.inventory.line', 'inventory_id', string='Inventory Lines', copy=True)

    total_qty_actual = fields.Float(compute='_compute_totals', string='Total Actual Qty')
    total_diff = fields.Float(compute='_compute_totals', string='Total Difference')
    total_diff_inc = fields.Float(compute='_compute_totals', string='Total Difference Increase')
    total_diff_dec = fields.Float(compute='_compute_totals', string='Total Difference Decrease')

    @api.depends('line_ids.qty_actual', 'line_ids.diff')
    def _compute_totals(self):
        for rec in self:
            rec.total_qty_actual = sum(rec.line_ids.mapped('qty_actual'))
            rec.total_diff = sum(rec.line_ids.mapped('diff'))
            rec.total_diff_inc = sum(rec.line_ids.filtered(lambda l: l.diff > 0).mapped('diff'))
            rec.total_diff_dec = sum(rec.line_ids.filtered(lambda l: l.diff < 0).mapped('diff'))

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info("SwiftStockInventory.create: %s", vals_list)
        for vals in vals_list:
            if not isinstance(vals, dict):
                _logger.warning("SwiftStockInventory.create: expected dict, got %s", type(vals))
                continue
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('swift.stock.inventory') or _('New')
        return super(SwiftStockInventory, self).create(vals_list)

    def action_validate(self):
        """Update real Odoo stock based on the inventory sheet."""
        # Find an internal location to apply the adjustment
        location = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
        if not location:
            return False

        for line in self.line_ids:
            # Skip non-storable products (Consume/Service) as they don't have quants
            if line.product_id.type != 'product':
                _logger.info("Skipping non-storable product in inventory: %s", line.product_id.display_name)
                continue

            # Search for existing quant or create new one to set inventory quantity
            quant = self.env['stock.quant'].with_context(inventory_mode=True).search([
                ('product_id', '=', line.product_id.id),
                ('location_id', '=', location.id)
            ], limit=1)

            if quant:
                quant.inventory_quantity = line.qty_actual
                quant.action_apply_inventory()
            else:
                new_quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
                    'product_id': line.product_id.id,
                    'location_id': location.id,
                    'inventory_quantity': line.qty_actual,
                })
                new_quant.action_apply_inventory()

        self.write({'state': 'done'})
        return True

class SwiftStockInventoryLine(models.Model):
    _name = 'swift.stock.inventory.line'
    _description = 'Swift POS Inventory Line'

    inventory_id = fields.Many2one('swift.stock.inventory', string='Inventory', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty_on_hand = fields.Float(string='On Hand Qty')
    qty_actual = fields.Float(string='Actual Qty')
    diff = fields.Float(string='Difference', compute='_compute_diff', store=True)
    price = fields.Float(string='Product Price')
    diff_value = fields.Float(string='Difference Value', compute='_compute_diff', store=True)

    @api.depends('qty_on_hand', 'qty_actual', 'price')
    def _compute_diff(self):
        for line in self:
            line.diff = line.qty_actual - line.qty_on_hand
            line.diff_value = line.diff * line.price
