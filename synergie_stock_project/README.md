# synergie_stock_project — Dimension projet sur le stock

Introduit une **dimension projet à tout le stock** : le projet de la
transaction source (OF, Réception) est porté par le mouvement
de stock. Il est propagé au lot à la validation, puis sur le stock disponible
pour pouvoir filtrer et grouper par projet.

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
   - Mouvement de **consommation de composants** (`raw_material_production_id`)
     → `raw_material_production_id.project_id` — **uniquement pour restreindre
     sa réservation**  
   - **Transfert portant un projet** (`picking_id.project_id`, tout type —
     réception, livraison, interne) → hook `_get_picking_project()` →
     `picking_id.project_id` (cf. §4).
   - **Mouvement amont sans signal direct** (`move_dest_ids.project_id`) →
     hérite du projet déjà déterminé sur son mouvement **aval**
   - Sinon → la valeur courante est conservée (saisie manuelle possible),
     jamais forcée à `False`.

2. **Propagation vers `stock.lot`** dans `stock.move._action_done()` :
   après `super()`, pour chaque mouvement validé avec un `project_id` renseigné
   - **Jamais d'écrasement** d'un projet déjà posé.
   - Couvre d'un coup le **lot fini**, les **sous-produits** et les **fails**
     du même OF (tous portés par des mouvements à `project_id` renseigné).


3. **`stock.quant.project_id`** : `related='lot_id.project_id'`, **stocké**
   (`store=True`), indexé. Permet de filtrer / grouper le **stock disponible**
   par projet sans jointure coûteuse.

Tous les `project_id` sont **indexés** (filtres / group_by fréquents).

## 3. Hypothèse : lot mono-projet

Dans ce modèle, un lot **ne vit que sur un seul projet**. 

- Le lot prend le projet du premier mouvement validé qui le porte
- Aucun besoin de réconcilier plusieurs projets concurrents sur un même lot.

## 4. Source projet portée par le TRANSFERT (réception, livraison, interne)

Pour les flux **OF**, la source est le document OF (`mrp.production.project_id`).
Pour **tout transfert** (réception, livraison, transfert interne), la source
est le projet est SAISI sur le transfert
(`stock.picking.project_id`) — miroir exact du modèle OF (projet porté par le
document).

Mécanique :
- Champ `project_id` ajouté sur `stock.picking`, saisi sur le transfert (tout
  type).
- Le hook `stock.move._get_picking_project()` renvoie `picking_id.project_id`.
- Le compute de `stock.move.project_id` dépend de `picking_id.project_id` : le
  mouvement se met à jour dès que le projet est posé/modifié sur le transfert.


Aucune dépendance `purchase_stock` requise : marche aussi pour les réceptions
**sans commande d'achat** (retours, etc.).

## 5. Réservation restreinte au projet
La **réservation automatique** de stock (`_action_assign`, 
déclenchée à la confirmation d'un mouvement ou via
« Vérifier la disponibilité ») est elle aussi contrainte par projet : un
mouvement portant un `project_id` ne peut réserver que des lots du **même**
projet.

Mécanique :

1. `stock.move._update_reserved_quantity()` — le point appelé par
   `_action_assign()` pour réserver un mouvement MTS (sans `move_orig_ids`) —
   pose un contexte `restrict_project_id` égal au `project_id` du mouvement
   avant de déléguer au cœur. Sans projet sur le mouvement, comportement
   Odoo standard, aucun filtre.
2. `stock.quant._get_gather_domain()` — Le point où le cœur construit le
   domaine de recherche des quants candidats (dont `_gather`,
   `_get_available_quantity`, `_get_reserve_quantity` découlent tous) — lit ce
   contexte et ajoute `lot_id.project_id = restrict_project_id` au domaine.

Si aucun quant ne correspond au projet, la réservation prend 0, comme un
prélévement standard Odoo (le mouvement reste `confirmed`/`waiting` ou passe
`partially_available`) : **pas d'erreur, jamais de réservation d'un lot hors
projet**.

### 5.1 Chemin MTO (mouvement chaîné) : couvert pour tout mouvement projeté

`_update_reserved_quantity()` (§5) n'est appelée par `_action_assign()` que
sur le chemin **MTS** (mouvement sans `move_orig_ids`). Un mouvement
**chaîné** (`move_orig_ids` renseigné) suit une branche entièrement
différente : `_action_assign()` y appelle directement
`_update_reserved_quantity_vals()` sur les (emplacement, lot, colis,
propriétaire) renvoyés par `stock.move._get_available_move_lines()`, **sans
repasser par la recherche de quants** 



**Portée retenue** : `stock.move._get_available_move_lines()` est surchargée
pour filtrer les lots hérités du mouvement amont, pour **tout mouvement
portant un `project_id`** — OF (consommation en une étape via
`_update_reserved_quantity`, ou chaînée via une route de préparation, couvert
ici) comme simple transfert chaîné (réapprovisionnement interne multi-étapes,
**sous-traitance incluse**). 


### 5.2 Sélection manuelle d'un quant (widget « Pick From »)

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

Le choix a été pris de ne pas bloquezr cette possibilité, on se contente de mettre
par défaut un regroupement par projet sur les quants à sélectionner et le client
peut alors surcharger manuellement s'il le souhaite




## 6. Lien avec `synergie_mrp_performance`

`synergie_mrp_performance` fournit le **rendement (FPY)** par OF et un reporting
agrégé ; il s'appuie sur `mrp.production.project_id` pour grouper par projet.

Ce module-ci fournit la **dimension `project_id` sur le stock** (mouvement, lot,
stock disponible), en aval de l'OF. Les deux sont complémentaires mais
**indépendants** :

- `synergie_mrp_performance` raisonne sur les **quantités produites** (rendement) ;
- `synergie_stock_project` raisonne sur la **traçabilité** (où vit le stock, sur
  quel projet).

