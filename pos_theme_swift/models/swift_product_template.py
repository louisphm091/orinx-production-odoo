from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class ProductTemplate(models.Model):
    _inherit = "product.template"

    swift_is_low_stock = fields.Boolean(
        string="Low Stock (Swift)",
        search="_search_swift_is_low_stock",
    )

    swift_is_high_stock = fields.Boolean(
        string="High Stock (Swift)",
        search="_search_swift_is_high_stock",
    )

    swift_branch_config_ids = fields.Many2many(
        "pos.config",
        "swift_product_template_pos_config_rel",
        "product_tmpl_id",
        "config_id",
        string="POS Branches",
        help="Only products assigned to selected POS branches are available in those branches. Leave empty to keep the product hidden from branch-specific POS flows.",
    )

    swift_branch_qty_html = fields.Html(
        string="Số lượng theo chi nhánh",
        compute="_compute_swift_branch_qty_html",
    )

    def _swift_get_branch_configs(self):
        """Return POS configs to use for branch stock breakdown."""
        if self.swift_branch_config_ids:
            return self.swift_branch_config_ids.filtered(lambda c: c.active)
        return self.env["pos.config"].sudo().search(
            [("active", "=", True), ("company_id", "=", self.env.company.id)],
            order="name asc",
        )

    def _swift_get_branch_location(self, config):
        if not config:
            return False
        if config.swift_warehouse_id and config.swift_warehouse_id.lot_stock_id:
            return config.swift_warehouse_id.lot_stock_id
        if config.picking_type_id and config.picking_type_id.default_location_src_id:
            return config.picking_type_id.default_location_src_id
        return False

    @api.depends(
        "product_variant_ids",
        "product_variant_ids.qty_available",
        "swift_branch_config_ids",
    )
    def _compute_swift_branch_qty_html(self):
        for template in self:
            if not template.is_storable:
                template.swift_branch_qty_html = ""
                continue
            branches = template._swift_get_branch_configs()
            if not branches:
                template.swift_branch_qty_html = ""
                continue

            rows = []
            for config in branches:
                location = template._swift_get_branch_location(config)
                if not location:
                    continue
                qty = template.with_context(location=location.id).qty_available
                rows.append((config.name or location.display_name, qty))

            if not rows:
                template.swift_branch_qty_html = ""
                continue

            rows.sort(key=lambda r: (r[0] or "").lower())
            items = "".join(
                "<li>%s: <strong>%s</strong></li>"
                % (name, ("%0.2f" % qty).rstrip("0").rstrip("."))
                for name, qty in rows
            )
            template.swift_branch_qty_html = "<ul class='o_swift_branch_qty'>%s</ul>" % items

    def _swift_get_threshold_config(self):
        """Pick a POS config for threshold/location context.

        Priority:
        1) explicit `pos_config_id` in context
        2) user's latest opened POS session
        3) if only 1 active config exists, use it
        """
        PosConfig = self.env["pos.config"].sudo()
        ctx = self.env.context
        if ctx.get("pos_config_id"):
            return PosConfig.browse(int(ctx["pos_config_id"])).exists()

        session = self.env["pos.session"].sudo().search(
            [
                ("user_id", "=", self.env.user.id),
                ("state", "=", "opened"),
                ("company_id", "=", self.env.company.id),
            ],
            order="id desc",
            limit=1,
        )
        if session and session.config_id:
            return session.config_id

        configs = PosConfig.search(
            [("active", "=", True), ("company_id", "=", self.env.company.id)],
            limit=2,
        )
        return configs if len(configs) == 1 else PosConfig.browse()

    def _swift_get_low_stock_threshold(self, config=False):
        config = config or self._swift_get_threshold_config()
        if config:
            return float(getattr(config, "swift_low_stock_threshold", 10.0) or 10.0)

        # Fallback: use the minimum threshold among active POS configs.
        thresholds = (
            self.env["pos.config"]
            .sudo()
            .search([("active", "=", True), ("company_id", "=", self.env.company.id)])
            .mapped("swift_low_stock_threshold")
        )
        thresholds = [t for t in thresholds if t is not None]
        return float(min(thresholds)) if thresholds else 10.0
    def _swift_get_high_stock_threshold(self, config=False):
        config = config or self._swift_get_threshold_config()
        if config:
            return float(getattr(config, "swift_high_stock_threshold", 100.0) or 100.0)

        # Fallback: use the maximum threshold among active POS configs.
        thresholds = (
            self.env["pos.config"]
            .sudo()
            .search([("active", "=", True), ("company_id", "=", self.env.company.id)])
            .mapped("swift_high_stock_threshold")
        )
        thresholds = [t for t in thresholds if t is not None]
        return float(max(thresholds)) if thresholds else 100.0

    def _swift_get_inventory_location(self, config=False):
        config = config or self._swift_get_threshold_config()
        if config:
            if getattr(config, "swift_warehouse_id", False) and config.swift_warehouse_id.lot_stock_id:
                return config.swift_warehouse_id.lot_stock_id
            if config.picking_type_id and config.picking_type_id.default_location_src_id:
                return config.picking_type_id.default_location_src_id
        return self.env["stock.location"].sudo().search([("usage", "=", "internal")], limit=1)

    @api.model
    def _search_swift_is_low_stock(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("Unsupported operator for low stock filter."))
        want_low = bool(value)
        if operator == "!=":
            want_low = not want_low

        config = self._swift_get_threshold_config()
        threshold = self._swift_get_low_stock_threshold(config=config)
        location = self._swift_get_inventory_location(config=config)

        Product = self.env["product.product"].sudo()
        product_domain = [
            ("available_in_pos", "=", True),
            ("active", "=", True),
            ("is_storable", "=", True),
        ]
        if config:
            product_domain.append(("product_tmpl_id.swift_branch_config_ids", "in", config.ids))
            if getattr(config, "limit_categories", False) and config.iface_available_categ_ids:
                product_domain.append(("pos_categ_ids", "in", config.iface_available_categ_ids.ids))

        products = Product.search(product_domain)
        if not products:
            return [("id", "=", 0)] if want_low else []

        quant_domain = [
            ("product_id", "in", products.ids),
            ("location_id.usage", "=", "internal"),
        ]
        if location:
            quant_domain.append(("location_id", "child_of", location.id))

        quant_groups = self.env["stock.quant"].sudo().read_group(
            quant_domain,
            ["quantity:sum", "product_id"],
            ["product_id"],
        )
        qty_by_product = {g["product_id"][0]: g["quantity"] for g in quant_groups if g.get("product_id")}

        qty_by_template = {}
        for product in products:
            qty = qty_by_product.get(product.id, 0.0)
            qty_by_template[product.product_tmpl_id.id] = qty_by_template.get(product.product_tmpl_id.id, 0.0) + qty

        low_tmpl_ids = [tmpl_id for tmpl_id, qty in qty_by_template.items() if qty <= threshold]
        return [("id", "in", low_tmpl_ids)] if want_low else [("id", "not in", low_tmpl_ids)]

    @api.model
    def _search_swift_is_high_stock(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("Unsupported operator for high stock filter."))
        want_high = bool(value)
        if operator == "!=":
            want_high = not want_high

        config = self._swift_get_threshold_config()
        threshold = self._swift_get_high_stock_threshold(config=config)
        location = self._swift_get_inventory_location(config=config)

        Product = self.env["product.product"].sudo()
        product_domain = [
            ("available_in_pos", "=", True),
            ("active", "=", True),
            ("is_storable", "=", True),
        ]
        if config:
            product_domain.append(("product_tmpl_id.swift_branch_config_ids", "in", config.ids))

        products = Product.search(product_domain)
        if not products:
            return [("id", "=", 0)] if want_high else []

        quant_domain = [
            ("product_id", "in", products.ids),
            ("location_id.usage", "=", "internal"),
        ]
        if location:
            quant_domain.append(("location_id", "child_of", location.id))

        quant_groups = self.env["stock.quant"].sudo().read_group(
            quant_domain,
            ["quantity:sum", "product_id"],
            ["product_id"],
        )
        qty_by_product = {g["product_id"][0]: g["quantity"] for g in quant_groups if g.get("product_id")}

        qty_by_template = {}
        for product in products:
            qty = qty_by_product.get(product.id, 0.0)
            qty_by_template[product.product_tmpl_id.id] = qty_by_template.get(product.product_tmpl_id.id, 0.0) + qty

        high_tmpl_ids = [tmpl_id for tmpl_id, qty in qty_by_template.items() if qty > threshold]
        return [("id", "in", high_tmpl_ids)] if want_high else [("id", "not in", high_tmpl_ids)]

    def action_swift_import_goods_filtered(self):
        """Create purchase RFQs for low-stock products in current filter."""
        ctx = self.env.context
        active_ids = ctx.get("active_ids") or []
        domain = ctx.get("active_domain") or ctx.get("search_domain") or ctx.get("domain") or []
        if isinstance(domain, str):
            domain = safe_eval(domain)
        if not isinstance(domain, list):
            domain = []

        if active_ids:
            products = self.browse(active_ids)
        elif domain:
            products = self.search(domain)
        elif self:
            products = self
        else:
            products = self.search([("available_in_pos", "=", True)])

        threshold = self._swift_get_low_stock_threshold()

        # When the button is clicked from the low-stock screen, try to respect
        # the filter; but if the context/config cannot be inferred reliably,
        # fall back to the user's explicit selection.
        products = products.filtered(lambda p: p.is_storable)
        if ctx.get("swift_low_stock_mode"):
            low_stock_products = products.filtered_domain([("swift_is_low_stock", "=", True)])
            if low_stock_products:
                products = low_stock_products
            elif not active_ids:
                raise UserError(_("No low-stock products (<= %s) found in current filter.") % threshold)

        if not products:
            raise UserError(_("Please select at least one storable product."))

        target_qty = float(ctx.get("swift_target_qty") or 20.0)
        variants = products.mapped("product_variant_ids").filtered(lambda p: p.is_storable)
        if not variants:
            raise UserError(_("No inventory-managed product variants found."))

        PurchaseOrder = self.env["purchase.order"]
        PurchaseOrderLine = self.env["purchase.order.line"]

        today = fields.Date.context_today(self)
        now = fields.Datetime.now()

        missing_vendors = []
        lines_by_partner = {}

        for product in variants:
            current_qty = product.qty_available
            needed_qty = target_qty - current_qty
            if needed_qty <= 0:
                continue

            seller = product._select_seller(
                quantity=needed_qty,
                date=today,
                uom_id=product.uom_id,
            )
            if not seller or not seller.partner_id:
                missing_vendors.append(product.display_name)
                continue

            partner = seller.partner_id
            lines_by_partner.setdefault(partner, []).append((product, needed_qty, seller))

        if missing_vendors:
            sample = ", ".join(missing_vendors[:20])
            more = "" if len(missing_vendors) <= 20 else _(" (and %s more)") % (len(missing_vendors) - 20)
            raise UserError(_("Missing vendor on products: %s%s") % (sample, more))

        if not lines_by_partner:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Import Goods"),
                    "message": _("No products needed purchase (all already >= %s).") % target_qty,
                    "type": "warning",
                    "sticky": False,
                    "next": {"type": "ir.actions.client", "tag": "reload"},
                },
            }

        created_orders = PurchaseOrder.browse()

        for partner, items in lines_by_partner.items():
            order = PurchaseOrder.create({
                "partner_id": partner.id,
                "company_id": self.env.company.id,
            })

            for product, qty, seller in items:
                uom = getattr(seller, "product_uom_id", False) or product.uom_id
                PurchaseOrderLine.create({
                    "order_id": order.id,
                    "product_id": product.id,
                    "name": product.display_name,
                    "product_qty": qty,
                    "product_uom_id": uom.id,
                    "price_unit": seller.price if seller else product.standard_price,
                    "date_planned": now,
                })

            created_orders |= order

        if len(created_orders) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Request for Quotation"),
                "res_model": "purchase.order",
                "view_mode": "form",
                "res_id": created_orders.id,
                "target": "current",
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Requests for Quotation"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", created_orders.ids)],
            "target": "current",
            "context": {
                "search_default_draft": 1,
                "default_company_id": self.env.company.id,
            },
        }

    def action_open_swift_branch_assignment_wizard(self):
        products = self
        if not products:
            active_ids = self.env.context.get("active_ids", [])
            products = self.browse(active_ids)
        products = products.filtered(lambda product: product.available_in_pos)
        if not products:
            raise UserError(_("Please select at least one POS product."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Gán chi nhánh POS"),
            "res_model": "swift.branch.product.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_product_tmpl_ids": [(6, 0, products.ids)],
            },
        }

class ProductProduct(models.Model):
    _inherit = "product.product"

    def action_open_swift_branch_assignment_wizard(self):
        return self.product_tmpl_id.action_open_swift_branch_assignment_wizard()
