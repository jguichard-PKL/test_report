# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Projet porté par le DOCUMENT de transfert, saisi manuellement sur le bon
    # de réception. Source du projet en entrée de stock (réception wafer, ...),
    # miroir du modèle OF où le projet est porté par mrp.production.
    #
    # Le mouvement (stock.move) le récupère via _get_reception_project(), puis
    # il est propagé au lot à la validation. index=True : filtres / group_by.
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        index=True,
        help=(
            "Projet de rattachement du transfert. Sur une réception, il est "
            "propagé aux mouvements de stock puis aux lots reçus."
        ),
    )
