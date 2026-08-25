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

## 5. Réservation restreinte au projet

Au-delà du tamponnage (§2-4), la **réservation automatique** de stock
(`_action_assign`, déclenchée à la confirmation d'un mouvement ou via
« Vérifier la disponibilité ») est elle aussi contrainte par projet : un
mouvement portant un `project_id` ne peut réserver que des lots du **même**
projet.

Mécanique (suit l'idiome déjà utilisé par le cœur pour `with_expiration`) :

1. `stock.move._update_reserved_quantity()` — le point appelé par
   `_action_assign()` pour réserver un mouvement MTS (sans `move_orig_ids`) —
   pose un contexte `restrict_project_id` égal au `project_id` du mouvement
   avant de déléguer au cœur. Sans projet sur le mouvement, comportement
   Odoo standard, aucun filtre.
2. `stock.quant._get_gather_domain()` — LE point où le cœur construit le
   domaine de recherche des quants candidats (dont `_gather`,
   `_get_available_quantity`, `_get_reserve_quantity` découlent tous) — lit ce
   contexte et ajoute `lot_id.project_id = restrict_project_id` au domaine.

Si aucun quant ne correspond au projet, la réservation prend 0, comme un
stockout standard Odoo (le mouvement reste `confirmed`/`waiting` ou passe
`partially_available`) : **pas d'erreur, jamais de réservation d'un lot hors
projet**.

**Hors périmètre** : le chemin MTO (mouvement chaîné, `move_orig_ids`
renseigné) réutilise les lots déjà réservés par le mouvement amont sans
nouvelle recherche de quants — aucun trou tant que ce mouvement amont porte
lui-même le bon projet (cas normal, le projet est porté de bout en bout par
la chaîne).

### 5.1 Sélection manuelle d'un quant (widget « Pick From »)

La réservation automatique (`_action_assign`) n'est pas le seul chemin pour
choisir un lot : le champ `quant_id` (widget `pick_from`) sur
`stock.move.line` permet à un utilisateur de choisir **manuellement** un
quant précis (opérations détaillées, ligne du formulaire de mouvement). Ce
sélecteur **ne passe pas** par `_action_assign` / `_get_gather_domain` — il
interroge `stock.quant` via un domaine posé en dur dans deux vues cœur
(`stock.view_stock_move_line_operation_tree` et
`stock.view_stock_move_line_detailed_operation_tree`), filtré uniquement par
produit et emplacement. **Sans correctif, ce sélecteur listait des lots de
tous les projets**, contournant entièrement la restriction du §5.

Corrigé par héritage de ces deux vues
([stock_move_line_views.xml](views/stock_move_line_views.xml)) : le domaine
du champ `quant_id` est complété avec `lot_id.project_id = <projet du
mouvement>` quand le mouvement (ou la ligne, selon la vue) porte un projet.
Sans projet sur le mouvement, aucune restriction (comportement standard
conservé).

**Reste hors périmètre** : la saisie manuelle d'un **numéro de lot en texte
libre** (champ `lot_name`, utilisé en réception quand le lot n'existe pas
encore) n'est par nature liée à aucun quant existant — rien à filtrer.

## 6. Périmètre couvert / non couvert

| Flux | Couvert ? | Détail |
|------|-----------|--------|
| OF — produit fini | ✅ | `production_id.project_id` → mouvement → lot |
| OF — sous-produits | ✅ | mouvements finis à `production_id`, même OF |
| OF — fails (sous-produits lot-trackés) | ✅ | idem sous-produits |
| Lot déjà rattaché à un projet | ✅ | **jamais écrasé** |
| Filtre / group_by par projet | ✅ | lots, mouvements, transferts, **stock disponible** |
| Réception (entrée de stock) | ✅ | projet saisi sur le transfert (`stock.picking`) → mouvement → lot |
| Réservation automatique par projet | ✅ | `_action_assign` (MTS) ne réserve que des lots du même projet |
| Sélection manuelle d'un quant (widget « Pick From ») | ✅ | domaine du champ `quant_id` complété par projet (§5.1) |
| Réservation MTO (mouvement chaîné) | ➖ hors périmètre | hérite du filtrage du mouvement amont, pas de re-filtrage |
| Saisie d'un lot en texte libre (`lot_name`) | ➖ hors périmètre | pas de quant existant à filtrer (création de lot en réception) |
| Composants consommés | ➖ hors périmètre | volontairement non traités |

## 7. Lien avec `synergie_mrp_performance`

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
- existence et signature de `stock.quant._get_gather_domain()` et de
  `stock.move._update_reserved_quantity()` (mécanique de réservation, §5) ;
- identifiants et structure de `stock.view_stock_move_line_operation_tree` et
  `stock.view_stock_move_line_detailed_operation_tree`, présence du champ
  `quant_id` (widget `pick_from`) et de ses variables de domaine
  (`parent.location_id`, `picking_location_id`) — cf. §5.1 ;
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
