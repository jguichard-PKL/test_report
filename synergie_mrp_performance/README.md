# Synergie - Suivi de rendement MRP (`synergie_mrp_performance`)

Module Odoo 19 Enterprise de suivi du **rendement (first-pass yield)** des ordres de
fabrication, pensé pour un flux d'industrialisation ASIC backend
(wafer → bumping → wafer test → assembly → final test → retest → EOL → finished goods).

Chaque étape est un OF (`mrp.production`). Les pièces **non conformes (« fails »)** ne sont
**jamais mises au rebut** : elles sont modélisées comme un **article dédié sorti en
sous-produit (by-product)** de la nomenclature, restant en stock, lot-tracké et expédiable.

## Dépendances

- `mrp`
- `stock`

> Volontairement minimal : on n'utilise ni `quality` ni `mrp_account`. La quantité de fail
> se lit directement sur les mouvements de sortie de l'OF (`move_finished_ids`).

## Installation sur Odoo.sh

1. Placer le dossier `synergie_mrp_performance/` dans un répertoire d'addons suivi par votre
   dépôt Odoo.sh (ex. racine du repo ou `addons/`).
2. `git add synergie_mrp_performance && git commit && git push` sur la branche cible.
3. Odoo.sh reconstruit ; installer le module depuis **Apps** (mettre à jour la liste des
   applications si besoin) ou via mise à jour de la base sur la branche.

## Description fonctionnelle

### Marquer un article comme fail / retest

Sur la fiche article (`product.template`), champ **« Type de sortie de production »**
(`pkl_output_type`) :

- **Conforme** (`good`, défaut) : pièce bonne, typiquement le produit principal de l'OF.
- **Fail** (`fail`) : pièce non conforme conservée en stock.
- **Retest** (`retest`) : pièce à repasser en test.

Créez un article fail dédié par étape concernée et ajoutez-le en **sous-produit** dans la
nomenclature de l'étape. La quantité fail est alors lue automatiquement.

### Indicateurs par OF (`mrp.production`, onglet « Rendement »)

Champs calculés **stockés** (filtrables / groupables / pivot) :

| Champ | Sens |
|---|---|
| `pkl_qty_good` | Qté du produit principal produite (mouvements `done`) |
| `pkl_qty_fail` | Σ sous-produits `pkl_output_type='fail'` |
| `pkl_qty_retest` | Σ sous-produits `pkl_output_type='retest'` |
| `pkl_qty_output` | good + fail + retest (total testé) |
| `pkl_fpy` | first-pass yield = good / output |
| `pkl_fail_rate` | fail / output |
| `pkl_retest_rate` | retest / output |

Regroupements disponibles : **projet** (`project_id`), **étape** (`product_id`), période,
état, **origine** et **groupe d'approvisionnement** (pour agréger les OF splittés / backorders
OF-1/-2/-3).

### Reporting agrégé multi-OF

Menu **Fabrication > Rapports > Rendement de fabrication** : modèle SQL
`pkl.mrp.yield.report` (vues pivot / graph / liste), axes par défaut **projet × étape ×
période**.

Deux familles de mesures, basculables via le menu **Mesures** du pivot :

- **Vue valeur** : `qty_good`, `qty_fail`, `qty_retest`, `qty_output` (quantités, additionnables).
- **Vue %** : `fpy`, `fail_rate`, `retest_rate`, exprimées en **%** (0–100).

Les taux ne sont pas une moyenne de pourcentages : `_read_group` / `_read_grouping_sets` les recalcule comme
**ratio de sommes** (`100 × Σnum / Σden`) au niveau d'agrégation affiché, donc le rendement
reste correct quel que soit le regroupement.

## Hypothèses & arbitrages

### 1. Détection du retest : par article (retenu) vs préfixe de lot

La détection est faite **par article** (`pkl_output_type`), plus simple et fiable que le
parsing de lot. La logique est **isolée** dans `MrpProduction._pkl_classify_move()` : pour
basculer sur une détection **par préfixe de lot** (ex. lots `RT...`), surcharger uniquement
cette méthode et inspecter `move.move_line_ids.lot_id.name`. Le calcul et les dépendances
restent inchangés, et **la numérotation de lot n'est jamais modifiée — seulement lue**.

### 2. Reporting : champs stockés **+** vue SQL dédiée (les deux)

- Champs calculés stockés sur l'OF → form / liste / pivot rapides sur les quantités.
- Vue SQL `pkl.mrp.yield.report` → **rendement agrégé correct**.

Raison : **un pourcentage ne s'additionne pas**. En pivot, on n'affiche donc **que des
quantités** comme mesures ; le rendement d'un groupe se lit `Σ(qty_good) / Σ(qty_output)`.
Le champ `fpy` du rapport est marqué `aggregator=False` (valable uniquement par ligne/OF)
pour interdire toute moyenne trompeuse.

### 3. Unité du rendement et changement d'UoM

- **Unité** : sur l'OF (`mrp.production`), les ratios (`pkl_fpy`, `pkl_fail_rate`,
  `pkl_retest_rate`) sont stockés en **ratio 0–1** et affichés en **%** via
  `widget="percentage"`. Dans le rapport (`pkl.mrp.yield.report`), les taux sont en
  **points de % (0–100)** car le pivot n'applique pas le widget percentage ; l'agrégation
  correcte (ratio de sommes) est assurée par `_read_group` / `_read_grouping_sets`.
- **UoM** : l'UoM peut changer entre l'**entrée** et la **sortie** d'une étape (wafers →
  dies, ratio variable). Les rendements sont donc calculés **uniquement sur les quantités de
  sortie** (good / fail / retest), homogènes entre elles. Aucun rendement « vs quantité
  d'entrée consommée » n'est fourni par défaut (il nécessiterait une conversion d'UoM
  explicite) ; c'est une extension optionnelle possible.

## Limites connues

- **Rendement après retest = V2.** Un RT peut revenir conforme dans un OF aval : c'est un
  indicateur **inter-OF**, non calculable de façon fiable sur un OF isolé. Il n'est donc pas
  exposé au niveau OF. Les quantités good/fail/retest sont agrégées par étape/projet pour
  permettre sa dérivation ; le calcul exact nécessite la **généalogie de lot** (V2).
- Le champ **`project_id`** de `mrp.production` est supposé présent dans votre installation
  (décision métier). S'il provient d'un module additionnel, ajoutez-le à `depends`.
- Le module ne crée **aucun scrap** et ne touche **pas** à la numérotation de lot.

## Tests

`tests/test_yield.py` : valide le FPY d'un OF avec sous-produit fail (90 good + 10 fail →
FPY 0,90) et le garde-fou division par zéro.

```bash
odoo -d <db> -i synergie_mrp_performance --test-enable --stop-after-init
```
