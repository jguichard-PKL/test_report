# synergie_project_planning — Planification prévisionnelle du flux de production (Prototype)

**Statut : PROTOTYPE TECHNIQUE.** Destiné à une démonstration/validation
rapide avec Synergie CAD PSC (CAPECO), pas à la production. Basé sur
`Spec_Technique_Prototype_ClaudeCode.md` (v0.3), lui-même adossé à
`Specification_Synthetique_Planification_Previsionnelle_v0.1.md` (v0.5) —
les deux dans `Documents/Spécifications/` au moment de l'écriture de ce
module ; s'y référer pour tout point de contexte métier manquant ici.

Cible : **Odoo 19**. Conçu pour s'installer et fonctionner (sans vue Gantt)
même sur une base **Community** — cf. §0.

---

## 0. Hypothèse critique : Enterprise vs Community

⚠️ **Confirmé en test réel d'installation, pas seulement en théorie** :
`project_enterprise` n'est pas installé sur l'instance de test
(`jguichard-pkl-test-report-lot-stock-....dev.odoo.com`). Première tentative
d'installation en échec (`ValueError: Wrong @depends... Dependency field
'planned_date_end' not found in model project.task`) — corrigé depuis (voir
`_compute_x_deviation_days` ci-dessous) : le module s'installe désormais
correctement sur cette base.

La spec (§0) demande explicitement de vérifier l'édition de la base avant de
commencer, et d'arrêter/remonter le point si Community. Plutôt que de
trancher ça à l'avance (aucun accès à votre instance de test depuis cet
environnement), **le wizard vérifie ce prérequis lui-même, à l'exécution** :

- `project.task.planned_date_begin` / `planned_date_end` sont ajoutés par le
  module Enterprise `project_enterprise` — **vérifié en lisant directement
  le code source**
  `project/models/project_task.py` (branche 19.0) : ces champs **n'existent
  pas du tout** sur `project.task` en Community, pas juste absents d'une vue.
- `action_generate()` vérifie `"planned_date_begin" in
  self.env["project.task"]._fields` **avant** toute création de tâche. Si
  absent, il lève une `UserError` explicite plutôt que de laisser échouer
  `create()` avec une erreur ORM peu lisible, ou pire, de créer des tâches
  à moitié correctes.
- Aucune vue XML de ce module ne référence `planned_date_begin`/
  `planned_date_end` directement (ça ferait échouer l'**installation** du
  module sur Community, pas juste son exécution). Quand `project_enterprise`
  est installé, ses propres vues affichent déjà ces champs — rien à ajouter
  côté ce module.
- L'action de retour du wizard (§4.3 point 6) détecte aussi dynamiquement si
  `project_enterprise` est installé pour proposer la vue Gantt, sinon liste.

⚠️ **Piège distinct, rencontré en test réel** : le garde-fou runtime du
wizard (ci-dessus) ne protège que l'**exécution** du wizard — il ne protège
PAS l'**installation** du module. Le champ `x_deviation_days`
([models/project_task.py](models/project_task.py)) avait initialement
`planned_date_end` dans son `@api.depends`. Odoo valide les `@api.depends`
à la **construction du registre** (donc à l'install/upgrade du module, avant
même qu'un utilisateur touche à quoi que ce soit) — un `@api.depends` sur un
champ absent du modèle fait échouer l'installation entière avec
`ValueError: Wrong @depends`, sans rapport avec le garde-fou runtime du
wizard. Corrigé en ne dépendant que de `x_actual_end_date` (champ propre à
ce module, toujours présent) et en lisant `planned_date_end` dynamiquement
dans le corps de la méthode, seulement s'il existe (`"planned_date_end" in
self._fields`). Conséquence assumée : si `project_enterprise` est installé
et que `planned_date_end` change après coup (ex. glissé dans le Gantt),
`x_deviation_days` ne se recalcule pas automatiquement — il faudra
rouvrir/resauvegarder la tâche.

**Conséquence pratique** : sur une base Community, le wizard refuse de
générer quoi que ce soit tant que ce point n'est pas résolu (module Gantt
tiers, ou confirmation que le point est hors périmètre pour ce test) — mais
le **module s'installe sans erreur** dans tous les cas, dépendances de
tâches (`depend_on_ids`, natif Community depuis Odoo 17) comprises.

## 1. Périmètre — ce qui N'est PAS touché

Repris strictement de la spec (§1) : **aucun** modèle `mrp.*` ou `stock.*`
existant n'est modifié, étendu, ni même dépendu par ce module. Aucun lien
automatique avec les OF, mouvements, lots ou restrictions par projet déjà en
place (`synergie_stock_project`, `synergie_mrp_performance`). Le
déclenchement est **exclusivement manuel** via le wizard — pas de génération
automatique depuis un BL, une commande, ou tout autre événement.

## 2. Modèle de données

### 2.1 Extension de `project.task` ([models/project_task.py](models/project_task.py))

| Champ | Type | Détail |
|---|---|---|
| `x_duration_type` | Selection (Fixe/Proportionnelle), required | Défaut `proportional`. |
| `x_fixed_duration_hours` | Float | Utilisé si `x_duration_type == 'fixed'`. |
| `x_unit_time_minutes` | Float | Copié depuis le paramètre système (§2.3) **à la création uniquement** (`default=`, pas de `compute`) — pas de lien dynamique ensuite, pour ne pas modifier une planification déjà communiquée si le paramètre change. |
| `x_planned_qty` | Integer | Calculée par le wizard. 0 pour une étape fixe. Non éditable manuellement après génération (prototype). |
| `x_planned_duration_hours` | Float, computed, stored | Fixe si type Fixe, sinon `qty × temps_unitaire / 60`. |
| `x_generated_by_wizard` | Boolean | Marqueur utilisé par le garde-fou d'idempotence du wizard. |
| `x_actual_end_date` | Date | Saisie manuelle admin. Aucun lien avec un OF. |
| `x_deviation_days` | Float, computed, stored | = date réelle − `planned_date_end`, en jours. |

⚠️ **Limite assumée** sur `x_deviation_days` : type `Float`, donc sans valeur
calculable il vaut `0.0`, pas "vide" au sens strict (un `Float` standard ne
distingue pas 0 de "non renseigné" dans les vues Odoo). Cohérent avec la
simplicité demandée pour ce prototype ; à reconsidérer si ça prête à
confusion en démo (ex. widget dédié, ou passage en `Char` formaté).

Champs natifs réutilisés tels quels : `planned_date_begin`, `planned_date_end`
(Enterprise uniquement, cf. §0), `depend_on_ids`, `project_id`.

### 2.2 Pas d'extension du produit

Décision explicite reprise de la spec (§2.2) : `product.template` n'est **pas**
touché. Les rendements sont de simples champs du wizard, sans stockage
persistant — cf. §8 de la spec synthétique pour le point ouvert sur leur
emplacement définitif (hors périmètre du prototype).

### 2.3 Paramètre système ([data/ir_config_parameter_data.xml](data/ir_config_parameter_data.xml))

`ir.config_parameter` clé `planning.default_unit_time_minutes`, valeur
prototype `1` (min/pièce). `noupdate="1"` : une valeur modifiée manuellement
n'est jamais écrasée par une mise à jour du module.

## 3. Catalogue des étapes ([wizard/project_planning_generate_wizard.py](wizard/project_planning_generate_wizard.py), `_get_flow_steps()`)

Codé en dur (liste Python ordonnée), **pas** un référentiel paramétrable —
conforme à la spec (§3) : « ne pas chercher à généraliser au-delà de ce
catalogue ». Valeurs de démonstration (5j / 3j / 24h), **pas des données
validées avec le client**.

| Étape | Code(s) | Condition d'activation | Type |
|---|---|---|---|
| Wafer Foundry | WF | Toujours | Fixe, 5j |
| Bumping | BP | `has_bumping` | Fixe, 3j |
| Wafer Test | D1, D2, D3 | 1 à 3 selon `wafer_test_temp_count` | Proportionnelle |
| Retention Bake | RB | `has_retention_bake` | Fixe, 24h |
| Assembly | RL | Toujours | Proportionnelle |
| Final Test | TG (Std), TH (Hot), TC (Cold) | 1 à 3 selon `final_test_temp_count` | Proportionnelle |
| End Of Line | FG | Toujours | Proportionnelle |

⚠️ **Interprétation assumée, à confirmer avec le client** : la spec dit
« Nombre de températures configurable (1 à 3) » pour Wafer Test et Final
Test sans détailler l'effet sur la génération. Ce module génère **une tâche
séquentielle par température** (ex. `wafer_test_temp_count=2` → deux tâches
D1 puis D2, chaînées), **toutes à la même quantité prévisionnelle** — le
rendement du groupe (`yield_wafer_test`/`yield_final_test`) s'applique **une
seule fois**, à l'entrée du groupe, pas par température testée
individuellement. Cohérent avec l'exemple chiffré de la spec synthétique
(§6 : un seul rendement par groupe d'étape), mais si plusieurs températures
impliquent réellement des rendements distincts en production, cette logique
devra être revue avant généralisation.

Retention Bake est un code unique (`RB`), pas de variante par température
précédente (la spec catalogue mentionne `D1B`/`D2B` sans en préciser l'usage
fonctionnel exact) — simplification assumée, sans impact sur le calcul.

## 4. Wizard de génération (`project.planning.generate.wizard`)

Bouton « Générer la planification prévisionnelle » sur l'en-tête du
formulaire projet ([views/project_project_views.xml](views/project_project_views.xml)) — `type="action"`
référençant directement l'action du wizard : Odoo passe alors automatiquement
`active_id`/`active_model` dans le contexte, exploités par le `default` de
`project_id` sur le wizard (pas de méthode Python dédiée sur `project.project`
nécessaire).

### Algorithme (`action_generate()`)

Numérotation alignée sur la spec §4.3 :

0. **[Ajout non demandé explicitement par ce numéro, mais nécessaire — cf. §0]** Vérifie que `planned_date_begin` existe sur `project.task` ; sinon `UserError` explicite.
1. Garde-fou d'idempotence : `UserError` si une planification existe déjà pour ce projet (`x_generated_by_wizard = True`).
2. Active `allow_task_dependencies` sur le projet si besoin.
3. Construit la liste ordonnée des étapes actives (§3).
4. Propage la quantité à travers les rendements saisis (100% par défaut → propagation 1:1). Arrondi à l'entier le plus proche à chaque application de rendement.
5. Pour chaque étape : calcule la durée, chaîne `planned_date_begin`/`planned_date_end` via `resource.calendar.plan_hours()` (calendrier de la société du projet, à défaut de la société courante), crée la `project.task` avec `depend_on_ids` pointant vers l'étape précédente.
6. Retourne une action ouvrant les tâches créées — vue Gantt si `project_enterprise` est installé, sinon liste (détection dynamique, cf. §0).

⚠️ **`resource.calendar.plan_hours(hours, day_dt, compute_leaves=True)`** —
méthode confirmée en lisant directement `resource/models/resource_calendar.py`
(branche 19.0) : retourne la date/heure après avoir « planifié » N heures
ouvrées depuis `day_dt`. Appliquée **uniformément à toutes les étapes**
(fixes et proportionnelles), conformément à la lettre de l'algorithme §4.3
point 5c. Point à discuter avec le client : un lead time fournisseur ou un
bake physique tournent en temps réel continu, pas seulement en heures
ouvrées — les convertir en temps ouvré comme une étape de production
interne peut décaler artificiellement les dates (ex. un bake de 24h démarré
un vendredi soir « saute » le week-end au lieu de se terminer samedi). Choix
délibéré de suivre l'algorithme tel quel plutôt que d'improviser une
distinction fixe/proportionnelle non demandée ; à trancher si le prototype
est généralisé.

⚠️ **Durée nulle** : si `plan_hours(0, begin)` est appelé alors que `begin`
tombe hors horaires ouvrés, la méthode cœur peut renvoyer le **début du
prochain intervalle ouvré** plutôt que `begin` lui-même — ce qui décalerait
une étape à durée nulle. Contourné en court-circuitant `plan_hours()` pour
une durée nulle (`end = begin` directement).

Si `plan_hours()` renvoie `False` (aucun intervalle ouvré trouvé sur le
calendrier), repli sur un ajout de temps brut (`timedelta`) plutôt que de
bloquer la génération — pour rester utilisable en démo même avec un
calendrier mal configuré.

## 5. Vues ajoutées

- [views/project_task_views.xml](views/project_task_views.xml) : nouvelle page « Planification
  prévisionnelle » sur le formulaire tâche, insérée en fin de notebook
  (`position="inside"` sur `<notebook>`, pas ancrée à une page cœur précise —
  robuste si l'ordre/le nom des pages cœur change). Ne référence **jamais**
  `planned_date_begin`/`planned_date_end` (cf. §0). `depend_on_ids` n'est pas
  repris : déjà éditable nativement via la page cœur « Blocked By »,
  visible dès que `allow_task_dependencies` est actif (posé par le wizard).
- [views/project_project_views.xml](views/project_project_views.xml) : bouton d'accès au wizard.
- [wizard/project_planning_generate_wizard_views.xml](wizard/project_planning_generate_wizard_views.xml) : formulaire du wizard + action.

## 6. Scénario de test

Reprendre le scénario de la spec technique §6 (non dupliqué ici pour éviter
toute divergence entre les deux documents). Points à consigner précisément
en le déroulant, comme demandé par la spec :

- **Test 4/5 (cascade Gantt)** : le comportement réel de replanification
  (glisser-déposer Gantt vs formulaire standard vs écriture ORM) reste à
  confirmer sur votre instance — la recherche préalable (§0 de la spec)
  rend probable que seul le glisser-déposer déclenche une cascade, mais
  ceci n'a **pas** été vérifié en conditions réelles depuis cet
  environnement de développement (pas d'accès à une instance Odoo en
  direct). Le résultat de ce test conditionne si un développement de
  sécurisation supplémentaire (repropagation serveur des dates en cascade)
  est nécessaire — **non implémenté dans cette itération**, la spec
  demandant explicitement de traiter ce point comme un test à consigner,
  pas une fonctionnalité à construire par anticipation (cf. spec synthétique
  §8, changelog v0.5).

## 7. Simplifications assumées (cf. spec §7 — ne pas sur-développer au-delà)

- Un seul temps unitaire global, copié à la création de chaque tâche.
- Calcul strictement séquentiel, aucune capacité/parallélisation.
- Calendrier de travail standard (pas d'équipes postées).
- Flow fermé, codé en dur (§3).
- Aucun lien avec les modèles `mrp.*`/`stock.*` existants.
- Pas de données de démonstration dans ce module (déjà disponibles côté
  Synergie) — à créer manuellement si besoin (projet + produits stockables
  suivis par lot, cf. spec §5 pour la convention de nommage si utile).

## 8. Après le prototype

Ce module ne remplace pas une SFD complète. Les points ouverts de
`Specification_Synthetique_Planification_Previsionnelle_v0.1.md` §8 (type de
durée par étape à trancher avec le client, granularité du suivi réel,
répercussion automatique ou non d'un écart, stockage définitif des
rendements, etc.) restent à trancher avant toute généralisation au-delà du
projet pilote.
