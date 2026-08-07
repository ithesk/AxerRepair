from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

class PortalRepair(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        """Alimenta el contador de la tarjeta 'Repairs' del portal."""
        values = super()._prepare_home_portal_values(counters)
        if 'repair_count' in counters:
            partner = request.env.user.partner_id
            values['repair_count'] = request.env['repair.order'].search_count(
                [('partner_id', '=', partner.id)]
            )
        return values

    @http.route(['/my/repairs', '/my/repairs/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_repairs(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id

        RepairOrder = request.env['repair.order']
        domain = [('partner_id', '=', partner.id)]

        # Paginación
        repair_count = RepairOrder.search_count(domain)
        pager = portal_pager(
            url="/my/repairs",
            total=repair_count,
            page=page,
            step=self._items_per_page
        )

        repairs = RepairOrder.search(domain, limit=self._items_per_page, offset=pager['offset'])

        values.update({
            'repairs': repairs,
            'page_name': 'repair',
            'pager': pager,
            'default_url': '/my/repairs',
        })

        return request.render("axer_repair.portal_my_repairs", values)
    

    @http.route(['/my/repair/<int:repair_id>'], type='http', auth="user", website=True)
    def portal_repair_detail(self, repair_id, **kw):
        repair = request.env['repair.order'].browse(repair_id)
        if not repair.exists() or repair.partner_id != request.env.user.partner_id:
            return request.redirect('/my/repairs')

        values = {
            'repair': repair,
            'page_name': 'repair',
        }

        return request.render("axer_repair.portal_my_repairs_details", values)

    