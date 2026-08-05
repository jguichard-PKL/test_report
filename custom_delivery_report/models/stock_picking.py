from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def bl_get_addressee(self):
        """Invoice address of the linked order (top-right block)."""
        self.ensure_one()
        return self.sale_id.partner_invoice_id or self.partner_id

    def bl_get_ship_to(self):
        """Delivery address of this transfer ("Lieu de livraison" block).

        Uses the picking's own partner_id (not the order's partner_shipping_id)
        so it reflects any override made on the transfer itself, even after
        the order has been confirmed.
        """
        self.ensure_one()
        return self.partner_id

    def bl_get_report_date_str(self):
        self.ensure_one()
        date = self.date_done or self.scheduled_date
        if not date:
            return ''
        date = fields.Datetime.context_timestamp(self, date)
        return date.strftime('%d/%m/%y')

    def bl_get_currency(self):
        self.ensure_one()
        return self.sale_id.currency_id or self.company_id.currency_id

    def bl_get_lines(self):
        """Move lines to display on the report, in a stable order."""
        self.ensure_one()
        return self.move_line_ids.filtered(lambda l: l.quantity > 0).sorted('id')

    def bl_get_line_price_unit(self, move_line):
        sale_line = move_line.move_id.sale_line_id
        return sale_line.price_unit if sale_line else 0.0

    def bl_get_line_amount(self, move_line):
        return move_line.quantity * self.bl_get_line_price_unit(move_line)

    def bl_get_total_qty(self):
        self.ensure_one()
        return sum(self.bl_get_lines().mapped('quantity'))

    def bl_get_total_amount(self):
        self.ensure_one()
        return sum(self.bl_get_line_amount(line) for line in self.bl_get_lines())
