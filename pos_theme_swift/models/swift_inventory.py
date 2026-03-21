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
    config_id = fields.Many2one('pos.config', string='POS Branch', ondelete='restrict')
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
            if not vals.get('config_id'):
                config = self._get_pos_config(vals.get('config_id'))
                if config:
                    vals['config_id'] = config.id
        return super(SwiftStockInventory, self).create(vals_list)

    def _get_pos_config(self, config_id=None):
        PosConfig = self.env['pos.config'].sudo()
        if config_id:
            return PosConfig.browse(int(config_id)).exists()
        if self.env.context.get('pos_config_id'):
            return PosConfig.browse(int(self.env.context['pos_config_id'])).exists()
        if len(self) == 1 and self.config_id:
            return self.config_id
        configs = PosConfig.search([('active', '=', True)], limit=2)
        return configs if len(configs) == 1 else PosConfig.browse()

    def _get_inventory_location(self, config=None):
        config = config or self._get_pos_config()
        if config:
            if config.swift_warehouse_id and config.swift_warehouse_id.lot_stock_id:
                return config.swift_warehouse_id.lot_stock_id
            if config.picking_type_id.default_location_src_id:
                return config.picking_type_id.default_location_src_id
        return self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)

    def _get_branch_products(self, config):
        Product = self.env['product.product'].sudo()
        domain = [
            ('available_in_pos', '=', True),
            ('active', '=', True),
            ('product_tmpl_id.swift_branch_config_ids', 'in', config.ids),
        ]
        if getattr(config, 'limit_categories', False) and config.iface_available_categ_ids:
            domain.append(('pos_categ_ids', 'in', config.iface_available_categ_ids.ids))
        return Product.search(domain)

    def action_validate(self):
        """Update real Odoo stock based on the inventory sheet.

        Uses the official Odoo inventory-adjustment path (inventory_mode=True +
        inventory_quantity_auto_apply), which is the same path used by the
        Physical Inventory screen. This bypasses the is_storable constraint on
        stock.quant.create() and works for products with 0 on-hand stock.
        """
        _logger.info("action_validate: Starting for inventory id=%s", self.id)

        # Prefer the POS stock location; fall back to any internal location.
        pos_config = self._get_pos_config(self.config_id.id if self.config_id else None)
        location = self._get_inventory_location(pos_config)

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

        self.write({'state': 'done', 'config_id': pos_config.id if pos_config else False})
        # Trigger low-stock checks immediately after stock is updated so users
        # don't need to wait for the cron interval.
        self.cron_check_low_stock_alerts(config_id=pos_config.id if pos_config else False)
        _logger.info("action_validate: Done. Inventory id=%s marked as done.", self.id)
        return True

    @api.model
    def cron_check_low_stock_alerts(self, config_id=False):
        """Push admin notification when a POS product reaches low stock threshold."""
        Quant = self.env['stock.quant'].sudo()
        Alert = self.env['swift.low.stock.alert'].sudo()
        configs = self.env['pos.config'].sudo().browse()
        if config_id:
            configs = self.env['pos.config'].sudo().browse(int(config_id)).exists()
        if not configs:
            configs = self.env['pos.config'].sudo().search([('active', '=', True)])

        for config in configs:
            threshold = float(getattr(config, "swift_low_stock_threshold", 10.0) or 10.0)
            products = self._get_branch_products(config)
            if not products:
                continue

            qty_map = {pid: 0.0 for pid in products.ids}
            quant_domain = [
                ('product_id', 'in', products.ids),
                ('location_id.usage', '=', 'internal'),
            ]
            location = self._get_inventory_location(config)
            if location:
                quant_domain.append(('location_id', 'child_of', location.id))
            quants = Quant.search(quant_domain)
            for quant in quants:
                qty_map[quant.product_id.id] = qty_map.get(quant.product_id.id, 0.0) + quant.quantity

            active_alerts = Alert.search([('state', '=', 'active'), ('config_id', '=', config.id)])
            alert_by_product = {a.product_id.id: a for a in active_alerts}

            for product in products:
                qty_on_hand = qty_map.get(product.id, 0.0)
                alert = alert_by_product.get(product.id)
                if qty_on_hand <= threshold:
                    if not alert:
                        alert = Alert.create({
                            'product_id': product.id,
                            'config_id': config.id,
                            'threshold': threshold,
                            'qty_on_hand': qty_on_hand,
                            'state': 'active',
                            'last_notified_at': fields.Datetime.now(),
                        })
                        self._notify_low_stock_admins(product, qty_on_hand, threshold, config)
                    else:
                        alert.write({'qty_on_hand': qty_on_hand, 'threshold': threshold})
                else:
                    if alert:
                        existing_resolved = Alert.search([
                            ('product_id', '=', product.id),
                            ('config_id', '=', config.id),
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
    def _notify_low_stock_admins(self, product, qty_on_hand, threshold, config=False):
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

        # Real-time sticky toast in web client for admin users currently online.
        bus = self.env['bus.bus'].sudo()
        for admin in recipients:
            lang = admin.lang or self.env.user.lang or 'vi_VN'
            translator = self.with_context(lang=lang)
            title = translator._("Low Stock Alert")
            product_label = product.display_name
            if config:
                product_label = translator._("%s [%s]") % (product.display_name, config.name)
            message = translator._("Product '%s' has low stock: %s (threshold: %s).") % (
                product_label,
                qty_on_hand,
                int(threshold),
            )
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
            lang = self.env.user.lang or 'vi_VN'
            translator = self.with_context(lang=lang)
            product_label = product.display_name
            if config:
                product_label = translator._("%s [%s]") % (product.display_name, config.name)
            message = translator._("Product '%s' has low stock: %s (threshold: %s).") % (
                product_label,
                qty_on_hand,
                int(threshold),
            )
            product_tmpl.with_context(lang=lang).message_post(
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
    config_id = fields.Many2one('pos.config', required=True, index=True, ondelete='cascade')
    threshold = fields.Float(default=10.0, required=True)
    qty_on_hand = fields.Float(default=0.0)
    state = fields.Selection([
        ('active', 'Active'),
        ('resolved', 'Resolved'),
    ], default='active', required=True, index=True)
    last_notified_at = fields.Datetime()
    resolved_at = fields.Datetime()

    _sql_constraints = [
        ('swift_low_stock_alert_product_config_state_unique', 'unique(product_id, config_id, state)', 'Low stock alert already exists for this product/branch/state.'),
    ]
