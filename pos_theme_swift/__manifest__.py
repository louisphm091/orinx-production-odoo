{
    'name': 'POS Theme Swift',
    'version': '1.0',
    'category': 'Themes/Backend',
    'summary': 'The POS Theme Swift Is A Responsive And Ultimate '
               'Theme For Your Odoo V19.This Theme Will Give You '
               'A New Experience With Odoo.',
    'description': '''Minimalist and elegant backend POS theme for Odoo 18''',
    'author': 'Orinx',
    'company': 'Orinx',
    'website': 'https://www.erp.orinx.com.vn',
    'depends': ['point_of_sale'],
    'data': [
        'views/SwiftReportMenu.xml',
    ],
    'assets': {
        'web.assets_backend':
        [
            'pos_theme_swift/static/src/js/chart.umd.min.js',
            'pos_theme_swift/static/src/js/SwiftPosReport.js',
            'pos_theme_swift/static/src/xml/report/SwiftPosReport.xml',
            'pos_theme_swift/static/src/css/SwiftReport.css',
        ],
        'point_of_sale._assets_pos': [
            'pos_theme_swift/static/src/js/ProductScreen.js',
            'pos_theme_swift/static/src/js/PaymentScreenPatch.js',
            'pos_theme_swift/static/src/js/SwiftTabsPatch.js',
            'pos_theme_swift/static/src/js/PaymentSwiftPay.js',
            'pos_theme_swift/static/src/js/SwiftBottomBar.js',
            'pos_theme_swift/static/src/**/*.xml',
            'pos_theme_swift/static/src/css/custom.css',

        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
