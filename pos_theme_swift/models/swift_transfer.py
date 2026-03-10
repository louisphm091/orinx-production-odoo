# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class SwiftStockTransfer(models.Model):
    _name = 'swift.stock.transfer'
    _description = 'Swift POS Stock Transfer'
    _order = 'date_transfer desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    date_transfer = fields.Datetime(string='Transfer Date', default=fields.Datetime.now)
    date_receive = fields.Datetime(string='Receive Date')

    source_config_id = fields.Many2one('pos.config', string='Source Branch', ondelete='set null')
    dest_config_id = fields.Many2one('pos.config', string='Destination Branch', ondelete='set null')
    location_id = fields.Many2one('stock.location', string='Source Location', required=True, domain=[('usage', '=', 'internal')])
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', required=True, domain=[('usage', '=', 'internal')])

    state = fields.Selection([
        ('draft', 'Draft'),
        ('shipped', 'Shipped'),
        ('done', 'Received'),
    ], string='Status', default='draft', index=True, copy=False)

    note = fields.Text(string='Note')
    line_ids = fields.One2many('swift.stock.transfer.line', 'transfer_id', string='Transfer Lines', copy=True)

    total_value = fields.Float(compute='_compute_total_value', string='Total Value', store=True)

    @api.depends('line_ids.subtotal')
    def _compute_total_value(self):
        for rec in self:
            rec.total_value = sum(rec.line_ids.mapped('subtotal'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('swift.stock.transfer') or _('New')
        return super().create(vals_list)

    def action_ship(self):
        self.write({'state': 'shipped'})
        return True

    def action_receive_goods(self, lines_data=None):
        Quant = self.env['stock.quant'].sudo().with_context(inventory_mode=True)
        for transfer in self:
            dest_config = transfer.dest_config_id
            dest_location = transfer.location_dest_id
            source_location = transfer.location_id
            if not dest_config or not dest_location or not source_location:
                continue
            if source_location.id == dest_location.id:
                raise UserError(_(
                    "Cannot receive transfer '%s' because source branch and destination branch are using the same stock location."
                ) % transfer.display_name)

            received_map = {}
            for data in lines_data or []:
                try:
                    received_map[int(data.get('id'))] = float(data.get('received_qty') or 0.0)
                except (TypeError, ValueError):
                    continue

            for line in transfer.line_ids:
                received_qty = received_map.get(line.id, line.received_qty or line.qty or 0.0)
                if received_qty <= 0:
                    received_qty = line.qty or 0.0
                line.write({'received_qty': received_qty})

                product_tmpl = line.product_id.product_tmpl_id
                if dest_config.id not in product_tmpl.swift_branch_config_ids.ids:
                    product_tmpl.write({
                        'swift_branch_config_ids': [(4, dest_config.id)],
                    })

                source_quant = Quant.search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', source_location.id),
                ], limit=1)
                source_qty = source_quant.quantity if source_quant else 0.0
                new_source_qty = source_qty - received_qty
                if source_quant:
                    source_quant.write({
                        'inventory_quantity_auto_apply': new_source_qty,
                    })
                else:
                    Quant.create({
                        'product_id': line.product_id.id,
                        'location_id': source_location.id,
                        'inventory_quantity_auto_apply': new_source_qty,
                    })

                quant = Quant.search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', dest_location.id),
                ], limit=1)
                if quant:
                    quant.write({
                        'inventory_quantity_auto_apply': quant.quantity + received_qty,
                    })
                else:
                    Quant.create({
                        'product_id': line.product_id.id,
                        'location_id': dest_location.id,
                        'inventory_quantity_auto_apply': received_qty,
                    })

        self.action_done()
        return True

    def action_done(self):
        self.write({'state': 'done', 'date_receive': fields.Datetime.now()})
        # Handle stock updates here if needed (move stock from source to dest)
        return True

class SwiftStockTransferLine(models.Model):
    _name = 'swift.stock.transfer.line'
    _description = 'Swift POS Stock Transfer Line'

    transfer_id = fields.Many2one('swift.stock.transfer', string='Transfer', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    qty = fields.Float(string='Transfer Quantity', default=1.0)
    received_qty = fields.Float(string='Received Quantity', default=0.0)
    price = fields.Float(string='Price')
    subtotal = fields.Float(compute='_compute_subtotal', string='Subtotal', store=True)

    @api.depends('qty', 'price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.qty * line.price
