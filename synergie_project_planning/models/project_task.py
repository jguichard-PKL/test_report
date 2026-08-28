# -*- coding: utf-8 -*-
from odoo import api, fields, models

DEFAULT_UNIT_TIME_MINUTES_PARAM = "planning.default_unit_time_minutes"


class ProjectTask(models.Model):
    _inherit = "project.task"

    # ------------------------------------------------------------------
    # Cf. Spec_Technique_Prototype_ClaudeCode.md §2.1. Ces champs modélisent
    # une étape du flow de production (au sens agrégé, pas un OF/lot
    # individuel — cf. cadrage §1 de la synthèse fonctionnelle). Prototype :
    # pas de lien, ni de dépendance, vers un modèle mrp.*/stock.* existant.
    # ------------------------------------------------------------------
    x_duration_type = fields.Selection(
        [("fixed", "Fixe"), ("proportional", "Proportionnelle")],
        string="Type de durée",
        required=True,
        default="proportional",
        help="Durée fixe (ex. lead time fournisseur, bake) ou proportionnelle "
        "à la quantité prévisionnelle de l'étape.",
    )
    x_fixed_duration_hours = fields.Float(
        string="Durée fixe (h)",
        help="Utilisée si le type de durée est 'Fixe'.",
    )
    x_unit_time_minutes = fields.Float(
        string="Temps unitaire (min/pièce)",
        default=lambda self: self._get_default_unit_time_minutes(),
        help="Temps unitaire utilisé pour cette étape si le type de durée est "
        "'Proportionnelle'. Copié depuis le paramètre système par défaut à la "
        "création de la tâche : pas de lien dynamique ensuite, pour ne pas "
        "modifier une planification déjà communiquée si le paramètre change.",
    )
    x_planned_qty = fields.Integer(
        string="Quantité prévisionnelle",
        help="Calculée par le wizard de génération par propagation du "
        "rendement depuis la quantité d'entrée. Non éditable manuellement "
        "après génération dans ce prototype. Laissée à 0 pour une étape à "
        "durée fixe.",
    )
    x_planned_duration_hours = fields.Float(
        string="Durée prévisionnelle (h)",
        compute="_compute_x_planned_duration_hours",
        store=True,
        help="= Durée fixe si type Fixe, sinon quantité prévisionnelle × "
        "temps unitaire / 60.",
    )
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
        help="= Date réelle de fin - Date de fin planifiée, en jours. "
        "Positif = retard, négatif = avance. Indicateur affiché uniquement : "
        "ne répercute jamais automatiquement l'écart sur les tâches "
        "suivantes (choix assumé, cf. README).",
    )

    @api.model
    def _get_default_unit_time_minutes(self):
        """Valeur par défaut du temps unitaire (§2.3) : paramètre système,
        secours à 1 si jamais initialisé (cf. data/ir_config_parameter_data.xml).
        """
        param = self.env["ir.config_parameter"].sudo().get_param(
            DEFAULT_UNIT_TIME_MINUTES_PARAM
        )
        try:
            return float(param)
        except (TypeError, ValueError):
            return 1.0

    @api.depends(
        "x_duration_type",
        "x_fixed_duration_hours",
        "x_planned_qty",
        "x_unit_time_minutes",
    )
    def _compute_x_planned_duration_hours(self):
        for task in self:
            if task.x_duration_type == "fixed":
                task.x_planned_duration_hours = task.x_fixed_duration_hours
            else:
                task.x_planned_duration_hours = (
                    task.x_planned_qty * task.x_unit_time_minutes / 60.0
                )

    @api.depends("x_actual_end_date", "planned_date_end")
    def _compute_x_deviation_days(self):
        # [Limite assumée] x_deviation_days est un Float : sans valeur
        # calculable il est mis à 0.0, pas "vide" au sens strict (un champ
        # Float ne distingue pas 0 de "non renseigné" dans les vues standard).
        # Cohérent avec la simplicité demandée pour ce prototype ; à
        # reconsidérer (ex. widget dédié) si ça prête à confusion en démo.
        for task in self:
            if task.x_actual_end_date and task.planned_date_end:
                delta = task.x_actual_end_date - task.planned_date_end.date()
                task.x_deviation_days = delta.days
            else:
                task.x_deviation_days = 0.0
