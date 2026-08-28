# -*- coding: utf-8 -*-
{
    "name": "Synergie - Planification prévisionnelle du flux de production (Prototype)",
    "version": "19.0.1.0.0",
    "summary": "Prototype technique : génère une chaîne de tâches projet prévisionnelles "
    "(dates + quantités propagées par rendement) à partir d'un flow de production",
    "description": """
Prototype de démonstration — pas un livrable de production.

Cf. Spec_Technique_Prototype_ClaudeCode.md (v0.3) pour le cadrage complet.

Principes :
- Un wizard (assistant), lancé depuis la fiche projet, génère une chaîne de
  project.task représentant les étapes du flow de production (wafer -> die ->
  rawline -> ...), chaînées via les dépendances natives (depend_on_ids).
- Chaque étape a une durée FIXE (ex. lead time fournisseur, bake) ou
  PROPORTIONNELLE à une quantité prévisionnelle, elle-même propagée depuis une
  quantité d'entrée unique via des rendements saisis dans le wizard (100% par
  défaut = pas de perte).
- Les dates sont chaînées en avant depuis une date d'ancrage, converties en
  temps ouvré via le calendrier de la société (resource.calendar.plan_hours).
- Un champ de date réelle de fin + un écart calculé permettent un suivi
  manuel prévisionnel/réel, sans aucun lien automatique avec les OF/mouvements
  de stock existants (hors périmètre strict, cf. README).

Ce module ne modifie et ne dépend d'AUCUN modèle mrp.* ou stock.* existant.
    """,
    "author": "Peaklane",
    "website": "https://www.peaklane.fr",
    "license": "LGPL-3",
    "category": "Services/Project",
    # 'project' : project.task, project.project, dépendances de tâches natives.
    # Pas de dépendance à 'project_enterprise' : le module doit s'installer et
    # fonctionner (sans vue Gantt) même sur une base Community. La disponibilité
    # de la vue Gantt Enterprise est détectée dynamiquement à l'exécution
    # (cf. wizard, action_generate -> _get_result_action), jamais supposée.
    # Pas de dépendance à 'stock' : pas de données de démo dans ce module
    # (déjà disponibles côté Synergie) ; aucun modèle stock.* n'est étendu.
    "depends": ["project"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter_data.xml",
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
