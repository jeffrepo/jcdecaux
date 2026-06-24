# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    sap_id = fields.Char(
        string="SAP ID",
        copy=False,
        index=True,
        help="External SAP identifier. When set, it must be unique across contacts.",
    )

    def _auto_init(self):
        result = super()._auto_init()
        self.env.cr.execute(
            """
                CREATE UNIQUE INDEX IF NOT EXISTS res_partner_sap_id_unique_not_empty
                    ON res_partner (sap_id)
                 WHERE sap_id IS NOT NULL AND sap_id != ''
            """
        )
        return result

    @api.constrains("sap_id")
    def _check_unique_sap_id(self):
        for partner in self:
            if not partner.sap_id:
                continue
            duplicate = partner.with_context(active_test=False).search(
                [("id", "!=", partner.id), ("sap_id", "=", partner.sap_id)],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("The SAP ID '%(sap_id)s' is already assigned to '%(partner)s'.")
                    % {"sap_id": partner.sap_id, "partner": duplicate.display_name}
                )

    @api.constrains("vat", "parent_id", "commercial_partner_id")
    def _check_unique_vat(self):
        """Prevent VAT duplicates while respecting Odoo commercial contacts.

        Child contacts can inherit commercial information from their parent company.
        Therefore, a repeated VAT is only allowed inside the same commercial entity;
        another unrelated contact/company cannot use that VAT.
        """
        for partner in self:
            normalized_vat = partner._normalize_unique_vat(partner.vat)
            if not normalized_vat:
                continue

            duplicate = partner._find_duplicate_vat(normalized_vat)
            if duplicate:
                raise ValidationError(
                    _(
                        "The VAT '%(vat)s' is already assigned to '%(partner)s'. "
                        "VAT numbers must be unique across contacts."
                    )
                    % {"vat": partner.vat, "partner": duplicate.display_name}
                )

    @api.model
    def _normalize_unique_vat(self, vat):
        return (vat or "").replace(" ", "").replace("-", "").upper()

    def _find_duplicate_vat(self, normalized_vat):
        self.ensure_one()
        commercial_partner = self.commercial_partner_id or self
        self.env.cr.execute(
            """
                SELECT id
                  FROM res_partner
                 WHERE id != %s
                   AND COALESCE(commercial_partner_id, id) != %s
                   AND vat IS NOT NULL
                   AND UPPER(REPLACE(REPLACE(vat, ' ', ''), '-', '')) = %s
                 LIMIT 1
            """,
            (self.id, commercial_partner.id, normalized_vat),
        )
        result = self.env.cr.fetchone()
        return self.browse(result[0]) if result else self.env["res.partner"]
