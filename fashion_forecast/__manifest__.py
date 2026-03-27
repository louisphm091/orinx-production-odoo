{
    'name': "Fashion Forecast",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "Orinx",
    'website': "https://www.erp.orinx.com.vn",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Planning',
    'version': '0.1',

    # any module necessary for this one to work correctly
    "depends": ["base", "web", "product", "stock", "mrp", "sale_planning"],

    "assets": {
        "web.assets_backend": [
            "fashion_forecast/static/src/fashion_forecast/fashion_forecast.xml",
            "fashion_forecast/static/src/fashion_forecast/fashion_forecast.js",
            "fashion_forecast/static/src/fashion_forecast/fashion_forecast.scss",
            "fashion_forecast/static/src/fashion_forecast/chart.umd.min.js",
            "fashion_forecast/static/src/demand_forecast/demand_forecast.xml",
            "fashion_forecast/static/src/demand_forecast/demand_forecast.js",
            "fashion_forecast/static/src/demand_forecast/demand_forecast.scss",
            "fashion_forecast/static/src/demand_forecast/chart.umd.min.js",
        ]
    },
    'data': [
        "security/security.xml",
        "security/ir.model.access.csv",
        'views/menu.xml',
        'views/product_views.xml',
    ],

    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
