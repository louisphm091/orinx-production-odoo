from odoo import api, fields, models


class SwiftWorkShiftTemplate(models.Model):
    _name = "swift.work.shift.template"
    _description = "Swift Work Shift Template"
    _order = "id desc"

    name = fields.Char(string="Name", required=True)
    start_hour = fields.Float(string="Start Hour", required=True, default=8.0)
    end_hour = fields.Float(string="End Hour", required=True, default=17.0)
    checkin_start_hour = fields.Float(string="Check-in Start", default=7.5)
    checkin_end_hour = fields.Float(string="Check-in End", default=8.5)
    branch_name = fields.Char(string="Branch")
    color_class = fields.Selection([
        ("red", "Red"),
        ("orange", "Orange"),
        ("green", "Green"),
        ("blue", "Blue"),
    ], default="blue")
    duration_hours = fields.Float(string="Duration", compute="_compute_duration", store=True)

    @api.depends("start_hour", "end_hour")
    def _compute_duration(self):
        for rec in self:
            if rec.end_hour >= rec.start_hour:
                rec.duration_hours = rec.end_hour - rec.start_hour
            else:
                rec.duration_hours = (24.0 - rec.start_hour) + rec.end_hour


class SwiftWorkScheduleLine(models.Model):
    _name = "swift.work.schedule.line"
    _description = "Swift Work Schedule Line"
    _order = "date asc, employee_id asc, id asc"

    employee_id = fields.Many2one("res.users", string="Employee", required=True, index=True)
    date = fields.Date(string="Date", required=True, index=True)
    shift_template_id = fields.Many2one("swift.work.shift.template", string="Shift", required=True)
    branch_name = fields.Char(string="Branch")
    note = fields.Char(string="Note")

    _sql_constraints = [
        ("swift_work_schedule_unique", "unique(employee_id, date, shift_template_id)", "This shift already exists for this employee and date."),
    ]
