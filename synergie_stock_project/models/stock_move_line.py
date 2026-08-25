# -*- coding: utf-8 -*-
from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # Related non stocké : simple relais "à plat" du projet du mouvement
    # parent. Nécessaire pour être référençable dans le domaine du champ
    # quant_id (widget pick_from, cf. stock_move_line_views.xml) : un domaine
    # de vue ne peut résoudre qu'un champ directement chargé sur
    # l'enregistrement courant, jamais une chaîne relationnelle du type
    # move_id.project_id (non résolue côté client, filtre silencieusement
    # inopérant). Le cœur applique déjà ce contournement pour
    # picking_location_id (related sur stock.move.line), même logique ici.
    project_id = fields.Many2one(
        "project.project",
        string="Projet (mouvement)",
        related="move_id.project_id",
        store=False,
    )
