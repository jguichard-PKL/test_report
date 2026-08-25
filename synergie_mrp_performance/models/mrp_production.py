# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # ------------------------------------------------------------------
    # Quantités de sortie (homogènes : on raisonne sur ce qui est PRODUIT)
    # ------------------------------------------------------------------
    pkl_qty_good = fields.Float(
        string="Qté conforme",
        compute="_compute_pkl_yield",
        store=True,
        digits="Product Unit of Measure",
        help="Quantité du produit principal réellement produite (mouvements 'done').",
    )
    pkl_qty_fail = fields.Float(
        string="Qté fail",
        compute="_compute_pkl_yield",
        store=True,
        digits="Product Unit of Measure",
        help="Somme des sous-produits dont le type de sortie est 'Fail'.",
    )
    pkl_qty_retest = fields.Float(
        string="Qté retest",
        compute="_compute_pkl_yield",
        store=True,
        digits="Product Unit of Measure",
        help="Somme des sous-produits dont le type de sortie est 'Retest'.",
    )
    pkl_qty_output = fields.Float(
        string="Qté totale testée",
        compute="_compute_pkl_yield",
        store=True,
        digits="Product Unit of Measure",
        help="Total produit = conforme + fail + retest.",
    )

    # ------------------------------------------------------------------
    # Indicateurs de rendement (ratio 0–1, affichés en % via widget)
    #
    # Choix : on stocke un ratio 0–1 et on l'affiche avec widget="percentage".
    # Ces champs sont marqués aggregator=False : un pourcentage NE S'ADDITIONNE
    # PAS et ne doit pas être moyenné aveuglément en vue liste/pivot. Pour le
    # rendement agrégé multi-OF, utiliser le modèle pkl.mrp.yield.report.
    # ------------------------------------------------------------------
    pkl_fpy = fields.Float(
        string="FPY",
        compute="_compute_pkl_yield",
        store=True,
        aggregator=False,
        digits=(16, 4),
        help="First-pass yield = conforme / total testé (ratio 0–1).",
    )
    pkl_fail_rate = fields.Float(
        string="Taux de fail",
        compute="_compute_pkl_yield",
        store=True,
        aggregator=False,
        digits=(16, 4),
        help="fail / total testé (ratio 0–1).",
    )
    pkl_retest_rate = fields.Float(
        string="Taux de retest",
        compute="_compute_pkl_yield",
        store=True,
        aggregator=False,
        digits=(16, 4),
        help="retest / total testé (ratio 0–1).",
    )

    # ------------------------------------------------------------------
    # Classification d'un mouvement de sortie
    # ------------------------------------------------------------------
    def _pkl_classify_move(self, move):
        """Retourne la catégorie de rendement d'un mouvement fini.

        Valeurs possibles : 'good', 'fail', 'retest' ou False (ignoré).

        La détection est faite PAR ARTICLE (product_template.pkl_output_type).
        Cette méthode isole volontairement la logique de classification : pour
        ajouter une détection PAR PRÉFIXE DE LOT (ex. lots commençant par 'RT'),
        il suffit de surcharger ici et d'inspecter
        ``move.move_line_ids.lot_id.name`` — sans toucher au calcul ni aux
        dépendances. La numérotation de lot n'est jamais modifiée, seulement lue.
        """
        self.ensure_one()
        # Le produit principal de l'OF est toujours considéré comme conforme.
        if move.product_id == self.product_id:
            return "good"
        output_type = move.product_id.pkl_output_type
        if output_type in ("fail", "retest"):
            return output_type
        # Autre sous-produit (consommable, rebut récupérable, etc.) : hors calcul.
        return False

    @api.depends(
        "move_finished_ids",
        "move_finished_ids.state",
        "move_finished_ids.quantity",
        "move_finished_ids.product_id",
        "move_finished_ids.product_id.pkl_output_type",
        "product_id",
        "state",
    )
    def _compute_pkl_yield(self):
        for production in self:
            good = fail = retest = 0.0
            for move in production.move_finished_ids:
                # On ne compte que ce qui est réellement produit (mouvements 'done').
                if move.state != "done":
                    continue
                category = production._pkl_classify_move(move)
                if category == "good":
                    good += move.quantity
                elif category == "fail":
                    fail += move.quantity
                elif category == "retest":
                    retest += move.quantity

            output = good + fail + retest
            production.pkl_qty_good = good
            production.pkl_qty_fail = fail
            production.pkl_qty_retest = retest
            production.pkl_qty_output = output

            # Garde-fou division par zéro.
            production.pkl_fpy = (good / output) if output else 0.0
            production.pkl_fail_rate = (fail / output) if output else 0.0
            production.pkl_retest_rate = (retest / output) if output else 0.0

    # NB : le "rendement après retest" est un indicateur INTER-OF (un RT peut
    # revenir conforme dans un OF aval). Il n'est PAS calculable de façon fiable
    # sur un OF isolé et n'est donc volontairement pas exposé ici. Les quantités
    # good/fail/retest sont agrégées par étape/projet dans pkl.mrp.yield.report
    # pour permettre sa dérivation ; le calcul exact nécessite la généalogie de
    # lot (prévu en V2).
