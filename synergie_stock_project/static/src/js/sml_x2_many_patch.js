/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { SMLX2ManyField } from "@stock/fields/stock_move_line_x2_many_field";

/**
 * [TEMPORAIRE] Blocage par projet retiré (cf. décision Synergie) : le
 * sélecteur de quant du widget "Detailed Operations" (champ move_line_ids,
 * widget sml_x2_many, popup "Move Detail" — stock.view_stock_move_operations)
 * n'est PLUS restreint par projet ici. Remplacé par un regroupement par
 * projet actif par défaut, pour guider visuellement l'utilisateur sans
 * bloquer la sélection (cf. README §5.3).
 *
 * Rappel du contexte : ce widget construit son domaine/contexte de recherche
 * de quants EN JAVASCRIPT, dans onAdd() (cf. stock/static/src/fields/
 * stock_move_line_x2_many_field.js). Le contexte de champ XML
 * (this.props.context) n'y est PAS fusionné dans ce chemin précis
 * (contrairement à X2ManyField.onAdd() de base) : impossible de forcer le
 * regroupement uniquement via un attribut `context` XML sur move_line_ids,
 * d'où ce patch JS malgré tout.
 *
 * [À vérifier v19] Ce patch DUPLIQUE la logique de onAdd() (pas de point
 * d'extension isolant la construction du domaine/contexte) pour n'y changer
 * que le contexte transmis à selectCreate(). Fragile aux futures évolutions
 * du cœur : si onAdd() change de signature/logique côté Odoo, ce patch doit
 * être resynchronisé à la main.
 *
 * Pour rétablir le blocage dur précédent : réintroduire dans le domaine
 * `["lot_id.project_id", "=", projectId]` quand
 * `this.props.record.data.project_id` est renseigné (cf. historique git).
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
            // --- Ajout Synergie : regroupement par projet actif par défaut ---
            group_by: "project_id",
            // --- Fin ajout ---
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
