# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class BarcodeKioskController(http.Controller):

    @http.route('/barcode_kiosk/process_scan', type='json', auth='user')
    def process_scan(self, session_id, barcode, operation_type=None):
        """
        Process barcode scan with operation type validation
        Returns: {
            'success': bool,
            'type': str,  # 'picking', 'product', 'location', 'lot', 'serial'
            'data': dict,
            'message': str,
            'scan_line_id': int
        }
        """
        try:
            _logger.info(f"=== Processing Scan ===")
            _logger.info(f"Session: {session_id}, Barcode: {barcode}, Operation: {operation_type}")
            
            Session = request.env['barcode.kiosk.session']
            Picking = request.env['stock.picking']
            Product = request.env['product.product']
            Location = request.env['stock.location']
            LotSerial = request.env['stock.lot']
            
            # Get session
            session = Session.browse(session_id)
            if not session.exists():
                return {
                    'success': False,
                    'message': 'Invalid session'
                }
            
            # Operation type from session
            session_operation_type = operation_type or session.operation_type
            
            # Priority 1: Check if it's a PICKING barcode
            picking = Picking.search([('name', '=', barcode)], limit=1)
            if picking:
                _logger.info(f"Found picking: {picking.name}, Type: {picking.picking_type_id.code}")
                
                # VALIDATE OPERATION TYPE MATCH
                picking_code = picking.picking_type_id.code
                
                # Define operation type to picking code mapping
                valid_codes = self._get_valid_picking_codes(session_operation_type)
                
                _logger.info(f"Session operation: {session_operation_type}")
                _logger.info(f"Valid codes: {valid_codes}")
                _logger.info(f"Picking code: {picking_code}")
                
                if picking_code not in valid_codes:
                    # WRONG OPERATION TYPE
                    operation_names = {
                        'incoming': 'Incoming (Receipts)',
                        'outgoing': 'Outgoing (Deliveries)',
                        'internal': 'Internal Transfers',
                        'incoming_return': 'Incoming Returns',
                        'outgoing_return': 'Outgoing Returns',
                    }
                    
                    picking_type_names = {
                        'incoming': 'Receipt',
                        'outgoing': 'Delivery',
                        'internal': 'Internal Transfer',
                    }
                    
                    current_session = operation_names.get(session_operation_type, session_operation_type)
                    scanned_type = picking_type_names.get(picking_code, picking_code)
                    
                    return {
                        'success': False,
                        'type': 'picking',
                        'message': f'❌ Operation Type Mismatch!\n\n'
                                   f'You scanned: {picking.name} ({scanned_type})\n'
                                   f'Current session: {current_session}\n\n'
                                   f'Please scan a {current_session} picking or switch session type.',
                        'data': {
                            'picking_name': picking.name,
                            'picking_type': scanned_type,
                            'session_type': current_session,
                        }
                    }
                
                # Valid picking - create scan line
                scan_line = request.env['barcode.kiosk.scan.line'].create({
                    'session_id': session_id,
                    'barcode': barcode,
                    # 'operation_type': 'operation_type',
                    'picking_id': picking.id,
                    'status': 'success',
                })
                
                # Update session picking
                session.write({'picking_id': picking.id})
                
                return {
                    'success': True,
                    'type': 'picking',
                    'message': f'✓ Picking {picking.name} scanned successfully',
                    'scan_line_id': scan_line.id,
                    'data': {
                        'id': picking.id,
                        'name': picking.name,
                        'partner': picking.partner_id.name if picking.partner_id else 'N/A',
                        'state': picking.state,
                        'picking_type': picking.picking_type_id.name,
                    }
                }
            
            # Priority 2: Check if it's a PRODUCT barcode
            product = Product.search([('barcode', '=', barcode)], limit=1)
            if product:
                _logger.info(f"Found product: {product.name}")
                
                # Check if session has a picking assigned
                if not session.picking_id:
                    return {
                        'success': False,
                        'message': '⚠️ Please scan a picking first before scanning products'
                    }
                
                # Validate product belongs to session operation type
                session_picking = session.picking_id
                picking_code = session_picking.picking_type_id.code
                valid_codes = self._get_valid_picking_codes(session_operation_type)
                
                if picking_code not in valid_codes:
                    return {
                        'success': False,
                        'message': f'❌ Cannot add product to {picking_code} picking in {session_operation_type} session'
                    }
                
                # Find or create move line
                move = session_picking.move_ids_without_package.filtered(
                    lambda m: m.product_id.id == product.id
                )
                
                if move:
                    # Update quantity
                    move[0].quantity += 1
                    qty_done = move[0].quantity
                    expected = move[0].product_uom_qty
                else:
                    # Create new move line
                    move = request.env['stock.move'].create({
                        'name': product.name,
                        'product_id': product.id,
                        'product_uom_qty': 1,
                        'quantity': 1,
                        'product_uom': product.uom_id.id,
                        'picking_id': session_picking.id,
                        'location_id': session_picking.location_id.id,
                        'location_dest_id': session_picking.location_dest_id.id,
                    })
                    qty_done = 1
                    expected = 1
                
                # Create scan line
                scan_line = request.env['barcode.kiosk.scan.line'].create({
                    'session_id': session_id,
                    'barcode': barcode,
                    'operation_type': 'product',
                    'product_id': product.id,
                    'picking_id': session_picking.id,
                    'quantity': 1,
                    'status': 'success',
                })
                
                return {
                    'success': True,
                    'type': 'product',
                    'message': f'✓ Product {product.name} added (Qty: {qty_done}/{expected})',
                    'scan_line_id': scan_line.id,
                    'data': {
                        'id': product.id,
                        'name': product.name,
                        'qty_done': qty_done,
                        'expected': expected,
                    }
                }
            
            # Priority 3: Check if it's a LOCATION barcode
            location = Location.search([('barcode', '=', barcode)], limit=1)
            if location:
                _logger.info(f"Found location: {location.name}")
                
                scan_line = request.env['barcode.kiosk.scan.line'].create({
                    'session_id': session_id,
                    'barcode': barcode,
                    'operation_type': 'location',
                    'location_id': location.id,
                    'status': 'success',
                })
                
                return {
                    'success': True,
                    'type': 'location',
                    'message': f'✓ Location {location.complete_name} scanned',
                    'scan_line_id': scan_line.id,
                    'data': {
                        'id': location.id,
                        'name': location.complete_name,
                    }
                }
            
            # Priority 4: Check if it's a LOT/SERIAL number
            lot = LotSerial.search([
                '|',
                ('name', '=', barcode),
                ('ref', '=', barcode)
            ], limit=1)
            
            if lot:
                _logger.info(f"Found lot/serial: {lot.name}")
                
                scan_line = request.env['barcode.kiosk.scan.line'].create({
                    'session_id': session_id,
                    'barcode': barcode,
                    'operation_type': 'lot' if lot.product_id.tracking == 'lot' else 'serial',
                    'lot_id': lot.id,
                    'product_id': lot.product_id.id,
                    'status': 'success',
                })
                
                return {
                    'success': True,
                    'type': 'lot' if lot.product_id.tracking == 'lot' else 'serial',
                    'message': f'✓ Lot/Serial {lot.name} scanned',
                    'scan_line_id': scan_line.id,
                    'data': {
                        'lot_name': lot.name,
                        'product_id': lot.product_id.id,
                        'product_name': lot.product_id.name,
                    }
                }
            
            # No match found
            _logger.warning(f"Barcode not found: {barcode}")
            
            # Create failed scan line
            scan_line = request.env['barcode.kiosk.scan.line'].create({
                'session_id': session_id,
                'barcode': barcode,
                'operation_type': 'unknown',
                'status': 'error',
            })
            
            return {
                'success': False,
                'message': f'❌ Barcode not recognized: {barcode}',
                'scan_line_id': scan_line.id,
            }
            
        except Exception as e:
            import traceback
            _logger.error(f"Error processing scan: {str(e)}")
            _logger.error(traceback.format_exc())
            
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
    
    def _get_valid_picking_codes(self, operation_type):
        """
        Returns valid picking type codes for a given operation type
        """
        mapping = {
            'incoming': ['incoming'],
            'outgoing': ['outgoing'],
            'internal': ['internal'],
            'incoming_return': ['incoming'],  # Returns use same type but marked differently
            'outgoing_return': ['outgoing'],
            'scrap': ['internal'],  # Scrap uses internal transfers
        }
        return mapping.get(operation_type, [])


    @http.route('/barcode_kiosk/create_session', type='json', auth='user', methods=['POST'])
    def create_session(self, picking_type_id=None):
        try:
            _logger.debug("create_session called with picking_type_id=%s", picking_type_id)

            # Find the default warehouse
            warehouse = request.env['stock.warehouse'].search([
                ('company_id', '=', request.env.company.id)
            ], limit=1)

            picking_type_map = {}
            if warehouse:
                picking_type_map = {
                    'incoming': warehouse.in_type_id.id,
                    'outgoing': warehouse.out_type_id.id,
                    'internal': warehouse.int_type_id.id,
                }
                _logger.debug("create_session picking_type_map: %s", picking_type_map)

            # Convert string key → integer ID if needed
            if isinstance(picking_type_id, str) and picking_type_id in picking_type_map:
                picking_type_id = picking_type_map[picking_type_id]

            # Create new session
            session = request.env['barcode.kiosk.session'].sudo().create({
                'picking_type_id': picking_type_id,
                'user_id': request.env.user.id,
            })

            _logger.info("New Barcode Session Created → %s", session.id)

            return {
                "success": True,
                "message": "New kiosk session created",
                "session_id": session.id,
                "session_name": session.name,
            }

        except Exception as e:
            _logger.exception("Error in create_session")

            return {
                "success": False,
                "message": "Error creating session: %s" % str(e),
                "session_id": None,
            }

    @http.route('/barcode_kiosk/get_pickings', type='json', auth='user')
    def get_pickings(self, session_id=None, operation_type=None, picking_types=None, show_returns=False):
        """
        Get pickings filtered by operation type
        """
        
        try:
            PickingType = request.env['stock.picking.type']
            Picking = request.env['stock.picking']
            
            _logger.info(f"=== Get Pickings Called ===")
            _logger.info(f"Operation Type: {operation_type}")
            _logger.info(f"Picking Types: {picking_types}")
            _logger.info(f"Show Returns: {show_returns}")
            
            # Build domain based on operation type
            domain = []
            
            if not picking_types:
                picking_types = []
            
            # Get picking type IDs that match the codes
            if picking_types:
                type_domain = []
                
                for ptype in picking_types:
                    if ptype in ['incoming', 'receipt']:
                        type_domain.append(('code', '=', 'incoming'))
                    elif ptype in ['outgoing', 'delivery']:
                        type_domain.append(('code', '=', 'outgoing'))
                    elif ptype == 'internal':
                        type_domain.append(('code', '=', 'internal'))
                
                if type_domain:
                    # Combine with OR logic
                    if len(type_domain) > 1:
                        search_domain = ['|'] * (len(type_domain) - 1) + type_domain
                    else:
                        search_domain = type_domain
                    
                    _logger.info(f"Picking Type Search Domain: {search_domain}")
                    picking_type_ids = PickingType.search(search_domain)
                    _logger.info(f"Found Picking Types: {picking_type_ids.mapped('name')}")
                    
                    if picking_type_ids:
                        domain.append(('picking_type_id', 'in', picking_type_ids.ids))
            
            # Handle returns - check if field exists first
            _logger.info(f"Checking for is_return field...")
            _logger.info(f"Available fields: {list(Picking._fields.keys())[:20]}...")  # Show first 20 fields
            
            if 'is_return' in Picking._fields:
                _logger.info("is_return field exists - using it")
                if show_returns:
                    domain.append(('is_return', '=', True))
                else:
                    domain.append(('is_return', '=', False))
            else:
                _logger.info("is_return field does NOT exist - using origin workaround")
                if show_returns:
                    # Include returns based on origin
                    domain.append('|')
                    domain.append(('origin', 'ilike', 'Return of'))
                    domain.append(('origin', 'ilike', 'return'))
                elif operation_type not in ['incoming_return', 'outgoing_return']:
                    # Exclude returns
                    domain.append(('origin', 'not ilike', 'Return of'))
            
            # Only show non-cancelled pickings
            domain.append(('state', '!=', 'cancel'))
            
            _logger.info(f"Final Search Domain: {domain}")
            
            # Get pickings
            pickings = Picking.search(domain, order='scheduled_date desc, id desc', limit=50)
            _logger.info(f"Found {len(pickings)} pickings")
            
            # Get session scanned picking IDs
            scanned_picking_ids = []
            if session_id:
                session = request.env['barcode.kiosk.session'].browse(session_id)
                if session.exists():
                    scanned_picking_ids = session.scan_line_ids.mapped('picking_id').ids
                    _logger.info(f"Scanned picking IDs: {scanned_picking_ids}")
            
            result = []
            for picking in pickings:
                is_scanned = picking.id in scanned_picking_ids
                
                move_lines = []
                for move in picking.move_ids_without_package:
                    move_lines.append({
                        'product_id': move.product_id.id,
                        'product': move.product_id.name,
                        'barcode': move.product_id.barcode or '',
                        'qty_done': move.quantity,
                        'qty_total': move.product_uom_qty,
                    })
                
                result.append({
                    'id': picking.id,
                    'name': picking.name,
                    'partner_name': picking.partner_id.name if picking.partner_id else 'N/A',
                    'state': picking.state,
                    'scheduled_date': picking.scheduled_date.strftime('%Y-%m-%d %H:%M') if picking.scheduled_date else 'N/A',
                    'picking_type': picking.picking_type_id.name,
                    'picking_type_code': picking.picking_type_id.code,
                    'move_lines': move_lines,
                    'is_scanned': is_scanned,
                    'origin': picking.origin or '',
                })
            
            _logger.info(f"Returning {len(result)} pickings")
            
            return {
                'success': True,
                'pickings': result,
                'operation_type': operation_type,
                'count': len(result)
            }
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            _logger.error(f"Error in get_pickings: {str(e)}")
            _logger.error(error_trace)
            
            return {
                'success': False,
                'error': str(e),
                'traceback': error_trace,
                'pickings': []
            }


    @http.route('/barcode_kiosk/close_session', type='json', auth='user', methods=['POST'])
    def close_session(self, session_id):
        try:
            _logger.debug("close_session called: %s", session_id)
            session = request.env['barcode.kiosk.session'].sudo().browse(session_id)
            if not session.exists():
                _logger.warning("close_session: session not found: %s", session_id)
                return {'error': 'Session not found'}

            session.action_close_session()
            _logger.info("Session closed: %s", session_id)
            return {'success': True}

        except Exception as e:
            _logger.exception("Error in close_session")
            return {'error': str(e)}

    @http.route('/barcode_kiosk/validate_operation', type='json', auth='user', methods=['POST'])
    def validate_operation(self, session_id):
        try:
            _logger.debug("validate_operation called: %s", session_id)
            session = request.env['barcode.kiosk.session'].sudo().browse(session_id)
            if not session.exists():
                _logger.warning("validate_operation: session not found: %s", session_id)
                return {'error': 'Session not found'}

            session.action_validate_picking()
            _logger.info("validate_operation: validated session %s", session_id)
            return {'success': True}

        except Exception as e:
            _logger.exception("Error in validate_operation")
            return {'error': str(e)}

    @http.route('/barcode_kiosk/get_session_data', type='json', auth='user', methods=['POST'])
    def get_session_data(self, **kwargs):
        try:
            session_id = kwargs.get("session_id")
            if not session_id:
                return {'error': 'session_id missing'}

            _logger.debug("get_session_data called: %s", session_id)

            session = request.env['barcode.kiosk.session'].sudo().browse(session_id)
            if not session.exists():
                return {'error': f'Session not found for id {session_id}'}

            data = {
                'session_id': session.id,
                'session_name': session.name,
                'picking_type_id': session.picking_type_id.id if session.picking_type_id else None,
                'picking_id': session.picking_id.id if session.picking_id else None,
                'picking_name': session.picking_id.name if session.picking_id else '',
                'total_scans': session.total_scans,
                'successful_scans': session.successful_scans,
                'failed_scans': session.failed_scans,
                'scan_lines': [],
            }

            for line in session.scan_line_ids.sorted('scan_time', reverse=True)[:50]:
                data['scan_lines'].append({
                    'id': line.id,
                    'barcode': line.barcode or '',
                    'operation_type': line.operation_type,
                    'status': line.status,
                    'message': line.message or '',
                    'product_name': line.product_id.display_name if line.product_id else '',
                    'scan_time': line.scan_time.strftime('%Y-%m-%d %H:%M:%S') if line.scan_time else '',
                })

            return data

        except Exception as e:
            _logger.exception("Error in get_session_data")
            return {'error': str(e)}


    @http.route('/barcode_kiosk/update_move_quantity', type='json', auth='user')
    def update_move_quantity(self, picking_id, product_id, quantity):
        try:
            picking = request.env['stock.picking'].sudo().browse(picking_id)
            if not picking.exists():
                return {'success': False, 'error': 'Picking not found'}
            
            # Find the stock move for this product
            move = picking.move_ids_without_package.filtered(
                lambda m: m.product_id.id == product_id
            )
            
            if not move:
                return {'success': False, 'error': 'Product not found in picking'}
            
            # Update quantity
            move[0].quantity = quantity
            
            return {'success': True}
            
        except Exception as e:
            _logger.exception("Error updating move quantity")
            return {'success': False, 'error': str(e)}

    @http.route('/barcode_kiosk/validate_picking', type='json', auth='user')
    def validate_picking(self, picking_id):
        try:
            picking = request.env['stock.picking'].sudo().browse(picking_id)
            if not picking.exists():
                return {'success': False, 'error': 'Picking not found'}
            
            if picking.state == 'done':
                return {'success': False, 'error': 'Picking already validated'}
            
            # Validate the picking
            picking.button_validate()
            
            return {'success': True}
            
        except Exception as e:
            _logger.exception("Error validating picking")
            return {'success': False, 'error': str(e)}

    @http.route('/barcode_kiosk/search_picking', type='json', auth='user', methods=['POST'])
    def search_picking(self, picking_type_id):
        try:
            _logger.debug("search_picking called with picking_type_id=%s", picking_type_id)
            domain = [('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned'])]
            warehouse = request.env['stock.warehouse'].search([
                ('company_id', '=', request.env.company.id)
            ], limit=1)

            if warehouse:
                picking_type_map = {
                    'incoming': warehouse.in_type_id.id,
                    'outgoing': warehouse.out_type_id.id,
                    'internal': warehouse.int_type_id.id,
                }
                if picking_type_id in picking_type_map:
                    domain.append(('picking_type_id', '=', picking_type_map[picking_type_id]))

            pickings = request.env['stock.picking'].search(domain, limit=20)
            _logger.debug("search_picking found %s pickings", len(pickings))
            result = []
            for p in pickings:
                result.append({
                    'id': p.id,
                    'name': p.name,
                    'partner_name': p.partner_id.name or '',
                    'scheduled_date': p.scheduled_date.strftime('%Y-%m-%d') if p.scheduled_date else '',
                    'state': p.state,
                })
            _logger.debug("search_picking result sample: %s", result[:3])
            return result

        except Exception as e:
            _logger.exception("Error in search_picking")
            return {'error': str(e)}

    @http.route('/barcode_kiosk/get_all_pickings', type='json', auth='user', methods=['POST'])
    def get_all_pickings(self, session_id=None):
        try:
            _logger.debug("get_all_pickings called with session_id=%s", session_id)
            print("get_all_pickings called with session_id:", session_id)
            
            # Get scanned picking IDs from the session
            scanned_picking_ids = []
            if session_id:
                session = request.env['barcode.kiosk.session'].sudo().browse(session_id)
                if session.exists():
                    # Get all picking IDs from scan lines
                    scanned_picking_ids = session.scan_line_ids.mapped('picking_id').ids
                    _logger.debug("Scanned picking IDs from session: %s", scanned_picking_ids)
            
            # Search only for scanned pickings OR all pickings (your choice)
            # Option 1: Show only scanned pickings
            if scanned_picking_ids:
                domain = [('id', 'in', scanned_picking_ids)]
            else:
                domain = []  # Show all if nothing scanned yet
                
            # Option 2: Show all pickings but mark which are scanned
            # domain = []
            
            pickings = request.env['stock.picking'].sudo().search(domain)

            _logger.debug("Total pickings found: %s", len(pickings))
            print("Total pickings found:", len(pickings))

            result = []
            for picking in pickings:
                # Check if this picking has been scanned in current session
                is_scanned = picking.id in scanned_picking_ids
                
                picking_info = {
                    'id': picking.id,
                    'name': picking.name,
                    'partner_name': picking.partner_id.name if picking.partner_id else '',
                    'scheduled_date': picking.scheduled_date.strftime('%Y-%m-%d') if picking.scheduled_date else '',
                    'state': picking.state,
                    'picking_type': picking.picking_type_id.name if picking.picking_type_id else '',
                    'is_scanned': is_scanned,  # Flag to identify scanned pickings
                    'is_editable': is_scanned,  # Only scanned pickings are editable
                }

                picking_barcode = getattr(picking, 'barcode', '') or ''
                picking_info['barcode'] = picking_barcode

                _logger.debug("Processing picking id=%s name=%s is_scanned=%s", 
                            picking.id, picking.name, is_scanned)

                moves_list = []
                for move in picking.move_ids:
                    prod = move.product_id
                    prod_barcode = getattr(prod, 'barcode', '') or ''
                    move_info = {
                        'product_id': prod.id if prod else None,
                        'product': prod.display_name if prod else '',
                        'barcode': prod_barcode,
                        'qty_done': getattr(move, 'quantity', None) if hasattr(move, 'quantity') else getattr(move, 'qty_done', None),
                        'qty_total': getattr(move, 'product_uom_qty', 0),
                    }
                    moves_list.append(move_info)

                picking_info['move_lines'] = moves_list
                result.append(picking_info)

            _logger.debug("get_all_pickings returning %s entries", len(result))
            print("get_all_pickings returning entries:", len(result))
            return {'success': True, 'pickings': result}

        except Exception as e:
            _logger.exception("Error in get_all_pickings")
            return {'error': str(e)}
