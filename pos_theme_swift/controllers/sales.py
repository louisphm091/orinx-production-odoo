# -*- coding: utf-8 -*-

import base64
import html

from odoo import fields, http, _
from odoo.exceptions import UserError
from odoo.http import request

from .api import SwiftZaloApiController


class SwiftSalesApiController(SwiftZaloApiController):
    """Sales-focused API surface for the Flutter POS app."""

    # ---------------------------------------------------------------------
    # Generic helpers
    # ---------------------------------------------------------------------

    def _swift_parse_order_id(self, order_ref):
        if isinstance(order_ref, int):
            return order_ref
        if not order_ref:
            return 0

        order_ref = str(order_ref).strip()
        for prefix in ("cart_", "draft_", "order_", "pos_"):
            if order_ref.startswith(prefix):
                order_ref = order_ref[len(prefix):]
                break

        if order_ref.isdigit():
            return int(order_ref)
        return 0

    def _swift_find_order(self, order_ref):
        order_id = self._swift_parse_order_id(order_ref)
        order = request.env["pos.order"].sudo().browse(order_id).exists() if order_id else request.env["pos.order"].sudo().browse()
        if order:
            return order

        ref = (order_ref or "").strip()
        if not ref:
            return request.env["pos.order"].sudo().browse()

        return request.env["pos.order"].sudo().search([
            "|", "|",
            ("name", "=", ref),
            ("pos_reference", "=", ref),
            ("access_token", "=", ref),
        ], limit=1)

    def _swift_open_session(self, branch_id=False):
        branch_config = self._swift_get_branch_config(branch_id)
        if branch_config and branch_config.current_session_id and branch_config.current_session_id.state == "opened":
            return branch_config.current_session_id, branch_config

        if branch_config:
            session = request.env["pos.session"].sudo().search([
                ("config_id", "=", branch_config.id),
                ("state", "=", "opened"),
            ], limit=1, order="id desc")
            if session:
                return session, branch_config

        session = request.env["pos.session"].sudo().search([
            ("state", "=", "opened"),
        ], limit=1, order="id desc")
        if session:
            return session, session.config_id
        return False, branch_config

    def _swift_get_default_partner(self):
        return {
            "id": "walk_in",
            "name": _("Khách lẻ"),
            "phone": "",
            "code": "KH000001",
            "priceListId": self._swift_default_pricelist().id if self._swift_default_pricelist() else "",
        }

    def _swift_default_pricelist(self, branch_config=False):
        branch_config = branch_config or False
        if branch_config and branch_config.pricelist_id:
            return branch_config.pricelist_id
        if request.env.company and request.env.company.partner_id and request.env.company.partner_id.property_product_pricelist:
            return request.env.company.partner_id.property_product_pricelist
        return request.env["product.pricelist"].sudo().search([], limit=1)

    def _swift_default_customer_payload(self, partner=False):
        if not partner:
            return self._swift_get_default_partner()
        pricelist = partner.property_product_pricelist or self._swift_default_pricelist()
        return {
            "id": str(partner.id),
            "name": partner.name or "",
            "phone": partner.phone or partner.mobile or "",
            "code": partner.ref or f"KH{partner.id:06d}",
            "priceListId": pricelist.id if pricelist else "",
        }

    def _swift_payment_method_payload(self, method):
        method_type = method.type if "type" in method._fields else ""
        return {
            "id": method.id,
            "name": method.name,
            "type": method_type,
            "isCash": bool(getattr(method, "is_cash_count", False)),
            "journalId": method.journal_id.id if method.journal_id else False,
        }

    def _swift_order_lines(self, order):
        lines = []
        for line in order.lines.sorted("id"):
            lines.append(self._swift_line_payload(line))
        return lines

    def _swift_is_adjustment_line(self, line):
        code = (line.product_id.default_code or "").strip()
        return code in ("SWIFT_POS_DISCOUNT", "SWIFT_POS_EXTRA")

    def _swift_line_payload(self, line):
        product = line.product_id
        return {
            "lineId": f"line_{line.id}",
            "id": line.id,
            "productId": product.id,
            "product": {
                "id": product.id,
                "name": product.display_name or product.name or "",
                "description": product.description_sale or "",
                "price": line.price_unit,
                "imageUrl": f"/web/image?model=product.product&id={product.id}&field=image_128",
            },
            "quantity": line.qty,
            "unitPrice": line.price_unit,
            "lineTotal": line.price_subtotal_incl,
            "note": line.note or "",
            "isAdjustment": self._swift_is_adjustment_line(line),
        }

    def _swift_order_payload(self, order):
        branch = order.session_id.config_id if order.session_id else False
        partner = order.partner_id if order.partner_id else False
        discount_percent = order.swift_discount_percent or 0.0
        extra_charge = order.swift_extra_charge or 0.0
        subtotal = sum(line.price_subtotal_incl for line in order.lines.filtered(lambda line: not self._swift_is_adjustment_line(line)))
        discount_amount = round(subtotal * discount_percent / 100.0, 2)
        amount_due = order.amount_total if order.state in ("paid", "done") else round(subtotal - discount_amount + extra_charge, 2)

        return {
            "cartId": f"cart_{order.id}",
            "draftId": f"draft_{order.id}",
            "orderId": order.name if order.name and order.name != "/" else f"order_{order.id}",
            "id": order.id,
            "status": order.state,
            "mode": order.swift_mode or "sell",
            "branch": {
                "id": branch.id if branch else "",
                "name": branch.name if branch else "",
            },
            "customer": self._swift_default_customer_payload(partner),
            "priceList": {
                "id": order.pricelist_id.id if order.pricelist_id else "",
                "name": order.pricelist_id.name if order.pricelist_id else "",
            },
            "note": order.swift_note or order.general_customer_note or order.internal_note or "",
            "lines": self._swift_order_lines(order),
            "subtotal": round(subtotal, 2),
            "discountPercent": discount_percent,
            "discountAmount": round(discount_amount, 2),
            "extraCharge": round(extra_charge, 2),
            "amountDue": round(amount_due, 2),
            "itemCount": len(order.lines.filtered(lambda line: not self._swift_is_adjustment_line(line))),
            "createdAt": int(order.date_order.timestamp() * 1000) if order.date_order else 0,
            "updatedAt": int((order.write_date or order.date_order or fields.Datetime.now()).timestamp() * 1000) if (order.write_date or order.date_order) else 0,
        }

    def _swift_adjustment_product(self, kind):
        assert kind in ("discount", "extra")
        code = "SWIFT_POS_DISCOUNT" if kind == "discount" else "SWIFT_POS_EXTRA"
        name = _("Swift POS Discount") if kind == "discount" else _("Swift POS Extra Charge")
        product = request.env["product.template"].sudo().search([
            ("default_code", "=", code),
            ("company_id", "in", [False, request.env.company.id]),
        ], limit=1)
        if product:
            return product.product_variant_id

        unit = request.env.ref("uom.product_uom_unit", raise_if_not_found=False) or request.env["uom.uom"].sudo().search([], limit=1)
        vals = {
            "name": name,
            "default_code": code,
            "sale_ok": True,
            "available_in_pos": True,
            "list_price": 0.0,
        }
        if "detailed_type" in request.env["product.template"]._fields:
            vals["detailed_type"] = "service"
        if "type" in request.env["product.template"]._fields:
            vals["type"] = "service"
        if "company_id" in request.env["product.template"]._fields:
            vals["company_id"] = request.env.company.id
        if unit:
            vals["uom_id"] = unit.id
            vals["uom_po_id"] = unit.id
        template = request.env["product.template"].sudo().create(vals)
        return template.product_variant_id

    def _swift_sync_adjustment_lines(self, order, discount_percent=None, extra_charge=None):
        discount_percent = order.swift_discount_percent if discount_percent is None else self._swift_to_float(discount_percent, 0.0)
        extra_charge = order.swift_extra_charge if extra_charge is None else self._swift_to_float(extra_charge, 0.0)

        base_lines = order.lines.filtered(lambda line: not self._swift_is_adjustment_line(line))
        subtotal = sum(base_lines.mapped("price_subtotal_incl"))
        discount_amount = round(subtotal * discount_percent / 100.0, 2)

        order.lines.filtered(self._swift_is_adjustment_line).unlink()

        if discount_amount:
            discount_product = self._swift_adjustment_product("discount")
            order.env["pos.order.line"].sudo().create({
                "order_id": order.id,
                "product_id": discount_product.id,
                "qty": 1.0,
                "price_unit": -abs(discount_amount),
                "discount": 0.0,
                "tax_ids": [(6, 0, discount_product.taxes_id.ids)],
                "full_product_name": discount_product.display_name or discount_product.name,
                "name": discount_product.display_name or discount_product.name,
            })

        if extra_charge:
            extra_product = self._swift_adjustment_product("extra")
            order.env["pos.order.line"].sudo().create({
                "order_id": order.id,
                "product_id": extra_product.id,
                "qty": 1.0,
                "price_unit": abs(extra_charge),
                "discount": 0.0,
                "tax_ids": [(6, 0, extra_product.taxes_id.ids)],
                "full_product_name": extra_product.display_name or extra_product.name,
                "name": extra_product.display_name or extra_product.name,
            })

        order.write({
            "swift_discount_percent": discount_percent,
            "swift_extra_charge": extra_charge,
        })
        order._compute_prices()
        return order

    def _swift_set_order_context(self, order, payload):
        values = {}
        if "customerId" in payload:
            customer_id = payload.get("customerId")
            partner = request.env["res.partner"].sudo().browse(self._swift_parse_order_id(customer_id)).exists()
            values["partner_id"] = partner.id if partner else False
        if "priceListId" in payload:
            pricelist = request.env["product.pricelist"].sudo().browse(self._swift_parse_order_id(payload.get("priceListId"))).exists()
            if pricelist:
                values["pricelist_id"] = pricelist.id
        if "mode" in payload:
            mode = (payload.get("mode") or "sell").strip().lower()
            values["swift_mode"] = "order" if mode == "order" else "sell"
        if "note" in payload:
            note = (payload.get("note") or "").strip()
            values["swift_note"] = note
            values["general_customer_note"] = note
        if values:
            order.write(values)
        return order

    def _swift_find_payment_method(self, order, method_value):
        session = order.session_id
        methods = session.config_id.payment_method_ids if session and session.config_id else request.env["pos.payment.method"].sudo().browse()

        if isinstance(method_value, int):
            method = methods.filtered(lambda m: m.id == method_value)[:1]
            if method:
                return method

        method_value = (str(method_value or "").strip().lower())
        if method_value in ("cash", "tiền mặt"):
            return methods.filtered(lambda m: getattr(m, "is_cash_count", False))[:1] or methods[:1]
        if method_value in ("transfer", "bank", "card", "wallet", "other", "chuyển khoản"):
            non_cash = methods.filtered(lambda m: not getattr(m, "is_cash_count", False))
            return non_cash[:1] or methods[:1]
        if method_value.isdigit():
            method = methods.filtered(lambda m: m.id == int(method_value))[:1]
            if method:
                return method
        method = methods[:1]
        if not method:
            raise UserError(_("No payment method available for this POS session"))
        return method

    def _swift_add_payment(self, order, payment_method, amount, is_change=False):
        order.add_payment({
            "pos_order_id": order.id,
            "amount": amount,
            "payment_method_id": payment_method.id,
            "payment_date": fields.Datetime.now(),
            "name": payment_method.name,
            "is_change": is_change,
        })

    def _swift_prepare_qr_svg(self, bank_name, account_number, account_name, amount, content):
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="420" height="420" viewBox="0 0 420 420">
          <rect width="420" height="420" fill="#ffffff"/>
          <rect x="20" y="20" width="380" height="380" rx="24" fill="#f7f7f7" stroke="#222" stroke-width="4"/>
          <text x="40" y="74" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#111">{html.escape(bank_name)}</text>
          <text x="40" y="116" font-family="Arial, sans-serif" font-size="20" fill="#111">STK: {html.escape(account_number)}</text>
          <text x="40" y="154" font-family="Arial, sans-serif" font-size="20" fill="#111">Tên: {html.escape(account_name)}</text>
          <text x="40" y="202" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111">Số tiền: {html.escape(f"{amount:,.0f}")}</text>
          <text x="40" y="244" font-family="Arial, sans-serif" font-size="18" fill="#111">Nội dung: {html.escape(content)}</text>
          <rect x="40" y="280" width="340" height="96" rx="12" fill="#111"/>
          <text x="210" y="335" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#fff">TRANSFER QR</text>
        </svg>
        """
        return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")

    def _swift_receipt_html(self, order):
        rows = []
        for line in order.lines:
            if self._swift_is_adjustment_line(line):
                rows.append(f"<tr><td colspan='3'>{html.escape(line.product_id.display_name or line.product_id.name or '')}</td><td style='text-align:right'>{line.price_subtotal_incl:,.0f}</td></tr>")
                continue
            rows.append(
                "<tr>"
                f"<td>{html.escape(line.product_id.display_name or line.product_id.name or '')}</td>"
                f"<td style='text-align:right'>{line.qty:,.0f}</td>"
                f"<td style='text-align:right'>{line.price_unit:,.0f}</td>"
                f"<td style='text-align:right'>{line.price_subtotal_incl:,.0f}</td>"
                "</tr>"
            )
        branch = order.session_id.config_id if order.session_id else False
        customer = order.partner_id.name if order.partner_id else _("Khách lẻ")
        return f"""
        <html>
          <head><meta charset="utf-8"><title>{html.escape(order.name or order.pos_reference or 'Receipt')}</title></head>
          <body style="font-family: Arial, sans-serif; padding: 16px;">
            <h2>{html.escape(request.env.company.name or '')}</h2>
            <p>Chi nhánh: {html.escape(branch.name if branch else '')}<br/>
               Khách hàng: {html.escape(customer)}<br/>
               Mã đơn: {html.escape(order.name or order.pos_reference or '')}</p>
            <table width="100%" border="1" cellspacing="0" cellpadding="6" style="border-collapse: collapse;">
              <thead>
                <tr><th align="left">Sản phẩm</th><th>Số lượng</th><th>Đơn giá</th><th>Thành tiền</th></tr>
              </thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
            <p>Tạm tính: {order.amount_total:,.0f}<br/>
               Đã trả: {order.amount_paid:,.0f}<br/>
               Trả lại: {order.amount_return:,.0f}</p>
          </body>
        </html>
        """

    # ---------------------------------------------------------------------
    # Sales context / catalog
    # ---------------------------------------------------------------------

    @http.route("/api/swift/v1/sales/context", type="http", auth="user", methods=["GET"], csrf=False)
    def sales_context(self, **kwargs):
        session, branch_config = self._swift_open_session(request.httprequest.args.get("branchId"))
        shift = request.env["swift.staff.shift"].sudo().search([
            ("employee_id", "=", request.env.uid),
            ("state", "=", "active"),
        ], limit=1)
        partner = request.env.user.partner_id
        pricelist = self._swift_default_pricelist(branch_config)
        bank_account = request.env.company.partner_id.bank_ids[:1]
        payment_methods = branch_config.payment_method_ids if branch_config else request.env["pos.payment.method"].sudo().browse()
        cash_enabled = any(getattr(pm, "is_cash_count", False) for pm in payment_methods)
        bank_enabled = any(not getattr(pm, "is_cash_count", False) for pm in payment_methods)
        data = {
            "branch": {
                "id": branch_config.id if branch_config else "",
                "name": branch_config.name if branch_config else "",
            },
            "cashier": {
                "id": str(request.env.uid),
                "name": request.env.user.name,
                "code": request.env["swift.employee.profile"].sudo().search([("user_id", "=", request.env.uid)], limit=1).employee_code if "swift.employee.profile" in request.env.registry else f"NV{request.env.uid}",
            },
            "shift": {
                "id": shift.id if shift else "",
                "name": shift.note or _("Ca làm việc") if shift else "",
                "openedAt": int(shift.check_in.timestamp() * 1000) if shift and shift.check_in else 0,
            },
            "defaultCustomer": self._swift_get_default_partner(),
            "defaultPriceList": {
                "id": pricelist.id if pricelist else "",
                "name": pricelist.name if pricelist else "",
            },
            "paymentConfig": {
                "cashEnabled": cash_enabled,
                "transferEnabled": bank_enabled,
                "cardEnabled": bank_enabled,
                "walletEnabled": False,
                "bankAccount": {
                    "bankName": bank_account.bank_id.name if bank_account and bank_account.bank_id else "",
                    "accountNumber": bank_account.acc_number if bank_account else "",
                    "accountName": bank_account.acc_holder_name if bank_account else "",
                },
            },
        }
        return self._ok(data)

    @http.route("/api/swift/v1/sales/products", type="http", auth="user", methods=["GET"], csrf=False)
    def sales_products(self, **kwargs):
        return self.get_products(**kwargs)

    @http.route("/api/swift/v1/sales/products/by-barcode/<string:barcode>", type="http", auth="user", methods=["GET"], csrf=False)
    def sales_product_by_barcode(self, barcode, **kwargs):
        return self.get_product_by_barcode(barcode, **kwargs)

    @http.route("/api/swift/v1/sales/product-filters", type="http", auth="user", methods=["GET"], csrf=False)
    def sales_product_filters(self, **kwargs):
        categories = [{"id": "all", "name": _("Tất cả")}] + [
            {"id": c.id, "name": c.name}
            for c in request.env["pos.category"].sudo().search([], order="name asc")
        ]
        stock_statuses = [
            {"id": "all", "name": _("Tất cả tồn")},
            {"id": "in_stock", "name": _("Còn hàng")},
            {"id": "out_of_stock", "name": _("Hết hàng")},
            {"id": "negative", "name": _("Âm kho")},
        ]
        return self._ok({
            "categories": categories,
            "stockStatuses": stock_statuses,
        })

    # ---------------------------------------------------------------------
    # Customers / price lists / payment methods
    # ---------------------------------------------------------------------

    @http.route("/api/swift/v1/customers", type="http", auth="user", methods=["GET"], csrf=False)
    def get_customers(self, **kwargs):
        args = request.httprequest.args
        search = (args.get("search") or args.get("keyword") or "").strip()
        page = max(self._swift_to_int(args.get("page"), 1), 1)
        page_size = max(self._swift_to_int(args.get("pageSize"), 20), 1)

        domain = [("customer_rank", ">", 0)]
        if search:
            domain += ["|", "|", "|",
                ("name", "ilike", search),
                ("phone", "ilike", search),
                ("mobile", "ilike", search),
                ("ref", "ilike", search),
            ]
        partners = request.env["res.partner"].sudo().search(domain, order="name asc, id desc")
        total = len(partners)
        start = (page - 1) * page_size
        end = start + page_size
        items = [self._swift_default_customer_payload(False)] if not search else []
        for partner in partners[start:end]:
            items.append(self._swift_default_customer_payload(partner))
        return self._ok({
            "items": items,
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": total,
            },
        })

    @http.route("/api/swift/v1/customers", type="http", auth="user", methods=["POST"], csrf=False)
    def create_customer(self, **kwargs):
        payload = self._json_body()
        name = (payload.get("name") or "").strip()
        phone = (payload.get("phone") or "").strip()
        if not name:
            return self._error(_("Name is required"))
        partner = request.env["res.partner"].sudo().create({
            "name": name,
            "phone": phone,
            "mobile": phone,
            "customer_rank": 1,
        })
        return self._ok(self._swift_default_customer_payload(partner))

    @http.route("/api/swift/v1/price-lists", type="http", auth="user", methods=["GET"], csrf=False)
    def price_lists(self, **kwargs):
        price_lists = request.env["product.pricelist"].sudo().search([], order="name asc")
        return self._ok({
            "items": [{"id": p.id, "name": p.name} for p in price_lists],
        })

    @http.route("/api/swift/v1/sales/payment-methods", type="http", auth="user", methods=["GET"], csrf=False)
    def sales_payment_methods(self, **kwargs):
        session, branch_config = self._swift_open_session(request.httprequest.args.get("branchId"))
        methods = session.config_id.payment_method_ids if session and session.config_id else request.env["pos.payment.method"].sudo().search([("company_id", "=", request.env.company.id)], order="id asc")
        return self._ok({
            "items": [self._swift_payment_method_payload(method) for method in methods],
        })

    @http.route("/api/swift/v1/sales/payments/transfer-qr", type="http", auth="user", methods=["POST"], csrf=False)
    def sales_transfer_qr(self, **kwargs):
        payload = self._json_body()
        amount = self._swift_to_float(payload.get("amount"), 0.0)
        session, branch_config = self._swift_open_session(payload.get("branchId"))
        bank_accounts = request.env.company.partner_id.bank_ids
        bank = bank_accounts[:1]
        if not bank:
            return self._error(_("No bank account configured"))

        content = f"DH-{payload.get('cartId') or payload.get('orderId') or request.env.uid}"
        qr_svg = self._swift_prepare_qr_svg(
            bank.bank_id.name or "",
            bank.acc_number or "",
            bank.acc_holder_name or request.env.company.name or "",
            amount,
            content,
        )
        return self._ok({
            "bankName": bank.bank_id.name or "",
            "accountNumber": bank.acc_number or "",
            "accountName": bank.acc_holder_name or request.env.company.name or "",
            "qrImageUrl": qr_svg,
            "transferContent": content,
        })

    # ---------------------------------------------------------------------
    # Cart / draft order
    # ---------------------------------------------------------------------

    def _swift_prepare_cart_values(self, payload):
        branch_id = payload.get("branchId") or payload.get("config_id")
        session, branch_config = self._swift_open_session(branch_id)
        if not session:
            raise UserError(_("No open POS session found"))

        customer_id = payload.get("customerId")
        partner = request.env["res.partner"].sudo().browse(self._swift_parse_order_id(customer_id)).exists() if customer_id and str(customer_id).isdigit() else False
        pricelist = request.env["product.pricelist"].sudo().browse(self._swift_parse_order_id(payload.get("priceListId"))).exists() if payload.get("priceListId") else False
        if not pricelist:
            pricelist = self._swift_default_pricelist(branch_config)
        if not pricelist:
            raise UserError(_("No pricelist found"))

        mode = (payload.get("mode") or "sell").strip().lower()
        mode = "order" if mode == "order" else "sell"
        note = (payload.get("note") or "").strip()

        return session, branch_config, partner, pricelist, mode, note

    def _swift_create_cart(self, payload):
        session, branch_config, partner, pricelist, mode, note = self._swift_prepare_cart_values(payload)
        order_vals = {
            "session_id": session.id,
            "user_id": request.env.uid,
            "partner_id": partner.id if partner else False,
            "pricelist_id": pricelist.id,
            "state": "draft",
            "swift_mode": mode,
            "swift_note": note,
            "general_customer_note": note,
            "amount_tax": 0.0,
            "amount_total": 0.0,
            "amount_paid": 0.0,
            "amount_return": 0.0,
        }
        if "swift_discount_percent" in request.env["pos.order"]._fields:
            order_vals["swift_discount_percent"] = self._swift_to_float(payload.get("discountPercent"), 0.0)
        if "swift_extra_charge" in request.env["pos.order"]._fields:
            order_vals["swift_extra_charge"] = self._swift_to_float(payload.get("extraCharge"), 0.0)
        order = request.env["pos.order"].sudo().create(order_vals)
        return order, branch_config

    def _swift_add_lines_to_order(self, order, items):
        if not items:
            return order

        for item in items:
            product = request.env["product.product"].sudo().browse(self._swift_parse_order_id(item.get("productId"))).exists()
            if not product:
                continue
            qty = self._swift_to_float(item.get("quantity"), 1.0) or 1.0
            pricelist = order.pricelist_id or self._swift_default_pricelist(order.session_id.config_id if order.session_id else False)
            price = pricelist._get_product_price(product, qty, currency=order.currency_id) if pricelist else (product.lst_price or 0.0)
            taxes = product.taxes_id.filtered_domain(request.env["account.tax"]._check_company_domain(order.company_id))
            if order.fiscal_position_id:
                taxes = order.fiscal_position_id.map_tax(taxes)
            line_vals = {
                "order_id": order.id,
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
                "discount": 0.0,
                "tax_ids": [(6, 0, taxes.ids)],
                "name": product.display_name or product.name,
                "full_product_name": product.display_name or product.name,
                "note": (item.get("note") or "").strip(),
            }
            request.env["pos.order.line"].sudo().create(line_vals)

        order._compute_prices()
        return order

    @http.route("/api/swift/v1/sales/carts", type="http", auth="user", methods=["POST"], csrf=False)
    def create_cart(self, **kwargs):
        payload = self._json_body()
        items = payload.get("items") or []
        order, branch_config = self._swift_create_cart(payload)
        self._swift_add_lines_to_order(order, items)
        self._swift_sync_adjustment_lines(
            order,
            discount_percent=payload.get("discountPercent"),
            extra_charge=payload.get("extraCharge"),
        )
        return self._ok(self._swift_order_payload(order))

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def get_cart(self, cart_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        return self._ok(self._swift_order_payload(order))

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>", type="http", auth="user", methods=["PATCH"], csrf=False)
    def update_cart(self, cart_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        payload = self._json_body()
        self._swift_set_order_context(order, payload)
        self._swift_sync_adjustment_lines(
            order,
            discount_percent=payload.get("discountPercent"),
            extra_charge=payload.get("extraCharge"),
        )
        return self._ok(self._swift_order_payload(order))

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>/lines", type="http", auth="user", methods=["POST"], csrf=False)
    def add_cart_line(self, cart_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        payload = self._json_body()
        product = request.env["product.product"].sudo().browse(self._swift_parse_order_id(payload.get("productId"))).exists()
        if not product:
            return self._error(_("Product not found"), status=404)
        qty = self._swift_to_float(payload.get("quantity"), 1.0) or 1.0
        existing = order.lines.filtered(lambda line: line.product_id.id == product.id and not self._swift_is_adjustment_line(line))[:1]
        if existing:
            existing.write({"qty": existing.qty + qty})
            line = existing
        else:
            pricelist = order.pricelist_id or self._swift_default_pricelist(order.session_id.config_id if order.session_id else False)
            price = pricelist._get_product_price(product, qty, currency=order.currency_id) if pricelist else (product.lst_price or 0.0)
            taxes = product.taxes_id.filtered_domain(request.env["account.tax"]._check_company_domain(order.company_id))
            if order.fiscal_position_id:
                taxes = order.fiscal_position_id.map_tax(taxes)
            line = request.env["pos.order.line"].sudo().create({
                "order_id": order.id,
                "product_id": product.id,
                "qty": qty,
                "price_unit": price,
                "discount": 0.0,
                "tax_ids": [(6, 0, taxes.ids)],
                "name": product.display_name or product.name,
                "full_product_name": product.display_name or product.name,
                "note": (payload.get("note") or "").strip(),
            })
        order._compute_prices()
        return self._ok(self._swift_line_payload(line))

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>/lines/<string:line_id>", type="http", auth="user", methods=["PATCH"], csrf=False)
    def update_cart_line(self, cart_id, line_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        payload = self._json_body()
        line = order.lines.filtered(lambda l: f"line_{l.id}" == line_id or str(l.id) == line_id)[:1]
        if not line:
            return self._error(_("Line not found"), status=404)
        qty = self._swift_to_float(payload.get("quantity"), line.qty)
        if qty <= 0:
            line.unlink()
            order._compute_prices()
            return self._ok({"lineId": line_id, "deleted": True})
        line.write({"qty": qty})
        if payload.get("note") is not None:
            line.write({"note": (payload.get("note") or "").strip()})
        order._compute_prices()
        return self._ok(self._swift_line_payload(line))

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>/lines/<string:line_id>", type="http", auth="user", methods=["DELETE"], csrf=False)
    def delete_cart_line(self, cart_id, line_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        line = order.lines.filtered(lambda l: f"line_{l.id}" == line_id or str(l.id) == line_id)[:1]
        if not line:
            return self._error(_("Line not found"), status=404)
        line.unlink()
        order._compute_prices()
        return self._ok({"lineId": line_id, "deleted": True})

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>/quote", type="http", auth="user", methods=["POST"], csrf=False)
    def quote_cart(self, cart_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        payload = self._json_body()
        self._swift_set_order_context(order, payload)
        self._swift_sync_adjustment_lines(
            order,
            discount_percent=payload.get("discountPercent"),
            extra_charge=payload.get("extraCharge"),
        )
        return self._ok({
            "subtotal": round(sum(line.price_subtotal_incl for line in order.lines.filtered(lambda l: not self._swift_is_adjustment_line(l))), 2),
            "discountAmount": round(sum(-line.price_subtotal_incl for line in order.lines.filtered(lambda l: self._swift_is_adjustment_line(l) and line.price_unit < 0)), 2),
            "extraCharge": round(sum(line.price_subtotal_incl for line in order.lines.filtered(lambda l: self._swift_is_adjustment_line(l) and line.price_unit > 0)), 2),
            "amountDue": round(order.amount_total, 2),
            "itemCount": len(order.lines.filtered(lambda l: not self._swift_is_adjustment_line(l))),
            "lines": [self._swift_line_payload(line) for line in order.lines.sorted("id")],
        })

    @http.route("/api/swift/v1/sales/carts/<string:cart_id>/save-draft", type="http", auth="user", methods=["POST"], csrf=False)
    def save_cart_draft(self, cart_id, **kwargs):
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)
        order.write({"state": "draft"})
        return self._ok({
            "draftId": f"draft_{order.id}",
            "status": "draft",
        })

    @http.route("/api/swift/v1/sales/drafts", type="http", auth="user", methods=["GET"], csrf=False)
    def list_drafts(self, **kwargs):
        orders = request.env["pos.order"].sudo().search([
            ("state", "=", "draft"),
            ("user_id", "=", request.env.uid),
        ], order="write_date desc, id desc", limit=50)
        return self._ok({
            "items": [self._swift_order_payload(order) for order in orders],
        })

    @http.route("/api/swift/v1/sales/drafts/<string:draft_id>/restore", type="http", auth="user", methods=["POST"], csrf=False)
    def restore_draft(self, draft_id, **kwargs):
        order = self._swift_find_order(draft_id)
        if not order:
            return self._error(_("Draft not found"), status=404)
        order.write({"state": "draft"})
        return self._ok(self._swift_order_payload(order))

    # ---------------------------------------------------------------------
    # Checkout / orders
    # ---------------------------------------------------------------------

    def _swift_finalize_checkout(self, order, payload):
        payment_info = payload.get("payment") or {}
        method = self._swift_find_payment_method(order, payment_info.get("method") or payment_info.get("paymentMethod") or "cash")
        amount_received = self._swift_to_float(payment_info.get("amountReceived") or payment_info.get("amount") or order.amount_total, order.amount_total)
        amount_due = round(order.amount_total, 2)

        if amount_received < amount_due and (payload.get("mode") or order.swift_mode or "sell") == "sell":
            raise UserError(_("Amount received is lower than amount due"))

        order.payment_ids.unlink()
        self._swift_add_payment(order, method, amount_received, is_change=False)
        change_amount = 0.0
        if getattr(method, "is_cash_count", False) and amount_received > amount_due:
            change_amount = round(amount_received - amount_due, 2)
            if change_amount:
                self._swift_add_payment(order, method, -change_amount, is_change=True)

        order._compute_prices()
        order.action_pos_order_paid()
        invoice = False
        try:
            invoice_action = order.action_pos_order_invoice()
            invoice = order.account_move if order.account_move else False
        except Exception:
            invoice_action = False
            invoice = order.account_move if order.account_move else False

        order._ensure_access_token()
        return {
            "orderId": f"order_{order.id}",
            "invoiceId": invoice.id if invoice else "",
            "receiptId": order.pos_reference or order.name or f"RCPT-{order.id}",
            "status": "paid",
            "paidAmount": round(order.amount_paid, 2),
            "changeAmount": change_amount,
            "shareToken": order.access_token,
        }

    @http.route("/api/swift/v1/sales/checkout", type="http", auth="user", methods=["POST"], csrf=False)
    def sales_checkout(self, **kwargs):
        payload = self._json_body()
        cart_id = payload.get("cartId")
        order = self._swift_find_order(cart_id)
        if not order:
            return self._error(_("Cart not found"), status=404)

        mode = (payload.get("mode") or order.swift_mode or "sell").strip().lower()
        self._swift_set_order_context(order, payload)
        self._swift_sync_adjustment_lines(
            order,
            discount_percent=payload.get("discountPercent"),
            extra_charge=payload.get("extraCharge"),
        )

        if mode == "order":
            order.write({"state": "draft", "swift_mode": "order"})
            order._ensure_access_token()
            return self._ok({
                "orderId": f"order_{order.id}",
                "status": "draft_order",
            })

        order.write({"swift_mode": "sell"})
        result = self._swift_finalize_checkout(order, payload)
        return self._ok(result)

    @http.route("/api/swift/v1/sales/orders", type="http", auth="user", methods=["POST"], csrf=False)
    def sales_orders(self, **kwargs):
        payload = self._json_body()
        payload.setdefault("mode", "order")
        order, _branch_config = self._swift_create_cart(payload)
        items = payload.get("items") or []
        self._swift_add_lines_to_order(order, items)
        self._swift_sync_adjustment_lines(
            order,
            discount_percent=payload.get("discountPercent"),
            extra_charge=payload.get("extraCharge"),
        )
        order.write({"swift_mode": "order", "state": "draft"})
        order._ensure_access_token()
        return self._ok({
            "orderId": f"order_{order.id}",
            "status": "draft_order",
        })

    @http.route("/api/swift/v1/sales/orders/<string:order_ref>/receipt", type="http", auth="user", methods=["GET"], csrf=False)
    def sales_order_receipt(self, order_ref, **kwargs):
        order = self._swift_find_order(order_ref)
        if not order:
            return self._error(_("Order not found"), status=404)
        order._ensure_access_token()
        return self._ok({
            "receiptHtml": self._swift_receipt_html(order),
            "receiptPdfUrl": f"/api/swift/v1/sales/orders/{order.id}/receipt?access_token={order.access_token}",
        })

    @http.route("/api/swift/v1/sales/orders/<string:order_ref>/share", type="http", auth="user", methods=["POST"], csrf=False)
    def sales_order_share(self, order_ref, **kwargs):
        order = self._swift_find_order(order_ref)
        if not order:
            return self._error(_("Order not found"), status=404)
        order._ensure_access_token()
        return self._ok({
            "shareUrl": f"/api/swift/v1/sales/orders/{order.id}/receipt?access_token={order.access_token}",
        })
