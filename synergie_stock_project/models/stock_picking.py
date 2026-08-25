# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # Projet porté par le DOCUMENT de transfert, saisi manuellement sur le
    # transfert (réception, livraison, interne). Miroir du modèle OF où le
    # projet est porté par mrp.production.
    #
    # Le mouvement (stock.move) le récupère via _get_picking_project(), puis
    # il est propagé au lot à la validation. index=True : filtres / group_by.
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        index=True,
        help=(
            "Projet de rattachement du transfert. Il est propagé aux "
            "mouvements de stock, puis aux lots mouvementés à la validation."
        ),
    )
