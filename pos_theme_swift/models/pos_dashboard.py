# -*- coding: utf-8 -*-
import random

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import pytz
import logging
_logger = logging.getLogger(__name__)

class PosDashboardSwift(models.AbstractModel):
    _name = 'pos.dashboard.swift'
    _description = 'POS Dashboard Logic for Swift'
    _swift_access_code_length = 6
    _swift_access_code_validity_minutes = 5

    def _swift_is_vietnamese(self):
        ctx_lang = self.env.context.get('lang') or ''
        user_lang = self.env.user.lang or ''
        return ctx_lang.lower().startswith('vi') or user_lang.lower().startswith('vi')

    def _swift_translate_status_label(self, text):
        if not self._swift_is_vietnamese():
            return text
        # Direct map as safety fallback if Odoo _() fails
        vi_map = {
            'Checked In': 'Đã chấm công vào',
            'Checked Out': 'Đã chấm công ra',
            'Not Checked In': 'Chưa chấm công vào',
            'Active': 'Đang làm việc',
            'Off': 'Đã nghỉ',
        }
        translated = _(text)
        if translated == text:
            return vi_map.get(text, text)
        return translated

    def _swift_normalize_branch_label(self, value):
        return (value or '').strip().casefold()

    def _swift_get_session_branch_name(self, pos_session_or_config_id):
        if not pos_session_or_config_id:
            return ''
        branch = self.env['pos.config'].sudo().browse(int(pos_session_or_config_id)).exists()
        if branch:
            return branch.name or branch.display_name or ''

        session = self.env['pos.session'].sudo().browse(int(pos_session_or_config_id)).exists()
        if session and session.config_id:
            return session.config_id.name or session.config_id.display_name or ''

        return ''

    def _swift_get_employee_branch_name(self, profile):
        if not profile:
            return ''
        return profile.work_branch or ''

    def _swift_get_pos_company_id(self, pos_session_or_config_id):
        if not pos_session_or_config_id:
            return False
        config = self.env['pos.config'].sudo().browse(int(pos_session_or_config_id)).exists()
        if config:
            return config.company_id.id

        session = self.env['pos.session'].sudo().browse(int(pos_session_or_config_id)).exists()
        if session and session.config_id:
            return session.config_id.company_id.id

        return False

    def _swift_get_employee_record(self, user, pos_session_or_config_id=False):
        if not user:
            return self.env['hr.employee']
        employee_model = self.env['hr.employee'].sudo()
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if profile and profile.hr_employee_id:
            employee = profile.hr_employee_id.sudo().exists()
            if employee:
                return employee
        company_id = self._swift_get_pos_company_id(pos_session_or_config_id)
        domain = [('user_id', '=', user.id)]
        if company_id:
            employee = employee_model.search(domain + [('company_id', '=', company_id)], limit=1)
            if employee:
                return employee
        return employee_model.search(domain, limit=1)

    def _swift_format_access_code(self, code):
        digits = ''.join(ch for ch in str(code or '') if ch.isdigit())
        return ' '.join(digits) if digits else ''

    def _swift_access_code_remaining_seconds(self, profile):
        expiry = profile.pos_access_code_expiry if profile else False
        if not expiry:
            return 0
        now_dt = fields.Datetime.now()
        return max(int((expiry - now_dt).total_seconds()), 0)

    def _swift_access_code_payload(self, profile):
        remaining_seconds = self._swift_access_code_remaining_seconds(profile)
        if not profile or not profile.pos_access_code or remaining_seconds <= 0:
            return {
                'code': '',
                'displayCode': '',
                'expiresAt': '',
                'remainingSeconds': 0,
            }
        return {
            'code': profile.pos_access_code,
            'displayCode': self._swift_format_access_code(profile.pos_access_code),
            'expiresAt': fields.Datetime.to_string(profile.pos_access_code_expiry),
            'remainingSeconds': remaining_seconds,
        }

    def _swift_clear_access_code(self, profile):
        if profile:
            profile.sudo().write({
                'pos_access_code': False,
                'pos_access_code_expiry': False,
            })

    def _swift_get_profile_by_access_code(self, access_code):
        clean_code = ''.join(ch for ch in str(access_code or '') if ch.isdigit())
        if not clean_code:
            return False
        profile = self.env['swift.employee.profile'].sudo().search([
            ('pos_access_code', '=', clean_code),
        ], limit=1)
        if not profile:
            return False
        if self._swift_access_code_remaining_seconds(profile) <= 0:
            self._swift_clear_access_code(profile)
            return False
        return profile

    def _swift_generate_unique_access_code(self):
        profile_model = self.env['swift.employee.profile'].sudo()
        for _attempt in range(20):
            code = ''.join(random.choices('0123456789', k=self._swift_access_code_length))
            duplicate = profile_model.search([
                ('pos_access_code', '=', code),
                ('pos_access_code_expiry', '>', fields.Datetime.now()),
            ], limit=1)
            if not duplicate:
                return code
        return ''.join(random.choices('0123456789', k=self._swift_access_code_length))

    def _swift_get_job_title_options(self):
        try:
            job_model = self.env['hr.job']
        except Exception:
            job_model = False

        if job_model:
            jobs = job_model.sudo().search([], order='name asc')
            rows = []
            for job in jobs:
                rows.append({
                    'id': job.id,
                    'name': job.name or '',
                })
            return rows

        profiles = self.env['swift.employee.profile'].sudo().search([])
        job_titles = sorted({(profile.job_title or '').strip() for profile in profiles if (profile.job_title or '').strip()})
        return [{'id': title, 'name': title} for title in job_titles]

    def _swift_log_pos_access(self, employee_id, pos_session_or_config_id, status='success'):
        try:
            pos_session = False
            if pos_session_or_config_id:
                session = self.env['pos.session'].sudo().browse(int(pos_session_or_config_id)).exists()
                if session:
                    pos_session = session.id
                else:
                    config = self.env['pos.config'].sudo().browse(int(pos_session_or_config_id)).exists()
                    if config:
                        session = self.env['pos.session'].sudo().search([('config_id', '=', config.id)], limit=1, order='id desc')
                        pos_session = session.id if session else False
            self.env['swift.pos.access.log'].sudo().create({
                'employee_id': int(employee_id),
                'pos_session_id': pos_session,
                'access_time': fields.Datetime.now(),
                'status': status,
            })
        except Exception as e:
            _logger.warning('Failed to log POS access: %s', e)

    def _partner_phone_value(self, partner):
        if not partner:
            return ''
        if 'phone' in partner._fields and partner.phone:
            return partner.phone
        if 'mobile' in partner._fields and partner.mobile:
            return partner.mobile
        return ''

    def _write_partner_phone(self, partner, phone):
        if not partner:
            return
        vals = {}
        if 'phone' in partner._fields:
            vals['phone'] = phone
        if 'mobile' in partner._fields:
            vals['mobile'] = phone
        if vals:
            partner.sudo().write(vals)

    def _to_float_amount(self, value, default=0.0):
        if value in (None, False, ''):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return default
        s = s.replace(' ', '')
        filtered = ''.join(ch for ch in s if ch.isdigit() or ch in ',.-')
        if not filtered:
            return default
        # Support common VN number formats: 1.000.000 or 1,000,000
        if filtered.count('.') > 1 and ',' not in filtered:
            filtered = filtered.replace('.', '')
        if filtered.count(',') > 1 and '.' not in filtered:
            filtered = filtered.replace(',', '')
        if ',' in filtered and '.' in filtered:
            if filtered.rfind(',') > filtered.rfind('.'):
                filtered = filtered.replace('.', '').replace(',', '.')
            else:
                filtered = filtered.replace(',', '')
        elif ',' in filtered:
            filtered = filtered.replace(',', '.')
        try:
            return float(filtered)
        except Exception:
            return default

    def _to_date_value(self, value):
        if not value:
            return False
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return False
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(raw, fmt).date()
                except Exception:
                    continue
        try:
            return fields.Date.to_date(value)
        except Exception:
            return False

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
            return _('%s days ago') % diff.days
        hours = diff.seconds // 3600
        if hours > 0:
            return _('%s hours ago') % hours
        mins = (diff.seconds % 3600) // 60
        if mins > 0:
            return _('%s minutes ago') % mins
        return _('just now')

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

    def _get_pos_config(self, config_id=False):
        PosConfig = self.env['pos.config'].sudo()
        if config_id:
            return PosConfig.browse(int(config_id)).exists()
        if self.env.context.get('pos_config_id'):
            return PosConfig.browse(int(self.env.context['pos_config_id'])).exists()
        return PosConfig.browse()

    def _get_pos_stock_location(self, config=False):
        config = config or self._get_pos_config()
        if not config:
            return False
        if config.swift_warehouse_id and config.swift_warehouse_id.lot_stock_id:
            return config.swift_warehouse_id.lot_stock_id
        if config.picking_type_id.default_location_src_id:
            return config.picking_type_id.default_location_src_id
        return False

    def _get_pos_config_by_location(self, location):
        if not location:
            return self.env['pos.config'].browse()
        # 1. Search by warehouse lot_stock_id
        config = self.env['pos.config'].sudo().search([
            ('active', '=', True),
            ('swift_warehouse_id.lot_stock_id', '=', location.id),
        ], limit=1)
        if config:
            return config
        # 2. Fallback to picking type
        return self.env['pos.config'].sudo().search([
            ('active', '=', True),
            ('picking_type_id.default_location_src_id', '=', location.id),
        ], limit=1)

    def _get_pos_branch_location_rows(self):
        configs = self.env['pos.config'].sudo().search([('active', '=', True)])
        rows = []
        for config in configs:
            location = self._get_pos_stock_location(config)
            if not location:
                continue
            rows.append({
                'id': config.id,
                'config_id': config.id,
                'name': config.name,
                'location_id': location.id,
                'location_name': location.display_name,
            })
        return rows

    def _get_location_branch_name_map(self):
        return {
            row['location_id']: row['name']
            for row in self._get_pos_branch_location_rows()
        }

    def _get_location_branch_label(self, location, branch_map=None):
        if not location:
            return ''
        branch_map = branch_map or self._get_location_branch_name_map()
        return branch_map.get(location.id, location.display_name)

    @api.model
    def get_inventory_products(self, keyword='', config_id=False):
        """Return products with current on-hand quantity for inventory lines."""
        config = self._get_pos_config(config_id)
        if not config:
            return []

        domain = [
            ('available_in_pos', '=', True),
            ('active', '=', True),
            ('product_tmpl_id.swift_branch_config_ids', 'in', config.ids),
        ]
        if config.limit_categories and config.iface_available_categ_ids:
            domain.append(('pos_categ_ids', 'in', config.iface_available_categ_ids.ids))
        if keyword:
            domain += ['|',
                ('name', 'ilike', keyword),
                ('barcode', 'ilike', keyword),
            ]
        products = self.env['product.product'].search(domain, limit=200)
        location = self._get_pos_stock_location(config)
        res = []
        for p in products:
            # get stock for all warehouses
            quant_domain = [('product_id', '=', p.id), ('location_id.usage', '=', 'internal')]
            if location:
                quant_domain.append(('location_id', 'child_of', location.id))
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
                    'config_id': r.config_id.id if r.config_id else False,
                    'branch_name': r.config_id.name if r.config_id else '',
                    'date': fields.Datetime.to_string(r.date) if r.date else '',
                    'status': r.state if r.state else 'draft',
                })
        except Exception as e:
            _logger.warning('get_recent_inventories: %s', e)
        return res

    @api.model
    def get_products_by_barcodes(self, barcodes, config_id=False):
        """Look up products by barcode list, returning product info + stock qty."""
        if not barcodes:
            return []
        res = []
        try:
            config = self._get_pos_config(config_id)
            if not config:
                return []
            domain = [
                ('barcode', 'in', barcodes),
                ('product_tmpl_id.swift_branch_config_ids', 'in', config.ids),
            ]
            products = self.env['product.product'].search(domain)
            location = self._get_pos_stock_location(config)
            for p in products:
                # Get internal stock
                quant_domain = [
                    ('product_id', '=', p.id),
                    ('location_id.usage', '=', 'internal'),
                ]
                if location:
                    quant_domain.append(('location_id', 'child_of', location.id))
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
        except Exception as e:
            _logger.warning('get_products_by_barcodes: %s', e)
        return res

    @api.model
    def get_inventory_detail(self, inventory_id):
        """Load an existing swift.stock.inventory record including lines.

        qty_on_hand is returned as the LIVE current stock (from stock.quant),
        not the stored snapshot, so col-num always reflects the real on-hand
        quantity after any adjustments.
        """
        try:
            inv = self.env['swift.stock.inventory'].browse(inventory_id)
            if not inv.exists():
                return False

            # Pre-fetch current quant quantities for all products in one query.
            product_ids = inv.line_ids.mapped('product_id').ids
            quant_domain = [
                ('product_id', 'in', product_ids),
                ('location_id.usage', '=', 'internal'),
            ]
            location = self._get_pos_stock_location(inv.config_id)
            if location:
                quant_domain.append(('location_id', 'child_of', location.id))
            quants = self.env['stock.quant'].search(quant_domain)
            live_qty = {}
            for q in quants:
                live_qty[q.product_id.id] = live_qty.get(q.product_id.id, 0.0) + q.quantity

            lines = []
            for line in inv.line_ids:
                pid = line.product_id.id
                lines.append({
                    'product_id': pid,
                    'product_name': line.product_id.display_name,
                    'barcode': line.product_id.barcode or '',
                    'uom': line.product_id.uom_id.name if line.product_id.uom_id else '',
                    'qty_on_hand': live_qty.get(pid, 0.0),   # live stock — not stored snapshot
                    'qty_actual': line.qty_actual,
                    'diff': line.diff,
                    'diff_value': line.diff_value,
                    'price': line.price,
                })
            return {
                'id': inv.id,
                'name': inv.name,
                'config_id': inv.config_id.id if inv.config_id else False,
                'branch_name': inv.config_id.name if inv.config_id else '',
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
            config_id = vals.get('config_id', False)
            note     = vals.get('note', '')
            state    = vals.get('state', 'draft')
            lines_data = vals.get('lines', [])

            Inventory = self.env['swift.stock.inventory']
            config = self._get_pos_config(config_id)
            if not config:
                raise UserError(_('Please select a POS branch before saving inventory data.'))

            if inv_id:
                inv = Inventory.browse(inv_id)
                if not inv.exists():
                    inv_id = False

            if not inv_id:
                inv = Inventory.create({'note': note, 'config_id': config.id if config else False})
            else:
                inv.write({'note': note, 'config_id': config.id if config else False})

            # Update lines
            inv.line_ids.unlink()
            line_vals = []
            location = self._get_pos_stock_location(config or inv.config_id)
            for ld in lines_data:
                product = self.env['product.product'].browse(ld['product_id'])
                if not product.exists():
                    continue

                # Fetch current qty on hand for internal locations
                quant_domain = [
                    ('product_id', '=', product.id),
                    ('location_id.usage', '=', 'internal')
                ]
                if location:
                    quant_domain.append(('location_id', 'child_of', location.id))
                quants = self.env['stock.quant'].search(quant_domain)
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
            config_id = vals.get('config_id', False)
            dest_config_id = vals.get('dest_config_id', False)
            loc_dest_id = vals.get('loc_dest_id')
            loc_src_id = vals.get('loc_src_id')
            note = vals.get('note', '')
            state = vals.get('state', 'draft')
            lines_data = vals.get('lines', [])

            config = self._get_pos_config(config_id)
            dest_config = self._get_pos_config(dest_config_id)
            if not config:
                raise UserError(_('Please select a source branch.'))
            if not dest_config:
                raise UserError(_('Please select a destination branch.'))
            if config.id == dest_config.id:
                raise UserError(_('Source branch and destination branch must be different.'))
            loc_src = False
            if config:
                loc_src = self._get_pos_stock_location(config)
            if not loc_src and loc_src_id:
                loc_src = self.env['stock.location'].browse(int(loc_src_id)).exists()
            if not loc_src:
                raise UserError(_("Source branch '%s' does not have a stock location configured.") % config.display_name)

            loc_dest = False
            if dest_config:
                loc_dest = self._get_pos_stock_location(dest_config)
            if not loc_dest and loc_dest_id:
                loc_dest = self.env['stock.location'].browse(int(loc_dest_id)).exists()
            if not loc_dest:
                raise UserError(_("Destination branch '%s' does not have a stock location configured.") % dest_config.display_name)

            if not config and loc_src:
                config = self._get_pos_config_by_location(loc_src)
            if not dest_config and loc_dest:
                dest_config = self._get_pos_config_by_location(loc_dest)
            if loc_src.id == loc_dest.id:
                raise UserError(_('Source branch and destination branch cannot use the same stock location.'))

            Transfer = self.env['swift.stock.transfer']

            transfer_vals = {
                'source_config_id': config.id if config else False,
                'dest_config_id': dest_config.id if dest_config else False,
                'location_id': loc_src.id,
                'location_dest_id': loc_dest.id,
                'note': str(note or ''),
                'state': str(state or 'draft'),
            }
            _logger.info('create_or_update_transfer: transfer_vals=%s', transfer_vals)

            if transfer_id:
                transfer = Transfer.browse(transfer_id)
                if transfer.exists() and transfer.state == 'draft':
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

            return {
                'id': transfer.id,
                'name': transfer.name,
                'state': transfer.state,
            }
        except Exception as e:
            _logger.error('create_or_update_transfer: %s', e)
            raise

    @api.model
    def get_transfer_detail(self, transfer_id, config_id=False):
        """Fetch full details and lines for a stock transfer."""
        try:
            t = self.env['swift.stock.transfer'].browse(transfer_id)
            if not t.exists():
                return False
            current_config = self._get_pos_config(config_id)
            current_location = self._get_pos_stock_location(current_config)
            branch_map = self._get_location_branch_name_map()
            lines = []
            for l in t.line_ids:
                received_qty = l.received_qty
                if current_config and t.dest_config_id.id == current_config.id and t.state == 'shipped' and not received_qty:
                    received_qty = l.qty
                lines.append({
                    'id': l.id,
                    'product_id': l.product_id.id,
                    'product_code': l.product_id.barcode or l.product_id.id,
                    'product_name': l.product_id.display_name,
                    'uom': l.product_id.uom_id.name if l.product_id.uom_id else '',
                    'qty': l.qty,
                    'received_qty': received_qty,
                    'price': l.price,
                })

            # Stock at current locations (if needed)
            product_ids = t.line_ids.mapped('product_id').ids
            stock_src = self.get_location_stock(product_ids, t.location_id.id)
            stock_dest = self.get_location_stock(product_ids, t.location_dest_id.id)

            direction = 'other'
            can_receive = False
            can_edit = t.state == 'draft'
            is_dest_branch = False
            is_source_branch = False
            if current_config:
                is_dest_branch = (
                    t.dest_config_id.id == current_config.id or
                    (current_location and t.location_dest_id.id == current_location.id)
                )
                is_source_branch = (
                    t.source_config_id.id == current_config.id or
                    (current_location and t.location_id.id == current_location.id)
                )
                if is_dest_branch:
                    direction = 'inbound'
                    can_receive = t.state == 'shipped'
                    can_edit = False
                elif is_source_branch:
                    direction = 'outbound'

            # Map stock back to lines based on the branch perspective used to open the transfer.
            for l in lines:
                qty_source = stock_src.get(l['product_id'], 0.0)
                qty_destination = stock_dest.get(l['product_id'], 0.0)
                l['qty_source'] = qty_source
                l['qty_destination'] = qty_destination
                l['qty_dest'] = qty_destination
                if is_dest_branch:
                    l['qty_on_hand'] = qty_destination
                else:
                    l['qty_on_hand'] = qty_source

            return {
                'id': t.id,
                'name': t.name,
                'state': t.state,
                'note': t.note or '',
                'loc_src': t.source_config_id.name or self._get_location_branch_label(t.location_id, branch_map),
                'loc_src_id': t.location_id.id,
                'loc_src_config_id': t.source_config_id.id if t.source_config_id else False,
                'loc_dest': t.dest_config_id.name or self._get_location_branch_label(t.location_dest_id, branch_map),
                'loc_dest_id': t.location_dest_id.id,
                'loc_dest_config_id': t.dest_config_id.id if t.dest_config_id else False,
                'date_transfer': fields.Datetime.to_string(t.date_transfer),
                'date_receive': fields.Datetime.to_string(t.date_receive) if t.date_receive else '',
                'sender': t.create_uid.name,
                'total_value': t.total_value,
                'lines': lines,
                'direction': direction,
                'can_receive': can_receive,
                'can_edit': can_edit,
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
                raise UserError(_('Stock transfer not found.'))

            t.action_receive_goods(lines_data)
            return True
        except Exception as e:
            _logger.error('action_receive_transfer: %s', e)
            raise

    # ──────────────────────────────────────────────────────────────
    # Stock Transfer (Chuyển Hàng) helpers
    # ──────────────────────────────────────────────────────────────

    @api.model
    def get_locations(self):
        """Return internal locations for filtering."""
        return self._get_pos_branch_location_rows()

    @api.model
    def get_stock_transfers(self, filters=None, config_id=False):
        """Fetch stock transfers based on sidebar filters."""
        domain = []
        current_config = self._get_pos_config(config_id)
        current_location = self._get_pos_stock_location(current_config)
        user_tz = self.env.user.tz or 'UTC'
        now_local = datetime.now(pytz.timezone(user_tz))
        if filters:
            if filters.get('states'):
                domain.append(('state', 'in', filters['states']))

            # Date filter (This Month, Today, etc.)
            if filters.get('date_range') == 'this_month':
                start, end = self._get_date_range('this_month', now_local)
                domain += [('date_transfer', '>=', start), ('date_transfer', '<=', end)]
            elif filters.get('date_range') == 'today':
                start, end = self._get_date_range('today', now_local)
                domain += [('date_transfer', '>=', start), ('date_transfer', '<=', end)]

        transfers = self.env['swift.stock.transfer'].search(domain, order='date_transfer desc')
        branch_map = self._get_location_branch_name_map()
        res = []
        for t in transfers:
            direction = 'other'
            can_receive = False
            if current_config:
                is_dest_branch = (
                    t.dest_config_id.id == current_config.id or
                    (current_location and t.location_dest_id.id == current_location.id)
                )
                is_source_branch = (
                    t.source_config_id.id == current_config.id or
                    (current_location and t.location_id.id == current_location.id)
                )
                if is_dest_branch:
                    direction = 'inbound'
                    can_receive = t.state == 'shipped'
                elif is_source_branch:
                    direction = 'outbound'
            res.append({
                'id': t.id,
                'name': t.name,
                'date_transfer': fields.Datetime.to_string(t.date_transfer) if t.date_transfer else '',
                'date_receive': fields.Datetime.to_string(t.date_receive) if t.date_receive else '',
                'loc_src': t.source_config_id.name or self._get_location_branch_label(t.location_id, branch_map),
                'loc_src_id': t.location_id.id,
                'loc_src_config_id': t.source_config_id.id if t.source_config_id else False,
                'loc_dest': t.dest_config_id.name or self._get_location_branch_label(t.location_dest_id, branch_map),
                'loc_dest_id': t.location_dest_id.id,
                'loc_dest_config_id': t.dest_config_id.id if t.dest_config_id else False,
                'total_value': t.total_value,
                'state': t.state,
                'direction': direction,
                'can_receive': can_receive,
            })
        return res

    # ──────────────────────────────────────────────────────────────
    # Shift Management (Ca làm việc) helpers
    # ──────────────────────────────────────────────────────────────

    @api.model
    def get_shift_init_data(self):
        """Return everything the client needs to start the shift management UI."""
        user = self.env.user
        config = self._get_pos_config()

        # Current status
        shift = self.env['swift.staff.shift'].search([
            ('employee_id', '=', user.id),
            ('state', '=', 'active')
        ], limit=1)

        status = {
            'state': 'active' if shift else 'idle',
            'check_in': fields.Datetime.to_string(shift.check_in) if shift else False,
        }

        return {
            'user_name': user.name,
            'branch_name': config.name if config else _('Branch'),
            'status': status,
            'stats': self.get_shift_stats(),
        }

    @api.model
    def get_shift_stats(self):
        """Calculate total hours worked today and this week for the user."""
        user_id = self.env.uid

        # Determine local date range
        user_tz = self.env.user.tz or 'UTC'
        local = pytz.timezone(user_tz)
        now_local = datetime.now(local)

        start_today, _ = self._get_date_range('today', now_local)
        start_week, _ = self._get_date_range('this_week', now_local)

        def get_total_hours(start_date):
            shifts = self.env['swift.staff.shift'].search([
                ('employee_id', '=', user_id),
                ('check_in', '>=', start_date),
                ('state', '=', 'done')
            ])
            return sum(shifts.mapped('duration'))

        return {
            'today': get_total_hours(start_today),
            'week': get_total_hours(start_week),
        }

    @api.model
    def get_shift_status(self):
        """Return the current active shift for the user."""
        shift = self.env['swift.staff.shift'].search([
            ('employee_id', '=', self.env.uid),
            ('state', '=', 'active')
        ], limit=1)
        if shift:
            return {
                'id': shift.id,
                'check_in': fields.Datetime.to_string(shift.check_in),
                'state': 'active',
            }
        return {'state': 'idle'}

    @api.model
    def action_shift_toggle(self, note=''):
        """Toggle check-in/out for the current user."""
        shift = self.env['swift.staff.shift'].search([
            ('employee_id', '=', self.env.uid),
            ('state', '=', 'active')
        ], limit=1)
        if shift:
            shift.write({
                'check_out': fields.Datetime.now(),
                'state': 'done',
                'note': note
            })
            return {'state': 'idle'}
        else:
            new_shift = self.env['swift.staff.shift'].create({
                'employee_id': self.env.uid,
                'check_in': fields.Datetime.now(),
                'state': 'active',
                'note': note
            })
            return {
                'id': new_shift.id,
                'check_in': fields.Datetime.to_string(new_shift.check_in),
                'state': 'active'
            }

    @api.model
    def get_recent_shifts(self, limit=10):
        """Return the most recent shifts for the current user."""
        shifts = self.env['swift.staff.shift'].search([
            ('employee_id', '=', self.env.uid)
        ], limit=limit, order='check_in desc')
        res = []
        for s in shifts:
            res.append({
                'id': s.id,
                'check_in': fields.Datetime.to_string(s.check_in),
                'check_out': fields.Datetime.to_string(s.check_out) if s.check_out else '',
                'duration': s.duration,
                'state': s.state,
                'note': s.note or '',
            })
        return res

    # ──────────────────────────────────────────────────────────────
    # Paycheck (Bảng lương) helpers
    # ──────────────────────────────────────────────────────────────

    def _fmt_date_vi(self, value):
        if not value:
            return ''
        return value.strftime('%d/%m/%Y')

    def _fmt_datetime_vi(self, value):
        if not value:
            return ''
        local_dt = fields.Datetime.context_timestamp(self, value)
        return local_dt.strftime('%d/%m/%Y %H:%M:%S')

    @api.model
    def get_paycheck_records(self, keyword=''):
        domain = []
        kw = (keyword or '').strip()
        if kw:
            domain += ['|', '|',
                ('name', 'ilike', kw),
                ('title', 'ilike', kw),
                ('branch_name', 'ilike', kw),
            ]

        state_map = {
            'draft': _('Đang tạo'),
            'temporary': _('Tạm tính'),
            'finalized': _('Đã chốt lương'),
            'cancelled': _('Đã hủy'),
        }
        cycle_map = {
            'monthly': _('Hàng tháng'),
        }

        records = self.env['swift.paycheck'].search(domain, order='date_from desc, id desc', limit=200)
        result = []
        for rec in records:
            payslips = []
            for line in rec.line_ids.sorted('id'):
                payslips.append({
                    'id': line.id,
                    'code': line.name,
                    'employee': line.user_id.name or '',
                    'salary': line.amount,
                    'paid': line.paid_amount,
                    'remaining': line.remaining_amount,
                })

            history = []
            for pay in sorted(rec.payment_ids, key=lambda p: p.payment_time or fields.Datetime.now(), reverse=True):
                history.append({
                    'id': pay.id,
                    'time': self._fmt_datetime_vi(pay.payment_time),
                    'method': _('Tiền mặt') if pay.method == 'cash' else _('Chuyển khoản'),
                    'amount': pay.amount,
                    'note': pay.note or '',
                    'user': pay.user_id.name or '',
                })

            result.append({
                'id': rec.id,
                'code': rec.name,
                'name': rec.title,
                'cycle': cycle_map.get(rec.cycle, rec.cycle),
                'period': f"{self._fmt_date_vi(rec.date_from)} - {self._fmt_date_vi(rec.date_to)}",
                'branch': rec.branch_name or '',
                'totalSalary': rec.total_salary,
                'paidToEmployee': rec.paid_amount,
                'remaining': rec.remaining_amount,
                'status': state_map.get(rec.state, rec.state),
                'createdAt': self._fmt_datetime_vi(rec.create_date),
                'createdBy': rec.create_uid.name or '',
                'preparedBy': rec.create_uid.name or '',
                'employeeCount': rec.employee_count,
                'scope': _('Tất cả nhân viên'),
                'finalizedBy': rec.write_uid.name if rec.state == 'finalized' else '',
                'note': rec.note or '',
                'lastUpdated': self._fmt_datetime_vi(rec.write_date),
                'payslips': payslips,
                'history': history,
            })
        return result

    @api.model
    def action_create_paycheck(self):
        paycheck = self.env['swift.paycheck'].create_default_paycheck()
        return {
            'id': paycheck.id,
            'code': paycheck.name,
        }

    @api.model
    def action_paycheck_pay(self, paycheck_id, method='cash', note=''):
        paycheck = self.env['swift.paycheck'].browse(int(paycheck_id))
        if not paycheck.exists():
            return {'ok': False, 'message': _('Paycheck not found')}

        remaining = paycheck.remaining_amount
        if remaining <= 0:
            return {'ok': False, 'message': _('No remaining amount to pay')}

        self.env['swift.paycheck.payment'].create({
            'paycheck_id': paycheck.id,
            'amount': remaining,
            'method': method if method in ('cash', 'bank') else 'cash',
            'note': note or '',
        })

        for line in paycheck.line_ids:
            if line.remaining_amount > 0:
                line.paid_amount = line.amount

        paycheck.state = 'finalized'
        return {'ok': True}

    # ──────────────────────────────────────────────────────────────
    # Attendance (Bảng chấm công) helpers
    # ──────────────────────────────────────────────────────────────

    def _get_attendance_staff_users(self, keyword=''):
        group_ids = []
        grp_user = self.env.ref("point_of_sale.group_pos_user", raise_if_not_found=False)
        grp_manager = self.env.ref("point_of_sale.group_pos_manager", raise_if_not_found=False)
        if grp_user:
            group_ids.append(grp_user.id)
        if grp_manager:
            group_ids.append(grp_manager.id)

        domain = [('active', '=', True), ('share', '=', False)]
        if group_ids:
            domain.append(('group_ids', 'in', group_ids))
        if keyword:
            domain += ['|', ('name', 'ilike', keyword), ('login', 'ilike', keyword)]
        users = self.env['res.users'].sudo().search(domain, order='name asc')

        # Keep current internal user visible in HR-like submenus even when
        # group assignment was recently changed and cache/session is stale.
        current_user = self.env.user.sudo()
        if current_user.exists() and current_user.active and not current_user.share:
            matched_keyword = True
            if keyword:
                kw = (keyword or '').strip().lower()
                matched_keyword = kw in (current_user.name or '').lower() or kw in (current_user.login or '').lower()
            if matched_keyword and current_user not in users:
                users |= current_user

        return users.sorted(lambda u: (u.name or '').lower())

    def _get_week_range_from_offset(self, week_offset=0):
        today = fields.Date.context_today(self)
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7 * int(week_offset or 0))
        sunday = monday + timedelta(days=6)
        return monday, sunday

    @api.model
    def get_attendance_overview(self, week_offset=0, keyword=''):
        start_date, end_date = self._get_week_range_from_offset(week_offset)
        try:
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())

            users = self._get_attendance_staff_users(keyword)
            shifts = self.env['swift.staff.shift'].sudo().search([
                ('employee_id', 'in', users.ids),
                ('check_in', '>=', fields.Datetime.to_string(start_dt)),
                ('check_in', '<=', fields.Datetime.to_string(end_dt)),
            ], order='check_in asc')

            by_user = {}
            for shift in shifts:
                by_user.setdefault(shift.employee_id.id, []).append(shift)

            has_employee_model = 'hr.employee' in self.env
            has_contract_model = 'hr.contract' in self.env
            rows = []

            for user in users:
                user_shifts = by_user.get(user.id, [])
                worked_hours = 0.0
                worked_dates = set()

                for s in user_shifts:
                    if s.check_in:
                        worked_dates.add(fields.Datetime.context_timestamp(self, s.check_in).date())
                    if s.state == 'done' and s.duration:
                        worked_hours += s.duration
                    elif s.state == 'active' and s.check_in:
                        now = fields.Datetime.now()
                        diff = now - s.check_in
                        worked_hours += max(diff.total_seconds(), 0.0) / 3600.0

                worked_days = len(worked_dates)
                off_days = max(7 - worked_days, 0)
                overtime = max(worked_hours - (worked_days * 8.0), 0.0)

                employee_code = f"NV{str(user.id).zfill(6)}"
                salary_type = _('Chưa thiết lập')
                if has_employee_model:
                    employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
                    if employee:
                        employee_code = employee.barcode or employee.identification_id or employee_code
                        if has_contract_model:
                            contract = self.env['hr.contract'].sudo().search([
                                ('employee_id', '=', employee.id),
                                ('state', 'in', ['open', 'running']),
                            ], order='date_start desc, id desc', limit=1)
                            if contract:
                                salary_type = _('Theo ngày công chuẩn')

                rows.append({
                    'userId': user.id,
                    'employeeName': user.name,
                    'employeeCode': employee_code,
                    'salaryType': salary_type,
                    'workedDays': worked_days,
                    'workedHours': round(worked_hours, 2),
                    'offDays': off_days,
                    'late': 0,
                    'early': 0,
                    'overtime': round(overtime, 2),
                    'hasData': bool(user_shifts),
                })
        except Exception as e:
            _logger.exception("get_attendance_overview failed: %s", e)
            rows = []

        return {
            'weekStart': fields.Date.to_string(start_date),
            'weekEnd': fields.Date.to_string(end_date),
            'weekLabel': _('Tuần %s - Th %s %s') % (start_date.isocalendar().week, start_date.month, start_date.year),
            'rows': rows,
        }

    @api.model
    def get_attendance_employee_detail(self, user_id, week_start, week_end):
        try:
            user = self.env['res.users'].sudo().browse(int(user_id))
            if not user.exists():
                return {'ok': False, 'message': _('Employee not found')}

            start_date = fields.Date.to_date(week_start)
            end_date = fields.Date.to_date(week_end)
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.max.time())

            pos_config = self._get_pos_config()
            branch_name = pos_config.name if pos_config else _('Chi nhánh trung tâm')

            shifts = self.env['swift.staff.shift'].sudo().search([
                ('employee_id', '=', user.id),
                ('check_in', '>=', fields.Datetime.to_string(start_dt)),
                ('check_in', '<=', fields.Datetime.to_string(end_dt)),
            ], order='check_in asc')

            rows = []
            total_hours = 0.0
            for s in shifts:
                check_in_local = fields.Datetime.context_timestamp(self, s.check_in) if s.check_in else False
                check_out_local = fields.Datetime.context_timestamp(self, s.check_out) if s.check_out else False

                hours = s.duration or 0.0
                if s.state == 'active' and s.check_in:
                    now = fields.Datetime.now()
                    hours = max((now - s.check_in).total_seconds(), 0.0) / 3600.0
                total_hours += hours

                time_range = '--:--'
                if check_in_local and check_out_local:
                    time_range = f"{check_in_local.strftime('%H:%M')} - {check_out_local.strftime('%H:%M')}"
                elif check_in_local:
                    time_range = f"{check_in_local.strftime('%H:%M')} - --:--"

                rows.append({
                    'date': check_in_local.strftime('%d/%m/%Y') if check_in_local else '',
                    'dayType': _('Ngày thường'),
                    'shiftName': s.note or _('Ca làm việc'),
                    'branch': branch_name,
                    'timeRange': time_range,
                    'hours': round(hours, 2),
                    'workday': round(hours / 8.0, 2),
                })

            employee_code = f"NV{str(user.id).zfill(6)}"
            if 'hr.employee' in self.env:
                employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
                if employee:
                    employee_code = employee.barcode or employee.identification_id or employee_code

            return {
                'ok': True,
                'employeeName': user.name,
                'employeeCode': employee_code,
                'from': start_date.strftime('%d/%m/%Y'),
                'to': end_date.strftime('%d/%m/%Y'),
                'totalHours': round(total_hours, 2),
                'totalDays': round(total_hours / 8.0, 2),
                'rows': rows,
            }
        except Exception as e:
            _logger.exception("get_attendance_employee_detail failed: %s", e)
            return {'ok': False, 'message': _('Cannot load employee attendance detail')}

    @api.model
    def action_approve_attendance(self, week_start, week_end, user_id=False):
        """Approve attendance records (done shifts) for a week."""
        try:
            start_date = fields.Date.to_date(week_start)
            end_date = fields.Date.to_date(week_end)
            base_domain = [
                ('state', 'in', ['done', 'active']),
                ('check_in', '!=', False),
            ]
            if user_id:
                base_domain.append(('employee_id', '=', int(user_id)))
            else:
                # Keep approval scope aligned with attendance table scope.
                users = self._get_attendance_staff_users('')
                base_domain.append(('employee_id', 'in', users.ids))

            all_candidates = self.env['swift.staff.shift'].sudo().search(base_domain)
            total_in_week = self.env['swift.staff.shift'].sudo().browse()
            for s in all_candidates:
                local_in = fields.Datetime.context_timestamp(self, s.check_in).date() if s.check_in else False
                if local_in and start_date <= local_in <= end_date:
                    total_in_week |= s

            shifts = total_in_week.filtered(lambda s: not s.is_approved)
            already_count = len(total_in_week) - len(shifts)

            if not shifts:
                return {'ok': True, 'count': 0, 'already_count': already_count}

            shifts.write({
                'is_approved': True,
                'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(),
            })
            return {'ok': True, 'count': len(shifts), 'already_count': already_count}
        except Exception as e:
            _logger.exception("action_approve_attendance failed: %s", e)
            return {'ok': False, 'count': 0}

    # ──────────────────────────────────────────────────────────────
    # Work Schedule (Lịch làm việc) helpers
    # ──────────────────────────────────────────────────────────────

    def _schedule_day_label(self, day):
        labels = {
            0: _('Thứ hai'),
            1: _('Thứ ba'),
            2: _('Thứ tư'),
            3: _('Thứ năm'),
            4: _('Thứ sáu'),
            5: _('Thứ bảy'),
            6: _('Chủ nhật'),
        }
        return labels.get(day.weekday(), '')

    def _get_user_contract_wage(self, user):
        if 'hr.employee' not in self.env or 'hr.contract' not in self.env:
            return 0.0
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
        if not employee:
            return 0.0
        contract = self.env['hr.contract'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', 'in', ['open', 'running']),
        ], order='date_start desc, id desc', limit=1)
        return (contract.wage or 0.0) if contract else 0.0

    @api.model
    def get_work_schedule_overview(self, week_offset=0, keyword=''):
        start_date, end_date = self._get_week_range_from_offset(week_offset)
        users = self._get_attendance_staff_users(keyword)

        days = []
        day = start_date
        while day <= end_date:
            days.append({
                'date': fields.Date.to_string(day),
                'label': self._schedule_day_label(day),
                'day': day.day,
                'weekdayIndex': day.weekday(),
            })
            day += timedelta(days=1)

        lines = self.env['swift.work.schedule.line'].sudo().search([
            ('employee_id', 'in', users.ids),
            ('date', '>=', start_date),
            ('date', '<=', end_date),
        ], order='date asc, id asc')

        by_emp_date = {}
        for line in lines:
            by_emp_date.setdefault(line.employee_id.id, {}).setdefault(fields.Date.to_string(line.date), []).append({
                'id': line.id,
                'name': line.shift_template_id.name,
                'start': line.shift_template_id.start_hour,
                'end': line.shift_template_id.end_hour,
                'color': line.shift_template_id.color_class or 'blue',
                'duration': line.shift_template_id.duration_hours or 0.0,
            })

        rows = []
        for user in users:
            emp_code = f"NV{str(user.id).zfill(6)}"
            if 'hr.employee' in self.env:
                employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
                if employee:
                    emp_code = employee.barcode or employee.identification_id or emp_code

            day_data = by_emp_date.get(user.id, {})
            total_hours = 0.0
            total_shifts = 0
            for d in day_data.values():
                for s in d:
                    total_hours += s.get('duration', 0.0)
                    total_shifts += 1

            wage = self._get_user_contract_wage(user)
            estimated_salary = 0.0
            if wage > 0 and total_hours > 0:
                estimated_salary = (wage / 208.0) * total_hours

            rows.append({
                'userId': user.id,
                'employeeName': user.name,
                'employeeCode': emp_code,
                'dayData': day_data,
                'estimatedSalary': estimated_salary,
                'salaryConfigured': wage > 0,
                'shiftCount': total_shifts,
            })

        templates = self.env['swift.work.shift.template'].sudo().search([], order='id desc')
        template_data = []
        for t in templates:
            template_data.append({
                'id': t.id,
                'name': t.name,
                'startHour': t.start_hour,
                'endHour': t.end_hour,
                'checkinStartHour': t.checkin_start_hour,
                'checkinEndHour': t.checkin_end_hour,
                'color': t.color_class or 'blue',
            })

        return {
            'weekStart': fields.Date.to_string(start_date),
            'weekEnd': fields.Date.to_string(end_date),
            'weekLabel': _('Tuần %s - Th %s %s') % (start_date.isocalendar().week, start_date.month, start_date.year),
            'days': days,
            'rows': rows,
            'templates': template_data,
        }

    @api.model
    def save_work_schedule(self, employee_id, base_date, template_ids=None, apply_weekly=False, weekday_indexes=None, copy_employee_ids=None):
        template_ids = template_ids or []
        weekday_indexes = weekday_indexes or []
        copy_employee_ids = copy_employee_ids or []

        emp_ids = [int(employee_id)] + [int(x) for x in copy_employee_ids if x]
        target_dates = []
        date_obj = fields.Date.to_date(base_date)
        target_dates.append(date_obj)

        if apply_weekly and weekday_indexes:
            start = date_obj - timedelta(days=date_obj.weekday())
            end = start + timedelta(days=6)
            d = start
            wanted = {int(x) for x in weekday_indexes}
            while d <= end:
                if d.weekday() in wanted and d not in target_dates:
                    target_dates.append(d)
                d += timedelta(days=1)

        for emp_id in emp_ids:
            for d in target_dates:
                self.env['swift.work.schedule.line'].sudo().search([
                    ('employee_id', '=', emp_id),
                    ('date', '=', d),
                ]).unlink()

                for tmpl_id in template_ids:
                    tmpl = self.env['swift.work.shift.template'].sudo().browse(int(tmpl_id))
                    if tmpl.exists():
                        self.env['swift.work.schedule.line'].sudo().create({
                            'employee_id': emp_id,
                            'date': d,
                            'shift_template_id': tmpl.id,
                            'branch_name': tmpl.branch_name or '',
                        })
        return {'ok': True}

    @api.model
    def create_work_shift_template(self, vals):
        vals = vals or {}
        rec = self.env['swift.work.shift.template'].sudo().create({
            'name': vals.get('name') or _('Ca mới'),
            'start_hour': float(vals.get('start_hour') or 0.0),
            'end_hour': float(vals.get('end_hour') or 0.0),
            'checkin_start_hour': float(vals.get('checkin_start_hour') or 0.0),
            'checkin_end_hour': float(vals.get('checkin_end_hour') or 0.0),
            'branch_name': vals.get('branch_name') or '',
            'color_class': vals.get('color') if vals.get('color') in ('red', 'orange', 'green', 'blue') else 'blue',
        })
        return {'id': rec.id}

    # ──────────────────────────────────────────────────────────────
    # Employee (Nhân viên) helpers
    # ──────────────────────────────────────────────────────────────

    def _generate_unique_employee_code(self, user):
        profile_model = self.env['swift.employee.profile'].sudo()
        base_code = f"NV{str(user.id).zfill(6)}"
        if not profile_model.search_count([('employee_code', '=', base_code)]):
            return base_code
        index = 1
        while True:
            candidate = f"{base_code}-{index}"
            if not profile_model.search_count([('employee_code', '=', candidate)]):
                return candidate
            index += 1

    def _ensure_employee_profile(self, user):
        profile_model = self.env['swift.employee.profile'].sudo()
        profile = profile_model.search([('user_id', '=', user.id)], limit=1)
        if profile:
            return profile
        generated_code = self._generate_unique_employee_code(user)
        values = {
            'user_id': user.id,
            'employee_code': generated_code,
            'attendance_code': generated_code,
            'phone': self._partner_phone_value(user.partner_id),
            'work_branch': _('Chi nhánh trung tâm'),
            'pay_branch': _('Chi nhánh trung tâm'),
        }
        try:
            with self.env.cr.savepoint():
                return profile_model.create(values)
        except Exception as e:
            _logger.warning("_ensure_employee_profile create failed for user %s: %s", user.id, e)
            # Handle race condition or legacy duplicate data without crashing UI RPC.
            profile = profile_model.search([('user_id', '=', user.id)], limit=1)
            if profile:
                return profile
            with self.env.cr.savepoint():
                values['employee_code'] = self._generate_unique_employee_code(user)
                values['attendance_code'] = values['employee_code']
                return profile_model.create(values)

    def _normalize_job_title_value(self, job_title):
        job_title = (job_title or '').strip()
        if not job_title:
            return ''
        if job_title.isdigit() and 'hr.job' in self.env:
            job = self.env['hr.job'].sudo().browse(int(job_title)).exists()
            if job:
                return job.name or ''
        return job_title

    def _swift_employee_company(self, user=False):
        company = self.env.company
        if user and user.company_id:
            company = user.company_id
        return company

    def _swift_get_or_create_department(self, department_name, company):
        department_name = (department_name or '').strip()
        if not department_name or 'hr.department' not in self.env:
            return self.env['hr.department']
        department_model = self.env['hr.department'].sudo()
        domain = [('name', '=', department_name)]
        if company and 'company_id' in department_model._fields:
            department = department_model.search(domain + [('company_id', '=', company.id)], limit=1)
            if department:
                return department
        department = department_model.search(domain, limit=1)
        if department:
            return department
        create_vals = {'name': department_name}
        if company and 'company_id' in department_model._fields:
            create_vals['company_id'] = company.id
        return department_model.create(create_vals)

    def _swift_get_or_create_job(self, job_title, department=False, company=False):
        job_title = (job_title or '').strip()
        if not job_title or 'hr.job' not in self.env:
            return self.env['hr.job']
        job_model = self.env['hr.job'].sudo()
        domain = [('name', '=', job_title)]
        if company and 'company_id' in job_model._fields:
            job = job_model.search(domain + [('company_id', '=', company.id)], limit=1)
            if job:
                return job
        job = job_model.search(domain, limit=1)
        if job:
            return job
        create_vals = {'name': job_title}
        if department and 'department_id' in job_model._fields:
            create_vals['department_id'] = department.id
        if company and 'company_id' in job_model._fields:
            create_vals['company_id'] = company.id
        return job_model.create(create_vals)

    def _swift_sync_hr_employee(self, user, profile):
        if 'hr.employee' not in self.env or not user or not profile:
            return self.env['hr.employee']

        employee_model = self.env['hr.employee'].sudo()
        company = self._swift_employee_company(user)
        employee = profile.hr_employee_id.sudo().exists() if profile.hr_employee_id else self.env['hr.employee']
        if not employee:
            domain = [('user_id', '=', user.id)]
            if company and 'company_id' in employee_model._fields:
                employee = employee_model.search(domain + [('company_id', '=', company.id)], limit=1)
            if not employee:
                employee = employee_model.search(domain, limit=1)

        department = self._swift_get_or_create_department(profile.department, company)
        job = self._swift_get_or_create_job(profile.job_title, department=department, company=company)

        employee_vals = {
            'name': user.name or profile.employee_code,
            'user_id': user.id,
            'company_id': company.id if company else self.env.company.id,
            'barcode': profile.attendance_code or profile.employee_code or False,
            'identification_id': profile.id_number or False,
            'birthday': profile.birth_date or False,
            'sex': profile.gender or False,
            'mobile_phone': profile.phone or False,
            'work_phone': profile.phone or False,
            'work_email': user.email or user.partner_id.email or False,
            'department_id': department.id if department else False,
            'job_id': job.id if job else False,
            'job_title': (job.name if job else profile.job_title) or False,
            'active': profile.status == 'working',
        }

        if employee:
            employee.write(employee_vals)
        else:
            employee = employee_model.create(employee_vals)

        if profile.hr_employee_id != employee:
            profile.sudo().write({'hr_employee_id': employee.id})
        return employee

    def _swift_archive_hr_employee(self, profile):
        employee = profile.hr_employee_id.sudo().exists() if profile and profile.hr_employee_id else self.env['hr.employee']
        if not employee and profile and profile.user_id and 'hr.employee' in self.env:
            employee = self._swift_get_employee_record(profile.user_id)
        if employee:
            employee.sudo().write({'active': False})
            if profile and profile.hr_employee_id != employee:
                profile.sudo().write({'hr_employee_id': employee.id})
        return employee

    def _ensure_employee_internal_user(self, user):
        user = user.sudo()
        internal_group = self.env.ref('base.group_user', raise_if_not_found=False)
        pos_group = self.env.ref('point_of_sale.group_pos_user', raise_if_not_found=False)
        group_commands = []
        if internal_group and internal_group not in user.group_ids:
            group_commands.append((4, internal_group.id))
        if pos_group and pos_group not in user.group_ids:
            group_commands.append((4, pos_group.id))
        if group_commands:
            user.write({'group_ids': group_commands})
        return user

    def _build_employee_profile_domain(self, status='working', filters=None, keyword=''):
        filters = filters or {}
        profile_domain = [('user_id.active', '=', True)]
        if status in ('working', 'off'):
            profile_domain.append(('status', '=', status))

        work_branch = (filters.get('workBranch') or '').strip()
        pay_branch = (filters.get('payBranch') or '').strip()
        department = (filters.get('department') or '').strip()
        job_title = (filters.get('jobTitle') or '').strip()
        if work_branch:
            profile_domain.append(('work_branch', '=', work_branch))
        if pay_branch:
            profile_domain.append(('pay_branch', '=', pay_branch))
        if department:
            profile_domain.append(('department', '=', department))
        if job_title:
            profile_domain.append(('job_title', '=', job_title))
        if keyword:
            profile_domain += ['|', '|', '|',
                ('user_id.name', 'ilike', keyword),
                ('user_id.login', 'ilike', keyword),
                ('employee_code', 'ilike', keyword),
                ('attendance_code', 'ilike', keyword),
            ]
        return profile_domain

    def _get_local_day_bounds(self, target_date):
        user_tz = self.env.user.tz or 'UTC'
        local = pytz.timezone(user_tz)
        utc = pytz.utc
        start_local = local.localize(datetime.combine(target_date, datetime.min.time()))
        end_local = local.localize(datetime.combine(target_date, datetime.max.time()))
        return (
            start_local.astimezone(utc).replace(tzinfo=None),
            end_local.astimezone(utc).replace(tzinfo=None),
        )

    def _get_user_avatar_url(self, user):
        return f"/web/image/res.users/{user.id}/avatar_128"

    @api.model
    def get_employee_list_data(self, keyword='', status='working', filters=None):
        try:
            profile_domain = self._build_employee_profile_domain(status=status, filters=filters, keyword=keyword)
            profiles = self.env['swift.employee.profile'].sudo().search(profile_domain)

            rows = []
            for profile in profiles.sorted(lambda p: ((p.user_id.name or '').lower(), p.id)):
                user = profile.user_id

                if not profile.id_number and 'hr.employee' in self.env:
                    emp = self.env['hr.employee'].sudo().search([('user_id', '=', user.id), ('active', '=', True)], limit=1)
                    if emp and emp.identification_id:
                        profile.id_number = emp.identification_id

                rows.append({
                    'userId': user.id,
                    'employeeCode': profile.employee_code,
                    'attendanceCode': profile.attendance_code or profile.employee_code,
                    'employeeName': user.name,
                    'avatarUrl': self._get_user_avatar_url(user),
                    'phone': profile.phone or '',
                    'idNumber': profile.id_number or '',
                    'debtAdvance': profile.debt_advance_balance,
                    'note': '',
                    'status': profile.status,
                })
            return {'rows': rows}
        except Exception as e:
            self.env.cr.rollback()
            _logger.exception("get_employee_list_data failed: %s", e)
            return {'rows': []}

    @api.model
    def get_employee_checkin_board(self, date_value=False, filters=None, keyword=''):
        try:
            target_date = self._to_date_value(date_value) or fields.Date.context_today(self)
            profile_domain = self._build_employee_profile_domain(
                status='working',
                filters=filters,
                keyword=keyword,
            )
            profiles = self.env['swift.employee.profile'].sudo().search(profile_domain)
            if not profiles:
                return {
                    'date': fields.Date.to_string(target_date),
                    'rows': [],
                }

            start_dt, end_dt = self._get_local_day_bounds(target_date)
            shifts = self.env['swift.staff.shift'].sudo().search([
                ('employee_id', 'in', profiles.mapped('user_id').ids),
                ('check_in', '>=', fields.Datetime.to_string(start_dt)),
                ('check_in', '<=', fields.Datetime.to_string(end_dt)),
            ], order='check_in asc')

            shift_map = {}
            for shift in shifts:
                shift_map.setdefault(shift.employee_id.id, []).append(shift)

            today = fields.Date.context_today(self)
            rows = []
            for profile in profiles.sorted(lambda p: ((p.user_id.name or '').lower(), p.id)):
                user = profile.user_id
                user_shifts = shift_map.get(user.id, [])
                first_shift = user_shifts[0] if user_shifts else False
                active_shift = next((shift for shift in reversed(user_shifts) if shift.state == 'active'), False)
                last_done = next((shift for shift in reversed(user_shifts) if shift.check_out), False)
                total_hours = sum((shift.duration or 0.0) for shift in user_shifts if shift.state == 'done')
                if active_shift and active_shift.check_in:
                    total_hours += max((fields.Datetime.now() - active_shift.check_in).total_seconds(), 0.0) / 3600.0

                if active_shift:
                    status_label = self._swift_translate_status_label(_('Checked In'))
                    status_tone = 'warning'
                elif first_shift:
                    status_label = self._swift_translate_status_label(_('Checked Out'))
                    status_tone = 'success'
                else:
                    status_label = self._swift_translate_status_label(_('Not Checked In'))
                    status_tone = 'muted'

                check_in_local = fields.Datetime.context_timestamp(self, first_shift.check_in) if first_shift and first_shift.check_in else False
                check_out_local = fields.Datetime.context_timestamp(self, last_done.check_out) if last_done and last_done.check_out else False
                rows.append({
                    'userId': user.id,
                    'employeeCode': profile.employee_code,
                    'employeeName': user.name,
                    'avatarUrl': self._get_user_avatar_url(user),
                    'phone': profile.phone or self._partner_phone_value(user.partner_id),
                    'checkIn': check_in_local.strftime('%H:%M') if check_in_local else '--:--',
                    'checkOut': check_out_local.strftime('%H:%M') if check_out_local else '--:--',
                    'hours': round(total_hours, 2),
                    'statusLabel': status_label,
                    'statusTone': status_tone,
                    'note': (active_shift or last_done or first_shift).note if (active_shift or last_done or first_shift) else '',
                    'canCheckIn': target_date == today and not active_shift,
                    'canCheckOut': target_date == today and bool(active_shift),
                })

            return {
                'date': fields.Date.to_string(target_date),
                'rows': rows,
            }
        except Exception as e:
            _logger.exception("get_employee_checkin_board failed: %s", e)
            return {
                'date': fields.Date.to_string(fields.Date.context_today(self)),
                'rows': [],
            }

    @api.model
    def action_employee_checkin(self, user_id, note=''):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile or profile.status != 'working':
            return {'ok': False, 'message': _('Employee record not found')}
        active_shift = self.env['swift.staff.shift'].sudo().search([
            ('employee_id', '=', user.id),
            ('state', '=', 'active'),
        ], limit=1)
        if active_shift:
            return {'ok': False, 'message': _('Employee is already checked in')}
        self.env['swift.staff.shift'].sudo().create({
            'employee_id': user.id,
            'check_in': fields.Datetime.now(),
            'state': 'active',
            'note': note or '',
        })
        return {'ok': True}

    @api.model
    def action_employee_checkout(self, user_id, note=''):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        active_shift = self.env['swift.staff.shift'].sudo().search([
            ('employee_id', '=', user.id),
            ('state', '=', 'active'),
        ], limit=1)
        if not active_shift:
            return {'ok': False, 'message': _('Employee has no active shift')}
        active_shift.sudo().write({
            'check_out': fields.Datetime.now(),
            'state': 'done',
            'note': note or active_shift.note,
        })
        return {'ok': True}

    @api.model
    def get_employee_detail_data(self, user_id):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}
        employee = self._swift_get_employee_record(user)

        # schedule matrix this week
        week_start, week_end = self._get_week_range_from_offset(0)
        days = []
        d = week_start
        while d <= week_end:
            days.append({'date': fields.Date.to_string(d), 'label': self._schedule_day_label(d), 'day': d.day})
            d += timedelta(days=1)

        lines = self.env['swift.work.schedule.line'].sudo().search([
            ('employee_id', '=', user.id),
            ('date', '>=', week_start),
            ('date', '<=', week_end),
        ], order='date asc')
        shifts = []
        by_shift = {}
        for l in lines:
            sid = l.shift_template_id.id
            if sid not in by_shift:
                by_shift[sid] = {
                    'id': sid,
                    'name': l.shift_template_id.name,
                    'time': f"{int(l.shift_template_id.start_hour):02d}:00 - {int(l.shift_template_id.end_hour):02d}:00",
                    'days': [],
                }
            by_shift[sid]['days'].append(fields.Date.to_string(l.date))
        shifts = list(by_shift.values())

        # payslips from paycheck lines
        payslip_rows = []
        paycheck_lines = self.env['swift.paycheck.line'].sudo().search([('user_id', '=', user.id)], order='id desc', limit=12)
        for ln in paycheck_lines:
            p = ln.paycheck_id
            payslip_rows.append({
                'code': ln.name,
                'period': f"{self._fmt_date_vi(p.date_from)} - {self._fmt_date_vi(p.date_to)}",
                'total': ln.amount,
                'paid': ln.paid_amount,
                'remaining': ln.remaining_amount,
                'status': p.state,
            })

        finance_rows = []
        for f in profile.finance_line_ids.sorted(lambda x: x.date or fields.Date.today(), reverse=True):
            finance_rows.append({
                'date': fields.Date.to_string(f.date),
                'type': f.line_type,
                'amount': f.amount,
                'note': f.note or '',
            })

        return {
            'ok': True,
            'profile': {
                'employeeCode': profile.employee_code,
                'attendanceCode': profile.attendance_code or profile.employee_code,
                'name': user.name,
                'phone': profile.phone or '',
                'idNumber': profile.id_number or '',
                'birthDate': fields.Date.to_string(profile.birth_date) if profile.birth_date else '',
                'gender': profile.gender or '',
                'workBranch': profile.work_branch or '',
                'payBranch': profile.pay_branch or '',
                'department': profile.department or '',
                'jobTitle': profile.job_title or '',
                'salaryType': profile.salary_type,
                'salaryAmount': profile.salary_amount,
                'advancedSetting': profile.advanced_setting,
                'overtimeEnabled': profile.overtime_enabled,
                'debtAdvance': profile.debt_advance_balance,
                'accessCode': self._swift_access_code_payload(profile),
                'hrEmployeeId': employee.id if employee else False,
                'hrEmployeeActive': bool(employee and employee.active),
            },
            'days': days,
            'scheduleShifts': shifts,
            'payslips': payslip_rows,
            'financeRows': finance_rows,
        }

    @api.model
    def get_available_employee_users(self, keyword=''):
        domain = [('active', '=', True), ('share', '=', False)]
        if keyword:
            domain += ['|', ('name', 'ilike', keyword), ('login', 'ilike', keyword)]
        users = self.env['res.users'].sudo().search(domain, order='name asc', limit=200)

        profile_model = self.env['swift.employee.profile'].sudo()
        profile_by_user = {
            p.user_id.id: p for p in profile_model.search([('user_id', 'in', users.ids)])
        } if users else {}

        rows = []
        for user in users:
            profile = profile_by_user.get(user.id)
            if profile and profile.status == 'working':
                # already active in this employee system
                continue
            rows.append({
                'userId': user.id,
                'name': user.name,
                'login': user.login or '',
                'phone': self._partner_phone_value(user.partner_id),
            })
        return {'rows': rows}

    @api.model
    def get_employee_branch_options(self):
        branch_domain = [('active', '=', True)]
        if 'company_id' in self.env['pos.config']._fields:
            branch_domain.append(('company_id', '=', self.env.company.id))
        branches = self.env['pos.config'].sudo().search(branch_domain, order='name asc')
        return {
            'rows': [
                {
                    'id': branch.id,
                    'name': branch.name,
                }
                for branch in branches
            ]
        }

    @api.model
    def get_employee_filter_options(self):
        profiles = self.env['swift.employee.profile'].sudo().search([
            ('user_id.active', '=', True),
        ])
        branch_rows = self.get_employee_branch_options().get('rows', [])
        departments = sorted({(profile.department or '').strip() for profile in profiles if (profile.department or '').strip()})
        job_titles = self._swift_get_job_title_options()
        pay_branches = sorted({(profile.pay_branch or '').strip() for profile in profiles if (profile.pay_branch or '').strip()})

        known_branch_names = {row['name'] for row in branch_rows}
        for branch_name in pay_branches:
            if branch_name not in known_branch_names:
                branch_rows.append({
                    'id': f'pay-{branch_name}',
                    'name': branch_name,
                })

        return {
            'workBranches': branch_rows,
            'payBranches': branch_rows,
            'departments': [{'id': name, 'name': name} for name in departments],
            'jobTitles': job_titles,
        }

    @api.model
    def create_employee_record(self, vals):
        vals = vals or {}
        try:
            selected_user_id = vals.get('userId')
            name = (vals.get('name') or '').strip()
            if not name and not selected_user_id:
                return {'ok': False, 'message': _('Name is required')}

            phone = (vals.get('phone') or '').strip()
            birth_date = self._to_date_value(vals.get('birthDate'))
            salary_amount = self._to_float_amount(vals.get('salaryAmount'), 0.0)
            job_title = self._normalize_job_title_value(vals.get('jobTitle'))
            if not phone:
                return {'ok': False, 'message': _('Phone Number is required')}
            if not birth_date:
                return {'ok': False, 'message': _('Birth Date is required')}
            if salary_amount <= 0:
                return {'ok': False, 'message': _('Salary Amount is required')}
            if not job_title:
                return {'ok': False, 'message': _('Job Title is required')}
            if selected_user_id:
                user = self.env['res.users'].sudo().browse(int(selected_user_id))
                if not user.exists():
                    return {'ok': False, 'message': _('Employee not found')}
            else:
                login = phone or f"swift_employee_{fields.Datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                if self.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', login)]):
                    login = f"swift_employee_{fields.Datetime.now().strftime('%Y%m%d%H%M%S%f')}"

                user_vals = {
                    'name': name,
                    'login': login,
                    'active': True,
                    'share': False,
                }

                with self.env.cr.savepoint():
                    try:
                        user = self.env['res.users'].sudo().create(user_vals)
                    except Exception:
                        # Fallback for race/legacy duplicate login edge cases.
                        user_vals['login'] = f"swift_employee_{fields.Datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                        user = self.env['res.users'].sudo().create(user_vals)

            user = self._ensure_employee_internal_user(user)
            if name:
                user.sudo().write({'name': name})
            self._write_partner_phone(user.partner_id, phone)

            profile = self._ensure_employee_profile(user)
            if selected_user_id and profile.status == 'working':
                return {'ok': False, 'message': _('User is already in employee list')}
            profile.sudo().write({
                'phone': phone,
                'id_number': vals.get('idNumber') or '',
                'birth_date': birth_date,
                'gender': vals.get('gender') or False,
                'department': vals.get('department') or '',
                'job_title': job_title,
                'work_branch': vals.get('workBranch') or _('Chi nhánh trung tâm'),
                'pay_branch': vals.get('payBranch') or _('Chi nhánh trung tâm'),
                'status': 'working',
                'salary_type': vals.get('salaryType') or 'hour',
                'salary_amount': salary_amount,
                'advanced_setting': bool(vals.get('advancedSetting')),
                'overtime_enabled': bool(vals.get('overtimeEnabled')),
            })
            self._swift_sync_hr_employee(user, profile)
            return {'ok': True, 'userId': user.id, 'createdNewUser': not bool(selected_user_id)}
        except Exception as e:
            self.env.cr.rollback()
            _logger.exception("create_employee_record failed: %s", e)
            return {'ok': False, 'message': _('Cannot create employee')}

    @api.model
    def update_employee_record(self, user_id, vals):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}

        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}

        vals = vals or {}
        job_title = self._normalize_job_title_value(vals.get('jobTitle'))
        phone = (vals.get('phone') or '').strip()
        birth_date = self._to_date_value(vals.get('birthDate'))
        salary_amount = self._to_float_amount(vals.get('salaryAmount'), profile.salary_amount)
        if not (vals.get('name') or '').strip():
            return {'ok': False, 'message': _('Name is required')}
        if not phone:
            return {'ok': False, 'message': _('Phone Number is required')}
        if not birth_date:
            return {'ok': False, 'message': _('Birth Date is required')}
        if salary_amount <= 0:
            return {'ok': False, 'message': _('Salary Amount is required')}
        try:
            user_vals = {}
            if vals.get('name'):
                user_vals['name'] = vals.get('name')
            if user_vals:
                user.sudo().write(user_vals)

            phone = (vals.get('phone') or '').strip()
            if phone:
                self._write_partner_phone(user.partner_id, phone)

            profile.sudo().write({
                'phone': phone,
                'id_number': vals.get('idNumber') or profile.id_number or '',
                'birth_date': birth_date,
                'gender': vals.get('gender') or profile.gender or False,
                'work_branch': vals.get('workBranch') or profile.work_branch or _('Chi nhánh trung tâm'),
                'pay_branch': vals.get('payBranch') or profile.pay_branch or _('Chi nhánh trung tâm'),
                'department': vals.get('department') or profile.department or '',
                'job_title': job_title or profile.job_title or '',
                'salary_type': vals.get('salaryType') or profile.salary_type,
                'salary_amount': salary_amount,
                'advanced_setting': bool(vals.get('advancedSetting')) if 'advancedSetting' in vals else profile.advanced_setting,
                'overtime_enabled': bool(vals.get('overtimeEnabled')) if 'overtimeEnabled' in vals else profile.overtime_enabled,
            })
            self._swift_sync_hr_employee(user, profile)
            return {'ok': True}
        except Exception as e:
            self.env.cr.rollback()
            _logger.exception("update_employee_record failed: %s", e)
            return {'ok': False, 'message': _('Cannot update employee')}

    @api.model
    def update_employee_salary_setup(self, user_id, vals):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}
        profile.sudo().write({
            'salary_type': vals.get('salaryType') or profile.salary_type,
            'salary_amount': self._to_float_amount(vals.get('salaryAmount'), 0.0),
            'advanced_setting': bool(vals.get('advancedSetting')),
            'overtime_enabled': bool(vals.get('overtimeEnabled')),
        })
        return {'ok': True}

    @api.model
    def update_employee_pin(self, user_id, pos_pin):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}

        profile.sudo().write({
            'pos_pin': pos_pin,
        })
        return {'ok': True}

    @api.model
    def generate_employee_access_code(self, user_id):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}

        code = self._swift_generate_unique_access_code()
        expiry = fields.Datetime.now() + timedelta(minutes=self._swift_access_code_validity_minutes)
        profile.sudo().write({
            'pos_access_code': code,
            'pos_access_code_expiry': expiry,
        })
        payload = self._swift_access_code_payload(profile)
        payload['validityMinutes'] = self._swift_access_code_validity_minutes
        return {
            'ok': True,
            'message': _('Access code generated successfully.'),
            'accessCode': payload,
        }

    @api.model
    def verify_employee_access_code(self, access_code, pos_session_or_config_id=False):
        if not access_code:
            return {'ok': False, 'message': _('Verification code is required.')}

        profile = self._swift_get_profile_by_access_code(access_code)
        if profile:
            session_branch_name = self._swift_get_session_branch_name(pos_session_or_config_id)
            employee_branch_name = self._swift_get_employee_branch_name(profile)
            if not session_branch_name:
                self._swift_log_pos_access(profile.user_id.id, pos_session_or_config_id, status='failed')
                return {'ok': False, 'message': _('Unable to determine the POS branch for this session.')}

            if self._swift_normalize_branch_label(employee_branch_name) != self._swift_normalize_branch_label(session_branch_name):
                self._swift_log_pos_access(profile.user_id.id, pos_session_or_config_id, status='failed')
                return {
                    'ok': False,
                    'code': 'branch_mismatch',
                    'message': _(
                        "This employee is assigned to '%(employee_branch)s' and cannot open POS '%(session_branch)s'."
                    ) % {
                        'employee_branch': employee_branch_name or _('Unassigned'),
                        'session_branch': session_branch_name,
                    },
                    'employee_branch': employee_branch_name or _('Unassigned'),
                    'session_branch': session_branch_name,
                }

            try:
                self._swift_log_pos_access(profile.user_id.id, pos_session_or_config_id, status='success')
            except Exception:
                pass

            admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
            admin_users = admin_group.user_ids if admin_group and 'user_ids' in admin_group._fields else (
                admin_group.users if admin_group else self.env['res.users']
            )
            employee = self._swift_get_employee_record(profile.user_id, pos_session_or_config_id)

            return {
                'ok': True,
                'user_id': profile.user_id.id,
                'user_name': profile.user_id.name,
                'employee_id': employee.id if employee else False,
                'employee_name': employee.name if employee else profile.user_id.name,
                'avatarUrl': f"/web/image/res.users/{profile.user_id.id}/avatar_128",
                'is_admin': bool(admin_group and profile.user_id in admin_users),
            }
        return {'ok': False, 'message': _('Incorrect or expired verification code.')}

    @api.model
    def add_employee_finance_entry(self, user_id, line_type, amount, note=''):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}
        self.env['swift.employee.finance.line'].sudo().create({
            'profile_id': profile.id,
            'line_type': line_type if line_type in ('debt', 'advance', 'payment') else 'advance',
            'amount': float(amount or 0.0),
            'note': note or '',
        })
        return {'ok': True}

    @api.model
    def action_set_employee_status(self, user_id, status='off'):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        status_value = status if status in ('working', 'off') else 'off'
        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}
        profile.sudo().write({'status': status_value})
        if status_value == 'working':
            self._swift_sync_hr_employee(user, profile)
            user.sudo().write({'active': True})
        else:
            self._swift_archive_hr_employee(profile)
        return {'ok': True, 'status': status_value}

    @api.model
    def action_delete_employee_record(self, user_id):
        user = self.env['res.users'].sudo().browse(int(user_id))
        if not user.exists():
            return {'ok': False, 'message': _('Employee not found')}
        if user.id == self.env.user.id:
            return {'ok': False, 'message': _('You cannot delete your own employee record.')}

        profile = self.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not profile:
            return {'ok': False, 'message': _('Employee record not found')}

        self._swift_clear_access_code(profile)
        self._swift_archive_hr_employee(profile)
        profile.sudo().write({'status': 'off'})
        return {'ok': True}
