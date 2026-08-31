# synergie_project_planning — Planification prévisionnelle (Maquette)

**Statut : MAQUETTE TECHNIQUE.** Démonstration très simple, pas un livrable
de production. 


---

## 0. Champs de date : `planned_date_begin` + `date_deadline`

**L'intérêt de cette maquette est d'utiliser le Gantt — décision du client.**
Après plusieurs itérations (cf. §6 pour l'historique complet), le module
pose **les deux champs** sur chaque tâche : `planned_date_begin` (début) et
`date_deadline` (fin).

## 1. Ce que fait la maquette

Un wizard, lancé depuis la fiche projet (bouton en en-tête) avec
**deux entrées en saisie** :

- **Date de réception prévue** (`expected_reception_date`, date + heure)
- **Nombre de pièces prévues** (`expected_qty`)

Et génère, en un clic (début = `planned_date_begin`, fin = `date_deadline`,
cf. §0) :

| Tâche | Dépend de | Début (`planned_date_begin`) | Fin (`date_deadline`) |
|---|---|---|---|
| **A** | — | date de réception prévue | début + (qty × 10 min) |
| **B** | A (« blocked by ») | lendemain de la fin de A, 9h00 | début + 48h |
| **C** | B (« blocked by ») | lendemain de la fin de B, 9h00 | début + 24h + (qty × 10 min) |

Et 2 jalons (`project.milestone`, natif Community — cf. §2) :

| Jalon | Échéance | Lié à |
|---|---|---|
| **Jalon 1** | date de fin de la tâche A | Tâche B (`milestone_id`) |
| **Deadline** | fin de la tâche C + 48h | — |


## 2. Wizard (`project.planning.generate.wizard`)

### 3.1 Champs

Seulement `project_id` (caché, `default` = `active_id`), `expected_reception_date`,
`expected_qty`. A voir pour ajouter d'autres paramétres pour affiner le configurateur





