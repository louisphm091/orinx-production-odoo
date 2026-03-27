from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = "product.template"

    minimum_inventory = fields.Float(string="Tồn kho tối thiểu", default=0.0)

class ProductProduct(models.Model):
    _inherit = "product.product"

    minimum_inventory = fields.Float(
        related="product_tmpl_id.minimum_inventory",
        readonly=False,
        store=True,
    )
