{
    'name': "Synergie - Bon de livraison",
    'summary': "Bon de livraison au format client, valorisé depuis la commande de vente liée",
    'description': """
Rapport PDF « Bon de Livraison » sur stock.picking.

Reproduit la maquette fournie par le client : en-tête société avec logo, bloc
destinataire, adresse de livraison, encadré BL / date / référence / transporteur,
tableau de lignes valorisé (référence, désignation + lot, quantité, UdM, prix
unitaire, montant) et pied de page légal.

Les prix sont repris de la ligne de commande de vente liée à chaque mouvement
de stock (stock.move.sale_line_id).
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
