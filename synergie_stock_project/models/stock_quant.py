# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.fields import Domain


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Projet en stock disponible : related stocké sur le projet du lot.
    # store=True permet de filtrer / grouper le stock disponible par projet
    # (besoin direct Synergie) sans jointure coûteuse.
    # index=True : filtres et group_by fréquents.
    project_id = fields.Many2one(
        "project.project",
        string="Projet",
        related="lot_id.project_id",
        store=True,
        index=True,
        help="Projet du lot en stock, pour filtrer / grouper le stock disponible.",
    )

    def _get_gather_domain(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        """Restreint les quants candidats à la réservation de stock au projet demandé.

        _get_gather_domain() est LE point où le core Odoo construit le domaine de
        recherche des quants pour toute réservation (_gather / _get_available_quantity
        / _get_reserve_quantity en découlent tous). Le core lui-même y lit déjà
        une clé de contexte ('with_expiration') pour étendre le domaine sans
        toucher aux appelants : on suit la même logique avec 'restrict_project_id',
        posé par stock.move._update_reserved_quantity() (cf. stock_move.py) quand
        le mouvement porte un projet.

        [À vérifier v19] Un quant sans lot (produit non tracké) ne matche jamais
        un restrict_project_id posé (lot_id.project_id est vide sur False) : un
        mouvement avec projet ne réserve donc que du stock avec lot et projet,
        jamais du stock générique non tracké. Cohérent avec le modèle du module
        (le projet vit sur le lot).
        """
        domain = super()._get_gather_domain(
            product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict
        )
        restrict_project_id = self.env.context.get("restrict_project_id")
        if restrict_project_id:
            domain &= Domain("lot_id.project_id", "=", restrict_project_id)
        return domain
