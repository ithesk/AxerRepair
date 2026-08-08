from odoo import http, fields
from odoo.http import request
import json
from dateutil import parser
import logging

_logger = logging.getLogger(__name__)

class DocuSealController(http.Controller):

    @http.route('/docuseal/webhook/', type='jsonrpc', auth='public', methods=['POST'], csrf=False)
    def docuseal_webhook(self, **kwargs):
        """Aviso del servicio de firma de que el cliente ha firmado.

        Exige el secreto compartido: sin él, cualquiera podría dar una
        reparación por firmada y disparar el aviso al cliente.
        """
        import hmac
        secreto = request.env['ir.config_parameter'].sudo().get_param(
            'axer_repair.webhook_secret')
        recibido = request.httprequest.headers.get('X-Webhook-Secret', '')
        if not secreto or not hmac.compare_digest(recibido, secreto):
            _logger.warning('Webhook de firma rechazado: secreto incorrecto')
            return {'status': 'error', 'message': 'No autorizado'}

        data = json.loads(request.httprequest.data)
        if data.get('event_type') == 'form.completed':
            submission_data = data.get('data', {})
            submission_id = submission_data.get('submission_id')
            status = submission_data.get('status')
            completed_at = submission_data.get('completed_at')
            _logger.info('Submission ID: %s', submission_id)

            try:
                signed_date = parser.parse(completed_at)
            except ValueError:
                return {'status': 'error', 'message': 'Invalid date format'}
            
            repair_order = request.env['repair.order'].sudo().search([('docuseal_document_id', '=', submission_id)], limit=1)

            if repair_order:
                repair_order.write({
                    'signature_status': 'signed',
                    'signed_date': fields.Datetime.to_string(signed_date),
                })
                repair_order.whatsapp_confirm()
                return {'status': 'success'}
            else:
                _logger.warning('No repair order found for submission ID: %s', submission_id)
                return {'status': 'error', 'message': 'No repair order found'}
        else:
            _logger.warning('Invalid event type: %s', data.get('event_type'))
            return {'status': 'error', 'message': 'Invalid event type'}
        

