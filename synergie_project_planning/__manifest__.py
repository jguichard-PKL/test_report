# -*- coding: utf-8 -*-
{
    "name": "Synergie - Planification prévisionnelle du flux de production (Prototype)",
    "version": "19.0.6.0.0",
    "summary": "Maquette : génère 3 tâches + 2 jalons prévisionnels dans le "
    "Gantt Enterprise, à partir d'une quantité et d'une date de début",
    "description": """
Prototype de démonstration — pas un livrable de production.

Cf. Spec_Technique_Prototype_ClaudeCode.md pour le cadrage initial, et le
README de ce module pour l'historique complet des arbitrages (§6 : 4
versions successives, dont l'identification du bon couple de champs de date).

Principes :
- Un wizard (assistant), lancé depuis la fiche projet, prend une quantité et
  une date de début, et génère 3 project.task chaînées par les dépendances
  natives (depend_on_ids) + 2 project.milestone, selon des règles de date
  fixes en dur (cf. wizard).
- Les dates sont écrites sur planned_date_begin (début, ajouté par un module
  Gantt type project_enterprise) et date_deadline (fin, Community natif,
  toujours présent) — c'est le couple réellement utilisé par Odoo pour la
  vue Gantt, PAS planned_date_end comme le supposaient des versions
  précédentes de ce module. Cf. README §0 pour comment ça a été identifié.
- Un champ de date réelle de fin + un écart calculé permettent un suivi
  manuel prévisionnel/réel, sans aucun lien automatique avec les OF/mouvements
  de stock existants (hors périmètre strict, cf. README).

Ce module ne modifie et ne dépend d'AUCUN modèle mrp.* ou stock.* existant.
    """,
    "author": "Peaklane",
    "website": "https://www.peaklane.fr",
    "license": "LGPL-3",
    "category": "Services/Project",
    # 'project' : project.task, project.project, project.milestone,
    # dépendances de tâches natives, date_deadline — tout Community. Pas de
    # dépendance dure à 'project_enterprise' (le module doit pouvoir
    # s'installer même sans), mais son absence bloque explicitement
    # action_generate() (planned_date_begin manquant) — cf. README §0.
    "depends": ["project"],
    "data": [
        "security/ir.model.access.csv",
        "views/project_task_views.xml",
        # AVANT project_project_views.xml : ce dernier référence l'action du
        # wizard (%(...)d) définie ici. Les fichiers XML sont chargés dans
        # l'ordre exact de cette liste ; une référence en avant vers un XML
        # ID pas encore chargé échoue immédiatement (confirmé en test réel :
        # "External ID not found in the system" à l'installation).
        "wizard/project_planning_generate_wizard_views.xml",
        "views/project_project_views.xml",
    ],
    "installable": True,
    "application": False,
}
