# from odoo import http


# class /volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/salePlanning(http.Controller):
#     @http.route('//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning.listing', {
#             'root': '//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning',
#             'objects': http.request.env['/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning./volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning'].search([]),
#         })

#     @http.route('//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning/objects/<model("/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning./volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/sale_planning.object', {
#             'object': obj
#         })

