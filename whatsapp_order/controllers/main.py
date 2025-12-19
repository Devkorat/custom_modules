import ast
import base64
import hashlib
import json
import requests

from odoo import http
from odoo.http import request
# ssh -R 80:127.0.0.1:8069 serveo.net


class WhatsappWebhookController(http.Controller):
    @http.route('/whatsapp/webhook', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    def whatsapp_webhook(self, **kwargs):
        if request.httprequest.method == 'GET':
            return self.handle_verification(kwargs)
        elif request.httprequest.method == 'POST':
            data = json.loads(request.httprequest.data)
            self.handle_incoming_message(data)
            return 'EVENT_RECEIVED'

    def handle_verification(self, kwargs):
        verify_token = 'K4QPNj5A'
        token_sent = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        if token_sent == verify_token:
            return challenge
        return 'Error, invalid verification token'

    def handle_incoming_message(self, data):
        if data.get('object') == 'whatsapp_business_account':
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('field') == 'messages':
                        messages = change.get('value', {}).get('messages', [])
                        contacts = change.get('value', {}).get('contacts', [])

                        for message in messages:
                            message_hash = self.generate_message_hash(message)
                            # Check if this message has been processed before
                            if not self.is_message_processed(message_hash):
                                from_number = message.get('from')
                                self.mark_message_as_processed(message_hash)
                                self.process_message(from_number, message, contacts)

    def generate_message_hash(self, message):
        # Extract relevant fields for hashing
        relevant_data = {
            'from': message.get('from'),
            'id': message.get('id'),
        }
        # Generate a hash of the relevant data
        return hashlib.md5(json.dumps(relevant_data, sort_keys=True).encode()).hexdigest()

    def is_message_processed(self, message_hash):
        # Check if the message hash exists in the database
        return request.env['whatsapp.processed.message'].sudo().search_count([('message_hash', '=', message_hash)]) > 0

    def mark_message_as_processed(self, message_hash):
        # Mark the message as processed in the database
        request.env['whatsapp.processed.message'].sudo().create({'message_hash': message_hash})

    def process_message(self, from_number, message, contacts):
        text = message.get('text', {}).get('body', '').strip().lower()
        order = message.get('order')
        button_text = message.get('interactive', {}).get('button_reply', {}).get('id')
        session = request.env['whatsapp.session'].sudo().search([('from_number', '=', from_number)], limit=1)
        if not session:
            session = request.env['whatsapp.session'].sudo().create({
                'from_number': from_number,
                'name': contacts and contacts[0].get('profile', {}).get('name')
            })
        if text == 'hi':
            self.send_welcome_message(from_number)
        elif order:
            self.handle_order(from_number, order)
        else:
            self.handle_user_input(from_number, button_text or text)

    def send_welcome_message(self, to_number):
        buttons = [
            {"type": "reply", "reply": {"id": "track_order", "title": "Track Order"}},
        ]
        self.send_message_with_buttons(to_number, "Welcome! How can I assist you today?", buttons)

    def handle_order(self, from_number, order):
        partner = self.get_or_create_partner(from_number)
        if not partner:
            self.request_user_info(from_number, order)
        else:
            self.create_sale_order(partner, order)

    def get_or_create_partner(self, from_number):
        partner = request.env['res.partner'].sudo().search([('mobile', '=', from_number)], limit=1)
        if not partner:
            return None
        return partner

    def request_user_info(self, from_number, order):
        self.send_message(from_number, "Please provide your email address.")
        session = request.env['whatsapp.session'].sudo().search([('from_number', '=', from_number)], limit=1)
        session.write({
            'state': 'waiting_for_email',
            'pending_order': order
        })

    def handle_user_input(self, from_number, text):
        session = request.env['whatsapp.session'].sudo().search([('from_number', '=', from_number)], limit=1)
        if not session:
            self.send_welcome_message(from_number)
            return
        state = session.state
        if state == 'waiting_for_email':
            self.handle_email_input(from_number, text, session)
        elif state == 'waiting_for_address':
            self.handle_address_input(from_number, text, session)
        elif text == 'track_order':
            self.send_order_tracking(from_number)
        elif text == 'confirm_order':
            self.confirm_order(from_number, session)
        elif text == 'cancel_order':
            self.cancel_order(from_number, session)

    def handle_email_input(self, from_number, email, session):
        session.write({'email': email, 'state': 'waiting_for_address'})
        self.send_message(from_number, "Thank you. Now, please provide your full address.")

    def handle_address_input(self, from_number, address, session):
        parsed_address = self.parse_address(address)
        if parsed_address:
            partner = request.env['res.partner'].sudo().create({
                'name': session.name or from_number,  # Use name if provided, otherwise use the phone number
                'mobile': from_number,
                'email': session.email,
                'street': parsed_address.get('street', ''),
                'street2': parsed_address.get('street2', ''),
                'city': parsed_address.get('city', ''),
                'state_id': parsed_address.get('state_id'),
                'country_id': parsed_address.get('country_id'),
                'zip': parsed_address.get('zip', ''),
            })
            session.write({'partner_id': partner.id, 'state': 'completed'})
            self.send_message(from_number, "Thank you for providing your information. Your account has been created.")
            if session.pending_order:
                self.create_sale_order(partner, ast.literal_eval(session.pending_order))
        else:
            self.send_message(from_number, "I'm sorry, I couldn't parse your address. Please provide it in the format: Street, City, State, Country, ZIP")
            
    def parse_address(self, address):
        api_key = request.env['ir.config_parameter'].sudo().get_param('google_map_api_key')
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
        response = requests.get(url)
        data = response.json()

        if data['status'] == 'OK':
            components = data['results'][0]['address_components']
            parsed = {}
            for component in components:
                types = component['types']
                if 'street_number' in types:
                    parsed['street_number'] = component['long_name']
                elif 'route' in types:
                    parsed['street'] = component['long_name']
                elif 'locality' in types:
                    parsed['city'] = component['long_name']
                elif 'administrative_area_level_1' in types:
                    parsed['state_id'] = component['long_name']
                elif 'country' in types:
                    parsed['country_id'] = component['short_name']
                elif 'postal_code' in types:
                    parsed['zip'] = component['long_name']
                elif 'sublocality' in types:
                    parsed['street2'] = component['long_name']

            # Add remaining address to street
            remaining_address = address.lower()
            for key, value in parsed.items():
                if value and type(value) == str:
                    remaining_address = remaining_address.replace(value.lower(), '', 1)
            if 'street' not in parsed:
                parsed['street'] = ''
            parsed['street'] = parsed['street'] + ', ' + remaining_address.strip()
            # Remove extra commas
            parsed['street'] = parsed['street'].replace(', ,', ',')
            parsed['street'] = parsed['street'].replace(',  ', ', ')
            parsed['street'] = parsed['street'].strip(', ')
            parsed['state_id'] = request.env['res.country.state'].sudo().search([
                ('name', '=ilike', parsed['state_id'])
            ], limit=1).id
            parsed['country_id'] = request.env['res.country'].sudo().search([
                ('code', '=', parsed['country_id'])
            ], limit=1).id

            return parsed
        else:
            return None

    def create_sale_order(self, partner, order_data):
        order_lines = []
        for item in order_data.get('product_items', []):
            product = request.env['product.product'].sudo().search([('default_code', '=', item['product_retailer_id'])], limit=1)
            if product:
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': item['quantity'],
                    'price_unit': item['item_price'],
                }))

        if order_lines:
            order = request.env['sale.order'].sudo().create({
                'partner_id': partner.id,
                'order_line': order_lines,
            })
            self.send_order_confirmation(partner.mobile, order)
        else:
            self.send_message(partner.mobile, "Sorry, we couldn't process your order. Please try again.")

    def send_order_confirmation(self, to_number, order):
        pdf_content, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf('sale.action_report_saleorder', [order.id])
        
        attachment = request.env['ir.attachment'].sudo().create({
            'name': f"{order.name}.pdf",
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'sale.order',
            'res_id': order.id,
        })

        access_token = attachment.generate_access_token()
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        attachment_url = f"{base_url}/web/content/{attachment.id}?download=true&access_token={access_token[0]}"
        message = f"Your order {order.name} has been created. Total amount: {order.amount_total:.2f} {order.currency_id.name}\n\nYou can confirm your order details here: {attachment_url}"
        buttons = [
            {"type": "reply", "reply": {"id": "confirm_order", "title": "Confirm Order"}},
            {"type": "reply", "reply": {"id": "cancel_order", "title": "Cancel Order"}},
        ]
        self.send_message_with_buttons(to_number, message, buttons)

        session = request.env['whatsapp.session'].sudo().search([('from_number', '=', to_number)], limit=1)
        if session:
            session.write({'pending_order_id': order.id})

    def confirm_order(self, from_number, session):
        if not session.pending_order_id:
            self.send_message(from_number, "No pending order found to confirm.")
            return

        order = request.env['sale.order'].sudo().browse(session.pending_order_id.id)
        if session.pending_order_id.state != 'draft':
            self.send_message(from_number, "This order has already been processed.")
            return

        session.pending_order_id.action_confirm()
        pdf_content, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf('sale.action_report_saleorder', [order.id])
        
        attachment = request.env['ir.attachment'].sudo().create({
            'name': f"{session.pending_order_id.name}.pdf",
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': 'sale.order',
            'res_id': session.pending_order_id.id,
        })
        
        access_token = attachment.generate_access_token()
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        attachment_url = f"{base_url}/web/content/{attachment.id}?download=true&access_token={access_token[0]}"

        confirmation_message = f"Your order {session.pending_order_id.name} has been confirmed. Total amount: {session.pending_order_id.amount_total:.2f} {session.pending_order_id.currency_id.name}\n\nYou can download your order details here: {attachment_url}"
        self.send_message(from_number, confirmation_message)
        
        session.write({'pending_order_id': False})

    def cancel_order(self, from_number, session):
        if not session.pending_order_id:
            self.send_message(from_number, "No pending order found to cancel.")
            return

        order = request.env['sale.order'].sudo().browse(session.pending_order_id)
        if order.state != 'draft':
            self.send_message(from_number, "This order has already been processed and cannot be cancelled.")
            return

        order.action_cancel()
        self.send_message(from_number, f"Thank you. Your order {order.name} has been cancelled.")
        session.write({'pending_order_id': False})

    def send_order_tracking(self, from_number):
        partner = self.get_or_create_partner(from_number)
        if not partner:
            self.send_message(from_number, "No orders found. Please place an order first.")
            return

        orders = request.env['sale.order'].sudo().search([('partner_id', '=', partner.id)], order='create_date desc', limit=5)
        if not orders:
            self.send_message(from_number, "No recent orders found.")
            return

        message = "Your recent orders:\n\n"
        for order in orders:
            message += f"Order {order.name}: {order.state.capitalize()} - {order.amount_total:.2f} {order.currency_id.name}\n"
        
        self.send_message(from_number, message)

    def send_message(self, to_number, text):
        WHATSAPP_KEY = request.env['ir.config_parameter'].sudo().get_param('whatsapp_api_key')
        WHATSAPP_NUMBER = request.env['ir.config_parameter'].sudo().get_param('whatsapp_number')
        WHATSAPP_API_URL = f'https://graph.facebook.com/v20.0/{WHATSAPP_NUMBER}/messages'

        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": text}
        }
        resp = requests.post(WHATSAPP_API_URL, headers={"Authorization": f"Bearer {WHATSAPP_KEY}"}, json=payload)

    def send_message_with_buttons(self, to_number, text, buttons):
        WHATSAPP_KEY = request.env['ir.config_parameter'].sudo().get_param('whatsapp_api_key')
        WHATSAPP_NUMBER = request.env['ir.config_parameter'].sudo().get_param('whatsapp_number')
        WHATSAPP_API_URL = f'https://graph.facebook.com/v20.0/{WHATSAPP_NUMBER}/messages'
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {"type": "text", "text": "Choose an option"},
                "body": {"text": text},
                "action": {"buttons": buttons}
            }
        }
        resp = requests.post(WHATSAPP_API_URL, headers={"Authorization": f"Bearer {WHATSAPP_KEY}"}, json=payload)
