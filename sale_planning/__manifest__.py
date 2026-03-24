{
    'name': "Demand & Supply Planning",

    'summary': "Plan and balance demand with supply across sales, inventory, and purchasing",

    'description': """
Demand & Supply Planning provides dashboards and analytics to plan,
track, and balance demand against supply. Developed by https://group.orinx.com.vn.
    """,

    'author': "Orinx",
    'website': "https://group.orinx.com.vn",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Planning',
    'version': '0.1.5',

    # any module necessary for this one to work correctly
    "depends": ["base", "web", "product", "stock", "sale", "purchase", "mrp"],
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_planning/static/src/sale_planning_dashboard/chart.umd.min.js",
            "sale_planning/static/src/sale_planning_dashboard/sale_planning_dashboard.xml",
            "sale_planning/static/src/sale_planning_dashboard/sale_planning_dashboard.js",
            "sale_planning/static/src/sale_planning_dashboard/sale_planning_dashboard.scss",
            "sale_planning/static/src/sale_schedule_dashboard/sale_schedule_dashboard.xml",
            "sale_planning/static/src/sale_schedule_dashboard/sale_schedule_dashboard.js",
            "sale_planning/static/src/sale_schedule_dashboard/sale_schedule_dashboard.scss",
            "sale_planning/static/src/dashboard_progress/dashboard_progress.xml",
            "sale_planning/static/src/dashboard_progress/dashboard_progress.js",
            "sale_planning/static/src/dashboard_progress/dashboard_progress.scss",
            "sale_planning/static/src/manufacture_tracking/manufacture_tracking.xml",
            "sale_planning/static/src/manufacture_tracking/manufacture_tracking.js",
            "sale_planning/static/src/manufacture_tracking/manufacture_tracking.scss",
            "sale_planning/static/src/replenishment_dashboard/replenishment_dashboard.xml",
            "sale_planning/static/src/replenishment_dashboard/replenishment_dashboard.js",
            "sale_planning/static/src/replenishment_dashboard/replenishment_dashboard.scss",
            "sale_planning/static/src/analytics_dashboard/analytics_dashboard.xml",
            "sale_planning/static/src/analytics_dashboard/analytics_dashboard.js",
            "sale_planning/static/src/analytics_dashboard/analytics_dashboard.scss",

        ],
    },
    "application": True,
    "installable": True,
    "license": "LGPL-3",
}
