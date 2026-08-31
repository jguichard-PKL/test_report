# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import _, fields, models

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
    expected_reception_date = fields.Datetime(
        string="Date de réception prévue", required=True
    )
    expected_qty = fields.Integer(
        string="Nombre de pièces prévues", required=True
    )

    @staticmethod
    def _next_day_at(dt, at_time=NEXT_DAY_START_TIME):
        """Lendemain (jour calendaire suivant) d'un datetime, à une heure
        fixe — cf. NEXT_DAY_START_TIME.
        """
        return datetime.combine(dt.date() + timedelta(days=1), at_time)

    def action_generate(self):
        """Génère 3 tâches + 2 jalons à partir de deux entrées seulement
        (date de réception prévue, nombre de pièces prévues) — règles de
        date FIXES, pas de catalogue de flow ni de rendement.

        `planned_date_begin` (début) ET `date_deadline` (fin) sont posés sur
        chaque tâche, pour qu'elle s'affiche en mode "plage" (barre) dans le
        Gantt. Confirmé en test réel que sans `planned_date_begin`, une
        tâche n'apparaît PAS DU TOUT dans le Gantt — pas juste comme un
        point.

        ⚠️ `planned_date_begin` n'est PAS un champ garanti sur toute
        installation (ajouté par un module Gantt type project_enterprise,
        absent en Community) — sa présence n'est plus vérifiée ici (garde-fou
        retiré sur demande). S'il est absent, `create()` échoue avec une
        erreur ORM brute (`Invalid field 'planned_date_begin' in
        'project.task'`) plutôt qu'un message explicite. Cf. README §0 pour
        comment vérifier sa présence en amont, fonctionnellement.

        - Tâche A : début = date de réception ; fin = début + (qty × 10 min).
        - Tâche B (bloquée par A, liée au jalon "Jalon 1") : début =
          lendemain de la fin de A (9h00) ; fin = début + 48h.
        - Tâche C (bloquée par B) : début = lendemain de la fin de B (9h00) ;
          fin = début + 24h + (qty × 10 min).
        - Jalon "Jalon 1" : échéance = date de fin de la tâche A.
        - Jalon "Deadline" : échéance = fin de la tâche C + 48h.

        Ne pose aucun tag (project.tags) : laissé à la saisie manuelle sur
        chaque tâche, décision explicite (cf. README).
        """
        self.ensure_one()

        if not self.project_id.allow_task_dependencies:
            self.project_id.allow_task_dependencies = True
        if not self.project_id.allow_milestones:
            self.project_id.allow_milestones = True

        piece_duration = timedelta(minutes=self.expected_qty * MINUTES_PER_PIECE)

        # --- Tâche A ---
        begin_a = self.expected_reception_date
        end_a = begin_a + piece_duration
        task_a = self.env["project.task"].create(
            {
                "name": "A - Réception",
                "project_id": self.project_id.id,
                "planned_date_begin": begin_a,
                "date_deadline": end_a,
            }
        )

        # --- Jalon "Jalon 1" (créé ici pour pouvoir être lié à la tâche B) ---
        milestone_1 = self.env["project.milestone"].create(
            {
                "name": "Jalon 1",
                "project_id": self.project_id.id,
                "deadline": end_a.date(),
            }
        )

        # --- Tâche B (bloquée par A, liée au jalon 1) ---
        begin_b = self._next_day_at(end_a)
        end_b = begin_b + timedelta(hours=48)
        task_b = self.env["project.task"].create(
            {
                "name": "B",
                "project_id": self.project_id.id,
                "planned_date_begin": begin_b,
                "date_deadline": end_b,
                "depend_on_ids": [(6, 0, task_a.ids)],
                "milestone_id": milestone_1.id,
            }
        )

        # --- Tâche C (bloquée par B) ---
        begin_c = self._next_day_at(end_b)
        end_c = begin_c + timedelta(hours=24) + piece_duration
        task_c = self.env["project.task"].create(
            {
                "name": "C",
                "project_id": self.project_id.id,
                "planned_date_begin": begin_c,
                "date_deadline": end_c,
                "depend_on_ids": [(6, 0, task_b.ids)],
            }
        )

        # --- Jalon "Deadline" ---
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
        """Vue Gantt si project_enterprise est installé, sinon liste —
        détection dynamique plutôt que supposée.
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
