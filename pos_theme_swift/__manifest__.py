{
    'name': 'POS Theme SWIFT',
    'version': '1.0.0',
    'category': 'Themes/Backend',
    'summary': 'The POS Theme Swift Is A Responsive And Ultimate '
               'Theme For Your Odoo V18.This Theme Will Give You '
               'A New Experience With Odoo.',
    'description': '''Minimalist and elegant backend POS theme for Odoo 18''',
    'author': 'Orinx',
    'company': 'Orinx',
    'website': 'https://www.erp.orinx.com.vn',
    'depends': ['point_of_sale'],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_theme_swift/static/src/js/ProductScreen.js',
            'pos_theme_swift/static/src/js/PaymentScreenPatch.js',
            'pos_theme_swift/static/src/js/saphire_tabs_patch.js',
            'pos_theme_swift/static/src/**/*.xml',
            'pos_theme_swift/static/src/css/custom.css',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
