# -*- coding: utf-8 -*-
from odoo import fields, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Projet en stock disponible : related stocké sur le projet du lot.
    # store=True permet de filtrer / grouper le stock disponible par projet
    # (besoin direct Synergie) sans jointure coûteuse.
    # index=True : filtres et group_by fréquents.
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        related="lot_id.project_id",
        store=True,
        index=True,
        help="Projet du lot en stock, pour filtrer / grouper le stock disponible.",
    )
