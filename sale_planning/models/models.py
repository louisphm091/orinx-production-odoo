# from odoo import models, fields, api


# class /volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning(models.Model):
#     _name = '/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning./volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning'
#     _description = '/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning./volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100

