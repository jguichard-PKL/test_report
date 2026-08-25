# -*- coding: utf-8 -*-
{
    "name": "Synergie - Suivi de rendement MRP",
    "version": "19.0.1.0.0",
    "summary": "Rendement (FPY) par ordre de fabrication et reporting agrégé multi-OF",
    "description": """
Suivi de la performance (rendement) des ordres de fabrication pour un flux
d'industrialisation ASIC (backend semi-conducteur).

Principes :
- Les pièces non conformes ("fails") ne sont jamais mises au rebut : elles sont
  modélisées comme un article dédié sorti en sous-produit de l'OF.
- Le module NE modifie NI ne surcharge la numérotation de lot.
- Aucun recours au scrap.
- Le rendement par OF est le first-pass yield (FPY) = conforme / total testé.
- Un modèle de reporting SQL agrège correctement le rendement multi-OF
  (un pourcentage ne s'additionne pas : SUM(good) / SUM(output)).
    """,
    "author": "Peaklane",
    "website": "https://www.peaklane.fr",
    "license": "LGPL-3",
    "category": "Manufacturing",
    # Dépendances minimales volontairement : on s'appuie uniquement sur les
    # mouvements de stock des sous-produits (move_finished_ids) et l'OF.
    "depends": ["mrp", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_template_views.xml",
        "views/mrp_production_views.xml",
        "report/mrp_yield_report_views.xml",
    ],
    "installable": True,
    "application": False,
}
