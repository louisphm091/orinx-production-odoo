{
    "name": "Product ZIP Image Import",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Import product images from a ZIP file and match by barcode or internal reference",
    "depends": ["product", "point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/WizardView.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
