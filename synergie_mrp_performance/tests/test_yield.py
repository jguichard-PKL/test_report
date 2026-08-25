# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPklYield(TransactionCase):
    """Validation minimale du calcul de FPY sur un OF avec un sous-produit fail."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")

        Product = cls.env["product.product"]
        # Produit principal conforme (good par défaut).
        cls.product_good = Product.create({
            "name": "DIE Conforme",
            "is_storable": True,
            "uom_id": cls.uom_unit.id,
        })
        # Article fail dédié (sous-produit, jamais scrappé).
        cls.product_fail = Product.create({
            "name": "DIE Fail",
            "is_storable": True,
            "uom_id": cls.uom_unit.id,
            "pkl_output_type": "fail",
        })

        # Emplacements (production -> stock).
        cls.location_prod = cls.env["stock.location"].search(
            [("usage", "=", "production")], limit=1
        )
        cls.location_stock = cls.env.ref("stock.stock_location_stock")

    def _make_finished_move(self, production, product, qty):
        """Crée un mouvement fini 'done' rattaché à l'OF (sortie de production)."""
        return self.env["stock.move"].create({
            "product_id": product.id,
            "product_uom": self.uom_unit.id,
            "product_uom_qty": qty,
            "quantity": qty,
            "state": "done",
            "location_id": self.location_prod.id,
            "location_dest_id": self.location_stock.id,
            "production_id": production.id,
        })

    def test_fpy_with_fail_byproduct(self):
        production = self.env["mrp.production"].create({
            "product_id": self.product_good.id,
            "product_qty": 100.0,
            "product_uom_id": self.uom_unit.id,
        })

        # 90 conformes + 10 fails => 100 testés, FPY = 0.90.
        self._make_finished_move(production, self.product_good, 90.0)
        self._make_finished_move(production, self.product_fail, 10.0)

        # Les champs sont des computed stockés : on force la relecture propre.
        production.invalidate_recordset()

        self.assertEqual(production.pkl_qty_good, 90.0)
        self.assertEqual(production.pkl_qty_fail, 10.0)
        self.assertEqual(production.pkl_qty_retest, 0.0)
        self.assertEqual(production.pkl_qty_output, 100.0)
        self.assertAlmostEqual(production.pkl_fpy, 0.90, places=4)
        self.assertAlmostEqual(production.pkl_fail_rate, 0.10, places=4)

    def test_fpy_no_output_is_zero(self):
        """Aucune sortie 'done' => pas de division par zéro."""
        production = self.env["mrp.production"].create({
            "product_id": self.product_good.id,
            "product_qty": 50.0,
            "product_uom_id": self.uom_unit.id,
        })
        production.invalidate_recordset()
        self.assertEqual(production.pkl_qty_output, 0.0)
        self.assertEqual(production.pkl_fpy, 0.0)
