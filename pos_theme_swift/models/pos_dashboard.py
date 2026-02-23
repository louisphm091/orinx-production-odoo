# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, timedelta
import pytz

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
        orders = self.env['pos.order'].read_group(domain, ['config_id', 'amount_total'], ['config_id'])

        labels = []
        datasets = []

        if not orders:
            return {'labels': ['-'], 'datasets': []}

        # For simplicity in this version, we use a single label (the period) or hours
        # The user's screenshot showed "09" as label and legend with branch names.

        for o in orders:
            config_name = o['config_id'][1] if o['config_id'] else _('Unknown')
            datasets.append({
                'label': config_name,
                'data': [o['amount_total']]
            })

        return {
            'labels': [fields.Date.to_string(start)], # Simple label for now
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
        lines = self.env['pos.order.line'].read_group(domain, ['product_id', 'price_subtotal_incl'], ['product_id'], limit=10, orderby='price_subtotal_incl desc')

        res = []
        if not lines:
            return res

        max_val = max(l['price_subtotal_incl'] for l in lines) if lines else 1
        for l in lines:
            res.append({
                'name': l['product_id'][1],
                'value': l['price_subtotal_incl'],
                'pct': int((l['price_subtotal_incl'] / max_val) * 100) if max_val > 0 else 0
            })
        return res
