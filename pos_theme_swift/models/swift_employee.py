from odoo import api, fields, models, _


class SwiftEmployeeProfile(models.Model):
    _name = "swift.employee.profile"
    _description = "Swift Employee Profile"

    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    employee_code = fields.Char(string="Employee Code", required=True, copy=False, index=True, default=lambda self: _("New"))
    attendance_code = fields.Char(string="Attendance Code")
    status = fields.Selection([
        ("working", "Working"),
        ("off", "Off"),
    ], default="working", required=True)

    phone = fields.Char(string="Phone")
    id_number = fields.Char(string="ID Number")
    birth_date = fields.Date(string="Birth Date")
    gender = fields.Selection([
        ("male", "Male"),
        ("female", "Female"),
    ], string="Gender")

    work_branch = fields.Char(string="Work Branch")
    pay_branch = fields.Char(string="Pay Branch")
    department = fields.Char(string="Department")
    job_title = fields.Char(string="Job Title")

    salary_type = fields.Selection([
        ("hour", "Theo giờ làm việc"),
        ("shift", "Theo ca làm việc"),
        ("month", "Theo tháng"),
    ], default="hour", required=True)
    salary_amount = fields.Float(string="Salary Amount", default=0.0)
    advanced_setting = fields.Boolean(string="Advanced Setting")
    overtime_enabled = fields.Boolean(string="Overtime Enabled")

    finance_line_ids = fields.One2many("swift.employee.finance.line", "profile_id", string="Finance Lines")
    debt_advance_balance = fields.Float(string="Debt/Advance", compute="_compute_debt_advance", store=True)

    _sql_constraints = [
        ("swift_employee_profile_user_unique", "unique(user_id)", "Employee profile already exists for this user."),
        ("swift_employee_profile_code_unique", "unique(employee_code)", "Employee code must be unique."),
    ]

    @api.depends("finance_line_ids.amount", "finance_line_ids.line_type")
    def _compute_debt_advance(self):
        for rec in self:
            balance = 0.0
            for line in rec.finance_line_ids:
                if line.line_type in ("debt", "advance"):
                    balance -= line.amount
                elif line.line_type == "payment":
                    balance += line.amount
            rec.debt_advance_balance = balance

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("employee_code", _("New")) == _("New"):
                vals["employee_code"] = self.env["ir.sequence"].next_by_code("swift.employee.profile") or _("New")
            if not vals.get("attendance_code"):
                vals["attendance_code"] = vals["employee_code"]
        return super().create(vals_list)


class SwiftEmployeeFinanceLine(models.Model):
    _name = "swift.employee.finance.line"
    _description = "Swift Employee Debt/Advance"
    _order = "date desc, id desc"

    profile_id = fields.Many2one("swift.employee.profile", required=True, ondelete="cascade", index=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    line_type = fields.Selection([
        ("debt", "Debt"),
        ("advance", "Advance"),
        ("payment", "Payment"),
    ], required=True, default="advance")
    amount = fields.Float(required=True)
    note = fields.Char()
