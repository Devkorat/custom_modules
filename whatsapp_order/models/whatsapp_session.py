from odoo import models, fields

class WhatsappSession(models.Model):
    _name = 'whatsapp.session'
    _description = 'WhatsApp Session'

    from_number = fields.Char(string='From Number', required=True)
    state = fields.Selection([
        ('initial', 'Initial'),
        ('waiting_for_name', 'Waiting for Name'),
        ('waiting_for_email', 'Waiting for Email'),
        ('waiting_for_address', 'Waiting for Address'),
        ('completed', 'Completed')
    ], default='initial', string='State')
    name = fields.Char(string='Name')
    email = fields.Char(string='Email')
    partner_id = fields.Many2one('res.partner', string='Partner')
    pending_order = fields.Text(string='Pending Order')
    pending_order_id = fields.Many2one('sale.order', string='Pending Order')