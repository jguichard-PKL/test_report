# synergie_project_planning — Planification prévisionnelle (Maquette)

**Statut : MAQUETTE TECHNIQUE.** Démonstration très simple, pas un livrable
de production. Cadrage initial dans `Spec_Technique_Prototype_ClaudeCode.md`
(dans `Documents/Spécifications/`) — **cette version s'en écarte
volontairement** : le catalogue de flow (Wafer Foundry, Bumping, Wafer
Test...), les rendements et la distinction durée fixe/proportionnelle ont
été **abandonnés sur demande**, au profit de 3 tâches à règles de date
fixes et 2 jalons. Voir §1 pour le détail du changement de cap.

Cible : **Odoo 19**.

---

## 0. Champs natifs Gantt : le bon couple identifié

**L'intérêt de cette maquette est d'utiliser le Gantt natif — décision du
client, confirmée explicitement.** Le wizard écrit sur des champs natifs
`project.task`, **pas** sur des champs propres au module (une version
intermédiaire l'avait fait pour contourner l'incertitude ci-dessous — revenue
en arrière sur demande).

✅ **Résolu** : le couple de champs réellement utilisé par Odoo pour une
tâche est **`planned_date_begin`** (début) et **`date_deadline`** (fin) —
**pas** `planned_date_end`, sur lequel deux versions précédentes de ce
module s'étaient braquées à tort. Découvert en observant le comportement
réel de l'UI : sur le champ *Deadline* d'une tâche, un bouton *"Toggle date
range mode"* permet de basculer vers la saisie d'un couple début/fin — ce
qui n'a de sens que si *Deadline* (`date_deadline`) **est** le champ de fin
utilisé en mode plage, avec `planned_date_begin` comme pendant "début".

Confirmé dans les sources cœur (`project/models/project_task.py`, branche
19.0) : `date_deadline = fields.Datetime(...)` est un champ **Community**
natif, toujours présent, avec précision heure (ce qu'il fallait pour nos
calculs en minutes). `planned_date_begin`, lui, reste ajouté par un module
Gantt (`project_enterprise` ou équivalent) — pas garanti présent partout,
mais visiblement actif sur l'instance cible (l'UI le confirme).

`planned_date_end` n'a jamais été le bon champ — les deux versions
précédentes de ce module poursuivaient une fausse piste (documentée par
prudence à l'§6, pour ne pas perdre cette leçon).

Le wizard vérifie toujours que `planned_date_begin` existe avant de générer
quoi que ce soit (`UserError` explicite sinon) — mais plus `planned_date_end`,
qui n'est simplement pas utilisé.

## 1. Ce que fait la maquette

Un wizard, lancé depuis la fiche projet (bouton en en-tête — cf. §4), prend
**deux entrées seulement** :

- **Quantité à réceptionner** (`input_qty`)
- **Date de début de projet** (`start_datetime`, date + heure)

Et génère, en un clic :

| Tâche | Dépend de | Début | Fin |
|---|---|---|---|
| **A** | — | `start_datetime` | début + (qty × 10 min) |
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

Champs natifs réutilisés tels quels : `planned_date_begin` (début, Gantt —
présence non garantie mais confirmée active sur l'instance cible),
`date_deadline` (fin, Community, toujours présent — cf. §0),
`depend_on_ids` (dépendances, Community depuis Odoo 17), `project_id`.

`x_deviation_days` dépend directement de `date_deadline` dans son
`@api.depends` — safe, puisque c'est un champ Community garanti. Pas besoin
du contournement (lecture dynamique via `_fields`) qu'aurait nécessité
`planned_date_begin` si on en avait eu besoin dans ce compute.

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

Seulement `project_id` (caché, `default` = `active_id`), `start_datetime`,
`input_qty`. Tous les autres champs de la version précédente (bumping,
températures, rendements) ont été **supprimés**, pas juste masqués.

### 3.2 Garde-fou

**`planned_date_begin` présent ?** (§0) — `UserError` explicite si absent,
**avant** toute création de tâche. `date_deadline` n'a pas besoin d'être
vérifié : c'est un champ Community, toujours présent.

⚠️ **Garde-fou d'idempotence retiré sur demande** (y compris le champ
`x_generated_by_wizard` qui le portait, supprimé) : le wizard ne bloque plus
si une planification existe déjà pour le projet — il génère systématiquement
3 nouvelles tâches + 2 nouveaux jalons à chaque clic, sans vérifier ni
supprimer ce qui existe déjà. Relancer plusieurs fois sur le même projet
**empile** les tâches/jalons plutôt que de les remplacer.

### 3.3 Action de retour

Vue Gantt si `project_enterprise` est installé (détection dynamique via
`ir.module.module`, pas supposée), sinon liste — même mécanique que dans la
version initiale du prototype.

## 4. Vues

- [views/project_task_views.xml](views/project_task_views.xml) : nouvelle page « Planification
  prévisionnelle » sur le formulaire tâche (suivi réel uniquement).
  **Ne référence jamais `planned_date_begin`** (§0) : le citer dans une vue
  XML casserait l'installation si absent — quand il est disponible, la vue
  Gantt Enterprise l'affiche déjà (avec `date_deadline`, déjà natif au
  formulaire tâche cœur), rien à ajouter côté ce module. `depend_on_ids` et
  les jalons ne sont pas repris non plus : déjà natifs (page « Blocked By »
  / onglet Jalons), visibles dès que `allow_task_dependencies`/
  `allow_milestones` sont actifs sur le projet (posés par le wizard).
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
- **v6 (actuelle)** : `x_generated_by_wizard` supprimé entièrement (champ,
  vue, création dans le wizard) — devenu sans usage une fois le garde-fou
  retiré (v5).
