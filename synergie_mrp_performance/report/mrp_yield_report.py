# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class PklMrpYieldReport(models.Model):
    """Reporting agrégé du rendement de fabrication (vue SQL en lecture seule).

    Pourquoi une vue SQL dédiée plutôt que de simplement piloter sur les champs
    calculés de mrp.production ? Parce qu'un POURCENTAGE NE S'ADDITIONNE PAS.
    En pivot, un FPY ne peut être ni sommé ni moyenné correctement.

    Ce modèle expose donc DEUX familles de mesures :
    - les QUANTITÉS (qty_good/fail/retest/output), additionnables → "vue valeur" ;
    - les TAUX (fpy/fail_rate/retest_rate), exprimés en % → "vue %".

    Les taux ne sont PAS de simples colonnes sommées : l'override de
    ``_read_group`` recalcule chaque taux comme un RATIO DE SOMMES
    (Σ numérateur / Σ dénominateur) au niveau d'agrégation demandé, ce qui donne
    le rendement correct quel que soit le regroupement (projet, étape, période…).

    Granularité de base : une ligne par ordre de fabrication.
    """

    _name = "pkl.mrp.yield.report"
    _description = "Rendement de fabrication (agrégé)"
    _auto = False
    _order = "date desc"

    # Taux exposés en % (0–100) -> mappés vers (numérateur, dénominateur) pour
    # le recalcul ratio-de-sommes dans _read_group.
    _PKL_RATE_FIELDS = {
        "fpy": ("qty_good", "qty_output"),
        "fail_rate": ("qty_fail", "qty_output"),
        "retest_rate": ("qty_retest", "qty_output"),
    }

    production_id = fields.Many2one(
        "mrp.production", string="Ordre de fabrication", readonly=True
    )
    product_id = fields.Many2one(
        "product.product", string="Produit / Étape", readonly=True
    )
    project_id = fields.Many2one(
        "project.project", string="Projet", readonly=True
    )
    company_id = fields.Many2one("res.company", string="Société", readonly=True)
    state = fields.Selection(
        selection=[
            ("draft", "Brouillon"),
            ("confirmed", "Confirmé"),
            ("progress", "En cours"),
            ("to_close", "À clôturer"),
            ("done", "Terminé"),
            ("cancel", "Annulé"),
        ],
        string="État",
        readonly=True,
    )
    date = fields.Datetime(string="Date", readonly=True)

    # --- Mesures "valeur" (additionnables) ---
    qty_good = fields.Float("Qté conforme", readonly=True)
    qty_fail = fields.Float("Qté fail", readonly=True)
    qty_retest = fields.Float("Qté retest", readonly=True)
    qty_output = fields.Float("Qté totale testée", readonly=True)

    # --- Mesures "%" (ratio de sommes via _read_group) ---
    # Exprimées en points de pourcentage (0–100) pour un affichage lisible en
    # pivot (qui n'applique pas le widget percentage). aggregator='sum' pour
    # qu'elles soient proposées comme mesures ; la valeur agrégée est corrigée
    # dans _read_group (sinon Postgres sommerait bêtement les % par ligne).
    fpy = fields.Float(
        "FPY (%)", readonly=True, aggregator="sum", digits=(16, 2),
        help="First-pass yield = Σ conforme / Σ testé (recalculé par groupe).",
    )
    fail_rate = fields.Float(
        "Taux de fail (%)", readonly=True, aggregator="sum", digits=(16, 2),
        help="Σ fail / Σ testé (recalculé par groupe).",
    )
    retest_rate = fields.Float(
        "Taux de retest (%)", readonly=True, aggregator="sum", digits=(16, 2),
        help="Σ retest / Σ testé (recalculé par groupe).",
    )

    # ------------------------------------------------------------------
    # Agrégation correcte des taux : RATIO DE SOMMES (et non somme de %).
    #
    # Le pivot Odoo 19 passe par _read_grouping_sets ; le graph et la liste
    # groupée par _read_group. Les deux reçoivent des agrégats sous forme
    # 'champ:fonction' et renvoient des tuples (valeurs de groupe + agrégats).
    # On remplace chaque taux demandé par les sommes num/dénominateur réelles,
    # puis on recalcule 100 * Σ(num) / Σ(den) par ligne de regroupement.
    # ------------------------------------------------------------------
    def _pkl_build_plan(self, aggregates):
        """Retourne (real_aggregates, plan) où plan dit comment reconstruire
        chaque agrégat demandé à partir des agrégats réellement interrogés."""
        real = []

        def ensure(spec):
            if spec not in real:
                real.append(spec)
            return real.index(spec)

        plan = []  # ('direct', idx) | ('rate', num_idx, den_idx)
        for spec in aggregates:
            field_name = spec.split(":", 1)[0]
            if field_name in self._PKL_RATE_FIELDS:
                num, den = self._PKL_RATE_FIELDS[field_name]
                plan.append(("rate", ensure("%s:sum" % num), ensure("%s:sum" % den)))
            else:
                plan.append(("direct", ensure(spec)))
        return real, plan

    def _pkl_apply_plan(self, plan, agg_vals):
        """Reconstruit la ligne d'agrégats demandée (taux = ratio de sommes)."""
        out = []
        for item in plan:
            if item[0] == "direct":
                out.append(agg_vals[item[1]])
            else:
                num = agg_vals[item[1]] or 0.0
                den = agg_vals[item[2]] or 0.0
                out.append((100.0 * num / den) if den else 0.0)
        return tuple(out)

    def _read_group(self, domain, groupby=(), aggregates=(), having=(),
                    offset=0, limit=None, order=None):
        real, plan = self._pkl_build_plan(list(aggregates))
        rows = super()._read_group(
            domain, groupby, tuple(real), having=having,
            offset=offset, limit=limit, order=order,
        )
        n_group = len(groupby)
        return [
            tuple(row[:n_group]) + self._pkl_apply_plan(plan, row[n_group:])
            for row in rows
        ]

    def _read_grouping_sets(self, domain, grouping_sets, aggregates=(), order=None):
        real, plan = self._pkl_build_plan(list(aggregates))
        results = super()._read_grouping_sets(
            domain, grouping_sets, tuple(real), order=order,
        )
        out = []
        for group_spec, rows in zip(grouping_sets, results):
            n_group = len(group_spec)
            out.append([
                tuple(row[:n_group]) + self._pkl_apply_plan(plan, row[n_group:])
                for row in rows
            ])
        return out

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Note : 'quantity' est la quantité réalisée du stock.move (Odoo 17+).
        # Les move_finished_ids référencent stock_move.production_id ; les
        # consommations (raw) utilisent raw_material_production_id, donc ne sont
        # pas captées ici — on ne lit bien que les SORTIES de l'OF.
        # Les taux par ligne (fpy/...) sont stockés en % (0–100) ; leur
        # agrégation correcte (ratio de sommes) est gérée par _read_group /
        # _read_grouping_sets ci-dessus.
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    mp.id AS id,
                    mp.id AS production_id,
                    mp.product_id AS product_id,
                    mp.project_id AS project_id,
                    mp.company_id AS company_id,
                    mp.state AS state,
                    COALESCE(mp.date_finished, mp.date_start) AS date,
                    COALESCE(g.qty, 0.0) AS qty_good,
                    COALESCE(f.qty, 0.0) AS qty_fail,
                    COALESCE(r.qty, 0.0) AS qty_retest,
                    COALESCE(g.qty, 0.0) + COALESCE(f.qty, 0.0)
                        + COALESCE(r.qty, 0.0) AS qty_output,
                    CASE WHEN out_qty.total > 0.0
                         THEN 100.0 * COALESCE(g.qty, 0.0) / out_qty.total
                         ELSE 0.0 END AS fpy,
                    CASE WHEN out_qty.total > 0.0
                         THEN 100.0 * COALESCE(f.qty, 0.0) / out_qty.total
                         ELSE 0.0 END AS fail_rate,
                    CASE WHEN out_qty.total > 0.0
                         THEN 100.0 * COALESCE(r.qty, 0.0) / out_qty.total
                         ELSE 0.0 END AS retest_rate
                FROM mrp_production mp
                LEFT JOIN (
                    SELECT sm.production_id AS pid, SUM(sm.quantity) AS qty
                    FROM stock_move sm
                    JOIN mrp_production p ON p.id = sm.production_id
                    WHERE sm.state = 'done'
                      AND sm.product_id = p.product_id
                    GROUP BY sm.production_id
                ) g ON g.pid = mp.id
                LEFT JOIN (
                    SELECT sm.production_id AS pid, SUM(sm.quantity) AS qty
                    FROM stock_move sm
                    JOIN product_product pp ON pp.id = sm.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE sm.state = 'done'
                      AND pt.pkl_output_type = 'fail'
                    GROUP BY sm.production_id
                ) f ON f.pid = mp.id
                LEFT JOIN (
                    SELECT sm.production_id AS pid, SUM(sm.quantity) AS qty
                    FROM stock_move sm
                    JOIN product_product pp ON pp.id = sm.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    WHERE sm.state = 'done'
                      AND pt.pkl_output_type = 'retest'
                    GROUP BY sm.production_id
                ) r ON r.pid = mp.id
                LEFT JOIN LATERAL (
                    SELECT COALESCE(g.qty, 0.0) + COALESCE(f.qty, 0.0)
                           + COALESCE(r.qty, 0.0) AS total
                ) out_qty ON TRUE
            )
            """
            % self._table
        )
