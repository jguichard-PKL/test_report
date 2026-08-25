# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Classification de la sortie de production.
    #
    # Sert à identifier, parmi les sous-produits (by-products) d'un ordre de
    # fabrication, ce qui constitue un "fail" (pièce non conforme conservée en
    # stock, jamais scrappée) ou un "retest" (pièce à repasser en test).
    #
    # NB : ce champ vit sur product.template mais reste accessible depuis
    # product.product par héritage par délégation (_inherits), donc
    # `move.product_id.pkl_output_type` fonctionne directement.
    pkl_output_type = fields.Selection(
        selection=[
            ("good", "Conforme"),
            ("fail", "Fail"),
            ("retest", "Retest"),
        ],
        string="Type de sortie de production",
        default="good",
        required=True,
        help=(
            "Rôle de l'article lorsqu'il est produit en sortie d'un ordre de "
            "fabrication :\n"
            "- Conforme : pièce bonne (typiquement le produit principal de l'OF).\n"
            "- Fail : pièce non conforme conservée en stock (jamais mise au rebut).\n"
            "- Retest : pièce à repasser en test.\n\n"
            "La détection du rendement par OF s'appuie sur ce champ pour classer "
            "les sous-produits."
        ),
    )
