# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class ProjectPlanningGenerateWizard(models.TransientModel):
    _name = "project.planning.generate.wizard"
    _description = "Génération de la planification prévisionnelle (prototype)"

    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        required=True,
        default=lambda self: self.env.context.get("active_id"),
    )
    anchor_date = fields.Datetime(
        string="Date de première réception",
        required=True,
        default=fields.Datetime.now,
    )
    input_qty = fields.Integer(
        string="Quantité d'entrée (ex : nombre de wafers)", required=True
    )
    has_bumping = fields.Boolean(string="Bumping")
    wafer_test_temp_count = fields.Selection(
        [("1", "1"), ("2", "2"), ("3", "3")],
        string="Nb. températures - Wafer Test",
        default="1",
        required=True,
    )
    has_retention_bake = fields.Boolean(string="Retention Bake")
    final_test_temp_count = fields.Selection(
        [("1", "1"), ("2", "2"), ("3", "3")],
        string="Nb. températures - Final Test",
        default="1",
        required=True,
    )
    yield_wafer_test = fields.Float(
        string="Rendement Wafer Test attendu (%)", default=100.0
    )
    yield_assembly = fields.Float(
        string="Rendement Assembly attendu (%)", default=100.0
    )
    yield_final_test = fields.Float(
        string="Rendement Final Test attendu (%)", default=100.0
    )

    # ------------------------------------------------------------------
    # Catalogue du flow (§3 de la spec). Codé en dur volontairement : ce
    # n'est PAS un référentiel paramétrable pour ce prototype (cf. README).
    # Les valeurs par défaut (5j / 3j / 24h) sont des valeurs de démo, pas
    # des données validées avec le client.
    # ------------------------------------------------------------------
    def _get_flow_steps(self):
        """Construit la liste ORDONNÉE des étapes actives.

        Chaque étape : dict avec 'code', 'name', 'duration_type'
        ('fixed'/'proportional'), 'fixed_hours' (si fixed) et 'yield_field'
        (nom du champ wizard dont le rendement s'applique UNE SEULE FOIS à
        l'entrée de ce groupe d'étapes — None si l'étape ne déclenche pas de
        nouveau rendement, ex. Wafer Test 2/3 ou Final Test Hot/Cold, qui
        partagent la quantité déjà calculée pour le groupe).

        [Interprétation assumée, non explicitée telle quelle dans la spec] :
        Wafer Test / Final Test à plusieurs températures génèrent PLUSIEURS
        tâches séquentielles (une par température, codes D1/D2/D3 et
        TG/TH/TC), toutes à la MÊME quantité prévisionnelle (le rendement de
        groupe — GDPW ou final test — s'applique une fois à l'entrée du
        groupe, pas par température testée individuellement). Cohérent avec
        l'exemple chiffré de la spec synthétique §6 (un seul rendement par
        groupe d'étape), mais à confirmer avec le client si plusieurs
        températures sont réellement testées en prod (cf. README).
        """
        self.ensure_one()
        steps = [
            {
                "code": "WF",
                "name": "Wafer Foundry",
                "duration_type": "fixed",
                "fixed_hours": 5 * 24.0,
            },
        ]
        if self.has_bumping:
            steps.append(
                {
                    "code": "BP",
                    "name": "Bumping",
                    "duration_type": "fixed",
                    "fixed_hours": 3 * 24.0,
                }
            )

        wafer_test_count = int(self.wafer_test_temp_count)
        for i in range(1, wafer_test_count + 1):
            steps.append(
                {
                    "code": "D%s" % i,
                    "name": "Wafer Test %s" % i,
                    "duration_type": "proportional",
                    "yield_field": "yield_wafer_test" if i == 1 else None,
                }
            )

        if self.has_retention_bake:
            steps.append(
                {
                    "code": "RB",
                    "name": "Retention Bake",
                    "duration_type": "fixed",
                    "fixed_hours": 24.0,
                }
            )

        steps.append(
            {
                "code": "RL",
                "name": "Assembly",
                "duration_type": "proportional",
                "yield_field": "yield_assembly",
            }
        )

        final_test_count = int(self.final_test_temp_count)
        final_test_labels = [
            ("TG", "Final Test Std"),
            ("TH", "Final Test Hot"),
            ("TC", "Final Test Cold"),
        ]
        for i in range(final_test_count):
            code, name = final_test_labels[i]
            steps.append(
                {
                    "code": code,
                    "name": name,
                    "duration_type": "proportional",
                    "yield_field": "yield_final_test" if i == 0 else None,
                }
            )

        steps.append(
            {
                "code": "FG",
                "name": "End Of Line",
                "duration_type": "proportional",
                "yield_field": None,
            }
        )
        return steps

    def action_generate(self):
        """Cf. §4.3 de la spec pour l'algorithme numéroté ; commentaires
        ci-dessous alignés sur cette numérotation.
        """
        self.ensure_one()

        # 0. Hypothèse critique (cf. §0 de la spec) : planned_date_begin/
        # planned_date_end sont supposés ajoutés par le module Enterprise
        # project_enterprise, absents sur une base Community. Un create()
        # dessus planterait si absents. On arrête ici, explicitement, plutôt
        # que de laisser échouer create() avec une erreur ORM peu explicite.
        #
        # ⚠️ Trou corrigé, rencontré en test réel : on ne vérifiait au
        # départ que 'planned_date_begin', en supposant les deux champs
        # toujours présents ensemble (ils le sont dans project_enterprise
        # côté sources publiques). Sur l'instance de test, 'planned_date_begin'
        # existe mais PAS 'planned_date_end' — origine exacte non confirmée
        # (autre module installé fournissant un champ de même nom pour un
        # usage différent ? champ renommé dans une variante de Gantt ?
        # project_enterprise non public, impossible à vérifier depuis cet
        # environnement). On vérifie donc explicitement les DEUX champs,
        # plutôt que de supposer leur présence liée.
        missing_fields = [
            f
            for f in ("planned_date_begin", "planned_date_end")
            if f not in self.env["project.task"]._fields
        ]
        if missing_fields:
            raise UserError(
                _(
                    "Ce prototype nécessite les champs %(fields)s sur "
                    "project.task (normalement ajoutés par le module "
                    "Enterprise 'project_enterprise', vue Gantt), absent(s) "
                    "sur cette base. Deux options : installer/activer le "
                    "module fournissant ces champs pour ce test, ou retirer "
                    "ce point du périmètre du prototype (dates calculées et "
                    "dépendances natives uniquement, sans rendu Gantt) — "
                    "cf. §0 de la spécification technique.",
                    fields=", ".join(missing_fields),
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

        # 2. Dépendances de tâches activées sur le projet.
        if not self.project_id.allow_task_dependencies:
            self.project_id.allow_task_dependencies = True

        # 3. Étapes actives du flow.
        steps = self._get_flow_steps()

        # Calendrier de travail : société du projet, à défaut société courante.
        calendar = (
            self.project_id.company_id.resource_calendar_id
            or self.env.company.resource_calendar_id
        )
        if not calendar:
            raise UserError(
                _(
                    "Aucun calendrier de travail n'est configuré sur la "
                    "société — impossible de calculer les dates planifiées."
                )
            )

        default_unit_time = self.env[
            "project.task"
        ]._get_default_unit_time_minutes()

        # 4 & 5. Propagation de la quantité + création chaînée des tâches.
        current_qty = self.input_qty
        current_end = self.anchor_date
        previous_task = self.env["project.task"]
        created_tasks = self.env["project.task"]

        for step in steps:
            vals = {
                "name": "%s - %s" % (step["code"], step["name"]),
                "project_id": self.project_id.id,
                "x_duration_type": step["duration_type"],
                "x_generated_by_wizard": True,
                "depend_on_ids": [(6, 0, previous_task.ids)],
            }

            if step["duration_type"] == "fixed":
                # Point 4 : les étapes fixes n'ont pas de quantité
                # prévisionnelle calculée (x_planned_qty laissé à 0).
                duration_hours = step["fixed_hours"]
                vals["x_fixed_duration_hours"] = duration_hours
            else:
                yield_field = step.get("yield_field")
                if yield_field:
                    yield_pct = getattr(self, yield_field) or 100.0
                    current_qty = round(current_qty * yield_pct / 100.0)
                vals["x_planned_qty"] = current_qty
                vals["x_unit_time_minutes"] = default_unit_time
                duration_hours = current_qty * default_unit_time / 60.0

            begin = current_end
            # [À vérifier v19] resource.calendar.plan_hours(hours, day_dt, ...)
            # confirmé présent en lisant resource/models/resource_calendar.py
            # (branche 19.0) : retourne la date/heure après avoir "planifié"
            # N heures ouvrées depuis day_dt. Skip si durée nulle : appeler
            # plan_hours(0, begin) peut renvoyer le début du PROCHAIN
            # intervalle ouvré (pas begin lui-même) si begin tombe hors
            # horaires ouvrés, ce qui décalerait une étape à durée nulle.
            end = (
                calendar.plan_hours(duration_hours, begin, compute_leaves=True)
                if duration_hours
                else begin
            )
            if not end:
                # plan_hours peut renvoyer False (calendrier sans intervalle
                # ouvré trouvé) : repli sur un ajout de temps brut plutôt que
                # de bloquer la génération, pour rester utilisable en démo.
                end = begin + timedelta(hours=duration_hours)
            vals["planned_date_begin"] = begin
            vals["planned_date_end"] = end

            task = self.env["project.task"].create(vals)
            created_tasks |= task
            previous_task = task
            current_end = end

        # 6. Action de retour : Gantt si Enterprise dispo, sinon liste.
        return self._get_result_action(created_tasks)

    def _get_result_action(self, tasks):
        """Détecte dynamiquement la disponibilité de la vue Gantt Enterprise
        plutôt que de la supposer (cf. §0 de la spec : le prototype doit
        fonctionner, sans rendu Gantt, même sur une base Community).
        """
        self.ensure_one()
        gantt_available = bool(
            self.env["ir.module.module"]
            .sudo()
            .search_count(
                [("name", "=", "project_enterprise"), ("state", "=", "installed")]
            )
        )
        view_mode = "gantt,list,kanban,form" if gantt_available else "list,form"
        return {
            "type": "ir.actions.act_window",
            "name": _("Planification prévisionnelle - %s", self.project_id.name),
            "res_model": "project.task",
            "view_mode": view_mode,
            "domain": [("id", "in", tasks.ids)],
            "context": {"default_project_id": self.project_id.id},
        }
