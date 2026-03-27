# -*- coding: utf-8 -*-

import base64
import csv
from contextlib import ExitStack
import io
import json
from datetime import datetime
import pytz
import odoo
import odoo.modules.registry
import logging
from odoo import fields, http, _
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request
from werkzeug.utils import secure_filename

_logger = logging.getLogger(__name__)

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

    def _swift_to_int(self, value, default=0):
        try:
            if value in (None, "", False):
                return default
            return int(value)
        except Exception:
            return default

    def _swift_to_float(self, value, default=0.0):
        try:
            if value in (None, "", False):
                return default
            return float(value)
        except Exception:
            return default

    def _swift_get_branch_config(self, branch_id):
        branch_id = self._swift_to_int(branch_id, 0)
        if not branch_id:
            return False
        return request.env["pos.config"].sudo().browse(branch_id).exists()

    def _swift_get_branch_location(self, branch_config):
        if not branch_config:
            return False
        dashboard = request.env["pos.dashboard.swift"]
        try:
            return dashboard._get_pos_stock_location(branch_config)
        except Exception:
            return False

    def _swift_product_category(self, product):
        categories = product.pos_categ_ids or product.product_tmpl_id.pos_categ_ids
        category = categories[:1]
        if category:
            return {"id": category.id, "name": category.name or ""}
        return {"id": "", "name": ""}

    def _swift_brand_name(self, template):
        brand_name = (getattr(template, "swift_brand_name", "") or "").strip()
        if brand_name:
            return brand_name
        seller = template.seller_ids[:1]
        if seller and seller.partner_id:
            return (seller.partner_id.name or "").strip()
        return ""

    def _swift_stock_qty_map(self, product_ids, branch_config=False):
        if not product_ids:
            return {}, False
        location = self._swift_get_branch_location(branch_config)
        quant_domain = [
            ("product_id", "in", product_ids),
            ("location_id.usage", "=", "internal"),
        ]
        if location:
            quant_domain.append(("location_id", "child_of", location.id))
        grouped = request.env["stock.quant"].sudo()._read_group(
            quant_domain,
            groupby=["product_id"],
            aggregates=["quantity:sum"],
        )
        qty_map = {}
        for product, quantity_sum in grouped:
            if product:
                qty_map[product.id] = quantity_sum or 0.0
        return qty_map, location

    def _swift_product_payload(self, product, qty_map=None, location=False):
        qty_map = qty_map or {}
        template = product.product_tmpl_id
        brand_name = self._swift_brand_name(template)
        category = self._swift_product_category(product)
        attrs = template.uom_ids.ids if "uom_ids" in template._fields else []
        qty_on_hand = qty_map.get(product.id, 0.0)
        status = "active" if product.active else "inactive"
        status_label = _("Đang kinh doanh") if product.active else _("Ngừng kinh doanh")
        updated_at = product.write_date or template.write_date or fields.Datetime.now()

        return {
            "id": product.id,
            "name": product.display_name or product.name or "",
            "sku": product.barcode or product.default_code or "",
            "itemCode": product.default_code or product.barcode or "",
            "barcode": product.barcode or "",
            "price": product.lst_price or 0.0,
            "costPrice": product.standard_price or template.standard_price or 0.0,
            "stock": qty_on_hand,
            "category": category,
            "brand": {"id": brand_name, "name": brand_name} if brand_name else {"id": "", "name": ""},
            "unitLabel": product.uom_id.name if product.uom_id else "",
            "uom": product.uom_id.name if product.uom_id else "",
            "attributeIds": attrs,
            "status": status,
            "statusLabel": status_label,
            "warehouseLocation": template.swift_warehouse_location or (location.display_name if location else ""),
            "minStockThreshold": template.swift_min_stock_threshold or 0.0,
            "maxStockThreshold": template.swift_max_stock_threshold or 0.0,
            "imageUrl": f"/web/image?model=product.product&id={product.id}&field=image_128",
            "updatedAt": fields.Datetime.to_string(updated_at),
        }

    def _swift_product_domain(self, search="", category_id=False, branch_id=False):
        domain = [
            ("sale_ok", "=", True),
            ("active", "=", True),
        ]
        if "available_in_pos" in request.env["product.product"]._fields:
            domain.append(("available_in_pos", "=", True))
        branch_config = self._swift_get_branch_config(branch_id)
        if branch_config:
            domain.append(("product_tmpl_id.swift_branch_config_ids", "in", branch_config.ids))
        if search:
            domain += ["|", ("name", "ilike", search), ("barcode", "ilike", search)]
        category_id = self._swift_to_int(category_id, 0)
        if category_id:
            domain.append(("product_tmpl_id.pos_categ_ids", "in", [category_id]))
        return domain, branch_config

    def _swift_apply_initial_stock(self, product, stock_qty, branch_config):
        if stock_qty in (None, ""):
            return
        stock_qty = self._swift_to_float(stock_qty, 0.0)
        location = self._swift_get_branch_location(branch_config)
        if not location:
            location = request.env["stock.location"].sudo().search([("usage", "=", "internal")], limit=1)
        if not location:
            return
        Quant = request.env["stock.quant"].sudo().with_context(inventory_mode=True)
        quant = Quant.search([
            ("product_id", "=", product.id),
            ("location_id", "=", location.id),
        ], limit=1)
        if quant:
            quant.write({"inventory_quantity_auto_apply": stock_qty})
        else:
            Quant.create({
                "product_id": product.id,
                "location_id": location.id,
                "inventory_quantity_auto_apply": stock_qty,
            })

    def _swift_write_product_from_payload(self, tmpl, payload, branch_config=False):
        vals = {}
        if "name" in payload and payload.get("name") is not None:
            name = (payload.get("name") or "").strip()
            if name:
                vals["name"] = name
        if payload.get("sku") is not None or payload.get("barcode") is not None:
            barcode = (payload.get("barcode") or payload.get("sku") or "").strip()
            vals["barcode"] = barcode
        if "salePrice" in payload:
            vals["list_price"] = self._swift_to_float(payload.get("salePrice"), getattr(tmpl, "list_price", 0.0) or 0.0)
        if "costPrice" in payload:
            vals["standard_price"] = self._swift_to_float(payload.get("costPrice"), getattr(tmpl, "standard_price", 0.0) or 0.0)
        if "status" in payload:
            status = (payload.get("status") or "").strip().lower()
            if status in ("inactive", "draft"):
                vals["active"] = False
            elif status == "active":
                vals["active"] = True
        if "brandId" in payload:
            vals["swift_brand_name"] = (payload.get("brandId") or "").strip()
        if "warehouseLocation" in payload:
            vals["swift_warehouse_location"] = (payload.get("warehouseLocation") or "").strip()
        if "minStockThreshold" in payload:
            vals["swift_min_stock_threshold"] = self._swift_to_float(payload.get("minStockThreshold"), getattr(tmpl, "swift_min_stock_threshold", 0.0) or 0.0)
        if "maxStockThreshold" in payload:
            vals["swift_max_stock_threshold"] = self._swift_to_float(payload.get("maxStockThreshold"), getattr(tmpl, "swift_max_stock_threshold", 0.0) or 0.0)

        category_id = self._swift_to_int(payload.get("categoryId"), 0)
        if category_id and "pos_categ_ids" in tmpl._fields:
            category = request.env["pos.category"].sudo().browse(category_id).exists()
            if category:
                vals["pos_categ_ids"] = [(6, 0, [category.id])]

        attribute_ids = payload.get("attributeIds") or []
        if "uom_ids" in tmpl._fields and isinstance(attribute_ids, list):
            uom_ids = []
            for item in attribute_ids:
                uom_id = self._swift_to_int(item, 0)
                if uom_id:
                    uom = request.env["uom.uom"].sudo().browse(uom_id).exists()
                    if uom:
                        uom_ids.append(uom.id)
            vals["uom_ids"] = [(6, 0, uom_ids)]

        if payload.get("imageId"):
            attachment = request.env["ir.attachment"].sudo().browse(self._swift_to_int(payload.get("imageId"), 0)).exists()
            if attachment and attachment.datas:
                vals["image_1920"] = attachment.datas

        if "swift_branch_config_ids" in tmpl._fields:
            branch_ids = []
            if isinstance(payload.get("branchIds"), list):
                branch_ids = [self._swift_to_int(bid, 0) for bid in payload.get("branchIds") if self._swift_to_int(bid, 0)]
            elif payload.get("branchId"):
                branch = self._swift_get_branch_config(payload.get("branchId"))
                branch_ids = [branch.id] if branch else []
            elif branch_config:
                branch_ids = [branch_config.id]
            if branch_ids:
                vals["swift_branch_config_ids"] = [(6, 0, branch_ids)]

        if "type" in tmpl._fields:
            vals.setdefault("type", "consu")
        if "is_storable" in tmpl._fields:
            vals.setdefault("is_storable", True)

        return vals

    def _swift_product_history_payload(self, product):
        stock_moves = request.env["stock.move.line"].sudo().search(
            [("product_id", "=", product.id), ("state", "=", "done")],
            order="date desc, id desc",
            limit=50,
        )
        stock_items = []
        for move in stock_moves:
            stock_items.append({
                "id": move.id,
                "date": fields.Datetime.to_string(move.date) if move.date else "",
                "reference": move.reference or move.picking_id.name or move.move_id.reference or "",
                "quantity": move.qty_done,
                "source": move.location_id.display_name if move.location_id else "",
                "destination": move.location_dest_id.display_name if move.location_dest_id else "",
                "state": move.state,
            })

        sale_lines = request.env["sale.order.line"].sudo().search(
            [("product_id", "=", product.id)],
            order="write_date desc, id desc",
            limit=25,
        )
        pos_lines = request.env["pos.order.line"].sudo().search(
            [("product_id", "=", product.id)],
            order="write_date desc, id desc",
            limit=25,
        )
        price_items = []
        for line in sale_lines:
            price_items.append({
                "id": f"sale-{line.id}",
                "date": fields.Datetime.to_string(line.write_date) if line.write_date else "",
                "reference": line.order_id.name or "",
                "price": line.price_unit,
                "source": "sale.order.line",
            })
        for line in pos_lines:
            price_items.append({
                "id": f"pos-{line.id}",
                "date": fields.Datetime.to_string(line.write_date) if line.write_date else "",
                "reference": line.order_id.name or "",
                "price": line.price_unit,
                "source": "pos.order.line",
            })

        return stock_items, price_items

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
        
        # Dynamic database detection:
        # 1. From payload 'db'
        # 2. From current request.db (session/domain/config)
        # 3. Fallback to the first available DB if only one exists (optional/conservative)
        db = payload.get("db") or request.db
        
        if not db:
            # If still no DB, try to find it from Odoo service
            try:
                db_list = odoo.service.db.list_dbs()
                if len(db_list) == 1:
                    db = db_list[0]
            except Exception:
                pass
            
            # Default fallback for Orinx
            if not db:
                db = "orinx-manufacturing"

        username = payload.get("username") or payload.get("login")
        password = payload.get("password")
        
        if not username or not password:
            return self._error(_("Username and password are required"))

        try:
            with ExitStack() as stack:
                if not request.db or request.db != db:
                    registry = odoo.modules.registry.Registry(db)
                    cr = stack.enter_context(registry.cursor())
                    # Use SUPERUSER_ID to ensure the environment has full access to the registry
                    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                else:
                    env = request.env
                
                # Verify that the model exists in the registry before proceeding
                if 'swift.employee.profile' not in env.registry:
                    return self._error(_("Model 'swift.employee.profile' not found in database '%s'. Please ensure the 'pos_theme_swift' module is installed and upgraded.") % db, status=500)

                # Allow login with phone number as a fallback (checking both partner and employee profile)
                # handle both 0xxx and +84xxx formats
                alt_phone = username.replace('0', '+84', 1) if username.startswith('0') else username.replace('+84', '0', 1)
                target_user = env['res.users'].sudo().with_context(active_test=True).search([
                    '|', ('login', '=', username),
                    '|', ('partner_id.phone', 'ilike', username),
                    '|', ('partner_id.phone', 'ilike', alt_phone),
                    '|', ('id', 'in', env['swift.employee.profile'].sudo().search([('phone', 'ilike', username)]).mapped('user_id').ids),
                    ('id', 'in', env['swift.employee.profile'].sudo().search([('phone', 'ilike', alt_phone)]).mapped('user_id').ids)
                ], limit=1)
                login_id = target_user.login if target_user else username
                _logger.info("Login attempt for %s -> mapped to login_id %s (target_user_id: %s)", username, login_id, target_user.id if target_user else None)

                try:
                    request.session.authenticate(env, {"login": login_id, "password": password, "type": "password"})
                except AccessDenied:
                    # Fallback to original username if mapped login failed
                    if login_id != username:
                        try:
                            request.session.authenticate(env, {"login": username, "password": password, "type": "password"})
                        except AccessDenied:
                            return self._error(_("Wrong login/password"), status=401)
                    else:
                        return self._error(_("Wrong login/password"), status=401)
                except Exception as e:
                    return self._error(str(e), status=401)
                request.session.db = db
                request._save_session(env)

                # Post-authentication, get the user and profile
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
        profile = False
        if 'swift.employee.profile' in request.env.registry:
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
        profile = False
        if 'swift.employee.profile' in request.env.registry:
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

    @http.route("/api/swift/v1/product-categories", type="http", auth="user", methods=["GET"], csrf=False)
    def get_product_categories(self, **kwargs):
        return self.get_inventory_categories(**kwargs)

    @http.route("/api/swift/v1/products", type="http", auth="user", methods=["GET"], csrf=False)
    def get_products(self, **kwargs):
        args = request.httprequest.args
        search = (args.get("search") or args.get("keyword") or "").strip()
        category_id = args.get("categoryId") or args.get("category_id") or ""
        branch_id = args.get("branchId") or args.get("config_id") or ""
        sort_by = (args.get("sortBy") or "price").strip()
        sort_order = (args.get("sortOrder") or "desc").strip().lower()
        page = max(self._swift_to_int(args.get("page"), 1), 1)
        page_size = max(self._swift_to_int(args.get("pageSize"), 20), 1)

        domain, branch_config = self._swift_product_domain(search=search, category_id=category_id, branch_id=branch_id)
        products = request.env["product.product"].sudo().search(domain)
        qty_map, location = self._swift_stock_qty_map(products.ids, branch_config=branch_config)

        items = [self._swift_product_payload(product, qty_map=qty_map, location=location) for product in products]
        reverse = sort_order != "asc"
        if sort_by == "name":
            items.sort(key=lambda item: (item.get("name") or "").lower(), reverse=reverse)
        elif sort_by == "stock":
            items.sort(key=lambda item: item.get("stock", 0.0), reverse=reverse)
        else:
            items.sort(key=lambda item: item.get("price", 0.0), reverse=reverse)

        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return self._ok({
            "items": items[start:end],
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": total,
            },
        })

    @http.route("/api/swift/v1/products/summary", type="http", auth="user", methods=["GET"], csrf=False)
    def get_products_summary(self, **kwargs):
        args = request.httprequest.args
        search = (args.get("search") or args.get("keyword") or "").strip()
        category_id = args.get("categoryId") or args.get("category_id") or ""
        branch_id = args.get("branchId") or args.get("config_id") or ""
        domain, branch_config = self._swift_product_domain(search=search, category_id=category_id, branch_id=branch_id)
        products = request.env["product.product"].sudo().search(domain)
        qty_map, _location = self._swift_stock_qty_map(products.ids, branch_config=branch_config)
        total_stock_value = 0.0
        for product in products:
            total_stock_value += (qty_map.get(product.id, 0.0) or 0.0) * (product.standard_price or 0.0)
        return self._ok({
            "totalItems": len(products),
            "totalStockValue": total_stock_value,
        })

    @http.route("/api/swift/v1/products/by-barcode/<string:barcode>", type="http", auth="user", methods=["GET"], csrf=False)
    def get_product_by_barcode(self, barcode, **kwargs):
        branch_id = request.httprequest.args.get("branchId") or request.httprequest.args.get("config_id") or ""
        branch_config = self._swift_get_branch_config(branch_id)
        domain = [
            ("barcode", "=", barcode),
            ("sale_ok", "=", True),
            ("active", "=", True),
        ]
        if "available_in_pos" in request.env["product.product"]._fields:
            domain.append(("available_in_pos", "=", True))
        if branch_config:
            domain.append(("product_tmpl_id.swift_branch_config_ids", "in", branch_config.ids))
        product = request.env["product.product"].sudo().search(domain, limit=1)
        if not product:
            return self._error(_("Product not found"), status=404)
        qty_map, location = self._swift_stock_qty_map(product.ids, branch_config=branch_config)
        return self._ok(self._swift_product_payload(product, qty_map=qty_map, location=location))

    @http.route("/api/swift/v1/products/export-stock-report", type="http", auth="user", methods=["POST"], csrf=False)
    def export_stock_report(self, **kwargs):
        payload = self._json_body()
        search = (payload.get("search") or payload.get("keyword") or "").strip()
        category_id = payload.get("categoryId") or payload.get("category_id") or ""
        branch_id = payload.get("branchId") or payload.get("config_id") or ""
        sort_by = (payload.get("sortBy") or "price").strip()
        sort_order = (payload.get("sortOrder") or "desc").strip().lower()
        domain, branch_config = self._swift_product_domain(search=search, category_id=category_id, branch_id=branch_id)
        products = request.env["product.product"].sudo().search(domain)
        qty_map, location = self._swift_stock_qty_map(products.ids, branch_config=branch_config)
        items = [self._swift_product_payload(product, qty_map=qty_map, location=location) for product in products]
        reverse = sort_order != "asc"
        if sort_by == "name":
            items.sort(key=lambda item: (item.get("name") or "").lower(), reverse=reverse)
        elif sort_by == "stock":
            items.sort(key=lambda item: item.get("stock", 0.0), reverse=reverse)
        else:
            items.sort(key=lambda item: item.get("price", 0.0), reverse=reverse)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["ID", "Name", "SKU", "Barcode", "Price", "Cost Price", "Stock", "Category", "Brand", "Unit", "Status"])
        for item in items:
            writer.writerow([
                item.get("id"),
                item.get("name"),
                item.get("sku"),
                item.get("barcode"),
                item.get("price"),
                item.get("costPrice"),
                item.get("stock"),
                item.get("category", {}).get("name", ""),
                item.get("brand", {}).get("name", ""),
                item.get("unitLabel"),
                item.get("statusLabel"),
            ])

        file_name = "bao-cao-ton-kho.csv"
        attachment = request.env["ir.attachment"].sudo().create({
            "name": file_name,
            "type": "binary",
            "datas": base64.b64encode(buffer.getvalue().encode("utf-8")),
            "mimetype": "text/csv",
        })
        return self._ok({
            "fileUrl": f"/web/content/{attachment.id}?download=true",
            "fileName": file_name,
        })

    @http.route("/api/swift/v1/products", type="http", auth="user", methods=["POST"], csrf=False)
    def create_product(self, **kwargs):
        payload = self._json_body()
        name = (payload.get("name") or "").strip()
        if not name:
            return self._error(_("Name is required"))

        tmpl_model = request.env["product.template"].sudo()
        tmpl_vals = self._swift_write_product_from_payload(tmpl_model, payload)
        tmpl_vals["name"] = name
        if "sale_ok" in tmpl_model._fields:
            tmpl_vals["sale_ok"] = True
        if "available_in_pos" in tmpl_model._fields:
            tmpl_vals["available_in_pos"] = True

        branch_config = self._swift_get_branch_config(payload.get("branchId") or payload.get("config_id") or "")
        if branch_config and "swift_branch_config_ids" in tmpl_model._fields and not tmpl_vals.get("swift_branch_config_ids"):
            tmpl_vals["swift_branch_config_ids"] = [(6, 0, [branch_config.id])]

        template = tmpl_model.create(tmpl_vals)
        product = template.product_variant_id or template.product_variant_ids[:1]
        if not product:
            return self._error(_("Cannot create product"), status=500)

        self._swift_apply_initial_stock(product, payload.get("stockQuantity"), branch_config)
        qty_map, location = self._swift_stock_qty_map(product.ids, branch_config=branch_config)
        return self._ok(self._swift_product_payload(product, qty_map=qty_map, location=location))

    @http.route("/api/swift/v1/services", type="http", auth="user", methods=["POST"], csrf=False)
    def create_service(self, **kwargs):
        payload = self._json_body()
        name = (payload.get("name") or "").strip()
        if not name:
            return self._error(_("Name is required"))

        tmpl_model = request.env["product.template"].sudo()
        tmpl_vals = self._swift_write_product_from_payload(tmpl_model, payload)
        tmpl_vals["name"] = name
        if "sale_ok" in tmpl_model._fields:
            tmpl_vals["sale_ok"] = True
        if "available_in_pos" in tmpl_model._fields:
            tmpl_vals["available_in_pos"] = True
        if "detailed_type" in tmpl_model._fields:
            tmpl_vals["detailed_type"] = "service"
        elif "type" in tmpl_model._fields:
            tmpl_vals["type"] = "service"

        template = tmpl_model.create(tmpl_vals)
        product = template.product_variant_id or template.product_variant_ids[:1]
        if not product:
            return self._error(_("Cannot create service"), status=500)
        qty_map, location = self._swift_stock_qty_map(product.ids, branch_config=False)
        return self._ok(self._swift_product_payload(product, qty_map=qty_map, location=location))

    @http.route("/api/swift/v1/products/<int:product_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def get_product_detail(self, product_id, **kwargs):
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        branch_id = request.httprequest.args.get("branchId") or request.httprequest.args.get("config_id") or ""
        branch_config = self._swift_get_branch_config(branch_id)
        qty_map, location = self._swift_stock_qty_map(product.ids, branch_config=branch_config)
        return self._ok(self._swift_product_payload(product, qty_map=qty_map, location=location))

    @http.route("/api/swift/v1/products/<int:product_id>", type="http", auth="user", methods=["PATCH"], csrf=False)
    def update_product(self, product_id, **kwargs):
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        payload = self._json_body()
        branch_config = self._swift_get_branch_config(payload.get("branchId") or payload.get("config_id") or "")
        tmpl_vals = self._swift_write_product_from_payload(product.product_tmpl_id, payload, branch_config=branch_config)
        if tmpl_vals:
            product.product_tmpl_id.sudo().write(tmpl_vals)
        if "stockQuantity" in payload:
            self._swift_apply_initial_stock(product, payload.get("stockQuantity"), branch_config)
        qty_map, location = self._swift_stock_qty_map(product.ids, branch_config=branch_config)
        return self._ok(self._swift_product_payload(product, qty_map=qty_map, location=location))

    @http.route("/api/swift/v1/products/<int:product_id>", type="http", auth="user", methods=["DELETE"], csrf=False)
    def delete_product(self, product_id, **kwargs):
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        try:
            product.product_tmpl_id.sudo().unlink()
            return self._ok({"message": _("Deleted successfully")})
        except Exception as e:
            return self._error(str(e), status=500)

    @http.route("/api/swift/v1/products/<int:product_id>/change-status", type="http", auth="user", methods=["POST"], csrf=False)
    def change_product_status(self, product_id, **kwargs):
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        payload = self._json_body()
        status = (payload.get("status") or "").strip().lower()
        if status not in ("active", "inactive", "draft"):
            return self._error(_("Invalid status"))
        product.product_tmpl_id.sudo().write({"active": status == "active"})
        branch_id = payload.get("branchId") or payload.get("config_id") or ""
        branch_config = self._swift_get_branch_config(branch_id)
        qty_map, location = self._swift_stock_qty_map(product.ids, branch_config=branch_config)
        return self._ok(self._swift_product_payload(product, qty_map=qty_map, location=location))

    @http.route("/api/swift/v1/products/<int:product_id>/stock-history", type="http", auth="user", methods=["GET"], csrf=False)
    def product_stock_history(self, product_id, **kwargs):
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        stock_items, _price_items = self._swift_product_history_payload(product)
        return self._ok({"items": stock_items})

    @http.route("/api/swift/v1/products/<int:product_id>/price-history", type="http", auth="user", methods=["GET"], csrf=False)
    def product_price_history(self, product_id, **kwargs):
        product = request.env["product.product"].sudo().browse(product_id).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        _stock_items, price_items = self._swift_product_history_payload(product)
        return self._ok({"items": price_items})

    @http.route("/api/swift/v1/brands", type="http", auth="user", methods=["GET"], csrf=False)
    def get_brands(self, **kwargs):
        templates = request.env["product.template"].sudo().search([])
        brand_names = set()
        for template in templates:
            brand = self._swift_brand_name(template)
            if brand:
                brand_names.add(brand)
        res = [{"id": name, "name": name} for name in sorted(brand_names, key=lambda v: v.lower())]
        return self._ok({"items": res})

    @http.route("/api/swift/v1/product-attributes", type="http", auth="user", methods=["GET"], csrf=False)
    def get_product_attributes(self, **kwargs):
        uoms = request.env["uom.uom"].sudo().search([])
        res = [{"id": u.id, "name": u.name} for u in uoms]
        return self._ok({"items": res})

    @http.route("/api/swift/v1/product-attributes", type="http", auth="user", methods=["POST"], csrf=False)
    def create_product_attribute(self, **kwargs):
        payload = self._json_body()
        name = (payload.get("name") or "").strip()
        if not name:
            return self._error(_("Name is required"))
        category = request.env.ref("uom.product_uom_categ_unit", raise_if_not_found=False)
        if not category:
            category = request.env["uom.category"].sudo().search([], limit=1)
        vals = {"name": name}
        if category:
            vals["category_id"] = category.id
        if "uom_type" in request.env["uom.uom"]._fields:
            vals["uom_type"] = "reference"
        if "measure_type" in request.env["uom.uom"]._fields:
            vals["measure_type"] = "unit"
        if "factor" in request.env["uom.uom"]._fields:
            vals["factor"] = 1.0
        uom = request.env["uom.uom"].sudo().create(vals)
        return self._ok({"id": uom.id, "name": uom.name})

    @http.route("/api/swift/v1/uploads/images", type="http", auth="user", methods=["POST"], csrf=False)
    def upload_product_image(self, **kwargs):
        file_storage = (
            request.httprequest.files.get("file")
            or request.httprequest.files.get("image")
            or request.httprequest.files.get("upload")
        )
        if not file_storage:
            return self._error(_("Image file is required"))
        content = file_storage.read()
        if not content:
            return self._error(_("Image file is empty"))
        attachment = request.env["ir.attachment"].sudo().create({
            "name": secure_filename(file_storage.filename or "product-image"),
            "datas": base64.b64encode(content),
            "mimetype": file_storage.mimetype or "application/octet-stream",
            "type": "binary",
        })
        return self._ok({
            "id": attachment.id,
            "url": f"/web/content/{attachment.id}?download=false",
        })

    @http.route("/api/swift/v1/uploads/images/<int:image_id>", type="http", auth="user", methods=["DELETE"], csrf=False)
    def delete_product_image(self, image_id, **kwargs):
        attachment = request.env["ir.attachment"].sudo().browse(image_id).exists()
        if not attachment:
            return self._error(_("Image not found"), status=404)
        attachment.sudo().unlink()
        return self._ok({"message": _("Deleted successfully")})

    # 6. Transfers
    @http.route("/api/swift/v1/transfers", type="http", auth="user", methods=["GET"], csrf=False)
    def get_transfers(self, **kwargs):
        args = request.httprequest.args
        branch_id = args.get('branchId')
        period = args.get('period')
        status = args.get('status')
        receipt_state = args.get('receiptState')
        keyword = args.get('keyword')
        page = max(self._swift_to_int(args.get('page'), 1), 1)
        page_size = max(self._swift_to_int(args.get('pageSize'), 20), 1)

        filters = {}
        if status:
            filters['states'] = status.split(',')
        if period:
            filters['date_range'] = period
        if keyword:
            filters['keyword'] = keyword
        if receipt_state:
            filters['receipt_state'] = receipt_state.split(',')

        dashboard = request.env["pos.dashboard.swift"]
        # We might need to update get_stock_transfers to handle more filters
        transfers = dashboard.get_stock_transfers(filters=filters, config_id=branch_id)
        
        # Transform to req doc shape
        res = []
        for t in transfers:
            # Try to get a preview product name
            preview = ""
            total_items = 0
            total_qty = 0
            received_qty = 0
            receipt_state_val = "none"

            if t.get("id"):
                transfer_rec = request.env['swift.stock.transfer'].sudo().browse(t["id"])
                total_items = len(transfer_rec.line_ids)
                total_qty = sum(transfer_rec.line_ids.mapped('qty'))
                received_qty = sum(transfer_rec.line_ids.mapped('received_qty'))
                
                if received_qty >= total_qty and total_qty > 0:
                    receipt_state_val = "full"
                elif received_qty > 0:
                    receipt_state_val = "partial"
                elif t["state"] in ('done', 'received'):
                    # if done but no received_qty tracked, assume full
                    receipt_state_val = "full"
                else:
                    receipt_state_val = "pending"

                if transfer_rec.line_ids:
                    first_line = transfer_rec.line_ids[0]
                    preview = f"{first_line.product_id.display_name} x{int(first_line.qty)}"
                    if total_items > 1:
                        preview += f" (+{total_items - 1})"

            # Filter by receiptState if provided
            incoming_receipt_state_filter = filters.get('receipt_state', [])
            if incoming_receipt_state_filter and receipt_state_val not in incoming_receipt_state_filter:
                continue

            res.append({
                "id": str(t["id"]),
                "code": t["name"],
                "status": t["state"],
                "fromBranch": {"id": str(t["loc_src_config_id"]), "name": t["loc_src"]},
                "toBranch": {"id": str(t["loc_dest_config_id"]), "name": t["loc_dest"]},
                "createdAt": int(fields.Datetime.from_string(t["date_transfer"]).timestamp() * 1000) if t["date_transfer"] else 0,
                "amount": t["total_value"],
                "preview": preview,
                "totalItems": total_items,
                "totalQuantity": total_qty,
                "receivedQuantity": received_qty,
                "receiptState": receipt_state_val
            })

        total = len(res)
        start = (page - 1) * page_size
        end = start + page_size
        
        return self._ok({
            "items": res[start:end],
            "summary": {"count": total}
        })

    @http.route("/api/swift/v1/transfers/filter-options", type="http", auth="user", methods=["GET"], csrf=False)
    def get_transfer_filter_options(self, **kwargs):
        data = {
            "periodOptions": [
                { "value": "today", "label": _("Hôm nay") },
                { "value": "last_7_days", "label": _("7 ngày gần đây") },
                { "value": "this_month", "label": _("Tháng này") },
                { "value": "last_month", "label": _("Tháng trước") }
            ],
            "statusOptions": [
                { "value": "draft", "label": _("Phiếu tạm") },
                { "value": "shipped", "label": _("Đang chuyển") },
                { "value": "done", "label": _("Đã nhận") },
                { "value": "cancel", "label": _("Đã huỷ") }
            ],
            "receiptStateOptions": [
                { "value": "full", "label": _("Nhận đủ") },
                { "value": "pending", "label": _("Chưa nhận đủ") },
                { "value": "partial", "label": _("Nhận một phần") }
            ]
        }
        return self._ok(data)

    @http.route("/api/swift/v1/transfers/<int:transfer_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def get_transfer_detail(self, transfer_id, **kwargs):
        branch_id = request.httprequest.args.get('branchId')
        dashboard = request.env["pos.dashboard.swift"]
        t = dashboard.get_transfer_detail(transfer_id, config_id=branch_id)
        if not t: return self._error(_("Transfer not found"), status=404)
        
        # Ensure name is TRF...
        t['name'] = t.get('name') or f"TRF{str(transfer_id).zfill(5)}"
        
        return self._ok(t)

    @http.route("/api/swift/v1/transfers", type="http", auth="user", methods=["POST"], csrf=False)
    def create_transfer(self, **kwargs):
        payload = self._json_body()
        dashboard = request.env["pos.dashboard.swift"]
        
        # Map README fields to Odoo internal fields if different
        processed_payload = {
            'config_id': payload.get('fromBranchId'),
            'dest_config_id': payload.get('toBranchId'),
            'note': payload.get('note', ''),
            'state': payload.get('status', 'draft'),
            'lines': []
        }
        
        for line in payload.get('lines', []):
            processed_payload['lines'].append({
                'product_id': line.get('productId'),
                'qty': line.get('qty', 0)
            })
            
        try:
            res = dashboard.create_or_update_transfer(processed_payload)
            return self._ok({
                "id": str(res["id"]),
                "code": res["name"],
                "status": res["state"]
            })
        except Exception as e:
            return self._error(str(e))

    @http.route("/api/swift/v1/transfers/<int:transfer_id>", type="http", auth="user", methods=["PATCH"], csrf=False)
    def update_transfer(self, transfer_id, **kwargs):
        payload = self._json_body()
        dashboard = request.env["pos.dashboard.swift"]
        
        processed_payload = {
            'id': transfer_id,
            'dest_config_id': payload.get('toBranchId'),
            'note': payload.get('note'),
            'lines': []
        }
        
        if 'lines' in payload:
            for line in payload.get('lines', []):
                processed_payload['lines'].append({
                    'product_id': line.get('productId'),
                    'qty': line.get('qty', 0)
                })
        else:
            # If lines not provided, we should probably keep existing lines
            # But create_or_update_transfer might unlink them.
            # I'll let the dashboard handle it or fetch existing lines if needed.
            pass
            
        try:
            res = dashboard.create_or_update_transfer(processed_payload)
            return self._ok({
                "id": str(res["id"]),
                "code": res["name"],
                "status": res["state"]
            })
        except Exception as e:
            return self._error(str(e))

    @http.route("/api/swift/v1/transfers/<int:transfer_id>/receive", type="http", auth="user", methods=["POST"], csrf=False)
    def receive_transfer(self, transfer_id, **kwargs):
        payload = self._json_body()
        dashboard = request.env["pos.dashboard.swift"]
        
        # Map README shape: { note, lines: [ { lineId, receivedQty } ] }
        # to dashboard shape: dashboard.action_receive_transfer(transfer_id, lines_data)
        lines_data = []
        for line in payload.get('lines', []):
            lines_data.append({
                'line_id': line.get('lineId'),
                'received_qty': line.get('receivedQty')
            })
            
        try:
            dashboard.action_receive_transfer(transfer_id, lines_data)
            # Re-fetch to return new status
            transfer = request.env['swift.stock.transfer'].sudo().browse(transfer_id)
            return self._ok({
                "id": str(transfer.id),
                "status": transfer.state,
                # We need to compute receiptState: pending, partial, full
                "receiptState": "full" if transfer.state == 'done' else "pending"
            })
        except Exception as e:
            return self._error(str(e))

    @http.route("/api/swift/v1/transfers/<int:transfer_id>/cancel", type="http", auth="user", methods=["POST"], csrf=False)
    def cancel_transfer(self, transfer_id, **kwargs):
        transfer = request.env['swift.stock.transfer'].sudo().browse(transfer_id)
        if not transfer.exists():
            return self._error(_("Transfer not found"), status=404)
        
        try:
            transfer.sudo().action_cancel()
            return self._ok({"message": _("Cancelled successfully")})
        except Exception as e:
            return self._error(str(e))

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
