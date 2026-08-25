/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { SMLX2ManyField } from "@stock/fields/stock_move_line_x2_many_field";

/**
 * Restreint au projet du mouvement le sélecteur de quant du widget
 * "Detailed Operations" (champ move_line_ids, widget sml_x2_many, popup
 * "Move Detail" — stock.view_stock_move_operations).
 *
 * Ce widget est un composant OWL qui construit son domaine de recherche de
 * quants EN JAVASCRIPT, dans onAdd() (cf. stock/static/src/fields/
 * stock_move_line_x2_many_field.js) : ["product_id", ...], ["location_id",
 * "child_of", ...], ["quantity", ">", 0.0]. Aucun attribut `domain` XML n'y
 * est lu — le domaine posé sur le champ quant_id côté serveur
 * (stock_move_line_views.xml) ne s'applique donc PAS à ce chemin, qui reste
 * un trou distinct malgré ce correctif-là (confirmé en test : sélection
 * manuelle d'un lot hors projet toujours possible via "Add a line").
 *
 * [À vérifier v19] Ce patch DUPLIQUE la logique de onAdd() (pas de point
 * d'extension isolant la construction du domaine) pour n'y ajouter qu'une
 * ligne. Fragile aux futures évolutions du cœur : si onAdd() change de
 * signature/logique côté Odoo, ce patch doit être resynchronisé à la main.
 */
patch(SMLX2ManyField.prototype, {
    async onAdd({ context, editable } = {}) {
        if (!this.props.record.data.show_quant) {
            return super.onAdd(...arguments);
        }
        // Compute the quant offset from move lines quantity changes that were not saved yet.
        // Hence, did not yet affect quant's quantity in DB.
        await this.updateDirtyQuantsData();
        context = {
            ...context,
            single_product: true,
            list_view_ref: "stock.view_stock_quant_tree_simple",
        };
        const productName = this.props.record.data.product_id.display_name;
        const title = _t("Add line: %s", productName);
        let domain = [
            ["product_id", "=", this.props.record.data.product_id.id],
            ["location_id", "child_of", this.props.context.default_location_id],
            ["quantity", ">", 0.0],
        ];
        if (this.quantListViewShowOnHandOnly) {
            domain.push(["on_hand", "=", true]);
        }
        // --- Ajout Synergie : restriction par projet du mouvement ---
        const projectId = this.props.record.data.project_id && this.props.record.data.project_id.id;
        if (projectId) {
            domain.push(["lot_id.project_id", "=", projectId]);
        }
        // --- Fin ajout ---
        if (this.dirtyQuantsData.size) {
            const notFullyUsed = [];
            const fullyUsed = [];
            for (const [quantId, quantData] of this.dirtyQuantsData.entries()) {
                if (quantData.available_quantity > 0) {
                    notFullyUsed.push(quantId);
                } else {
                    fullyUsed.push(quantId);
                }
            }
            if (fullyUsed.length) {
                domain = Domain.and([domain, [["id", "not in", fullyUsed]]]).toList();
            }
            if (notFullyUsed.length) {
                domain = Domain.or([domain, [["id", "in", notFullyUsed]]]).toList();
            }
        }
        return this.selectCreate({ domain, context, title });
    },
});
