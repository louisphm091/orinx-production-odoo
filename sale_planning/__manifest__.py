{
    'name': "Sale Planning",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "Orinx",
    'website': "https://erp.orinx.com.vn",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Planning',
    'version': '0.1',

    # any module necessary for this one to work correctly
    "depends": ["base", "web", "product", "stock", "mrp"],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            # Chart.js UMD (bạn đặt file ở path này)
            "sale_planning/static/src/sale_planning_dashboard/chart.umd.min.js",
            # OWL dashboard
            "sale_planning/static/src/sale_planning_dashboard/sale_planning_dashboard.xml",
            "sale_planning/static/src/sale_planning_dashboard/sale_planning_dashboard.js",
            "sale_planning/static/src/sale_planning_dashboard/sale_planning_dashboard.scss",
        ],
    },
    "application": True,
    "installable": True,
    "license": "LGPL-3",
}

