# synergie_project_planning — Planification prévisionnelle (Maquette)

**Statut : MAQUETTE TECHNIQUE.** Démonstration très simple, pas un livrable
de production. 

Cible : **Odoo 19**.

---

## 0. Champ de date : `date_deadline` seul, décision assumée

**L'intérêt de cette maquette est d'utiliser le Gantt — décision du client.**
Après plusieurs itérations (cf. §6 pour l'historique complet), le module
s'est arrêté sur un seul champ natif : **`date_deadline`**.

Confirmé dans les sources cœur (`project/models/project_task.py`, branche
19.0) : `date_deadline = fields.Datetime(...)` est un champ **Community**
natif, **toujours présent**, avec précision heure. Aucun risque d'échec à
l'installation ni à l'exécution, sur aucune instance.

⚠️ **Compromis assumé** : une tâche a aussi un champ `planned_date_begin`
(ajouté par un module Gantt type `project_enterprise`, pas garanti présent)
qui, combiné à `date_deadline`, permet d'afficher une tâche comme une
**barre** avec une durée visible dans le Gantt. Ce module n'écrit **plus**
sur `planned_date_begin` — décision explicite, pour ne dépendre d'aucun
champ dont la présence varie selon l'instance. Conséquence : chaque tâche
s'affiche dans le Gantt comme un **point** (sa `date_deadline`), pas une
barre représentant sa durée calculée. Si la visualisation de durée devient
importante, il faudra réintroduire `planned_date_begin` (et son garde-fou
de présence) — cf. §6 v4 pour le code déjà écrit à cet effet.

## 1. Ce que fait la maquette

Un wizard, lancé depuis la fiche projet (bouton en en-tête — cf. §4), prend
**deux entrées seulement** :

- **Date de réception prévue** (`expected_reception_date`, date + heure)
- **Nombre de pièces prévues** (`expected_qty`)

Et génère, en un clic (dates = `date_deadline` de chaque tâche, cf. §0 — le
"début" ci-dessous n'est qu'un repère de calcul interne, non stocké) :

| Tâche | Dépend de | Début (calcul interne) | Fin (`date_deadline`) |
|---|---|---|---|
| **A** | — | date de réception prévue | début + (qty × 10 min) |
| **B** | A (« blocked by ») | lendemain de la fin de A, 9h00 | début + 48h |
| **C** | B (« blocked by ») | lendemain de la fin de B, 9h00 | début + 24h + (qty × 10 min) |

Et 2 jalons (`project.milestone`, natif Community — cf. §2) :

| Jalon | Échéance |
|---|---|
| **Jalon 1** | date de fin de la tâche A |
| **Deadline** | fin de la tâche C + 48h |

✅ **Interprétations confirmées côté client** — l'énoncé initial ne précisait
pas tout littéralement, deux points ont été tranchés :

- « Date de fin = Date de début **×** (qty × 10 min) » n'avait pas de sens
  arithmétique sur une date tel quel. Confirmé : une **addition** (début +
  durée) — `piece_duration = timedelta(minutes=qty × MINUTES_PER_PIECE)`.
- « Lendemain de la date de fin » : confirmé comme **le jour calendaire
  suivant, à 9h00 fixe** (pas la même heure que la fin de la tâche
  précédente, pas minuit) — `_next_day_at()` /
  `NEXT_DAY_START_TIME = time(9, 0)`.
- 10 minutes/pièce est **en dur** dans le wizard (`MINUTES_PER_PIECE`,
  [wizard/project_planning_generate_wizard.py](wizard/project_planning_generate_wizard.py)) — plus de
  paramètre système ni de champ configurable (l'ancien `x_unit_time_minutes`
  et le paramètre `planning.default_unit_time_minutes` ont été retirés,
  devenus sans usage dans cette version).
- **Aucun calendrier ouvré** n'est appliqué (contrairement à la version
  précédente, qui passait par `resource.calendar.plan_hours()`) : tous les
  décalages sont des durées calendaires brutes (`timedelta`). Un week-end
  n'est jamais sauté.

## 2. Modèle de données

### 2.1 `project.task` ([models/project_task.py](models/project_task.py))

| Champ | Type | Détail |
|---|---|---|
| `x_actual_end_date` | Date | Saisie manuelle admin, aucun lien avec un OF. |
| `x_deviation_days` | Float, computed, stored | = date réelle − `date_deadline` (natif), en jours. |

Champs natifs réutilisés tels quels : `date_deadline` (planification,
Community, toujours présent — cf. §0), `depend_on_ids` (dépendances,
Community depuis Odoo 17), `project_id`.

`x_deviation_days` dépend directement de `date_deadline` dans son
`@api.depends` — safe, puisque c'est un champ Community garanti, aucun
contournement nécessaire.

⚠️ Comme précédemment, `x_deviation_days` vaut `0.0` (pas "vide") quand
non calculable — un `Float` standard ne distingue pas 0 de "non renseigné".

### 2.2 `project.milestone` — natif, pas d'extension

**Vérifié dans les sources** (`addons/project/models/project_milestone.py`,
branche 19.0) : `project.milestone` est **natif Community**, pas Enterprise
— aucun risque de reproduire le problème du §0. Champs utilisés tels quels :
`name`, `project_id`, `deadline` (type **Date**, pas Datetime — les jalons
n'ont pas d'heure, seulement `.date()` de la valeur calculée est stocké).

`project.project.allow_milestones` doit être actif pour que les jalons
soient visibles/utilisables (même mécanique que `allow_task_dependencies`
pour les dépendances) — le wizard l'active automatiquement si besoin.

Les jalons créés ne sont **pas** liés à une tâche via `task_ids`/
`milestone_id` (pas demandé) — ce sont des jalons de projet autonomes, avec
juste le bon nom et la bonne échéance.

## 3. Wizard (`project.planning.generate.wizard`)

### 3.1 Champs

Seulement `project_id` (caché, `default` = `active_id`), `expected_reception_date`,
`expected_qty`. Tous les autres champs des versions précédentes (bumping,
températures, rendements) ont été **supprimés**, pas juste masqués.

### 3.2 Aucun garde-fou

Ni sur la présence d'un champ (plus nécessaire, `date_deadline` est garanti —
cf. §0), ni sur l'idempotence (retiré sur demande, avec le champ
`x_generated_by_wizard` qui le portait, supprimé). Le wizard génère
systématiquement 3 nouvelles tâches + 2 nouveaux jalons à chaque clic, sans
rien vérifier ni supprimer. Relancer plusieurs fois sur le même projet
**empile** les tâches/jalons plutôt que de les remplacer.

### 3.3 Action de retour

Vue Gantt si `project_enterprise` est installé (détection dynamique via
`ir.module.module`, pas supposée), sinon liste — même mécanique que dans la
version initiale du prototype.

## 4. Vues

- [views/project_task_views.xml](views/project_task_views.xml) : nouvelle page « Planification
  prévisionnelle » sur le formulaire tâche (suivi réel uniquement).
  `date_deadline` n'est pas repris : déjà natif au formulaire tâche cœur,
  rien à ajouter côté ce module. `depend_on_ids` et les jalons non plus :
  déjà natifs (page « Blocked By » / onglet Jalons), visibles dès que
  `allow_task_dependencies`/`allow_milestones` sont actifs sur le projet
  (posés par le wizard).
- [views/project_project_views.xml](views/project_project_views.xml) : bouton d'accès au wizard sur
  l'en-tête du formulaire **projet** (`project.edit_project`) — **pas**
  visible en cliquant sur la carte du projet depuis le tableau de bord
  (qui ouvre ses tâches) ; utiliser le menu ⋮/engrenage de la carte →
  « Modifier » pour atteindre le vrai formulaire projet.
- [wizard/project_planning_generate_wizard_views.xml](wizard/project_planning_generate_wizard_views.xml) : formulaire du wizard (2 champs) + action.

⚠️ **Piège d'ordre de chargement, déjà rencontré et corrigé** :
`project_project_views.xml` référence l'action du wizard via
`%(...)d` — les fichiers XML se chargent dans l'ordre exact de la liste
`data` du manifeste ; le fichier définissant l'action doit être chargé
**avant** celui qui la référence, sous peine d'échec à l'installation
(`ValueError: External ID not found in the system`).

## 5. Hors périmètre (inchangé)

Aucun lien, aucune dépendance, à un modèle `mrp.*`/`stock.*` existant.
Déclenchement exclusivement manuel via le wizard. Pas de données de démo
dans ce module.

## 6. Historique des versions de ce module

- **v1 (abandonnée)** : catalogue de flow complet (Wafer Foundry → ... →
  End Of Line), rendements par étape saisis dans le wizard, distinction
  durée fixe/proportionnelle, temps unitaire paramétrable,
  `resource.calendar.plan_hours()` pour le temps ouvré. Écrivait déjà sur
  les champs natifs `planned_date_begin`/`planned_date_end`.
- **v2 (abandonnée)** : maquette simplifiée (3 tâches à règles de date
  fixes, 2 jalons), mais avec des champs de date **propres au module**
  (`x_planned_date_begin`/`x_planned_date_end`) pour contourner le problème
  du §0 — écarté : ça empêchait tout affichage dans le Gantt Enterprise, qui
  est précisément l'objectif de la maquette.
- **v3 (abandonnée)** : retour sur des champs natifs, mais toujours
  `planned_date_begin`/`planned_date_end` — le wizard échouait proprement
  (message explicite) faute de `planned_date_end`, sans résoudre le fond.
- **v4** : **bon couple de champs identifié** — `planned_date_begin` (début)
  + `date_deadline` (fin), pas `planned_date_end`. Découvert en observant le
  comportement réel de l'UI (bouton "Toggle date range mode" sur le champ
  *Deadline* de la tâche). `date_deadline` est Community natif, toujours
  présent ; `planned_date_begin` reste le seul champ dont la présence est
  vérifiée avant génération. Cf. §0.
- **v5** : garde-fou d'idempotence retiré sur demande (§3.2) — le wizard
  régénère systématiquement 3 tâches + 2 jalons à chaque clic, sans bloquer
  ni nettoyer une planification déjà existante sur le projet. Le champ
  `x_generated_by_wizard` qui le portait était laissé en place, réduit à un
  simple marqueur indicatif.
- **v6** : `x_generated_by_wizard` supprimé entièrement (champ, vue, création
  dans le wizard) — devenu sans usage une fois le garde-fou retiré (v5).
- **v7** : `planned_date_begin` abandonné à son tour, sur demande
  — ne reste que `date_deadline` (garanti partout, plus de garde-fou de
  présence du tout). Compromis assumé : les tâches s'affichent comme des
  points dans le Gantt, pas des barres avec une durée visible. Champs du
  wizard renommés en cohérence avec l'usage réel (`expected_reception_date`,
  `expected_qty`).
- **v8 (actuelle)** : assignation automatique d'un tag par le wizard essayée
  puis **retirée sur demande** — les tags restent à la discrétion de
  l'utilisateur, saisis manuellement sur chaque tâche. Point vérifié au
  passage et qui reste vrai : `tag_ids` est déjà affiché nativement sur la
  carte Kanban standard des tâches (`project.view_task_kanban`, celle du
  tableau de bord du projet, confirmé dans les sources cœur) — rien à
  ajouter côté vue pour ce module, quelle que soit la façon dont les tags
  sont renseignés.
