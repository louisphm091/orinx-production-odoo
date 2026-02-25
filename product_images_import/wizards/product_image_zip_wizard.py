from odoo import models, fields, _
from odoo.exceptions import UserError
import base64
import zipfile
import io
import os

class ProductImageZipWizard(models.TransientModel):
    _name = "product.image.zip.wizard"
    _description = "Import Product Images from ZIP"

    zip_file = fields.Binary(string="ZIP File", required=True)
    zip_filename = fields.Char(string="Filename")

    match_by = fields.Selection(
        [
            ("barcode", "Barcode (product.variant.barcode)"),
            ("default_code", "Internal Reference (product.variant.default_code)"),
            ("id", "Database ID (product.product.id)"),
        ],
        string="Match By",
        required=True,
        default="barcode",
    )

    target = fields.Selection(
        [
            ("template", "Product Template"),
            ("variant", "Product Variant"),
        ],
        string="Target",
        required=True,
        default="template",
    )

    overwrite = fields.Boolean(string="Overwrite existing image", default=True)

    def _normalize_key(self, filename: str) -> str:
        # Lấy basename + bỏ extension: "8938.jpg" -> "8938"
        base = os.path.basename(filename)
        key, _ext = os.path.splitext(base)
        return (key or "").strip()

    def action_import(self):
        self.ensure_one()
        if not self.zip_file:
            raise UserError(_("Please upload a ZIP file."))

        try:
            zip_bytes = base64.b64decode(self.zip_file)
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except Exception as e:
            raise UserError(_("Invalid ZIP file: %s") % str(e))

        allowed_ext = (".png", ".jpg", ".jpeg", ".webp")
        members = [m for m in zf.namelist() if m.lower().endswith(allowed_ext)]

        if not members:
            raise UserError(_("No image files found in ZIP. Allowed: %s") % ", ".join(allowed_ext))

        import logging
        _logger = logging.getLogger(__name__)

        # 1. Collect keys and filter members
        valid_members = []
        keys = []
        for member in members:
            filename = os.path.basename(member)
            if filename.startswith("._") or "__MACOSX" in member:
                continue

            key = self._normalize_key(member)
            if key:
                valid_members.append((member, key))
                keys.append(key)

        if not keys:
            raise UserError(_("No valid image files found in ZIP."))

        # 2. Bulk Search Products
        ProductV = self.env["product.product"]
        product_map = {}

        if self.match_by == "id":
            valid_ids = []
            for k in keys:
                try:
                    valid_ids.append(int(k))
                except (ValueError, TypeError):
                    continue
            products = ProductV.browse(valid_ids).exists()
            for p in products:
                product_map[str(p.id)] = p
        elif self.match_by == "barcode":
            products = ProductV.search([("barcode", "in", keys)])
            for p in products:
                # Use barcode as key (case-insensitive if needed, but 'in' is case-sensitive in PostgreSQL usually)
                # Odoo barcode is usually unique-ish, but let's handle multiples if it ever happens (limit 1 logic)
                product_map[p.barcode] = p
        else: # default_code
            products = ProductV.search([("default_code", "in", keys)])
            for p in products:
                product_map[p.default_code] = p

        # 3. Process Images
        updated = 0
        skipped = 0
        not_found = 0

        for member, key in valid_members:
            v = product_map.get(key)

            # If search didn't find it (maybe case sensitivity or ilike vs in)
            if not v and self.match_by != "id":
                # Fallback to ilike if direct match fails?
                # Actually 'in' is faster and usually 1:1.
                # If they used ilike before, it was to match "barcode" = "BARCODE"
                # Let's try to be a bit more flexible if product_map doesn't have it
                # but for bulk, 'in' is the way.
                pass

            if not v:
                _logger.warning("Product not found for key: %s (from %s)", key, member)
                not_found += 1
                continue

            record = v if self.target == "variant" else v.product_tmpl_id

            if not self.overwrite and record.image_1920:
                skipped += 1
                continue

            try:
                img_bytes = zf.read(member)
                record.image_1920 = base64.b64encode(img_bytes)
                updated += 1
                # Trigger a commit or flush periodically?
                # Odoo handles this at end of transaction,
                # but for 50 images, memory might be an issue if images are large.
                # However, 50 images is usually fine.
            except Exception as e:
                _logger.error("Error reading/saving image for %s: %s", key, str(e))
                skipped += 1

        msg = _("Import finished.\nUpdated: %s\nNot found: %s\nSkipped: %s") % (updated, not_found, skipped)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("ZIP Image Import"),
                "message": msg,
                "type": "success" if updated else "warning",
                "sticky": False,
            },
        }
