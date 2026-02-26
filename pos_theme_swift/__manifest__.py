{
    'name': 'POS Theme Swift',
    'version': '1.0',
    'category': 'Themes/Backend',
    'summary': 'POS Theme Swift - Professional and Responsive POS Interface for Odoo 19',
    'description': '''
POS Theme Swift is a modern, minimalist and performance-optimized
Point of Sale interface developed by Orinx.

This theme enhances the POS user experience with:
- Clean and intuitive UI
- Optimized payment flow
- Custom reporting dashboard
- Streamlined POS screen structure
- Responsive layout for multiple devices

Developed and maintained by Orinx.
''',
    'author': 'Orinx',
    'company': 'Orinx',
    'website': 'https://orinx.com.vn',
    'depends': ['point_of_sale'],
    'data': [
        'views/SwiftReportMenu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pos_theme_swift/static/src/js/chart.umd.min.js',
            'pos_theme_swift/static/src/js/SwiftPosReport.js',
            'pos_theme_swift/static/src/xml/report/SwiftPosReport.xml',
            'pos_theme_swift/static/src/css/SwiftReport.css',
        ],
        'point_of_sale._assets_pos': [
            'pos_theme_swift/static/src/js/PosAppPatch.js',
            'pos_theme_swift/static/src/js/RemoveProductScreen.js',
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
