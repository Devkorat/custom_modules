from odoo import models, fields

class WhatsappProcessedMessage(models.Model):
    _name = 'whatsapp.processed.message'
    _description = 'Processed WhatsApp Messages'

    message_hash = fields.Char(string='Message Hash', required=True, index=True)
    create_date = fields.Datetime(string='Processed Date', default=fields.Datetime.now)

    _sql_constraints = [
        ('unique_message_hash', 'UNIQUE(message_hash)', 'Message hash must be unique!')
    ]