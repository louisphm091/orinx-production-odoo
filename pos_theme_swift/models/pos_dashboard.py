# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta
import pytz
import logging
_logger = logging.getLogger(__name__)

class PosDashboardSwift(models.AbstractModel):
    _name = 'pos.dashboard.swift'
    _description = 'POS Dashboard Logic for Swift'

    @api.model
    def get_dashboard_data(self, filter_key='today'):
        # 1. Determine date ranges
        now = datetime.now()
        user_tz = self.env.user.tz or 'UTC'
        local = pytz.timezone(user_tz)
        now_local = datetime.now(local)

        start_date, end_date = self._get_date_range(filter_key, now_local)

        # 2. Results
        res = {
            'kpi': self._get_kpis(start_date, end_date, filter_key),
            'recent_orders': self._get_recent_orders(),
            'top_products': self._get_top_products(start_date, end_date),
            'chart_data': self._get_chart_data(start_date, end_date),
            'loading': False
        }
        return res

    def _get_chart_data(self, start, end):
        # Aggregate revenue by POS Config (Chi nhánh)
        domain = [('date_order', '>=', start), ('date_order', '<=', end), ('state', 'in', ['paid', 'done', 'invoiced'])]
        # _read_group returns a list of tuples: (config_id_record, amount_total_sum)
        groups = self.env['pos.order']._read_group(
            domain,
            groupby=['config_id'],
            aggregates=['amount_total:sum'],
        )

        datasets = []

        if not groups:
            return {'labels': ['-'], 'datasets': []}

        for config_rec, amount_total_sum in groups:
            config_name = config_rec.name if config_rec else _('Unknown')
            datasets.append({
                'label': config_name,
                'data': [amount_total_sum or 0.0]
            })

        return {
            'labels': [fields.Date.to_string(start)],  # Simple label for now
            'datasets': datasets
        }

    def _get_date_range(self, key, now_local):
        if key == 'today':
            start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif key == 'yesterday':
            yesterday = now_local - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif key == 'this_week':
            start = now_local - timedelta(days=now_local.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif key == 'this_month':
            start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Convert back to UTC for DB query
        user_tz = self.env.user.tz or 'UTC'
        local = pytz.timezone(user_tz)
        utc = pytz.utc

        start_utc = local.localize(start.replace(tzinfo=None)).astimezone(utc).replace(tzinfo=None)
        end_utc = local.localize(end.replace(tzinfo=None)).astimezone(utc).replace(tzinfo=None)

        return start_utc, end_utc

    def _get_kpis(self, start, end, key):
        domain = [('date_order', '>=', start), ('date_order', '<=', end), ('state', 'in', ['paid', 'done', 'invoiced'])]
        orders = self.env['pos.order'].search(domain)

        revenue = sum(orders.filtered(lambda x: x.amount_total > 0).mapped('amount_total'))
        refund = sum(orders.filtered(lambda x: x.amount_total < 0).mapped('amount_total'))
        net = revenue + refund # refund is negative

        return {
            'revenue': revenue,
            'refund': abs(refund),
            'net': net,
            'orders': len(orders)
        }

    def _get_recent_orders(self):
        orders = self.env['pos.order'].search([('state', 'in', ['paid', 'done', 'invoiced'])], limit=10, order='date_order desc')
        res = []
        for o in orders:
            res.append({
                'id': o.id,
                'partner': o.partner_id.name or _('Walking Customer'),
                'amount_total': o.amount_total,
                'time_ago': self._get_time_ago(o.date_order)
            })
        return res

    def _get_time_ago(self, dt):
        now = fields.Datetime.now()
        diff = now - dt
        if diff.days > 0:
            return _('%s ngày trước') % diff.days
        hours = diff.seconds // 3600
        if hours > 0:
            return _('%s giờ trước') % hours
        mins = (diff.seconds % 3600) // 60
        if mins > 0:
            return _('%s phút trước') % mins
        return _('vừa xong')

    def _get_top_products(self, start, end):
        domain = [('order_id.date_order', '>=', start), ('order_id.date_order', '<=', end), ('order_id.state', 'in', ['paid', 'done', 'invoiced'])]
        # _read_group returns list of tuples: (product_id_record, price_subtotal_incl_sum)
        groups = self.env['pos.order.line']._read_group(
            domain,
            groupby=['product_id'],
            aggregates=['price_subtotal_incl:sum'],
            order='price_subtotal_incl:sum desc',
            limit=10,
        )

        res = []
        if not groups:
            return res

        values = [amt or 0.0 for _, amt in groups]
        max_val = max(values) if values else 1
        for product_rec, amount in groups:
            amount = amount or 0.0
            res.append({
                'name': product_rec.name if product_rec else _('Unknown'),
                'value': amount,
                'pct': int((amount / max_val) * 100) if max_val > 0 else 0
            })
        return res

    # ──────────────────────────────────────────────────────────────
    # Inventory (Kiểm Kho) helpers
    # ──────────────────────────────────────────────────────────────

    @api.model
    def get_inventory_products(self, keyword=''):
        """Return products with current on-hand quantity for inventory lines."""
        domain = [('available_in_pos', '=', True)]
        if keyword:
            domain += ['|',
                ('name', 'ilike', keyword),
                ('barcode', 'ilike', keyword),
            ]
        products = self.env['product.product'].search(domain, limit=200)
        res = []
        for p in products:
            # get stock for all warehouses
            quant_domain = [('product_id', '=', p.id), ('location_id.usage', '=', 'internal')]
            quants = self.env['stock.quant'].search(quant_domain)
            qty_on_hand = sum(quants.mapped('quantity'))
            res.append({
                'id': p.id,
                'name': p.display_name or p.name,
                'barcode': p.barcode or '',
                'uom': p.uom_id.name if p.uom_id else '',
                'qty_on_hand': qty_on_hand,
                'price': p.standard_price or 0.0,
            })
        return res

    @api.model
    def get_recent_inventories(self):
        """Return the 5 most recent stock inventories using the custom model."""
        res = []
        try:
            records = self.env['swift.stock.inventory'].search(
                [], order='date desc', limit=5
            )
            for r in records:
                res.append({
                    'id': r.id,
                    'name': r.name or str(r.id),
                    'date': fields.Datetime.to_string(r.date) if r.date else '',
                    'status': r.state if r.state else 'draft',
                })
        except Exception as e:
            _logger.warning('get_recent_inventories: %s', e)
        return res

    @api.model
    def get_products_by_barcodes(self, barcodes):
        """Look up products by barcode list, returning product info + stock qty."""
        if not barcodes:
            return []
        res = []
        try:
            products = self.env['product.product'].search([
                ('barcode', 'in', barcodes)
            ])
            for p in products:
                # Get internal stock
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', p.id),
                    ('location_id.usage', '=', 'internal'),
                ])
                qty_on_hand = sum(quants.mapped('quantity'))
                res.append({
                    'id': p.id,
                    'name': p.display_name or p.name,
                    'barcode': p.barcode or '',
                    'uom': p.uom_id.name if p.uom_id else '',
                    'qty_on_hand': qty_on_hand,
                    'price': p.standard_price or 0.0,
                })
        except Exception as e:
            _logger.warning('get_products_by_barcodes: %s', e)
        return res

    @api.model
    def get_inventory_detail(self, inventory_id):
        """Load an existing swift.stock.inventory record including lines."""
        try:
            inv = self.env['swift.stock.inventory'].browse(inventory_id)
            if not inv.exists():
                return False
            lines = []
            for line in inv.line_ids:
                lines.append({
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'barcode': line.product_id.barcode or '',
                    'uom': line.product_id.uom_id.name if line.product_id.uom_id else '',
                    'qty_on_hand': line.qty_on_hand,
                    'qty_actual': line.qty_actual,
                    'diff': line.diff,
                    'diff_value': line.diff_value,
                    'price': line.price,
                })
            return {
                'id': inv.id,
                'name': inv.name,
                'state': inv.state,
                'note': inv.note or '',
                'lines': lines,
            }
        except Exception as e:
            _logger.warning('get_inventory_detail: %s', e)
            return False

    @api.model
    def create_or_update_inventory(self, vals):
        """Create or update a swift.stock.inventory record."""
        try:
            inv_id   = vals.get('id', False)
            note     = vals.get('note', '')
            state    = vals.get('state', 'draft')
            lines_data = vals.get('lines', [])

            Inventory = self.env['swift.stock.inventory']

            if inv_id:
                inv = Inventory.browse(inv_id)
                if not inv.exists():
                    inv_id = False

            if not inv_id:
                inv = Inventory.create({'note': note})
            else:
                inv.write({'note': note})

            # Update lines
            inv.line_ids.unlink()
            line_vals = []
            for ld in lines_data:
                product = self.env['product.product'].browse(ld['product_id'])
                if not product.exists():
                    continue

                # Fetch current qty on hand for internal locations
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id.usage', '=', 'internal')
                ])
                qty_on_hand = sum(quants.mapped('quantity'))

                line_vals.append((0, 0, {
                    'product_id': product.id,
                    'qty_on_hand': qty_on_hand,
                    'qty_actual': ld.get('qty_actual', 0.0),
                    'price': product.standard_price or 0.0,
                }))

            if line_vals:
                inv.write({'line_ids': line_vals})

            if state == 'done':
                inv.action_validate()

            return inv.id
        except Exception as e:
            _logger.error('create_or_update_inventory: %s', e)
            raise

    @api.model
    def get_location_stock(self, product_ids, location_id):
        """Return on-hand qty for a list of products at a specific location."""
        if not product_ids or not location_id:
            return {}
        res = {}
        quants = self.env['stock.quant'].search([
            ('product_id', 'in', product_ids),
            ('location_id', '=', int(location_id))
        ])
        for q in quants:
            res[q.product_id.id] = (res.get(q.product_id.id, 0.0) + q.quantity)
        return res

    @api.model
    def create_or_update_transfer(self, vals):
        """Create or update a swift.stock.transfer record."""
        try:
            _logger.info('create_or_update_transfer: vals=%s', vals)
            transfer_id = vals.get('id', False)
            loc_dest_id = vals.get('loc_dest_id')
            note = vals.get('note', '')
            state = vals.get('state', 'draft')
            lines_data = vals.get('lines', [])

            # Default source location (first internal)
            loc_src = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
            if not loc_src:
                raise ValueError("No internal source location found")

            Transfer = self.env['swift.stock.transfer']

            transfer_vals = {
                'location_id': loc_src.id,
                'location_dest_id': int(loc_dest_id) if loc_dest_id else False,
                'note': str(note or ''),
                'state': str(state or 'draft'),
            }
            _logger.info('create_or_update_transfer: transfer_vals=%s', transfer_vals)

            if transfer_id:
                transfer = Transfer.browse(transfer_id)
                if transfer.exists():
                    transfer.write(transfer_vals)
                else:
                    transfer = Transfer.create(transfer_vals)
            else:
                transfer = Transfer.create(transfer_vals)

            # Update lines
            transfer.line_ids.unlink()
            line_vals = []
            for ld in lines_data:
                try:
                    product_id = int(ld['product_id'])
                    qty = float(ld.get('qty') or 0.0)
                    price = float(ld.get('price') or 0.0)
                    line_vals.append((0, 0, {
                        'product_id': product_id,
                        'qty': qty,
                        'price': price,
                    }))
                except (ValueError, TypeError) as ee:
                    _logger.warning('Skipping invalid line data: %s - %s', ld, ee)

            _logger.info('create_or_update_transfer: line_vals count=%s', len(line_vals))
            if line_vals:
                transfer.write({'line_ids': line_vals})

            return transfer.id
        except Exception as e:
            _logger.error('create_or_update_transfer: %s', e)
            raise

    @api.model
    def get_transfer_detail(self, transfer_id):
        """Fetch full details and lines for a stock transfer."""
        try:
            t = self.env['swift.stock.transfer'].browse(transfer_id)
            if not t.exists():
                return False
            lines = []
            for l in t.line_ids:
                lines.append({
                    'id': l.id,
                    'product_id': l.product_id.id,
                    'product_code': l.product_id.barcode or l.product_id.id,
                    'product_name': l.product_id.display_name,
                    'uom': l.product_id.uom_id.name if l.product_id.uom_id else '',
                    'qty': l.qty,
                    'received_qty': l.received_qty,
                    'price': l.price,
                })

            # Stock at current locations (if needed)
            product_ids = t.line_ids.mapped('product_id').ids
            stock_src = self.get_location_stock(product_ids, t.location_id.id)
            stock_dest = self.get_location_stock(product_ids, t.location_dest_id.id)

            # Map stock back to lines
            for l in lines:
                l['qty_on_hand'] = stock_src.get(l['product_id'], 0.0)
                l['qty_dest'] = stock_dest.get(l['product_id'], 0.0)

            return {
                'id': t.id,
                'name': t.name,
                'state': t.state,
                'note': t.note or '',
                'loc_src': t.location_id.display_name,
                'loc_src_id': t.location_id.id,
                'loc_dest': t.location_dest_id.display_name,
                'loc_dest_id': t.location_dest_id.id,
                'date_transfer': fields.Datetime.to_string(t.date_transfer),
                'sender': t.create_uid.name,
                'lines': lines,
            }
        except Exception as e:
            _logger.error('get_transfer_detail: %s', e)
            return False

    @api.model
    def action_receive_transfer(self, transfer_id, lines_data):
        """Set state to done and update received quantities."""
        try:
            t = self.env['swift.stock.transfer'].browse(transfer_id)
            if not t.exists():
                return False

            # Update line quantities
            for ld in lines_data:
                line = self.env['swift.stock.transfer.line'].browse(ld['id'])
                if line.exists():
                    line.write({'received_qty': ld['received_qty']})

            t.action_done()
            return True
        except Exception as e:
            _logger.error('action_receive_transfer: %s', e)
            return False

    # ──────────────────────────────────────────────────────────────
    # Stock Transfer (Chuyển Hàng) helpers
    # ──────────────────────────────────────────────────────────────

    @api.model
    def get_locations(self):
        """Return internal locations for filtering."""
        locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        return [{'id': l.id, 'name': l.display_name} for l in locations]

    @api.model
    def get_stock_transfers(self, filters=None):
        """Fetch stock transfers based on sidebar filters."""
        domain = []
        if filters:
            if filters.get('loc_src'):
                domain.append(('location_id', '=', int(filters['loc_src'])))
            if filters.get('loc_dest'):
                domain.append(('location_dest_id', '=', int(filters['loc_dest'])))
            if filters.get('states'):
                domain.append(('state', 'in', filters['states']))

            # Date filter (This Month, Today, etc.)
            if filters.get('date_range') == 'this_month':
                start, end = self._get_date_range('this_month', datetime.now())
                domain += [('date_transfer', '>=', start), ('date_transfer', '<=', end)]
            elif filters.get('date_range') == 'today':
                start, end = self._get_date_range('today', datetime.now())
                domain += [('date_transfer', '>=', start), ('date_transfer', '<=', end)]

        transfers = self.env['swift.stock.transfer'].search(domain, order='date_transfer desc')
        res = []
        for t in transfers:
            res.append({
                'id': t.id,
                'name': t.name,
                'date_transfer': fields.Datetime.to_string(t.date_transfer) if t.date_transfer else '',
                'date_receive': fields.Datetime.to_string(t.date_receive) if t.date_receive else '',
                'loc_src': t.location_id.display_name,
                'loc_dest': t.location_dest_id.display_name,
                'total_value': t.total_value,
                'state': t.state,
            })
        return res
