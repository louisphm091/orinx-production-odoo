from odoo import models, fields, api, _

class SwiftStaffShift(models.Model):
    _name = 'swift.staff.shift'
    _description = 'Staff Shift Check-in/out'
    _order = 'check_in desc'

    employee_id = fields.Many2one('res.users', string='Employee', required=True, default=lambda self: self.env.user)
    check_in = fields.Datetime(string='Check In', default=fields.Datetime.now)
    check_out = fields.Datetime(string='Check Out')
    state = fields.Selection([
        ('active', 'Working'),
        ('done', 'Completed')
    ], string='Status', default='active')
    note = fields.Text(string='Note')

    duration = fields.Float(string='Duration (Hours)', compute='_compute_duration', store=True)

    @api.depends('check_in', 'check_out')
    def _compute_duration(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                diff = rec.check_out - rec.check_in
                rec.duration = diff.total_seconds() / 3600.0
            else:
                rec.duration = 0.0
