# -*- coding: utf-8 -*-

from contextlib import ExitStack

import odoo
import odoo.modules.registry

from odoo import fields, http, _
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request


class SwiftZaloApiController(http.Controller):
    def _json_body(self):
        return request.httprequest.get_json(silent=True) or {}

    def _ok(self, data=None, status=200):
        return request.make_json_response({
            "success": True,
            "data": data or {},
        }, status=status)

    def _error(self, message, status=400, code="bad_request"):
        return request.make_json_response({
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        }, status=status)

    def _ensure_pos_user(self):
        if not request.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessDenied(_("You do not have POS access rights."))

    def _get_open_session(self, config_id=None):
        domain = [("state", "not in", ("closed", "closing_control"))]
        if config_id:
            domain.append(("config_id", "=", int(config_id)))
        session = request.env["pos.session"].search(domain, limit=1, order="id desc")
        if not session:
            raise UserError(_("No open POS session found. Please open a POS session first."))
        return session

    @staticmethod
    def _compute_line_amounts(product, qty, price_unit, discount, fiscal_position, partner):
        discount = discount or 0.0
        effective_price = price_unit * (1.0 - discount / 100.0)
        taxes = product.taxes_id.filtered(lambda t: not t.company_id or t.company_id == product.company_id)
        if fiscal_position:
            taxes = fiscal_position.map_tax(taxes, product, partner)
        tax_res = taxes.compute_all(
            effective_price,
            currency=product.currency_id,
            quantity=qty,
            product=product,
            partner=partner,
        )
        return {
            "tax_ids": taxes.ids,
            "price_subtotal": tax_res["total_excluded"],
            "price_subtotal_incl": tax_res["total_included"],
        }

    @http.route("/api/swift/v1/auth/login", type="http", auth="none", methods=["POST"], csrf=False)
    def api_login(self, **kwargs):
        payload = self._json_body()
        db = payload.get("db") or request.db
        login = payload.get("login")
        password = payload.get("password")
        if not db or not login or not password:
            return self._error(_("Fields 'db', 'login' and 'password' are required."), 400, "missing_credentials")
        if not http.db_filter([db]):
            return self._error(_("Database not found."), 404, "db_not_found")

        try:
            with ExitStack() as stack:
                if not request.db or request.db != db:
                    cr = stack.enter_context(odoo.modules.registry.Registry(db).cursor())
                    env = odoo.api.Environment(cr, None, {})
                else:
                    env = request.env

                credential = {"login": login, "password": password, "type": "password"}
                auth_info = request.session.authenticate(env, credential)
                if auth_info.get("uid") != request.session.uid:
                    return self._error(_("Session renewal with MFA is not supported by this endpoint."), 401, "mfa_not_supported")

                request.session.db = db
                request._save_session(env)
                session_info = env["ir.http"].with_user(request.session.uid).session_info()
        except AccessDenied:
            return self._error(_("Wrong login/password."), 401, "invalid_credentials")
        except Exception:
            return self._error(_("Authentication failed."), 401, "auth_failed")

        user = request.env["res.users"].sudo().browse(request.session.uid)
        return self._ok({
            "uid": request.session.uid,
            "sid": request.session.sid,
            "db": request.session.db,
            "user": {
                "id": user.id,
                "name": user.name,
                "login": user.login,
            },
            "session_info": session_info,
        })

    @http.route("/api/swift/v1/auth/logout", type="http", auth="user", methods=["POST"], csrf=False)
    def api_logout(self, **kwargs):
        request.session.logout(keep_db=True)
        return self._ok({"message": _("Logged out successfully.")})

    @http.route("/api/swift/v1/shifts/status", type="http", auth="user", methods=["GET"], csrf=False)
    def api_shift_status(self, **kwargs):
        self._ensure_pos_user()
        dashboard = request.env["pos.dashboard.swift"]
        return self._ok({
            "status": dashboard.get_shift_status(),
            "stats": dashboard.get_shift_stats(),
            "recent": dashboard.get_recent_shifts(limit=10),
        })

    @http.route("/api/swift/v1/shifts/checkin", type="http", auth="user", methods=["POST"], csrf=False)
    def api_shift_checkin(self, **kwargs):
        self._ensure_pos_user()
        payload = self._json_body()
        note = payload.get("note", "")
        Shift = request.env["swift.staff.shift"]
        active = Shift.search([("employee_id", "=", request.env.uid), ("state", "=", "active")], limit=1)
        if active:
            return self._error(_("You are already checked in."), 409, "already_checked_in")

        new_shift = Shift.create({
            "employee_id": request.env.uid,
            "check_in": fields.Datetime.now(),
            "state": "active",
            "note": note,
        })
        return self._ok({
            "id": new_shift.id,
            "state": new_shift.state,
            "check_in": fields.Datetime.to_string(new_shift.check_in),
        })

    @http.route("/api/swift/v1/shifts/checkout", type="http", auth="user", methods=["POST"], csrf=False)
    def api_shift_checkout(self, **kwargs):
        self._ensure_pos_user()
        payload = self._json_body()
        note = payload.get("note", "")
        shift = request.env["swift.staff.shift"].search(
            [("employee_id", "=", request.env.uid), ("state", "=", "active")],
            limit=1,
        )
        if not shift:
            return self._error(_("No active shift found."), 404, "no_active_shift")

        shift.write({
            "check_out": fields.Datetime.now(),
            "state": "done",
            "note": note or shift.note,
        })
        return self._ok({
            "id": shift.id,
            "state": shift.state,
            "check_in": fields.Datetime.to_string(shift.check_in),
            "check_out": fields.Datetime.to_string(shift.check_out),
            "duration_hours": shift.duration,
        })

    @http.route("/api/swift/v1/employees", type="http", auth="user", methods=["GET"], csrf=False)
    def api_employees(self, **kwargs):
        self._ensure_pos_user()
        keyword = request.httprequest.args.get("keyword", "")
        status = request.httprequest.args.get("status", "working")
        data = request.env["pos.dashboard.swift"].get_employee_list_data(keyword=keyword, status=status)
        return self._ok(data)

    @http.route("/api/swift/v1/employees/me", type="http", auth="user", methods=["GET"], csrf=False)
    def api_employee_me(self, **kwargs):
        self._ensure_pos_user()
        data = request.env["pos.dashboard.swift"].get_employee_detail_data(user_id=request.env.uid)
        return self._ok(data)

    @http.route("/api/swift/v1/employees/<int:user_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def api_employee_detail(self, user_id, **kwargs):
        self._ensure_pos_user()
        data = request.env["pos.dashboard.swift"].get_employee_detail_data(user_id=user_id)
        if not data.get("ok"):
            return self._error(data.get("message") or _("Employee not found."), 404, "employee_not_found")
        return self._ok(data)

    @http.route("/api/swift/v1/pos/products", type="http", auth="user", methods=["GET"], csrf=False)
    def api_pos_products(self, **kwargs):
        self._ensure_pos_user()
        args = request.httprequest.args
        keyword = args.get("keyword", "")
        limit = int(args.get("limit", 100))
        offset = int(args.get("offset", 0))
        config_id = args.get("config_id")
        pos_config = False
        if config_id:
            pos_config = request.env["pos.config"].sudo().browse(int(config_id)).exists()
        if not pos_config:
            return self._ok({
                "rows": [],
                "pagination": {
                    "total": 0,
                    "limit": limit,
                    "offset": offset,
                },
            })

        domain = [("available_in_pos", "=", True), ("sale_ok", "=", True), ("active", "=", True)]
        domain.append(("product_tmpl_id.swift_branch_config_ids", "in", pos_config.ids))
        if pos_config.limit_categories and pos_config.iface_available_categ_ids:
            domain.append(("pos_categ_ids", "in", pos_config.iface_available_categ_ids.ids))
        if keyword:
            domain += ["|", "|", ("name", "ilike", keyword), ("default_code", "ilike", keyword), ("barcode", "ilike", keyword)]

        products = request.env["product.product"].sudo().search(domain, limit=limit, offset=offset, order="name asc")
        total = request.env["product.product"].sudo().search_count(domain)

        quant_domain = [("product_id", "in", products.ids), ("location_id.usage", "=", "internal")]
        if pos_config.picking_type_id.default_location_src_id:
            quant_domain.append(("location_id", "child_of", pos_config.picking_type_id.default_location_src_id.id))
        qty_groups = request.env["stock.quant"].sudo()._read_group(
            quant_domain,
            groupby=["product_id"],
            aggregates=["quantity:sum"],
        )
        qty_map = {p.id: qty for p, qty in qty_groups if p}

        currency = request.env.company.currency_id
        rows = []
        for product in products:
            rows.append({
                "id": product.id,
                "name": product.display_name,
                "barcode": product.barcode or "",
                "default_code": product.default_code or "",
                "list_price": product.lst_price,
                "qty_on_hand": qty_map.get(product.id, 0.0),
                "uom": product.uom_id.name,
                "currency": currency.name,
            })
        return self._ok({
            "rows": rows,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        })

    @http.route("/api/swift/v1/pos/orders", type="http", auth="user", methods=["POST"], csrf=False)
    def api_pos_create_order(self, **kwargs):
        self._ensure_pos_user()
        payload = self._json_body()

        lines = payload.get("lines") or []
        if not lines:
            return self._error(_("Field 'lines' is required and cannot be empty."), 400, "missing_lines")

        partner = False
        if payload.get("partner_id"):
            partner = request.env["res.partner"].browse(int(payload["partner_id"]))
            if not partner.exists():
                return self._error(_("Customer not found."), 404, "customer_not_found")

        session = self._get_open_session(payload.get("config_id"))
        fiscal_position = session.config_id.default_fiscal_position_id

        normalized_lines = []
        for item in lines:
            product_id = int(item.get("product_id", 0))
            qty = float(item.get("qty", 0.0))
            if not product_id or qty <= 0:
                return self._error(_("Each line must include valid 'product_id' and 'qty' > 0."), 400, "invalid_line")

            product = request.env["product.product"].browse(product_id)
            if not product.exists():
                return self._error(_("Product %s not found.") % product_id, 404, "product_not_found")
            normalized_lines.append({
                "product": product,
                "qty": qty,
                "price_unit": float(item.get("price_unit", product.lst_price)),
                "discount": float(item.get("discount", 0.0)),
            })

        order_vals = {
            "session_id": session.id,
            "user_id": request.env.uid,
            "partner_id": partner.id if partner else False,
            "state": "draft",
            "date_order": fields.Datetime.now(),
        }
        order = request.env["pos.order"].create(order_vals)

        order_line_model = request.env["pos.order.line"]
        for item in normalized_lines:
            line_amounts = self._compute_line_amounts(
                item["product"],
                item["qty"],
                item["price_unit"],
                item["discount"],
                fiscal_position,
                partner,
            )
            order_line_model.create({
                "order_id": order.id,
                "product_id": item["product"].id,
                "qty": item["qty"],
                "price_unit": item["price_unit"],
                "discount": item["discount"],
                "tax_ids": [(6, 0, line_amounts["tax_ids"])],
                "price_subtotal": line_amounts["price_subtotal"],
                "price_subtotal_incl": line_amounts["price_subtotal_incl"],
                "full_product_name": item["product"].display_name,
            })

        order._compute_prices()
        return self._ok({
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_total": order.amount_total,
            "amount_tax": order.amount_tax,
            "amount_paid": order.amount_paid,
            "amount_due": order.amount_total - order.amount_paid,
            "session_id": order.session_id.id,
            "config_id": order.config_id.id,
        }, status=201)

    @http.route("/api/swift/v1/pos/orders/<int:order_id>/pay", type="http", auth="user", methods=["POST"], csrf=False)
    def api_pos_pay_order(self, order_id, **kwargs):
        self._ensure_pos_user()
        payload = self._json_body()
        payment_method_id = payload.get("payment_method_id")
        if not payment_method_id:
            return self._error(_("Field 'payment_method_id' is required."), 400, "missing_payment_method")

        order = request.env["pos.order"].browse(order_id)
        if not order.exists():
            return self._error(_("POS order not found."), 404, "order_not_found")
        if order.state in ("paid", "done", "invoiced"):
            return self._error(_("Order is already validated."), 409, "already_validated")

        payment_method = request.env["pos.payment.method"].browse(int(payment_method_id))
        if not payment_method.exists():
            return self._error(_("Payment method not found."), 404, "payment_method_not_found")
        if payment_method not in order.session_id.config_id.payment_method_ids:
            return self._error(_("Payment method is not available in the order POS config."), 400, "invalid_payment_method")

        amount_due = order.amount_total - order.amount_paid
        amount = float(payload.get("amount", amount_due))
        if amount <= 0:
            return self._error(_("Payment amount must be greater than 0."), 400, "invalid_amount")

        order.add_payment({
            "pos_order_id": order.id,
            "payment_method_id": payment_method.id,
            "amount": amount,
            "payment_date": fields.Datetime.now(),
        })

        validated = False
        remaining = order.amount_total - order.amount_paid
        if remaining <= order.currency_id.rounding:
            order.action_pos_order_paid()
            order._create_order_picking()
            order._compute_total_cost_in_real_time()
            validated = True

        return self._ok({
            "id": order.id,
            "name": order.name,
            "state": order.state,
            "validated": validated,
            "amount_total": order.amount_total,
            "amount_paid": order.amount_paid,
            "amount_due": order.amount_total - order.amount_paid,
        })
