# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import qrcode
import base64
from io import BytesIO
import logging
import datetime
import pytz

_logger = logging.getLogger(__name__)

class BulkRepairPortal(http.Controller):
    
    @http.route(['/repair/bulk/<int:partner_id>/<string:token>'], type='http', auth="public", website=True)
    def portal_bulk_repair_view(self, partner_id, token=None, **kw):
        """
        Muestra todas las reparaciones de un cliente asociadas a entradas masivas
        Versión simplificada sin verificación de token
        """
        try:
            # Obtener el partner sin verificar token
            Partner = request.env['res.partner'].sudo().browse(partner_id)
            if not Partner or Partner.axer_portal_token != token:
                return request.render('axer_repair.bulk_repair_invalid_token', {})
            
            
            current_date = datetime.datetime.now()
            fifteen_days_ago = current_date - datetime.timedelta(days=15)
            seven_days_ago = current_date - datetime.timedelta(days=7)
            # Buscar todas las reparaciones recientes para este cliente
            recent_repairs = request.env['repair.order'].sudo().search([
                ('partner_id', '=', partner_id),
                '|',
                # Repairs normales (no entregadas) de los últimos 15 días
                '&',
                ('state', '!=', 'handover'),
                ('create_date', '>=', fifteen_days_ago.strftime('%Y-%m-%d %H:%M:%S')),
                # Repairs entregadas de los últimos 7 días
                '&',
                ('state', '=', 'handover'),
                ('create_date', '>=', seven_days_ago.strftime('%Y-%m-%d %H:%M:%S'))
            ], order='create_date desc')
            
            # Generar QR para cada reparación
            repairs_with_qr = []
            for repair in recent_repairs:
                # Generar URL para seguimiento individual
                # track_url = f"{request.httprequest.url_root.rstrip('/')}/repair/track/{repair.id}"
                track_url = f"{request.httprequest.url_root.rstrip('/')}/repair/track/{repair.id}/{repair.access_token}"
                
                # Crear código QR
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(track_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Convertir a base64
                buffer = BytesIO()
                img.save(buffer)
                qr_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                # Añadir a la lista - solo leer campos específicos
                repair_dict = repair.read([
                    'id', 'name', 'partner_id', 'product_id', 'imei', 'serial',
                    'state', 'description', 'typerepair', 'create_date', 'branch_id',
                    'access_token',
                    'faceid', 'wifi', 'signal', 'screen', 'camera', 'speaker',
                    'microphone', 'charging', 'buttons', 'touch', 'sim',
                    'camerafront', 'truetone', 'panic', 'screw', 'earphone',
                    'flash', 'battery', 'estimated_budget', 'currency_id'
                ])[0]
                repair_dict['qr_image'] = qr_image
                repair_dict['track_url'] = track_url
                repairs_with_qr.append(repair_dict)
            
            # Group by fecha de creación (día)
            from collections import defaultdict
            
            repairs_by_day = defaultdict(list)
            formatted_days = {}
            
            for repair in repairs_with_qr:
                create_date = repair['create_date']
                # Si create_date ya es un objeto datetime
                if isinstance(create_date, datetime.datetime):
                    day_key = create_date.strftime('%Y-%m-%d')
                    formatted_date = create_date.strftime('%d/%m/%Y')
                # Si create_date es un string
                else:
                    create_date = datetime.datetime.strptime(create_date, '%Y-%m-%d %H:%M:%S')
                    day_key = create_date.strftime('%Y-%m-%d')
                    formatted_date = create_date.strftime('%d/%m/%Y')
                    
                repairs_by_day[day_key].append(repair)
                
                # Guardar también la fecha formateada
                if day_key not in formatted_days:
                    formatted_days[day_key] = formatted_date
            
            # Obtener información de la sucursal para mostrar en el encabezado
            branch_name = "No especificada"
            if repairs_with_qr:
                first_repair = repairs_with_qr[0]
                if first_repair.get('branch_id'):
                    branch_name = first_repair['branch_id'][1]
            
            # Preparar primera fecha para mostrar
            first_day = ""
            if formatted_days:
                first_day = list(formatted_days.values())[0]
            else:
                first_day = datetime.datetime.now().strftime('%d/%m/%Y')
            
            # Conteo por estado y lista plana de reparaciones
            from collections import Counter
            state_counts = Counter()
            all_repairs = []
            for day_key, day_list in repairs_by_day.items():
                for r in day_list:
                    state_counts[r.get('state', '')] += 1
                    all_repairs.append(r)

            active_count = state_counts.get('under_repair', 0) + state_counts.get('test', 0)
            done_count = state_counts.get('done', 0) + state_counts.get('handover', 0)
            pending_count = state_counts.get('draft', 0) + state_counts.get('confirmed', 0)

            # Devolver la página web con todos los datos preparados
            return request.render('axer_repair.bulk_repair_portal_template', {
                'partner': Partner,
                'repairs_by_day': dict(repairs_by_day),
                'formatted_days': formatted_days,
                'repair_count': len(recent_repairs),
                'company': request.env.company,
                'today': datetime.datetime.now().strftime('%d/%m/%Y'),
                'first_day': first_day,
                'branch_name': branch_name,
                'all_repairs': all_repairs,
                'state_counts': dict(state_counts),
                'active_count': active_count,
                'done_count': done_count,
                'pending_count': pending_count,
            })
            
        except Exception as e:
            _logger.error(f"Error inesperado: {str(e)}", exc_info=True)
            return request.render('axer_repair.bulk_repair_error', {'error_message': f'Ha ocurrido un error inesperado: {str(e)}'})

    @http.route(['/repair/track/<int:repair_id>/<string:token>'], type='http', auth="public", website=True)
    def portal_repair_tracking(self, repair_id, token=None, **kw):
        """
        Permite seguimiento individual de una reparación
        Versión simplificada sin verificación de token
        """
        try:
            # Obtener la reparación sin verificar token
            Repair = request.env['repair.order'].sudo().browse(repair_id)
            if not Repair or Repair.access_token != token:
                return request.render('axer_repair.bulk_repair_invalid_token', {})
            
            # Generar URL para seguimiento individual (AÑADIR ESTA LÍNEA)
            # track_url = f"{request.httprequest.url_root.rstrip('/')}/repair/track/{repair_id}"
            track_url = f"{request.httprequest.url_root.rstrip('/')}/repair/track/{repair_id}/{Repair.access_token}"
            
            # Generar historial de estados
            # history = self._get_repair_history(Repair)
                        # Generar historial de estados
            _logger.info("Generando historial de estados...")
            history = self._get_repair_history_debug(Repair)


                        # Log del historial generado
            _logger.info(f"Historial generado con {len(history)} estados:")
            for idx, event in enumerate(history):
                _logger.info(f"Evento {idx+1}: {event['name']} - Fecha: {event.get('formatted_date')} - Active: {event['active']}")
            
            
            # Generar etiqueta para imprimir
            # label_url = f"{request.httprequest.url_root.rstrip('/')}/repair/label/{repair_id}"
            label_url = f"{request.httprequest.url_root.rstrip('/')}/repair/label/{repair_id}/{Repair.access_token}"
            
            # Calcular porcentaje de progreso
            progress_percentage = 0
            if hasattr(Repair, 'progress_percentage'):
                progress_percentage = Repair.progress_percentage
            else:
                # Cálculo básico de progreso basado en el estado
                state_progress = {
                    'draft': 10,
                    'confirmed': 25,
                    'ready': 40,
                    'under_repair': 60,
                    'test': 80,
                    'done': 90,
                    'handover': 100,
                    'cancel': 0,
                    'guarantee': 50
                }
                progress_percentage = state_progress.get(Repair.state, 0)
            
            # Generar URL de retorno al listado bulk
            bulk_url = ''
            if Repair.partner_id and Repair.partner_id.axer_portal_token:
                bulk_url = f"{request.httprequest.url_root.rstrip('/')}/repair/bulk/{Repair.partner_id.id}/{Repair.partner_id.axer_portal_token}"

            # Devolver la página web
            return request.render('axer_repair.repair_track_template', {
                'repair': Repair,
                'history': history,
                'label_url': label_url,
                'company': request.env.company,
                'progress_percentage': progress_percentage,
                'track_url': track_url,
                'bulk_url': bulk_url,
            })
            
        except Exception as e:
            _logger.error(f"Error inesperado: {str(e)}", exc_info=True)
            return request.render('axer_repair.bulk_repair_error', {'error_message': f'Ha ocurrido un error inesperado: {str(e)}'})
    
    @http.route(['/repair/label/<int:repair_id>/<string:token>'], type='http', auth="public", website=True)
    def portal_repair_label(self, repair_id, token=None, **kw):
        """
        Muestra la etiqueta para impresión for the customer
        Versión simplificada sin verificación de token
        """
        try:
            # Obtener la reparación sin verificar token
            Repair = request.env['repair.order'].sudo().browse(repair_id)
            if not Repair or Repair.access_token != token:
                 return request.render('axer_repair.bulk_repair_invalid_token', {})
            
            # Generar URL para seguimiento individual
            # track_url = f"{request.httprequest.url_root.rstrip('/')}/repair/track/{repair_id}"
            track_url = f"{request.httprequest.url_root.rstrip('/')}/repair/track/{repair_id}/{Repair.access_token}"
            
            # Crear código QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(track_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convertir a base64
            buffer = BytesIO()
            img.save(buffer)
            qr_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Devolver la página web
            return request.render('axer_repair.repair_label_template', {
                'repair': Repair,
                'qr_image': qr_image,
                'track_url': track_url,
                'company': request.env.company,
            })
            
        except Exception as e:
            _logger.error(f"Error inesperado: {str(e)}", exc_info=True)
            return request.render('axer_repair.bulk_repair_error', {'error_message': 'Ha ocurrido un error inesperado'})
    
     #funcion inicio 
    # Actualización para el controlador (bulk_web.py)
    def _get_repair_history_debug(self, repair):
        """
        Genera un historial de los cambios de estado de la reparación con registros de depuración
        """
        _logger.info("=== INICIO _get_repair_history_debug ===")
        from odoo import fields
        
        # Define estados y su información de visualización (código existente)
        state_mapping = {
            'draft': {
                'name': 'Condition rating',
                'icon': 'clipboard-check',
                'color': 'primary',
                'description': 'Device recibido para evaluación'
            },
            'confirmed': {
                'name': 'Confirmed',
                'icon': 'check-circle',
                'color': 'info',
                'description': 'Reparación confirmada'
            },
            'ready': {
                'name': 'Listo para reparar',
                'icon': 'tools',
                'color': 'primary',
                'description': 'Listo para comenzar la reparación'
            },
            'under_repair': {
                'name': 'Under repair',
                'icon': 'wrench',
                'color': 'warning',
                'description': 'Device en proceso de reparación'
            },
            'test': {
                'name': 'En prueba',
                'icon': 'microscope',
                'color': 'info',
                'description': 'Realizando pruebas finales'
            },
            '2binvoiced': {
                'name': 'Para facturar',
                'icon': 'file-invoice-dollar',
                'color': 'secondary',
                'description': 'Pending de facturación'
            },
            'done': {
                'name': 'Reparado',
                'icon': 'check-double',
                'color': 'success',
                'description': 'Reparación completada'
            },
            'handover': {
                'name': 'Handed over',
                'icon': 'handshake',
                'color': 'success',
                'description': 'Device entregado al cliente'
            },
            'cancel': {
                'name': 'Cancelled',
                'icon': 'times-circle',
                'color': 'danger',
                'description': 'Reparación cancelada'
            },
            'guarantee': {
                'name': 'Garantía',
                'icon': 'shield-alt',
                'color': 'primary',
                'description': 'En revisión por garantía'
            }
        }
        
        # Secuencia normal de estados en una reparación según el modelo
        state_sequence = ['draft', 'confirmed', 'ready', 'under_repair', 'test', 'done', 'handover']
        _logger.info(f"State actual de la reparación: {repair.state}")
        
        # Posición del estado actual en la secuencia
        current_state_idx = -1
        if repair.state in state_sequence:
            current_state_idx = state_sequence.index(repair.state)
            _logger.info(f"Posición en la secuencia: {current_state_idx+1} de {len(state_sequence)}")
        else:
            _logger.info(f"State {repair.state} fuera de la secuencia normal")
        
        # Diccionario para mapear nombres en inglés a códigos de estado
        state_name_to_code = {
            # Valores en inglés
            'Quotation': 'draft',
            'Confirmed': 'confirmed',
            'Ready to Repair': 'ready',
            'Under Repair': 'under_repair',
            'To be Invoiced': '2binvoiced',
            'Repaired': 'done',
            'Test': 'test',
            'Cancelled': 'cancel',
            'Handed over': 'handover',
            'Guarantee': 'guarantee',
            # Valores en español
            'Cotización': 'draft',
            'Confirmed': 'confirmed',
            'Listo para Reparar': 'ready',
            'Under repair': 'under_repair',
            'Para facturar': '2binvoiced',
            'Reparado': 'done',
            'Prueba': 'test',
            'Cancelled': 'cancel',
            'Garantía': 'guarantee'
        }
        
        
        # Cambios de estado a través del ORM. La consulta SQL anterior filtraba
        # por 'tv.field_desc', columna que Odoo 17 eliminó de la tabla de
        # seguimiento: la página de seguimiento for the customer respondía con un
        # error del servidor. Además, así se respeta el idioma del usuario en
        # lugar de comparar con una lista de traducciones escritas a mano.
        seguimientos = request.env['mail.tracking.value'].sudo().search([
            ('mail_message_id.model', '=', 'repair.order'),
            ('mail_message_id.res_id', '=', repair.id),
            ('field_id.name', '=', 'state'),
        ], order='id asc')

        state_changes = [
            (s.mail_message_id.id, s.mail_message_id.create_date,
             s.old_value_char, s.new_value_char)
            for s in seguimientos
        ]
        _logger.info("Encontrados %d cambios de estado", len(state_changes))

        # Los valores guardados son las etiquetas traducidas; se completa el
        # diccionario con las del propio campo para no depender de la lista fija.
        etiquetas = dict(repair._fields['state']._description_selection(request.env))
        for codigo, etiqueta in etiquetas.items():
            state_name_to_code.setdefault(etiqueta, codigo)

        # Obtener zona horaria del usuario
        user_tz = request.env.user.tz or 'UTC'
        _logger.info(f"Zona horaria del usuario: {user_tz}")
        
        # Función para convertir a zona horaria del usuario y formatear
        def format_date_for_display(dt):
            if not dt:
                _logger.warning("Intentando formatear una fecha nula")
                return None
                
            try:
                # Asegurarse de que tiene zona horaria
                if dt.tzinfo is None:
                    _logger.info(f"Fecha sin zona horaria: {dt}. Asumiendo UTC.")
                    dt = pytz.utc.localize(dt)
                    
                # Convertir a zona horaria del usuario
                local_tz = pytz.timezone(user_tz)
                local_dt = dt.astimezone(local_tz)
                _logger.info(f"Fecha convertida a zona horaria: {local_dt}")
                
                # Formatear
                formatted = local_dt.strftime('%d/%m/%Y %H:%M:%S')
                _logger.info(f"Fecha formateada: {formatted}")
                return formatted
            except Exception as e:
                _logger.error(f"Error al formatear fecha {dt}: {str(e)}")
                return str(dt)
        
        # Diccionario para almacenar las fechas de cada cambio de estado
        state_dates = {
            'draft': repair.create_date  # State inicial
        }
        _logger.info(f"Fecha inicial (creación): {repair.create_date}")
        
        # Procesar los cambios de estado
        for _, change_date, old_value, new_value in state_changes:
            if new_value in state_name_to_code:
                state_code = state_name_to_code[new_value]
                state_dates[state_code] = change_date
                _logger.info(f"State {state_code} tiene fecha: {change_date}")
        
        # Generar el historial basado en las fechas reales
        history = []
        
        # Añadir todos los estados hasta el actual como "activos"
        for i, state in enumerate(state_sequence):
            entry = {}
            
            if state in state_dates:  # Este estado tiene una fecha registrada
                date_obj = state_dates[state]
                formatted_date = format_date_for_display(date_obj)
                
                entry = {
                    'date': date_obj,
                    'formatted_date': formatted_date,
                    'state': state,
                    'name': state_mapping[state]['name'],
                    'icon': state_mapping[state]['icon'],
                    'color': state_mapping[state]['color'],
                    'description': state_mapping[state]['description'],
                    'active': True
                }
                _logger.info(f"State {state} ({state_mapping[state]['name']}): "
                            f"Tiene fecha registrada {formatted_date}")
                
            elif i <= current_state_idx:
                # State que debería estar activo pero sin fecha registrada
                _logger.info(f"State {state} ({state_mapping[state]['name']}): "
                            f"Debería estar activo pero sin fecha registrada")
                
                # Intentar usar la fecha del estado anterior + 1 segundo
                prev_date = None
                if i > 0 and state_sequence[i-1] in state_dates:
                    prev_date = state_dates[state_sequence[i-1]]
                    if prev_date:
                        prev_date = prev_date + datetime.timedelta(seconds=1)
                        _logger.info(f"  - Usando fecha del estado anterior + 1s: {prev_date}")
                else:
                    prev_date = repair.create_date
                    _logger.info(f"  - Usando fecha de creación: {prev_date}")
                
                formatted_date = format_date_for_display(prev_date)
                
                entry = {
                    'date': prev_date,
                    'formatted_date': formatted_date,
                    'state': state,
                    'name': state_mapping[state]['name'],
                    'icon': state_mapping[state]['icon'],
                    'color': state_mapping[state]['color'],
                    'description': state_mapping[state]['description'],
                    'active': True
                }
            else:
                # State futuro
                _logger.info(f"State {state} ({state_mapping[state]['name']}): State futuro")
                
                entry = {
                    'date': None,
                    'formatted_date': None,
                    'state': state,
                    'name': state_mapping[state]['name'],
                    'icon': state_mapping[state]['icon'],
                    'color': 'gray',
                    'description': state_mapping[state]['description'],
                    'active': False
                }
            
            # Add entrada al historial
            history.append(entry)
            # Verificar que la entrada tenga los datos esperados
            _logger.info(f"Entrada añadida al historial: {entry['name']}, "
                        f"Fecha: {entry.get('formatted_date')}, "
                        f"Active: {entry['active']}")
        
        # States especiales que no siguen la secuencia normal
        special_states = ['cancel', 'guarantee', '2binvoiced']
        if repair.state in special_states:
            _logger.info(f"State especial detectado: {repair.state}")
            
            if repair.state in state_dates:
                # State especial con fecha registrada
                date_obj = state_dates[repair.state]
                formatted_date = format_date_for_display(date_obj)
                
                entry = {
                    'date': date_obj,
                    'formatted_date': formatted_date,
                    'state': repair.state,
                    'name': state_mapping[repair.state]['name'],
                    'icon': state_mapping[repair.state]['icon'],
                    'color': state_mapping[repair.state]['color'],
                    'description': state_mapping[repair.state]['description'],
                    'active': True
                }
                _logger.info(f"State especial {repair.state}: Con fecha registrada {formatted_date}")
            else:
                # State especial sin fecha registrada
                now = fields.Datetime.now()
                formatted_date = format_date_for_display(now)
                
                entry = {
                    'date': now,
                    'formatted_date': formatted_date,
                    'state': repair.state,
                    'name': state_mapping[repair.state]['name'],
                    'icon': state_mapping[repair.state]['icon'],
                    'color': state_mapping[repair.state]['color'],
                    'description': state_mapping[repair.state]['description'],
                    'active': True
                }
                _logger.info(f"State especial {repair.state}: "
                            f"Sin fecha registrada, usando ahora: {formatted_date}")
            
            # Add entrada del estado especial
            history.append(entry)
        
        _logger.info(f"Historial completo generado con {len(history)} entradas")
        _logger.info("=== FIN _get_repair_history_debug ===")
        return history

    def _map_state_name_to_code(self, state_name):
        """
        Mapea el nombre visible del estado (en inglés) al código interno
        """
        state_mapping = {
            'Quotation': 'draft',
            'Confirmed': 'confirmed',
            'Ready to Repair': 'ready',
            'Under Repair': 'under_repair',
            'To be Invoiced': '2binvoiced',
            'Repaired': 'done',
            'Test': 'test',
            'Cancelled': 'cancel',
            'Handed over': 'handover',
            'Guarantee': 'guarantee'
        }
        return state_mapping.get(state_name)