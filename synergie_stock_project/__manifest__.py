# -*- coding: utf-8 -*-
{
    "name": "Synergie - Dimension projet sur le stock",
    "version": "19.0.1.0.0",
    "summary": "Propage le code projet de la transaction source (OF, réception) vers le mouvement de stock, le lot et le stock disponible",
    "description": """
Introduit une dimension projet transverse au stock pour un flux
d'industrialisation ASIC (backend semi-conducteur).

Principes :
- Les articles sont génériques : le projet ne peut pas être dérivé de l'article,
  il vient de la transaction SOURCE (ordre de fabrication, réception, ...).
- Le projet est porté par le mouvement de stock (stock.move), dénominateur
  commun de toutes les transactions.
- Il est propagé au lot (stock.lot) à la validation (_action_done), sans jamais
  écraser un projet déjà posé (hypothèse : un lot est mono-projet).
- Il est exposé sur le stock disponible (stock.quant) en related stocké pour
  filtrer / grouper le stock par projet.

Voir le README pour la décision d'architecture et le hook surchargeable de
source projet sur transfert (_get_picking_project).
    """,
    "author": "Peaklane",
    "website": "https://www.peaklane.fr",
    "license": "LGPL-3",
    "category": "Inventory/Inventory",
    # 'mrp' : source projet pour les flux de fabrication (mrp.production.project_id).
    # 'project' : modèle cible project.project.
    # Source projet sur transfert (réception, livraison, interne) : tranchée =
    # saisie sur le picking (stock.picking.project_id). Pas de dépendance
    # 'purchase_stock' nécessaire.
    "depends": ["stock", "mrp", "project"],
    "data": [
        "views/stock_picking_views.xml",
        "views/stock_lot_views.xml",
        "views/stock_move_views.xml",
        "views/stock_move_line_views.xml",
        "views/stock_quant_views.xml",
    ],
    "installable": True,
    "application": False,
}
