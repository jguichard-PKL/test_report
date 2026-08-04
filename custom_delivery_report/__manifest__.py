{
    'name': "Custom Delivery Slip Report",
    'summary': "Bon de Livraison report reproducing a client-provided layout, with pricing from the linked sale order.",
    'description': """
Custom Delivery Slip (Bon de Livraison) report for stock.picking.

Reproduces a client-supplied PDF layout: company header with logo, addressee
block, shipping address, BL/date/reference/carrier box, priced line table
(reference, description + lot, quantity, UoM, unit price, amount) and a
legal footer.

Pricing is pulled from the sale order line linked to each stock move
(stock.move.sale_line_id).
""",
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'Peaklane',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock', 'delivery'],
    'data': [
        'report/delivery_bl_report_actions.xml',
        'report/delivery_bl_report_template.xml',
    ],
    'installable': True,
    'application': False,
}
