# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    # Champ cible : le projet posé une fois pour toutes à la validation du
    # mouvement (cf. stock.move.line._action_done). Laissé en lecture/écriture
    # pour autoriser des corrections manuelles.
    # index=True : filtres et group_by fréquents par projet.
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        index=True,
        help=(
            "Projet de rattachement du lot, propagé depuis le mouvement de "
            "stock source à la validation. Un lot est mono-projet : une fois "
            "posé, le projet n'est pas écrasé automatiquement."
        ),
    )
