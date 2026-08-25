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
   - Mouvement de **consommation de composants** (`raw_material_production_id`)
     → `raw_material_production_id.project_id` — **uniquement pour restreindre
     sa réservation** (§5) : ce mouvement-là "pioche" bien dans le stock, sa
     réservation doit donc être contrainte au projet comme les autres flux
     sortants. Il reste néanmoins **exclu de la propagation au lot** (point 2
     ci-dessous) : un composant est potentiellement générique/partagé entre
     projets, contrairement au produit qui sort de l'OF.
   - **Transfert portant un projet** (`picking_id.project_id`, tout type —
     réception, livraison, interne) → hook `_get_picking_project()` →
     `picking_id.project_id` (cf. §4).
   - Sinon → la valeur courante est conservée (saisie manuelle possible),
     jamais forcée à `False`.

2. **Propagation vers `stock.lot`** dans `stock.move._action_done()` :
   après `super()`, pour chaque mouvement validé avec un `project_id` renseigné
   **et n'étant pas une consommation de composants** (`raw_material_production_id`
   exclu explicitement — cf. point ci-dessus), on parcourt ses `move_line_ids`
   et on écrit le projet sur tout `lot_id` **encore vide**.
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

## 4. Source projet portée par le TRANSFERT (réception, livraison, interne)

Pour les flux **OF**, la source est le document OF (`mrp.production.project_id`).
Pour **tout transfert** (réception, livraison, transfert interne), la source a
été **tranchée côté Synergie : le projet est SAISI sur le transfert**
(`stock.picking.project_id`) — miroir exact du modèle OF (projet porté par le
document).

⚠️ **Historique** : ce mécanisme ne couvrait initialement que les réceptions
(`picking_type_id.code == 'incoming'`). Élargi à tout type de picking après un
cas réel en test : une **livraison** sortante portant un projet sur le picking
ne le propageait pas à ses mouvements (le compute ne regardait que les
réceptions), donc la réservation restreinte par projet (§5) ne se déclenchait
jamais sur ce flux — la disponibilité restait calculée sans aucun filtre. Le
champ `stock.picking.project_id` est bien le même sur tous les types de
transfert ; c'est la **propagation vers le mouvement** qui était trop étroite.

Mécanique :
- Champ `project_id` ajouté sur `stock.picking`, saisi sur le transfert (tout
  type).
- Le hook `stock.move._get_picking_project()` renvoie `picking_id.project_id`.
- Le compute de `stock.move.project_id` dépend de `picking_id.project_id` : le
  mouvement se met à jour dès que le projet est posé/modifié sur le transfert.
- À la validation, le projet est propagé au(x) lot(s) mouvementé(s) (mécanique
  §2.2) — en réception comme en livraison.

Aucune dépendance `purchase_stock` requise : marche aussi pour les réceptions
**sans commande d'achat** (retours OSAT, etc.).

Le hook reste **surchargeable** : brancher une autre source (commande d'achat…)
se fait en redéfinissant `_get_picking_project()`, sans toucher au compute.

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

⚠️ **Pour tester : ne pas se fier au champ « Product Availability » du
transfert.** Ce texte (`stock.picking.products_availability`, "Available" /
"Not Available" / "Exp <date>") est un indicateur **prévisionnel** cœur Odoo,
calculé depuis `move.forecast_availability` → `product.free_qty` /
`virtual_available` — une quantité agrégée **par produit et par entrepôt,
tous lots et tous projets confondus**. Il ne passe jamais par
`_get_gather_domain()` et affichera "Available" dès qu'il existe du stock de
l'article quelque part, **même sans aucun lot du bon projet**.

L'indicateur fiable est la **barre de statut du transfert**
(Draft › Waiting › Ready › Done) et/ou `move_line_ids` : si la réservation a
réellement échoué faute de lot au bon projet, le transfert reste bloqué en
« Waiting » (jamais « Ready ») et la liste des mouvements (`move_line_ids`,
bouton « Moves ») reste vide — quel que soit ce que dit "Product
Availability".

### 5.1 Chemin MTO (mouvement chaîné) : couvert pour tout mouvement projeté

`_update_reserved_quantity()` (§5) n'est appelée par `_action_assign()` que
sur le chemin **MTS** (mouvement sans `move_orig_ids`). Un mouvement
**chaîné** (`move_orig_ids` renseigné) suit une branche entièrement
différente : `_action_assign()` y appelle directement
`_update_reserved_quantity_vals()` sur les (emplacement, lot, colis,
propriétaire) renvoyés par `stock.move._get_available_move_lines()`, **sans
repasser par la recherche de quants** — le filtre du §5 ne s'y déclenche donc
jamais tel quel.

Ce chemin est très concret chez Synergie : sur une route de fabrication
**« Prélever composants puis fabriquer »**, le mouvement de consommation réel
d'un composant (`raw_material_production_id`) est chaîné, alimenté par le
transfert de préparation des composants — c'est **le scénario métier
central** du module (wafer → rawline → tested goods, où chaque étape
consomme un article générique commun à tous les projets ; seul le lot/projet
distingue quelle pièce piocher). Sans couverture de ce chemin, un OF projeté
pourrait hériter du composant préparé pour un **autre** projet.

**Portée retenue** : `stock.move._get_available_move_lines()` est surchargée
pour filtrer les lots hérités du mouvement amont, pour **tout mouvement
portant un `project_id`** — OF (consommation en une étape via
`_update_reserved_quantity`, ou chaînée via une route de préparation, couvert
ici) comme simple transfert chaîné (réapprovisionnement interne multi-étapes,
**sous-traitance incluse**). Décision tranchée côté Synergie : aucun critère
technique fiable ne permettant de distinguer la sous-traitance des autres
transferts sans code de détection dédié (écarté), ces flux sont traités
comme tout autre mouvement projeté — ce qui a pour effet secondaire de les
restreindre par projet également.

Cette couverture rend le filtre robuste au réglage « Étapes de fabrication »
de vos types d'opération (1, 2 ou 3 étapes) comme au nombre d'étapes de vos
routes de transfert, sans avoir à les connaître précisément.

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

Corrigé par héritage de ces deux vues
([stock_move_line_views.xml](views/stock_move_line_views.xml)) : le domaine
du champ `quant_id` est complété avec `lot_id.project_id = <projet du
mouvement>` quand le mouvement (ou la ligne, selon la vue) porte un projet.
Sans projet sur le mouvement, aucune restriction (comportement standard
conservé).

⚠️ **Piège rencontré en test, corrigé** : un domaine de vue ne peut résoudre
qu'un champ **réellement chargé** sur l'enregistrement courant ou sur le
parent immédiat (un seul niveau) — jamais un champ non déclaré dans la vue,
ni une chaîne relationnelle à deux niveaux (`move_id.project_id`). Deux
correctifs supplémentaires ont été nécessaires pour que le filtre se
déclenche réellement (sans eux, `parent.project_id` / `move_id.project_id`
étaient toujours résolus comme absents, et le domaine ajouté ne filtrait
jamais, silencieusement) :

1. `project_id` n'était pas chargé sur le formulaire popup "Move Detail"
   (`stock.view_stock_move_operations`, ouvert via l'icône "Show details"
   sur une ligne de l'onglet Opérations) qui embarque
   `view_stock_move_line_operation_tree` — `parent.project_id` n'y était donc
   jamais résolu. Corrigé en ajoutant `project_id` (invisible) à ce
   formulaire ([stock_move_views.xml](views/stock_move_views.xml)).
2. `move_id.project_id` (deux niveaux) n'est pas résolu comme valeur de
   domaine côté client. Corrigé en ajoutant un champ related **à plat** sur
   `stock.move.line` ([stock_move_line.py](models/stock_move_line.py),
   `project_id = fields.Many2one(related='move_id.project_id')`), exactement
   le contournement déjà utilisé par le cœur pour `picking_location_id`
   (`related='picking_id.location_id'`, cf. `stock/models/stock_move_line.py`).

### 5.3 « Add a line » sur le popup "Move Detail" (widget JS `sml_x2_many`)

⚠️ **Troisième trou, distinct des deux précédents** : le popup "Move Detail"
(§5.2) affiche `move_line_ids` avec `widget="sml_x2_many"`
(`stock.view_stock_move_operations`), pas un simple champ x2many standard.
Ce widget est un composant **OWL côté client**
(`SMLX2ManyField`, `stock/static/src/fields/stock_move_line_x2_many_field.js`)
qui, sur clic « Add a line », construit **son propre domaine de recherche de
quants en JavaScript** dans sa méthode `onAdd()` — indépendamment de tout
attribut `domain` XML posé côté serveur. Le domaine du champ `quant_id` (§5.2)
ne s'y applique donc **pas** : confirmé en test réel, un lot d'un autre projet
restait sélectionnable via ce bouton et créait bien une ligne de mouvement.

Corrigé par un **patch JS** ([static/src/js/sml_x2_many_patch.js](static/src/js/sml_x2_many_patch.js)),
enregistré comme asset `web.assets_backend`
([__manifest__.py](__manifest__.py)) : surcharge de `onAdd()` via
`patch(SMLX2ManyField.prototype, {...})` (même mécanisme que celui utilisé
par le module cœur `mrp_subcontracting` pour patcher ce même composant),
ajoutant `["lot_id.project_id", "=", <projet du mouvement>]` au domaine
construit par le cœur. Sans projet sur le mouvement, aucune restriction.

⚠️ **Duplication assumée** : il n'existe aucun point d'extension isolant la
construction du domaine dans `onAdd()` (contrairement à
`quantListViewShowOnHandOnly`, un simple getter que `mrp_subcontracting`
surcharge proprement) — le patch **reproduit l'intégralité de la méthode**
avec une ligne ajoutée. Fragile aux futures évolutions du cœur : si `onAdd()`
change de signature ou de logique en v19.x, ce patch doit être resynchronisé
manuellement (pas d'erreur explicite en cas de désynchronisation, juste un
retour au comportement non filtré).

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
| Réception / livraison / transfert interne | ✅ | projet saisi sur le transfert (`stock.picking`, tout type) → mouvement → lot |
| Réservation automatique par projet (MTS) | ✅ | `_action_assign` (sans `move_orig_ids`) ne réserve que des lots du même projet |
| Réservation MTO (mouvement chaîné, dont sous-traitance) | ✅ | `_get_available_move_lines()` filtre tout mouvement projeté (§5.1) |
| Sélection manuelle d'un quant (widget « Pick From », domaine XML) | ✅ | domaine du champ `quant_id` complété par projet (§5.2) |
| Sélection manuelle via « Add a line » (widget JS `sml_x2_many`) | ✅ | patch JS de `onAdd()`, domaine construit côté client (§5.3) |
| Saisie d'un lot en texte libre (`lot_name`) | ➖ hors périmètre | pas de quant existant à filtrer (création de lot en réception) |
| Composants consommés — réservation restreinte par projet | ✅ | `raw_material_production_id.project_id`, MTS **et** MTO (§5, §5.1) |
| Composants consommés — propagation au lot | ➖ hors périmètre (volontaire) | jamais tamponnés (`_action_done` les exclut explicitement) |

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
- existence et signature de `stock.quant._get_gather_domain()`,
  `stock.move._update_reserved_quantity()` et
  `stock.move._get_available_move_lines()` (mécanique de réservation, §5,
  §5.1) ; structure des clés retournées par cette dernière
  (`(location_id, lot_id, package_id, owner_id)`, index 1 = lot) ;
- identifiants et structure de `stock.view_stock_move_operations`,
  `stock.view_stock_move_line_operation_tree` et
  `stock.view_stock_move_line_detailed_operation_tree`, présence du champ
  `quant_id` (widget `pick_from`) et de ses variables de domaine
  (`parent.location_id`, `picking_location_id`) — cf. §5.2 ;
- **JS** : implémentation complète de `SMLX2ManyField.onAdd()`
  (`stock/static/src/fields/stock_move_line_x2_many_field.js`), dupliquée par
  [static/src/js/sml_x2_many_patch.js](static/src/js/sml_x2_many_patch.js) —
  cf. §5.3. Le point le plus exposé à une casse silencieuse en cas de montée
  de version : à revérifier à chaque upgrade Odoo, pas seulement en v19 ;
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
