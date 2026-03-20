# -*- coding: utf-8 -*-

from odoo import models
from odoo.http import request

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        # Support Bearer token from Authorization header for Zalo/Mobile clients
        auth_header = request.httprequest.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
            if token and token != request.session.sid:
                # Load the session from the token provided in the header
                # This will find the session file on the server and set the user/db
                new_session = request.session_store.get(token)
                if new_session:
                    request.session = new_session
        
        return super(IrHttp, cls)._authenticate(endpoint)
