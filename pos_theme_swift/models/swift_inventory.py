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
        """Update real Odoo stock based on the inventory sheet.

        Uses the official Odoo inventory-adjustment path (inventory_mode=True +
        inventory_quantity_auto_apply), which is the same path used by the
        Physical Inventory screen. This bypasses the is_storable constraint on
        stock.quant.create() and works for products with 0 on-hand stock.
        """
        _logger.info("action_validate: Starting for inventory id=%s", self.id)

        # Prefer the POS stock location; fall back to any internal location.
        pos_config = self.env['pos.config'].search([], limit=1)
        if pos_config and pos_config.picking_type_id.default_location_src_id:
            location = pos_config.picking_type_id.default_location_src_id
        else:
            location = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)

        if not location:
            _logger.error("action_validate: No internal stock location found — aborting.")
            return False

        _logger.info("action_validate: Using location '%s' (id=%s)", location.display_name, location.id)

        # Use inventory_mode=True — this is the context Odoo's Physical Inventory
        # screen uses. It unlocks write access to inventory_quantity fields and
        # routes stock.quant.create() through a path that bypasses the
        # is_storable / check_product_id constraint.
        Quant = self.env['stock.quant'].sudo().with_context(inventory_mode=True)

        for line in self.line_ids:
            product = line.product_id
            target_qty = line.qty_actual

            _logger.info(
                "action_validate: product='%s' (id=%s) type=%s is_storable=%s → target=%s",
                product.display_name, product.id, product.type,
                getattr(product, 'is_storable', 'n/a'), target_qty,
            )

            try:
                # Look for an existing quant at this location.
                quant = Quant.search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id),
                ], limit=1)

                if quant:
                    # Update path: use .write() to reliably trigger the
                    # _set_inventory_quantity inverse for both increase AND
                    # decrease (direct attribute assignment can race with the
                    # computed-field recalculation in some Odoo versions).
                    quant.write({'inventory_quantity_auto_apply': target_qty})
                    _logger.info(
                        "action_validate: Updated existing quant id=%s → qty=%s",
                        quant.id, target_qty,
                    )
                else:
                    # Create path: by passing inventory_quantity_auto_apply in
                    # vals while inventory_mode=True, stock.quant.create() takes
                    # the inventory branch (lines 267-304 of stock_quant.py),
                    # which calls super().create(vals) as superuser — bypassing
                    # the check_product_id @api.constrains entirely.
                    Quant.create({
                        'product_id': product.id,
                        'location_id': location.id,
                        'inventory_quantity_auto_apply': target_qty,
                    })
                    _logger.info(
                        "action_validate: Created new quant for '%s' → qty=%s",
                        product.display_name, target_qty,
                    )

            except Exception as e:
                _logger.error(
                    "action_validate: ERROR for '%s': %s",
                    product.display_name, e,
                )
                continue

        self.write({'state': 'done'})
        # Trigger low-stock checks immediately after stock is updated so users
        # don't need to wait for the cron interval.
        self.cron_check_low_stock_alerts()
        _logger.info("action_validate: Done. Inventory id=%s marked as done.", self.id)
        return True

    @api.model
    def cron_check_low_stock_alerts(self):
        """Push admin notification when a POS product reaches low stock threshold."""
        threshold = 10.0
        Product = self.env['product.product'].sudo()
        Quant = self.env['stock.quant'].sudo()
        Alert = self.env['swift.low.stock.alert'].sudo()

        products = Product.search([
            ('available_in_pos', '=', True),
            ('active', '=', True),
        ])
        if not products:
            return True

        qty_map = {pid: 0.0 for pid in products.ids}
        quants = Quant.search([
            ('product_id', 'in', products.ids),
            ('location_id.usage', '=', 'internal'),
        ])
        for quant in quants:
            qty_map[quant.product_id.id] = qty_map.get(quant.product_id.id, 0.0) + quant.quantity

        active_alerts = Alert.search([('state', '=', 'active')])
        alert_by_product = {a.product_id.id: a for a in active_alerts}

        for product in products:
            qty_on_hand = qty_map.get(product.id, 0.0)
            alert = alert_by_product.get(product.id)
            if qty_on_hand <= threshold:
                if not alert:
                    alert = Alert.create({
                        'product_id': product.id,
                        'threshold': threshold,
                        'qty_on_hand': qty_on_hand,
                        'state': 'active',
                        'last_notified_at': fields.Datetime.now(),
                    })
                    self._notify_low_stock_admins(product, qty_on_hand, threshold)
                else:
                    alert.write({'qty_on_hand': qty_on_hand})
            else:
                if alert:
                    # Avoid unique conflict on (product_id, state) when a
                    # resolved record already exists for this product.
                    existing_resolved = Alert.search([
                        ('product_id', '=', product.id),
                        ('state', '=', 'resolved'),
                        ('id', '!=', alert.id),
                    ], limit=1)
                    if existing_resolved:
                        existing_resolved.write({
                            'qty_on_hand': qty_on_hand,
                            'resolved_at': fields.Datetime.now(),
                        })
                        alert.unlink()
                    else:
                        alert.write({
                            'state': 'resolved',
                            'resolved_at': fields.Datetime.now(),
                            'qty_on_hand': qty_on_hand,
                        })
        return True

    @api.model
    def _notify_low_stock_admins(self, product, qty_on_hand, threshold):
        admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
        pos_manager_group = self.env.ref('point_of_sale.group_pos_manager', raise_if_not_found=False)
        recipients = self.env['res.users'].sudo().browse()
        if admin_group:
            recipients |= admin_group.user_ids if 'user_ids' in admin_group._fields else admin_group.users
        if pos_manager_group:
            recipients |= pos_manager_group.user_ids if 'user_ids' in pos_manager_group._fields else pos_manager_group.users
        recipients = recipients.filtered(lambda u: u.active and not u.share)
        if not recipients:
            return

        title = _("Low Stock Alert")
        message = _("Product '%s' has low stock: %s (threshold: %s).") % (
            product.display_name,
            qty_on_hand,
            int(threshold),
        )

        # Real-time sticky toast in web client for admin users currently online.
        bus = self.env['bus.bus'].sudo()
        for admin in recipients:
            if admin.partner_id:
                bus._sendone(
                    admin.partner_id,
                    'simple_notification',
                    {
                        'title': title,
                        'message': message,
                        'type': 'warning',
                        'sticky': True,
                    },
                )

        # Persist notification in chatter for audit/history.
        product_tmpl = product.product_tmpl_id
        if hasattr(product_tmpl, 'message_post'):
            product_tmpl.message_post(
                body=message,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )



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


class SwiftLowStockAlert(models.Model):
    _name = 'swift.low.stock.alert'
    _description = 'Swift Low Stock Alert'
    _order = 'last_notified_at desc, id desc'

    product_id = fields.Many2one('product.product', required=True, index=True, ondelete='cascade')
    threshold = fields.Float(default=10.0, required=True)
    qty_on_hand = fields.Float(default=0.0)
    state = fields.Selection([
        ('active', 'Active'),
        ('resolved', 'Resolved'),
    ], default='active', required=True, index=True)
    last_notified_at = fields.Datetime()
    resolved_at = fields.Datetime()

    _sql_constraints = [
        ('swift_low_stock_alert_product_state_unique', 'unique(product_id, state)', 'Low stock alert already exists for this product/state.'),
    ]
