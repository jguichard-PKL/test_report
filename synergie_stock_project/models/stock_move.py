# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    # ------------------------------------------------------------------
    # Champ pivot : le projet vit sur le mouvement de stock, dénominateur
    # commun de toutes les transactions (OF, réception, transfert interne...).
    #
    # store=True + readonly=False : la valeur est auto-calculée par le compute
    # mais reste modifiable manuellement. Une modif manuelle persiste tant
    # qu'aucune dépendance du compute ne change.
    # index=True : filtres et group_by fréquents par projet.
    # ------------------------------------------------------------------
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        compute="_compute_project_id",
        store=True,
        readonly=False,
        index=True,
        help=(
            "Projet de rattachement du mouvement de stock, dérivé de la "
            "transaction source (ordre de fabrication ou réception). "
            "Propagé au lot à la validation."
        ),
    )

    # [À vérifier v19] : sur stock.move, les mouvements de SORTIE d'un OF (produit
    # fini, sous-produits, fails) portent 'production_id', tandis que les
    # mouvements de CONSOMMATION de composants portent 'raw_material_production_id'.
    # On ne dépend volontairement que de 'production_id' : les composants
    # consommés ne doivent pas re-tamponner les lots déjà existants.
    @api.depends(
        "production_id",
        "production_id.project_id",
        "picking_type_id",
        "picking_type_id.code",
        "picking_id",
        "picking_id.project_id",
    )
    def _compute_project_id(self):
        for move in self:
            if move.production_id:
                # Mouvement de sortie d'un OF (fini, sous-produit, fail).
                move.project_id = move.production_id.project_id
            elif move._is_incoming_reception():
                # Réception (bumping, rowlines OSAT, achats).
                move.project_id = move._get_reception_project()
            else:
                # Tout autre mouvement : on conserve la valeur courante
                # (saisie manuelle possible), on ne force pas à False.
                move.project_id = move.project_id

    def _is_incoming_reception(self):
        """Vrai si le mouvement est une réception (flux entrant).

        On s'appuie sur picking_type_id.code == 'incoming' (champ cœur stable)
        plutôt que sur une comparaison d'emplacements, pour rester robuste aux
        configurations multi-entrepôts.
        """
        self.ensure_one()
        return self.picking_type_id.code == "incoming"

    def _get_reception_project(self):
        """Hook : projet à appliquer aux mouvements de RÉCEPTION.

        Source tranchée côté Synergie : le projet est SAISI sur le transfert
        (stock.picking.project_id), miroir du modèle OF où le projet est porté
        par le document (mrp.production). Le mouvement le récupère ici, puis il
        est propagé au lot à la validation.

        Reste un hook surchargeable : une autre source (commande d'achat, etc.)
        pourrait être branchée ici sans toucher au compute.
        """
        self.ensure_one()
        return self.picking_id.project_id

    def _action_done(self, *args, **kwargs):
        """Propage le projet du mouvement vers le lot à la validation.

        Point de propagation : _action_done() sur stock.move est LE hook
        canonique de validation ("les mouvements sont 'done'"). À son retour,
        toutes les lignes (move_line_ids) portent leur lot_id définitif
        (créé/affecté au cours de la validation).

        NB : le handoff demandait initialement de surcharger
        stock.move.line._action_done() ; cette méthode n'est pas un point
        d'extension appelé en v19 (la surcharge y serait du code mort). On
        opère donc ici, sur stock.move, qui couvre d'un coup le lot fini, les
        sous-produits et les fails du même OF (tous portés par des mouvements
        à project_id renseigné).

        Garde-fou : on n'écrit le projet que si le lot n'en a pas déjà un.
        Cohérent avec l'hypothèse lot mono-projet : la première écriture suffit,
        aucun arbitrage, jamais d'écrasement.

        [À vérifier v19] : _action_done renvoie le recordset des mouvements
        réellement validés (peut différer de self après fusion/backorder) ; on
        itère donc sur la valeur de retour, pas sur self. Signature reprise en
        *args/**kwargs pour rester robuste à un éventuel changement.
        """
        moves_done = super()._action_done(*args, **kwargs)
        stamped_lots = self.env["stock.lot"]
        for move in moves_done:
            project = move.project_id
            if not project:
                continue
            for line in move.move_line_ids:
                lot = line.lot_id
                if lot and not lot.project_id:
                    lot.project_id = project
                    stamped_lots |= lot

        # Resynchronise le champ related stocké stock.quant.project_id.
        # Les quants du lot sont créés PENDANT super()._action_done(), donc
        # AVANT que le lot ne porte son projet : à cet instant le related vaut
        # False et est stocké tel quel. La recompute déclenchée par l'écriture
        # de lot.project_id peut alors manquer ces quants (ils ne sont pas
        # encore retrouvés en base au moment où l'ORM cherche les dépendants).
        # On force donc explicitement la recompute en signalant que 'lot_id'
        # a changé pour les quants des lots fraîchement tamponnés.
        if stamped_lots:
            quants = self.env["stock.quant"].search(
                [("lot_id", "in", stamped_lots.ids)]
            )
            quants.modified(["lot_id"])
        return moves_done

    def _update_reserved_quantity(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        """Restreint la réservation automatique aux lots du projet du mouvement.

        Point d'accroche : cette méthode est celle appelée par _action_assign()
        pour réserver un mouvement MTS (sans move_orig_ids) — cf. stock/models/
        stock_move.py, appel `move._update_reserved_quantity(need, move.location_id,
        strict=False)`. Elle délègue ensuite au cœur, qui recherche les quants via
        stock.quant._get_gather_domain() (cf. stock_quant.py). On y ajoute le
        filtre projet en posant un contexte 'restrict_project_id', plutôt qu'en
        réécrivant la mécanique de réservation.

        Sans projet sur le mouvement (project_id vide) : comportement standard
        Odoo inchangé, aucun filtre.

        [À vérifier v19] Ne couvre pas le chemin MTO (mouvement avec
        move_orig_ids, cf. _action_assign, branche `_update_reserved_quantity_vals`
        appelée directement) : ce chemin réutilise les lots déjà réservés par le
        mouvement amont, sans nouvelle recherche de quants. Aucun trou de filtrage
        tant que ce mouvement amont porte lui-même le bon project_id (cas normal :
        le projet est porté de bout en bout par la chaîne de transferts/OF).

        Si aucun quant ne correspond au projet, la réservation prend 0 (comme un
        stockout standard Odoo) : le mouvement reste 'confirmed'/'waiting' ou passe
        'partially_available', sans erreur ni réservation d'un lot hors projet.
        """
        self.ensure_one()
        if not self.project_id:
            return super()._update_reserved_quantity(
                need, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
            )
        return super(StockMove, self.with_context(restrict_project_id=self.project_id.id))._update_reserved_quantity(
            need, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
        )
