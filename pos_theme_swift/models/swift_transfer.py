# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class SwiftStockTransfer(models.Model):
    _name = 'swift.stock.transfer'
    _description = 'Swift POS Stock Transfer'
    _order = 'date_transfer desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    date_transfer = fields.Datetime(string='Transfer Date', default=fields.Datetime.now)
    date_receive = fields.Datetime(string='Receive Date')

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
