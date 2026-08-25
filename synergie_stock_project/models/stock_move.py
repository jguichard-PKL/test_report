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
    #
    # Les deux alimentent project_id (besoin : la consommation de composants
    # "pioche" elle aussi dans le stock, sa réservation doit donc être
    # restreinte par projet, §5). MAIS ce n'est pas symétrique pour autant :
    # _action_done() (plus bas) exclut explicitement raw_material_production_id
    # de la propagation au lot — un composant consommé ne doit jamais être
    # re-tamponné avec le projet de l'OF qui le consomme (lot potentiellement
    # générique/partagé entre plusieurs projets). project_id sert donc ici
    # UNIQUEMENT à restreindre la réservation pour ces mouvements-là.
    @api.depends(
        "production_id",
        "production_id.project_id",
        "raw_material_production_id",
        "raw_material_production_id.project_id",
        "picking_id",
        "picking_id.project_id",
    )
    def _compute_project_id(self):
        for move in self:
            if move.production_id:
                # Mouvement de sortie d'un OF (fini, sous-produit, fail).
                move.project_id = move.production_id.project_id
            elif move.raw_material_production_id:
                # Consommation de composants : projet de l'OF, pour la
                # réservation uniquement (jamais propagé au lot, cf.
                # _action_done ci-dessous).
                move.project_id = move.raw_material_production_id.project_id
            elif move.picking_id.project_id:
                # Transfert portant un projet : réception, livraison ou
                # transfert interne (élargi à tout type de picking, pas
                # seulement 'incoming' — une livraison dont le picking porte
                # un projet doit aussi tamponner ses mouvements, sans quoi la
                # réservation restreinte par projet ne se déclenche jamais
                # sur ce flux).
                move.project_id = move._get_picking_project()
            else:
                # Tout autre mouvement : on conserve la valeur courante
                # (saisie manuelle possible), on ne force pas à False.
                move.project_id = move.project_id

    def _get_picking_project(self):
        """Hook : projet à appliquer aux mouvements d'un TRANSFERT.

        Source tranchée côté Synergie : le projet est SAISI sur le transfert
        (stock.picking.project_id), miroir du modèle OF où le projet est porté
        par le document (mrp.production). Vaut pour tout type de picking
        (réception, livraison, interne) dès lors que le picking porte un
        projet ; le mouvement le récupère ici, puis il est propagé au lot à
        la validation.

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

        Exclusion volontaire : les mouvements de CONSOMMATION de composants
        (raw_material_production_id) portent désormais un project_id (cf.
        _compute_project_id, pour restreindre leur réservation), mais ne
        doivent JAMAIS tamponner le lot consommé — un composant peut être
        générique/partagé entre projets, contrairement au produit fini/
        sous-produit/fail qui, lui, EST le résultat de l'OF projeté.

        [À vérifier v19] : _action_done renvoie le recordset des mouvements
        réellement validés (peut différer de self après fusion/backorder) ; on
        itère donc sur la valeur de retour, pas sur self. Signature reprise en
        *args/**kwargs pour rester robuste à un éventuel changement.
        """
        moves_done = super()._action_done(*args, **kwargs)
        stamped_lots = self.env["stock.lot"]
        for move in moves_done:
            if move.raw_material_production_id:
                continue
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

        Ne couvre PAS le chemin MTO (mouvement avec move_orig_ids, cf.
        _action_assign, branche qui appelle _update_reserved_quantity_vals
        directement sur les lots renvoyés par _get_available_move_lines) : ce
        chemin ne recherche pas de nouveaux quants, donc ce filtre-ci ne s'y
        déclenche jamais. Couvert séparément par _get_available_move_lines()
        ci-dessous, pour TOUT mouvement projeté (OF ou non) — décision
        tranchée côté Synergie : un transfert chaîné sans lien OF (réception
        exceptée, hors périmètre par nature) doit lui aussi être restreint par
        projet, y compris la sous-traitance (aucun critère technique fiable ne
        permettant de l'exclure spécifiquement sans code dédié, écarté).

        Si aucun quant ne correspond au projet (chemin MTS), la réservation
        prend 0 (comme un stockout standard Odoo) : le mouvement reste
        'confirmed'/'waiting' ou passe 'partially_available', sans erreur ni
        réservation d'un lot hors projet.
        """
        self.ensure_one()
        if not self.project_id:
            return super()._update_reserved_quantity(
                need, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
            )
        return super(StockMove, self.with_context(restrict_project_id=self.project_id.id))._update_reserved_quantity(
            need, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
        )

    def _get_available_move_lines(self, assigned_moves_ids, partially_available_moves_ids):
        """Restreint au projet du mouvement les lots hérités d'un mouvement
        amont (chemin MTO/chaîné), pour TOUT mouvement portant un projet.

        _update_reserved_quantity() ci-dessus ne couvre que le chemin MTS.
        Un mouvement chaîné (move_orig_ids renseigné) suit une branche
        entièrement différente dans _action_assign() : celle-ci appelle
        directement _update_reserved_quantity_vals() sur les (emplacement,
        lot, colis, propriétaire) renvoyés PAR CETTE méthode, sans repasser
        par la recherche de quants. C'est donc ici, et seulement ici, que ce
        chemin peut être filtré.

        Portée volontaire : s'applique à tout mouvement projeté, qu'il soit
        lié à un OF (consommation de composants via une route "Prélever
        composants puis fabriquer" — le scénario métier central : plusieurs
        projets consomment un même article générique à une même étape, seul
        le lot/projet distingue quelle pièce piocher) ou à un simple
        transfert chaîné (réapprovisionnement interne multi-étapes, flux de
        sous-traitance inclus). Décision tranchée côté Synergie : aucun
        critère technique fiable ne permettant de distinguer la sous-traitance
        des autres transferts sans écrire de détection dédiée (écarté), ces
        flux sont traités comme tout autre mouvement projeté.

        Sans projet sur le mouvement : comportement standard, aucun filtre.
        Comme pour la réservation directe, on exclut aussi les lots sans
        projet (clé sans lot_id) : un mouvement projeté ne doit hériter que
        de lots du même projet, jamais de lots "orphelins".
        """
        self.ensure_one()
        available_move_lines = super()._get_available_move_lines(
            assigned_moves_ids, partially_available_moves_ids
        )
        if not self.project_id:
            return available_move_lines
        return {
            key: quantity
            for key, quantity in available_move_lines.items()
            if key[1] and key[1].project_id == self.project_id
        }
