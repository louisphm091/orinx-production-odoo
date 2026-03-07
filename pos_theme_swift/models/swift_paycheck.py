from datetime import date, timedelta

from odoo import api, fields, models, _


class SwiftPaycheck(models.Model):
    _name = "swift.paycheck"
    _description = "Swift Paycheck"
    _order = "date_from desc, id desc"

    name = fields.Char(string="Code", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    title = fields.Char(string="Title", required=True)
    cycle = fields.Selection([
        ("monthly", "Monthly"),
    ], string="Payment Cycle", default="monthly", required=True)
    date_from = fields.Date(string="Date From", required=True)
    date_to = fields.Date(string="Date To", required=True)
    branch_name = fields.Char(string="Branch")
    state = fields.Selection([
        ("draft", "Draft"),
        ("temporary", "Temporary"),
        ("finalized", "Finalized"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="temporary", required=True)
    note = fields.Text(string="Note")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)

    line_ids = fields.One2many("swift.paycheck.line", "paycheck_id", string="Payslip Lines", copy=True)
    payment_ids = fields.One2many("swift.paycheck.payment", "paycheck_id", string="Payments", copy=False)

    employee_count = fields.Integer(string="Employee Count", compute="_compute_totals", store=True)
    total_salary = fields.Float(string="Total Salary", compute="_compute_totals", store=True)
    paid_amount = fields.Float(string="Paid Amount", compute="_compute_totals", store=True)
    remaining_amount = fields.Float(string="Remaining Amount", compute="_compute_totals", store=True)

    @api.depends("line_ids.amount", "line_ids.paid_amount")
    def _compute_totals(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids)
            rec.total_salary = sum(rec.line_ids.mapped("amount"))
            rec.paid_amount = sum(rec.line_ids.mapped("paid_amount"))
            rec.remaining_amount = rec.total_salary - rec.paid_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("swift.paycheck") or _("New")
            if not vals.get("title") and vals.get("date_from"):
                start = fields.Date.to_date(vals["date_from"])
                vals["title"] = _("Monthly payroll %s/%s") % (start.month, start.year)
        return super().create(vals_list)

    @api.model
    def _get_staff_salary_rows(self):
        """Build paycheck rows from real Odoo staff data.

        Staff source:
        - POS users (group_pos_user + group_pos_manager)
        Salary source:
        - hr.contract.wage (open/running contract of linked hr.employee), if HR is installed
        - fallback 0.0 when salary data is unavailable
        """
        group_ids = []
        grp_user = self.env.ref("point_of_sale.group_pos_user", raise_if_not_found=False)
        grp_manager = self.env.ref("point_of_sale.group_pos_manager", raise_if_not_found=False)
        if grp_user:
            group_ids.append(grp_user.id)
        if grp_manager:
            group_ids.append(grp_manager.id)

        user_domain = [("active", "=", True), ("share", "=", False)]
        if group_ids:
            user_domain.append(("group_ids", "in", group_ids))

        users = self.env["res.users"].search(user_domain)
        rows = []
        has_employee_model = "hr.employee" in self.env
        has_contract_model = "hr.contract" in self.env

        for user in users:
            amount = 0.0
            if has_employee_model:
                employee = self.env["hr.employee"].search([("user_id", "=", user.id), ("active", "=", True)], limit=1)
                if employee and has_contract_model:
                    contract = self.env["hr.contract"].search([
                        ("employee_id", "=", employee.id),
                        ("state", "in", ["open", "running"]),
                    ], order="date_start desc, id desc", limit=1)
                    amount = contract.wage or 0.0
            rows.append({
                "user_id": user.id,
                "amount": amount,
                "paid_amount": 0.0,
            })

        if not rows:
            rows.append({
                "user_id": self.env.user.id,
                "amount": 0.0,
                "paid_amount": 0.0,
            })
        return rows

    @api.model
    def create_default_paycheck(self):
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        if today.month == 12:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 1, 1) - timedelta(days=1)

        pos_config = self.env["pos.config"].search([], limit=1)
        branch = pos_config.name if pos_config else _("Main Branch")

        paycheck = self.create({
            "title": _("Bảng lương tháng %s/%s") % (start.month, start.year),
            "date_from": start,
            "date_to": end,
            "branch_name": branch,
            "state": "temporary",
        })

        line_vals = self._get_staff_salary_rows()
        self.env["swift.paycheck.line"].create([
            {**vals, "paycheck_id": paycheck.id} for vals in line_vals
        ])
        return paycheck


class SwiftPaycheckLine(models.Model):
    _name = "swift.paycheck.line"
    _description = "Swift Paycheck Line"
    _order = "id asc"

    name = fields.Char(string="Code", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    paycheck_id = fields.Many2one("swift.paycheck", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", string="Employee", required=True)
    amount = fields.Float(string="Salary Amount", default=0.0)
    paid_amount = fields.Float(string="Paid", default=0.0)
    remaining_amount = fields.Float(string="Remaining", compute="_compute_remaining", store=True)

    @api.depends("amount", "paid_amount")
    def _compute_remaining(self):
        for rec in self:
            rec.remaining_amount = rec.amount - rec.paid_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("swift.paycheck.line") or _("New")
        return super().create(vals_list)


class SwiftPaycheckPayment(models.Model):
    _name = "swift.paycheck.payment"
    _description = "Swift Paycheck Payment"
    _order = "payment_time desc, id desc"

    paycheck_id = fields.Many2one("swift.paycheck", required=True, ondelete="cascade")
    amount = fields.Float(string="Amount", required=True)
    payment_time = fields.Datetime(string="Payment Time", default=fields.Datetime.now, required=True)
    method = fields.Selection([
        ("cash", "Cash"),
        ("bank", "Bank Transfer"),
    ], string="Method", default="cash", required=True)
    note = fields.Char(string="Note")
    user_id = fields.Many2one("res.users", string="Created By", default=lambda self: self.env.user, required=True)
