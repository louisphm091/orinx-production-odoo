# from odoo import http


# class /volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashionDemandForecast(http.Controller):
#     @http.route('//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast.listing', {
#             'root': '//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast',
#             'objects': http.request.env['/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast./volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast'].search([]),
#         })

#     @http.route('//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast//volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast/objects/<model("/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast./volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('/volumes/dev/workspace/orinx-odoo/fashion-orinx-odoo/fashion_forecast.object', {
#             'object': obj
#         })

