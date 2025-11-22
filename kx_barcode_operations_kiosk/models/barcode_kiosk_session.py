# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class BarcodeKioskSession(models.Model):
    _name = 'barcode.kiosk.session'
    _description = 'Barcode Kiosk Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_time desc'

    name = fields.Char(string='Session Name', required=True, readonly=True, default='New')
    user_id = fields.Many2one('res.users', string='User', required=True, 
                              default=lambda self: self.env.user, tracking=True)
    start_time = fields.Datetime(string='Start Time', required=True, 
                                  default=fields.Datetime.now, tracking=True)
    end_time = fields.Datetime(string='End Time', tracking=True)
    state = fields.Selection([
        ('active', 'Active'),
        ('closed', 'Closed'),
    ], string='State', default='active', required=True, tracking=True)
    
    operation_type = fields.Selection([
        ('incoming', 'Incoming (Receipts)'),
        ('outgoing', 'Outgoing (Deliveries)'),
        ('internal', 'Internal Transfers'),
        ('incoming', 'Returns'),
        ('scrap', 'Scrap'),
    ], string='Operation Type', tracking=True)
    
    picking_id = fields.Many2one('stock.picking', string='Current Picking', tracking=True)
    picking_type_id = fields.Many2one('stock.picking.type', string='Operation Type Ref')
    
    scan_line_ids = fields.One2many('barcode.kiosk.scan.line', 'session_id', 
                                     string='Scanned Lines')
    total_scans = fields.Integer(string='Total Scans', compute='_compute_totals', store=True)
    successful_scans = fields.Integer(string='Successful Scans', compute='_compute_totals', store=True)
    failed_scans = fields.Integer(string='Failed Scans', compute='_compute_totals', store=True)
    
    location_src_id = fields.Many2one('stock.location', string='Source Location')
    location_dest_id = fields.Many2one('stock.location', string='Destination Location')
    
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', string='Company', 
                                  default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('barcode.kiosk.session') or 'New'
        return super(BarcodeKioskSession, self).create(vals_list)

    @api.depends('scan_line_ids', 'scan_line_ids.status')
    def _compute_totals(self):
        for session in self:
            session.total_scans = len(session.scan_line_ids)
            session.successful_scans = len(session.scan_line_ids.filtered(lambda l: l.status == 'success'))
            session.failed_scans = len(session.scan_line_ids.filtered(lambda l: l.status == 'error'))

    def action_close_session(self):
        """Close the kiosk session"""
        self.ensure_one()
        self.write({
            'state': 'closed',
            'end_time': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Session Closed'),
                'message': _('Session %s has been closed successfully.') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reopen_session(self):
        """Reopen a closed session"""
        self.ensure_one()
        self.write({
            'state': 'active',
            'end_time': False,
        })

    def _process_product_scan(self, barcode):
        """Process a product barcode scan"""
        result = {'success': False, 'message': '', 'data': {}}
        
        # Search for product by barcode
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
        
        if not product:
            result['message'] = _('Product not found for barcode: %s') % barcode
            return result
            
        # Check if we have an active picking
        if not self.picking_id:
            # Try to find or create a picking based on operation type
            picking = self._get_or_create_picking()
            if not picking:
                result['message'] = _('No active operation found. Please select operation type.')
                return result
            self.picking_id = picking
        
        # Check if product is in the picking
        move_line = self.picking_id.move_ids_without_package.filtered(
            lambda m: m.product_id == product and m.state not in ['done', 'cancel']
        )
        
        if not move_line:
            result['message'] = _('Product %s is not in the current operation') % product.display_name
            return result
        
        # Process the scan - increase done quantity
        move_line = move_line[0]
        
        if move_line.quantity < move_line.product_uom_qty:
            move_line.quantity += 1
            result['success'] = True
            result['message'] = _('Product scanned successfully: %s (Qty: %s/%s)') % (
                product.display_name,
                move_line.quantity,
                move_line.product_uom_qty
            )
            result['data'] = {
                'product_id': product.id,
                'product_name': product.display_name,
                'quantity': move_line.quantity,
                'quantity_expected': move_line.product_uom_qty,
                'move_id': move_line.id,
            }
        else:
            result['message'] = _('Product %s: Expected quantity already scanned') % product.display_name
            result['data'] = {
                'product_id': product.id,
                'product_name': product.display_name,
            }
        
        # Check if picking is complete
        if all(m.quantity >= m.product_uom_qty for m in self.picking_id.move_ids_without_package):
            result['picking_complete'] = True
            
        return result

    def _process_location_scan(self, barcode):
        """Process a location barcode scan"""
        result = {'success': False, 'message': '', 'data': {}}
        
        location = self.env['stock.location'].search([('barcode', '=', barcode)], limit=1)
        
        if not location:
            result['message'] = _('Location not found for barcode: %s') % barcode
            return result
        
        # Update session location based on operation type
        if self.operation_type == 'internal':
            if not self.location_src_id:
                self.location_src_id = location
                result['message'] = _('Source location set: %s') % location.display_name
                result['success'] = True
            elif not self.location_dest_id:
                self.location_dest_id = location
                result['message'] = _('Destination location set: %s') % location.display_name
                result['success'] = True
            else:
                result['message'] = _('Both locations already set')
        else:
            self.location_dest_id = location
            result['message'] = _('Location set: %s') % location.display_name
            result['success'] = True
            
        result['data'] = {
            'location_id': location.id,
            'location_name': location.display_name,
        }
        
        return result

    def _process_operation_scan(self, barcode):
        """Process an operation/picking barcode scan"""
        result = {'success': False, 'message': '', 'data': {}}
        
        picking = self.env['stock.picking'].search([('name', '=', barcode)], limit=1)
        
        if not picking:
            result['message'] = _('Operation not found for barcode: %s') % barcode
            return result
        
        if picking.state in ['done', 'cancel']:
            result['message'] = _('Operation %s is already %s') % (picking.name, picking.state)
            return result
        
        self.picking_id = picking
        self.operation_type = self._get_operation_type_from_picking(picking)
        
        result['success'] = True
        result['message'] = _('Operation loaded: %s') % picking.name
        result['data'] = {
            'picking_id': picking.id,
            'picking_name': picking.name,
            'operation_type': self.operation_type,
        }

        return result

    def _process_user_scan(self, barcode):
        """Process a user barcode scan for authentication"""
        result = {'success': False, 'message': '', 'data': {}}
        
        # Search for user by barcode (you might need to add a barcode field to res.users)
        user = self.env['res.users'].search([('barcode', '=', barcode)], limit=1)
        
        if not user:
            result['message'] = _('User not found for barcode: %s') % barcode
            return result
        
        self.user_id = user
        result['success'] = True
        result['message'] = _('User authenticated: %s') % user.name
        result['data'] = {
            'user_id': user.id,
            'user_name': user.name,
        }
        
        return result

    def _create_scan_line(self, barcode, operation_type, result):
        """Create a scan line record and return it"""
        scan_line = self.env['barcode.kiosk.scan.line'].create({
            'session_id': self.id,
            'barcode': barcode,
            # 'scan_type': scan_type,  # REMOVED - field doesn't exist
            'operation_type': self.operation_type,  # Use session's operation_type
            'status': 'success' if result.get('success') else 'error',
            'message': result.get('message', ''),
            'product_id': result.get('data', {}).get('product_id'),
            'location_id': result.get('data', {}).get('location_id'),
            'picking_id': result.get('data', {}).get('picking_id'),
        })
        return scan_line


    def _get_or_create_picking(self):
        """Get or create a picking based on operation type"""
        if not self.operation_type:
            return False
        
        # Get the appropriate picking type
        picking_type = self._get_picking_type()
        if not picking_type:
            return False
        
        # Search for a draft/assigned picking of this type
        picking = self.env['stock.picking'].search([
            ('picking_type_id', '=', picking_type.id),
            ('state', 'in', ['draft', 'waiting', 'confirmed', 'assigned']),
            ('user_id', '=', self.user_id.id),
        ], limit=1)
        
        return picking

    def _get_picking_type(self):
        """Get picking type based on operation type"""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not warehouse:
            return False
        
        picking_type_map = {
            'incoming': warehouse.in_type_id,
            'outgoing': warehouse.out_type_id,
            'internal': warehouse.int_type_id,
            'return': warehouse.in_type_id,  # Adjust as needed
        }
        
        return picking_type_map.get(self.operation_type)

    def _get_operation_type_from_picking(self, picking):
        """Determine operation type from picking"""
        code = picking.picking_type_id.code
        type_map = {
            'incoming': 'incoming',
            'outgoing': 'outgoing',
            'internal': 'internal',
        }
        return type_map.get(code, 'internal')

    def action_validate_picking(self):
        """Validate the current picking"""
        self.ensure_one()
        
        if not self.picking_id:
            raise UserError(_('No active operation to validate'))
        
        if self.picking_id.state == 'done':
            raise UserError(_('Operation is already validated'))
        
        # Validate the picking
        try:
            self.picking_id.button_validate()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Operation %s validated successfully') % self.picking_id.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_('Error validating operation: %s') % str(e))


class BarcodeKioskScanLine(models.Model):
    _name = 'barcode.kiosk.scan.line'
    _description = 'Barcode Kiosk Scan Line'
    _order = 'scan_time desc'

    session_id = fields.Many2one('barcode.kiosk.session', string='Session', 
                                  required=True, ondelete='cascade')
    barcode = fields.Char(string='Barcode', required=True)
    scan_time = fields.Datetime(string='Scan Time', default=fields.Datetime.now, required=True)
    operation_type = fields.Selection([
        ('incoming', 'Incoming (Receipts)'),
        ('outgoing', 'Outgoing (Deliveries)'),
        ('internal', 'Internal Transfers'),
        ('incoming', 'Returns'),
        ('scrap', 'Scrap'),
    ], string='Operation Type', tracking=True)
    
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('warning', 'Warning'),
    ], string='Status', required=True, default='success')
    
    message = fields.Text(string='Message')
    
    product_id = fields.Many2one('product.product', string='Product')
    location_id = fields.Many2one('stock.location', string='Location')
    picking_id = fields.Many2one('stock.picking', string='Picking')
    
    user_id = fields.Many2one('res.users', string='User', 
                              default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', 
                                  related='session_id.company_id', store=True)