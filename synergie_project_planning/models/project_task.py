# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    x_generated_by_wizard = fields.Boolean(
        string="Générée par le wizard",
        default=False,
        help="Marqueur technique posé par le wizard de génération, utilisé "
        "par son garde-fou d'idempotence (une seule génération par projet).",
    )
    x_actual_end_date = fields.Date(
        string="Date réelle de fin",
        help="Saisie manuelle par l'admin lorsque l'étape est effectivement "
        "terminée. Aucun lien automatique avec l'OF/les mouvements de stock "
        "(hors périmètre, cf. README) : purement déclaratif.",
    )
    x_deviation_days = fields.Float(
        string="Écart (jours)",
        compute="_compute_x_deviation_days",
        store=True,
        help="= Date réelle de fin - date_deadline (natif), en jours. "
        "Positif = retard, négatif = avance. Indicateur affiché uniquement : "
        "ne répercute jamais automatiquement l'écart sur les tâches "
        "suivantes (choix assumé, cf. README).",
    )

    # date_deadline (fin, natif) peut être référencé directement dans
    # @api.depends : contrairement à planned_date_begin/planned_date_end,
    # c'est un champ Community natif toujours présent (pas ajouté par un
    # module Gantt) — confirmé dans les sources (project/models/
    # project_task.py). Pas besoin du contournement utilisé dans une version
    # précédente pour planned_date_end (absent sur l'instance cible).
    @api.depends("x_actual_end_date", "date_deadline")
    def _compute_x_deviation_days(self):
        # [Limite assumée] x_deviation_days est un Float : sans valeur
        # calculable il est mis à 0.0, pas "vide" au sens strict (un champ
        # Float ne distingue pas 0 de "non renseigné" dans les vues standard).
        for task in self:
            if task.x_actual_end_date and task.date_deadline:
                delta = task.x_actual_end_date - task.date_deadline.date()
                task.x_deviation_days = delta.days
            else:
                task.x_deviation_days = 0.0
