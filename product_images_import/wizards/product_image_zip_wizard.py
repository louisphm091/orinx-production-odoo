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

        ProductT = self.env["product.template"]
        ProductV = self.env["product.product"]

        updated = 0
        skipped = 0
        not_found = 0

        import logging
        _logger = logging.getLogger(__name__)

        for member in members:
            filename = os.path.basename(member)
            if filename.startswith("._") or "__MACOSX" in member:
                skipped += 1
                continue

            key = self._normalize_key(member)
            if not key:
                skipped += 1
                continue

            v = False
            if self.match_by == "id":
                try:
                    product_id = int(key)
                    v = ProductV.browse(product_id).exists()
                except (ValueError, TypeError):
                    v = False
            else:
                domain = []
                if self.match_by == "barcode":
                    domain = [("barcode", "=ilike", key)]
                else:
                    domain = [("default_code", "=ilike", key)]
                v = ProductV.search(domain, limit=1)

            if not v:
                _logger.warning("Product not found for key: %s (from %s)", key, member)
                not_found += 1
                continue

            _logger.info("Found product %s for key: %s", v.display_name, key)
            record = v if self.target == "variant" else v.product_tmpl_id

            try:
                img_bytes = zf.read(member)
                record.image_1920 = base64.b64encode(img_bytes)
                updated += 1
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
