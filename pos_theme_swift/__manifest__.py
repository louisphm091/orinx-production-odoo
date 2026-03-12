{
    'name': 'POS Theme Swift',
    'version': '1.0.2',
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

Developed and maintained by https://group.orinx.com.vn.
''',
    'author': 'Orinx',
    'company': 'https://group.orinx.com.vn',
    'website': 'https://group.orinx.com.vn',
    'depends': ['point_of_sale', 'stock', 'purchase', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/stock_alert_cron.xml',
        'views/SwiftReportMenu.xml',
        'views/SwiftPosConfigThreshold.xml',
        'views/SwiftProductLowStock.xml',
        'views/SwiftProductBranchQty.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pos_theme_swift/static/src/js/xlsx.mini.min.js',
            'pos_theme_swift/static/src/js/chart.umd.min.js',
            'pos_theme_swift/static/src/js/SwiftPosReport.js',
            'pos_theme_swift/static/src/xml/report/SwiftPosReport.xml',
            'pos_theme_swift/static/src/css/SwiftReport.css',
            'pos_theme_swift/static/src/css/SwiftPosDashboard.css',
            'pos_theme_swift/static/src/css/SwiftInventory.css',
            'pos_theme_swift/static/src/xml/inventory/SwiftInventory.xml',
            'pos_theme_swift/static/src/xml/inventory/SwiftInventoryForm.xml',
            'pos_theme_swift/static/src/js/SwiftInventoryManagement.js',
            'pos_theme_swift/static/src/js/SwiftInventoryForm.js',
            'pos_theme_swift/static/src/js/SwiftStockTransfer.js',
            'pos_theme_swift/static/src/xml/SwiftStockTransfer.xml',
            'pos_theme_swift/static/src/css/SwiftStockTransfer.css',
            'pos_theme_swift/static/src/js/SwiftShiftManagement.js',
            'pos_theme_swift/static/src/xml/SwiftShiftManagement.xml',
            'pos_theme_swift/static/src/css/SwiftShiftManagement.css',
            'pos_theme_swift/static/src/js/SwiftPaycheckManagement.js',
            'pos_theme_swift/static/src/xml/SwiftPaycheckManagement.xml',
            'pos_theme_swift/static/src/css/SwiftPaycheckManagement.css',
            'pos_theme_swift/static/src/js/SwiftAttendanceManagement.js',
            'pos_theme_swift/static/src/xml/SwiftAttendanceManagement.xml',
            'pos_theme_swift/static/src/css/SwiftAttendanceManagement.css',
            'pos_theme_swift/static/src/js/SwiftWorkScheduleManagement.js',
            'pos_theme_swift/static/src/xml/SwiftWorkScheduleManagement.xml',
            'pos_theme_swift/static/src/css/SwiftWorkScheduleManagement.css',
            'pos_theme_swift/static/src/js/SwiftEmployeeManagement.js',
            'pos_theme_swift/static/src/xml/SwiftEmployeeManagement.xml',
            'pos_theme_swift/static/src/css/SwiftEmployeeManagement.css',
            'pos_theme_swift/static/src/css/list_view_center.css',
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
