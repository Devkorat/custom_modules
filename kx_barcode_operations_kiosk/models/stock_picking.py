# -*- coding: utf-8 -*-

from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    barcode_kiosk_session_ids = fields.One2many(
        'barcode.kiosk.session', 'picking_id', 
        string='Kiosk Sessions'
    )
    kiosk_session_count = fields.Integer(
        string='Kiosk Sessions', 
        compute='_compute_kiosk_session_count'
    )

    @api.depends('barcode_kiosk_session_ids')
    def _compute_kiosk_session_count(self):
        for picking in self:
            picking.kiosk_session_count = len(picking.barcode_kiosk_session_ids)

    def action_view_kiosk_sessions(self):
        """View kiosk sessions for this picking"""
        self.ensure_one()
        return {
            'name': 'Kiosk Sessions',
            'type': 'ir.actions.act_window',
            'res_model': 'barcode.kiosk.session',
            'view_mode': 'list,form',
            'domain': [('picking_id', '=', self.id)],
            'context': {'default_picking_id': self.id},
        }
