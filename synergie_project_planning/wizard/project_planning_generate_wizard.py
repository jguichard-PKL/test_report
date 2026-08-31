# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

# Temps de traitement unitaire, en dur pour cette maquette (plus de
# paramètre système ni de champ configurable — cf. README).
MINUTES_PER_PIECE = 10

# Heure de reprise le "lendemain" d'une fin de tâche (confirmé côté client :
# 9h00 fixe, pas la même heure que la fin de la tâche précédente).
NEXT_DAY_START_TIME = time(9, 0)


class ProjectPlanningGenerateWizard(models.TransientModel):
    _name = "project.planning.generate.wizard"
    _description = "Génération de la planification prévisionnelle (maquette)"

    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        required=True,
        default=lambda self: self.env.context.get("active_id"),
    )
    start_datetime = fields.Datetime(
        string="Date de début de projet", required=True
    )
    input_qty = fields.Integer(
        string="Quantité à réceptionner", required=True
    )

    @staticmethod
    def _next_day_at(dt, at_time=NEXT_DAY_START_TIME):
        """Lendemain (jour calendaire suivant) d'un datetime, à une heure
        fixe — cf. NEXT_DAY_START_TIME.
        """
        return datetime.combine(dt.date() + timedelta(days=1), at_time)

    def action_generate(self):
        """Maquette simplifiée : 3 tâches à règles de date FIXES (pas de
        catalogue de flow, pas de rendement, pas de calendrier ouvré — de
        simples décalages calendaires en dur), + 2 jalons.

        Écrit sur les champs NATIFS planned_date_begin (début) et
        date_deadline (fin) — c'est tout l'intérêt de cette maquette (§0 du
        README). `date_deadline` remplace `planned_date_end` depuis la
        version précédente : couple confirmé en observant le comportement
        réel de l'UI (bouton "Toggle date range mode" sur le champ Deadline
        de la tâche, qui permet de saisir un début ET une fin) — pas
        `planned_date_end`, qui n'était probablement jamais le bon champ.
        `date_deadline` est un Datetime natif Community, toujours présent
        (contrairement à `planned_date_begin`, potentiellement ajouté par
        un module Gantt).

        - Tâche A : début = start_datetime ; fin = début + (qty × 10 min).
        - Tâche B (bloquée par A) : début = lendemain de la fin de A, 9h00 ;
          fin = début + 48h.
        - Tâche C (bloquée par B) : début = lendemain de la fin de B, 9h00 ;
          fin = début + 24h + (qty × 10 min).
        - Jalon "Jalon 1" : échéance = date de fin de la tâche A.
        - Jalon "Deadline" : échéance = fin de la tâche C + 48h.

        Confirmé côté client :
        - « Date de fin = Date de début × (qty × 10 min) » : une ADDITION
          (début + durée) — l'énoncé initial n'avait pas de sens arithmétique
          tel quel.
        - « Lendemain de la date de fin » : le jour calendaire suivant, à
          **9h00 fixe** (pas la même heure que la fin de la tâche
          précédente) — cf. `NEXT_DAY_START_TIME` / `_next_day_at`.
        """
        self.ensure_one()

        # 0. Prérequis (cf. README §0) : planned_date_begin est un champ
        # NATIF ajouté par un module Gantt (project_enterprise ou
        # équivalent), pas garanti présent partout. date_deadline, en
        # revanche, est natif Community (toujours présent) : pas besoin de
        # le vérifier.
        if "planned_date_begin" not in self.env["project.task"]._fields:
            raise UserError(
                _(
                    "Cette maquette nécessite le champ 'planned_date_begin' "
                    "sur project.task (normalement ajouté par le module "
                    "Gantt Enterprise 'project_enterprise'), absent sur "
                    "cette base. Vérifiez dans Réglages > Technique > Base "
                    "de données > Champs (modèle project.task, filtre "
                    "\"planned\") ce qui est réellement disponible — "
                    "cf. README §0.",
                )
            )

        # 1. Garde-fou d'idempotence.
        already_generated = self.env["project.task"].search_count(
            [
                ("project_id", "=", self.project_id.id),
                ("x_generated_by_wizard", "=", True),
            ]
        )
        if already_generated:
            raise UserError(
                _(
                    "Une planification existe déjà pour ce projet. "
                    "Supprimez les tâches générées existantes avant de "
                    "relancer le wizard."
                )
            )

        if not self.project_id.allow_task_dependencies:
            self.project_id.allow_task_dependencies = True
        if not self.project_id.allow_milestones:
            self.project_id.allow_milestones = True

        piece_duration = timedelta(minutes=self.input_qty * MINUTES_PER_PIECE)

        # --- Tâche A ---
        begin_a = self.start_datetime
        end_a = begin_a + piece_duration
        task_a = self.env["project.task"].create(
            {
                "name": "A - Réception",
                "project_id": self.project_id.id,
                "x_generated_by_wizard": True,
                "planned_date_begin": begin_a,
                "date_deadline": end_a,
            }
        )

        # --- Tâche B (bloquée par A) ---
        begin_b = self._next_day_at(end_a)
        end_b = begin_b + timedelta(hours=48)
        task_b = self.env["project.task"].create(
            {
                "name": "B",
                "project_id": self.project_id.id,
                "x_generated_by_wizard": True,
                "planned_date_begin": begin_b,
                "date_deadline": end_b,
                "depend_on_ids": [(6, 0, task_a.ids)],
            }
        )

        # --- Tâche C (bloquée par B) ---
        begin_c = self._next_day_at(end_b)
        end_c = begin_c + timedelta(hours=24) + piece_duration
        task_c = self.env["project.task"].create(
            {
                "name": "C",
                "project_id": self.project_id.id,
                "x_generated_by_wizard": True,
                "planned_date_begin": begin_c,
                "date_deadline": end_c,
                "depend_on_ids": [(6, 0, task_b.ids)],
            }
        )

        # --- Jalons ---
        self.env["project.milestone"].create(
            {
                "name": "Jalon 1",
                "project_id": self.project_id.id,
                "deadline": end_a.date(),
            }
        )
        self.env["project.milestone"].create(
            {
                "name": "Deadline",
                "project_id": self.project_id.id,
                "deadline": (end_c + timedelta(hours=48)).date(),
            }
        )

        created_tasks = task_a | task_b | task_c
        return self._get_result_action(created_tasks)

    def _get_result_action(self, tasks):
        """Vue Gantt si project_enterprise est installé (attendu, cf. §0),
        sinon liste — détection dynamique plutôt que supposée.
        """
        self.ensure_one()
        gantt_available = bool(
            self.env["ir.module.module"]
            .sudo()
            .search_count(
                [("name", "=", "project_enterprise"), ("state", "=", "installed")]
            )
        )
        view_mode = "gantt,list,kanban,form" if gantt_available else "list,kanban,form"
        return {
            "type": "ir.actions.act_window",
            "name": _("Planification prévisionnelle - %s", self.project_id.name),
            "res_model": "project.task",
            "view_mode": view_mode,
            "domain": [("id", "in", tasks.ids)],
            "context": {"default_project_id": self.project_id.id},
        }
