# synergie_stock_project — Dimension projet sur le stock

Introduit une **dimension projet transverse au stock** : le code projet de la
transaction source (ordre de fabrication, réception) est porté par le mouvement
de stock, propagé au lot à la validation, puis exposé sur le stock disponible
pour filtrer et grouper par projet.

Cible : **Odoo 19 Enterprise**. Code et identifiants en anglais.

---

## 1. Pourquoi « Spécifique » (et pas Standard / Studio)

Classification Peaklane : **Spécifique**.

- Aucun champ projet natif sur `stock.lot`, `stock.move` ou `stock.quant`.
- Aucune propagation native du projet de l'OF vers le lot produit.
- Studio (no-code) ne sait pas **mettre à jour un enregistrement lié**
  (écrire `lot.project_id` depuis le mouvement à la validation) ni implémenter
  le compute conditionnel sur `stock.move`.

Le besoin nécessite donc du code : un champ calculé sur le mouvement et une
surcharge de la validation des lignes de mouvement.

## 2. Décision d'architecture

1. **Le projet est porté par `stock.move`** (`project_id`), dénominateur commun
   de toutes les transactions de stock. Champ calculé (`_compute_project_id`)
   `store=True, readonly=False` : auto-renseigné mais modifiable manuellement.
   - Mouvement de **sortie d'un OF** (`production_id`) → `production_id.project_id`.
   - **Réception** (`picking_type_id.code == 'incoming'`) → hook
     `_get_reception_project()` → `picking_id.project_id` (cf. §4).
   - Sinon → la valeur courante est conservée (saisie manuelle possible),
     jamais forcée à `False`.
   - Les **composants consommés** (`raw_material_production_id`) ne sont
     **volontairement pas** traités : ils ne doivent pas re-tamponner des lots
     existants.

2. **Propagation vers `stock.lot`** dans `stock.move._action_done()` :
   après `super()`, pour chaque mouvement validé avec un `project_id` renseigné,
   on parcourt ses `move_line_ids` et on écrit le projet sur tout `lot_id`
   **encore vide**.
   - **Jamais d'écrasement** d'un projet déjà posé.
   - Couvre d'un coup le **lot fini**, les **sous-produits** et les **fails**
     du même OF (tous portés par des mouvements à `project_id` renseigné).
   - ⚠️ **Écart assumé par rapport au handoff** : la spec demandait de
     surcharger `stock.move.line._action_done()`. Cette méthode n'est pas un
     point d'extension appelé en v19 (la surcharge y serait du **code mort**,
     d'où un lot jamais tamponné). Le hook canonique de validation est
     `stock.move._action_done()` ; c'est là qu'on opère.

3. **`stock.quant.project_id`** : `related='lot_id.project_id'`, **stocké**
   (`store=True`), indexé. Permet de filtrer / grouper le **stock disponible**
   par projet sans jointure coûteuse.
   - ⚠️ Les quants sont créés **pendant** `_action_done`, donc **avant** que le
     lot ne porte son projet : le related est alors stocké à `False` et la
     recompute automatique peut les manquer. `stock.move._action_done()` **force**
     donc la recompute des quants des lots fraîchement tamponnés
     (`quants.modified(['lot_id'])`).

Tous les `project_id` sont **indexés** (filtres / group_by fréquents).

## 3. Hypothèse : lot mono-projet

Dans ce modèle, un lot **ne vit que sur un seul projet**. Cette hypothèse
justifie :

- la règle **« première écriture suffit »** (le lot prend le projet du premier
  mouvement validé qui le porte) ;
- l'**absence d'arbitrage** : aucun besoin de réconcilier plusieurs projets
  concurrents sur un même lot, donc le garde-fou « ne pas écraser » est
  suffisant et sûr.

## 4. Source projet en RÉCEPTION (tranchée)

Pour les flux **OF**, la source est le document OF (`mrp.production.project_id`).
Pour les **réceptions** (entrée de wafer, rowlines OSAT, achats), la source a été
**tranchée côté Synergie : le projet est SAISI sur le transfert**
(`stock.picking.project_id`) — miroir exact du modèle OF (projet porté par le
document).

Mécanique :
- Champ `project_id` ajouté sur `stock.picking`, saisi sur le bon de réception.
- Le hook `stock.move._get_reception_project()` renvoie `picking_id.project_id`.
- Le compute de `stock.move.project_id` dépend de `picking_id.project_id` : le
  mouvement se met à jour dès que le projet est posé/modifié sur le transfert.
- À la validation, le projet est propagé au(x) lot(s) reçu(s) (mécanique §2.2).

Aucune dépendance `purchase_stock` requise : marche aussi pour les réceptions
**sans commande d'achat** (retours OSAT, etc.).

Le hook reste **surchargeable** : brancher une autre source (commande d'achat…)
se fait en redéfinissant `_get_reception_project()`, sans toucher au compute.

## 5. Périmètre couvert / non couvert

| Flux | Couvert ? | Détail |
|------|-----------|--------|
| OF — produit fini | ✅ | `production_id.project_id` → mouvement → lot |
| OF — sous-produits | ✅ | mouvements finis à `production_id`, même OF |
| OF — fails (sous-produits lot-trackés) | ✅ | idem sous-produits |
| Lot déjà rattaché à un projet | ✅ | **jamais écrasé** |
| Filtre / group_by par projet | ✅ | lots, mouvements, transferts, **stock disponible** |
| Réception (entrée de stock) | ✅ | projet saisi sur le transfert (`stock.picking`) → mouvement → lot |
| Composants consommés | ➖ hors périmètre | volontairement non traités |

## 6. Lien avec `synergie_mrp_performance`

`synergie_mrp_performance` fournit le **rendement (FPY)** par OF et un reporting
agrégé ; il s'appuie sur `mrp.production.project_id` pour grouper par projet.

Ce module-ci fournit la **dimension `project_id` sur le stock** (mouvement, lot,
stock disponible), en aval de l'OF. Les deux sont complémentaires mais
**indépendants** :

- `synergie_mrp_performance` raisonne sur les **quantités produites** (rendement) ;
- `synergie_stock_project` raisonne sur la **traçabilité** (où vit le stock, sur
  quel projet).

**Choix retenu : modules séparés.** Les responsabilités, les dépendances et les
cycles de vie diffèrent (la dimension stock peut servir d'autres flux que le
rendement). Une fusion reste possible si Synergie veut un module « projet »
unique ; ce serait alors un simple regroupement de fichiers, sans changement de
logique.

---

## Notes de compatibilité v19

Plusieurs points d'API sont marqués `# [À vérifier v19]` dans le code :
- signature et valeur de retour de `stock.move._action_done()` ;
- présence de `production_id` vs `raw_material_production_id` sur `stock.move` ;
- valeur `picking_type_id.code == 'incoming'` pour détecter une réception ;
- identifiants externes des vues héritées (`stock.view_production_lot_form`,
  `stock.view_picking_form`, `stock.view_picking_internal_search`, etc.) et
  l'ancre `origin` sur le formulaire de transfert.

⚠️ **Prérequis critique non garanti par le module** : `mrp.production.project_id`.
Ce champ n'est **pas natif** dans Odoo (ni Community ni Enterprise). Le module
le **suppose présent** (fourni par `synergie_mrp_performance` ou un autre module
de votre installation), exactement comme `synergie_mrp_performance` lui-même. Si
le champ est absent, le module **ne s'installe pas** (`@api.depends` sur un champ
inexistant). À confirmer sur l'instance cible.

À valider sur l'instance cible avant mise en production.
