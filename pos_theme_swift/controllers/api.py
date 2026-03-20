# -*- coding: utf-8 -*-

from contextlib import ExitStack
import json
from datetime import datetime
import pytz
import odoo
import odoo.modules.registry
from odoo import fields, http, _
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

class SwiftZaloApiController(http.Controller):

    def _json_body(self):
        body = request.httprequest.get_json(silent=True) or {}
        if "params" in body and isinstance(body["params"], dict):
            return body["params"]
        return body

    def _ok(self, data=None, message="OK", status=200):
        return request.make_json_response({
            "error": 0,
            "message": message,
            "data": data if data is not None else {},
        }, status=status)

    def _error(self, message, error_code=-1, status=400):
        return request.make_json_response({
            "error": error_code,
            "message": message,
            "data": None,
        }, status=status)

    def _ensure_pos_user(self):
        if not request.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessDenied(_("You do not have POS access rights."))

    # 1. Core APIs
    @http.route("/api/swift/v1/merchant", type="http", auth="user", methods=["GET"], csrf=False)
    def get_merchant_info(self, **kwargs):
        company = request.env.company
        branches = request.env['pos.config'].sudo().search([('active', '=', True)])
        data = {
            "merchant": {
                "name": company.name,
                "address": company.street or "",
                "logoUrl": f"/web/image?model=res.company&id={company.id}&field=logo",
                "coverUrl": "",  # Placeholder or find a cover field
                "description": company.partner_id.comment or "",
                "status": "ACTIVE",
                "visibleOrder": "ENABLE",
                "branches": [{
                    "id": str(b.id),
                    "name": b.name,
                    "address": b.swift_branch_address or ""
                } for b in branches]
            }
        }
        return self._ok(data)

    @http.route("/api/swift/v1/menu-items", type="http", auth="user", methods=["GET"], csrf=False)
    def get_menu_items(self, **kwargs):
        config_id = request.httprequest.args.get('config_id')
        domain = [("available_in_pos", "=", True), ("sale_ok", "=", True), ("active", "=", True)]
        if config_id:
            domain.append(("product_tmpl_id.swift_branch_config_ids", "in", [int(config_id)]))

        products = request.env['product.product'].sudo().search(domain)
        
        # Group products by category
        cat_map = {}
        for product in products:
            cats = product.pos_categ_ids or product.product_tmpl_id.pos_categ_ids
            # If no category, put in a "General" one
            cat_list = cats if cats else [request.env['pos.category'].sudo().browse(0)]
            for cat in cat_list:
                cat_id = cat.id or 0
                cat_name = cat.name or _("Chung")
                if cat_id not in cat_map:
                    cat_map[cat_id] = {
                        "category": {"id": cat_id, "name": cat_name},
                        "products": []
                    }
                cat_map[cat_id]["products"].append({
                    "id": product.id,
                    "name": product.display_name,
                    "description": product.description_sale or "",
                    "price": product.lst_price,
                    "imageUrl": f"/web/image?model=product.product&id={product.id}&field=image_128",
                    "toppings": [] # To be implemented if needed
                })
        
        return self._ok(list(cat_map.values()))

    @http.route("/api/swift/v1/oa", type="http", auth="user", methods=["GET"], csrf=False)
    def get_oa_info(self, **kwargs):
        data = {
            "oa": {
                "id": "oa_swift",
                "name": "Swift Shop OA",
                "coverUrl": "",
                "avatarUrl": "",
                "phone": request.env.company.phone or ""
            },
            "followed": False
        }
        return self._ok(data)

    @http.route("/api/swift/v1/sessions", type="http", auth="user", methods=["GET"], csrf=False)
    def get_sessions(self, **kwargs):
        order_session_id = request.httprequest.args.get('orderSessionId')
        session = None
        if order_session_id:
            session = request.env['pos.session'].sudo().search([('name', '=', order_session_id)], limit=1)
        
        if not session:
            session = request.env['pos.session'].sudo().search([
                ('user_id', '=', request.env.uid),
                ('state', '=', 'opened')
            ], limit=1, order='id desc')

        if session:
            data = {
                "orderSession": {"id": session.name},
                "owner": {
                    "id": str(session.user_id.id),
                    "name": session.user_id.name,
                    "avatar": f"/web/image?model=res.users&id={session.user_id.id}&field=image_128"
                }
            }
        else:
            data = {
                "orderSession": None,
                "owner": {
                    "id": str(request.env.uid),
                    "name": request.env.user.name,
                    "avatar": f"/web/image?model=res.users&id={request.env.uid}&field=image_128"
                }
            }
        return self._ok(data)

    @http.route("/api/swift/v1/orders", type="http", auth="user", methods=["GET"], csrf=False)
    def get_orders_list(self, **kwargs):
        order_session_id = request.httprequest.args.get('orderSessionId')
        domain = []
        if order_session_id:
            domain.append(('session_id.name', '=', order_session_id))
        else:
            domain.append(('user_id', '=', request.env.uid))
        
        orders = request.env['pos.order'].sudo().search(domain, limit=20, order='date_order desc')
        res = []
        for o in orders:
            items = []
            for l in o.lines:
                items.append({
                    "id": f"{l.product_id.id}:{l.id}",
                    "product": {
                        "id": l.product_id.id,
                        "name": l.product_id.display_name,
                        "description": l.product_id.description_sale or "",
                        "price": l.price_unit,
                        "imageUrl": f"/web/image?model=product.product&id={l.product_id.id}&field=image_128"
                    },
                    "toppings": [],
                    "quantity": l.qty,
                    "note": "",
                    "itemPrice": l.price_subtotal_incl
                })
            res.append({
                "id": o.id,
                "total": o.amount_total,
                "createdAt": int(o.date_order.timestamp() * 1000),
                "items": items
            })
        return self._ok(res)

    @http.route("/api/swift/v1/orders", type="http", auth="user", methods=["POST"], csrf=False)
    def create_order(self, **kwargs):
        payload = self._json_body()
        order_session_id = payload.get("orderSessionId")
        items = payload.get("items", [])
        
        if not items:
            return self._error(_("No items in order"))

        session = None
        if order_session_id:
            session = request.env['pos.session'].sudo().search([('name', '=', order_session_id)], limit=1)
        if not session:
            session = request.env['pos.session'].sudo().search([('state', '=', 'opened')], limit=1, order='id desc')
        
        if not session:
            return self._error(_("No open POS session found"))

        order_vals = {
            'session_id': session.id,
            'user_id': request.env.uid,
            'state': 'draft',
            'date_order': fields.Datetime.now(),
        }
        order = request.env['pos.order'].sudo().create(order_vals)
        for item in items:
            product = request.env['product.product'].sudo().browse(item['productId'])
            request.env['pos.order.line'].sudo().create({
                'order_id': order.id,
                'product_id': product.id,
                'qty': item['quantity'],
                'price_unit': product.lst_price,
                'full_product_name': product.display_name,
                'price_subtotal': product.lst_price * item['quantity'],
                'price_subtotal_incl': product.lst_price * item['quantity'],
            })
        
        order._compute_prices()
        return self._ok({
            "orderId": order.id,
            "orderSessionId": session.name,
            "createdAt": int(order.date_order.timestamp() * 1000)
        })

    # 2. Auth & Staff APIs
    @http.route("/api/swift/v1/auth/login", type="http", auth="none", methods=["POST"], csrf=False)
    def login(self, **kwargs):
        payload = self._json_body()
        db = payload.get("db") or request.db
        login = payload.get("username") or payload.get("login")
        password = payload.get("password")
        
        if not login or not password:
            return self._error(_("Username and password are required"))

        try:
            with ExitStack() as stack:
                if not request.db or request.db != db:
                    cr = stack.enter_context(odoo.modules.registry.Registry(db).cursor())
                    env = odoo.api.Environment(cr, None, {})
                else:
                    env = request.env
                
                request.session.authenticate(env, {"login": login, "password": password, "type": "password"})
                request.session.db = db
                request._save_session(env)
                user = env['res.users'].sudo().browse(request.session.uid)
                profile = env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
                
                data = {
                    "accessToken": request.session.sid,
                    "refreshToken": "optional_refresh_token",
                    "expiresAt": int((fields.Datetime.now().timestamp() + 3600) * 1000),
                    "user": {
                        "id": str(user.id),
                        "name": user.name,
                        "code": profile.employee_code if profile else f"NV{user.id}",
                        "phone": profile.phone if profile else "",
                        "branchId": "cn_trung_tam"
                    }
                }
                return self._ok(data)
        except AccessDenied:
            return self._error(_("Wrong login/password"), status=401)
        except Exception as e:
            return self._error(str(e), status=500)

    @http.route("/api/swift/v1/auth/me", type="http", auth="user", methods=["GET"], csrf=False)
    def auth_me(self, **kwargs):
        user = request.env.user
        profile = request.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        data = {
            "id": str(user.id),
            "name": user.name,
            "code": profile.employee_code if profile else f"NV{user.id}",
            "phone": profile.phone if profile else "",
            "branchId": "cn_trung_tam"
        }
        return self._ok(data)

    @http.route("/api/swift/v1/auth/logout", type="http", auth="user", methods=["POST"], csrf=False)
    def logout(self, **kwargs):
        request.session.logout(keep_db=True)
        return self._ok({"message": _("Logged out successfully")})

    @http.route("/api/swift/v1/staff/me", type="http", auth="user", methods=["GET"], csrf=False)
    def staff_me(self, **kwargs):
        user = request.env.user
        profile = request.env['swift.employee.profile'].sudo().search([('user_id', '=', user.id)], limit=1)
        data = {
            "id": str(user.id),
            "name": user.name,
            "code": profile.employee_code if profile else f"NV{user.id}",
            "phone": profile.phone if profile else "",
            "salaryBranch": {"id": "cn_trung_tam", "name": _("Chi nhánh trung tâm")},
            "workingBranch": {"id": "cn_trung_tam", "name": _("Chi nhánh trung tâm")},
            "avatarUrl": f"/web/image?model=res.users&id={user.id}&field=image_128"
        }
        return self._ok(data)

    # 3. Shift APIs
    @http.route("/api/swift/v1/shifts/current", type="http", auth="user", methods=["GET"], csrf=False)
    def current_shift(self, **kwargs):
        shift = request.env['swift.staff.shift'].sudo().search([
            ('employee_id', '=', request.env.uid),
            ('state', '=', 'active')
        ], limit=1)
        if shift:
            return self._ok({
                "id": shift.id,
                "checkIn": fields.Datetime.to_string(shift.check_in),
                "state": "active"
            })
        return self._ok(None)

    @http.route("/api/swift/v1/shifts/check-in", type="http", auth="user", methods=["POST"], csrf=False)
    def shift_checkin(self, **kwargs):
        payload = self._json_body()
        note = payload.get("note", "")
        shift = request.env['swift.staff.shift'].sudo().create({
            'employee_id': request.env.uid,
            'check_in': fields.Datetime.now(),
            'state': 'active',
            'note': note
        })
        return self._ok({"id": shift.id, "state": shift.state})

    @http.route("/api/swift/v1/shifts/check-out", type="http", auth="user", methods=["POST"], csrf=False)
    def shift_checkout(self, **kwargs):
        shift = request.env['swift.staff.shift'].sudo().search([
            ('employee_id', '=', request.env.uid),
            ('state', '=', 'active')
        ], limit=1)
        if not shift:
            return self._error(_("No active shift found"))
        shift.write({
            'check_out': fields.Datetime.now(),
            'state': 'done'
        })
        return self._ok({"id": shift.id, "state": shift.state})

    @http.route("/api/swift/v1/shifts/close", type="http", auth="user", methods=["POST"], csrf=False)
    def shift_close(self, **kwargs):
        payload = self._json_body()
        shift_id = payload.get("shiftId")
        shift = request.env['swift.staff.shift'].sudo().browse(int(shift_id))
        if not shift.exists():
            return self._error(_("Shift not found"))
        shift.write({
            'closing_total': payload.get("closingTotal", 0),
            'cash_amount': payload.get("cashAmount", 0),
            'transfer_amount': payload.get("transferAmount", 0),
            'state': 'done',
            'check_out': fields.Datetime.now() if not shift.check_out else shift.check_out
        })
        return self._ok({"message": _("Shift closed successfully")})

    # 4. Timesheets
    @http.route("/api/swift/v1/timesheets", type="http", auth="user", methods=["GET"], csrf=False)
    def get_timesheets(self, **kwargs):
        dashboard = request.env["pos.dashboard.swift"]
        data = dashboard.get_attendance_overview()
        return self._ok({"items": data.get("rows", [])})

    # 5. Inventory
    @http.route("/api/swift/v1/inventory/items", type="http", auth="user", methods=["GET"], csrf=False)
    def get_inventory_items(self, **kwargs):
        keyword = request.httprequest.args.get('keyword', '')
        config_id = request.httprequest.args.get('branchId')
        dashboard = request.env["pos.dashboard.swift"]
        items = dashboard.get_inventory_products(keyword=keyword, config_id=config_id)
        # Match sample shape: { id, name, sku, price, stock, imageUrl }
        res = []
        for i in items:
            res.append({
                "id": i["id"],
                "name": i["name"],
                "sku": i["barcode"],
                "price": i["price"],
                "stock": i["qty_on_hand"],
                "imageUrl": f"/web/image?model=product.product&id={i['id']}&field=image_128"
            })
        return self._ok({"items": res, "total": len(res)})

    @http.route("/api/swift/v1/inventory/categories", type="http", auth="user", methods=["GET"], csrf=False)
    def get_inventory_categories(self, **kwargs):
        cats = request.env['pos.category'].sudo().search([])
        res = [{"id": c.id, "name": c.name} for c in cats]
        return self._ok(res)

    # 6. Transfers
    @http.route("/api/swift/v1/transfers", type="http", auth="user", methods=["GET"], csrf=False)
    def get_transfers(self, **kwargs):
        config_id = request.httprequest.args.get('branchId')
        dashboard = request.env["pos.dashboard.swift"]
        transfers = dashboard.get_stock_transfers(config_id=config_id)
        # Transform to req doc shape
        res = []
        for t in transfers:
            res.append({
                "id": str(t["id"]),
                "code": t["name"],
                "status": t["state"],
                "fromBranch": {"id": t["loc_src_id"], "name": t["loc_src"]},
                "toBranch": {"id": t["loc_dest_id"], "name": t["loc_dest"]},
                "createdAt": int(fields.Datetime.from_string(t["date_transfer"]).timestamp() * 1000) if t["date_transfer"] else 0,
                "amount": t["total_value"],
                "preview": ""
            })
        return self._ok({"items": res, "summary": {"count": len(res)}})

    @http.route("/api/swift/v1/transfers/<int:transfer_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def get_transfer_detail(self, transfer_id, **kwargs):
        dashboard = request.env["pos.dashboard.swift"]
        t = dashboard.get_transfer_detail(transfer_id)
        if not t: return self._error(_("Transfer not found"))
        return self._ok(t)

    @http.route("/api/swift/v1/transfers", type="http", auth="user", methods=["POST"], csrf=False)
    def create_transfer(self, **kwargs):
        payload = self._json_body()
        dashboard = request.env["pos.dashboard.swift"]
        res = dashboard.create_or_update_transfer(payload)
        return self._ok(res)

    @http.route("/api/swift/v1/transfers/<int:transfer_id>/receive", type="http", auth="user", methods=["POST"], csrf=False)
    def receive_transfer(self, transfer_id, **kwargs):
        payload = self._json_body()
        dashboard = request.env["pos.dashboard.swift"]
        dashboard.action_receive_transfer(transfer_id, payload.get("items", []))
        return self._ok({"message": "Received"})

    # 7. Stock Checks
    @http.route("/api/swift/v1/stock-checks", type="http", auth="user", methods=["GET"], csrf=False)
    def get_stock_checks(self, **kwargs):
        dashboard = request.env["pos.dashboard.swift"]
        checks = dashboard.get_recent_inventories()
        res = []
        for c in checks:
            res.append({
                "id": str(c["id"]),
                "code": c["name"],
                "status": c["status"],
                "branchName": c["branch_name"],
                "createdAt": int(fields.Datetime.from_string(c["date"]).timestamp() * 1000) if c["date"] else 0,
            })
        return self._ok({"items": res, "summary": {"count": len(res)}})

    @http.route("/api/swift/v1/stock-checks", type="http", auth="user", methods=["POST"], csrf=False)
    def create_stock_check(self, **kwargs):
        payload = self._json_body()
        dashboard = request.env["pos.dashboard.swift"]
        res_id = dashboard.create_or_update_inventory(payload)
        return self._ok({"id": res_id})

    # 8. Common
    @http.route("/api/swift/v1/branches", type="http", auth="user", methods=["GET"], csrf=False)
    def get_branches(self, **kwargs):
        branches = request.env['pos.config'].sudo().search([('active', '=', True)])
        res = [{"id": str(b.id), "name": b.name} for b in branches]
        return self._ok(res)

    @http.route("/api/swift/v1/users", type="http", auth="user", methods=["GET"], csrf=False)
    def get_users(self, **kwargs):
        dashboard = request.env["pos.dashboard.swift"]
        users = dashboard._get_attendance_staff_users()
        res = [{"id": u.id, "name": u.name} for u in users]
        return self._ok(res)

    @http.route("/api/swift/v1/customers/search", type="http", auth="user", methods=["GET"], csrf=False)
    def search_customers(self, **kwargs):
        keyword = request.httprequest.args.get('keyword', '')
        domain = [('name', 'ilike', keyword)]
        customers = request.env['res.partner'].sudo().search(domain, limit=20)
        res = [{"id": c.id, "name": c.name, "phone": c.phone or ""} for c in customers]
        return self._ok(res)

    @http.route("/api/swift/v1/price-books", type="http", auth="user", methods=["GET"], csrf=False)
    def get_price_books(self, **kwargs):
        pricebooks = request.env['product.pricelist'].sudo().search([])
        res = [{"id": p.id, "name": p.name} for p in pricebooks]
        return self._ok(res)

    @http.route("/api/swift/v1/payment-methods", type="http", auth="user", methods=["GET"], csrf=False)
    def get_payment_methods(self, **kwargs):
        methods = request.env['pos.payment.method'].sudo().search([])
        res = [{"id": m.id, "name": m.name} for m in methods]
        return self._ok(res)
