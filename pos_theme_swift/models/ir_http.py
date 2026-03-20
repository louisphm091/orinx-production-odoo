# -*- coding: utf-8 -*-

import logging
import odoo
from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        # Support Bearer token from Authorization header for Zalo/Mobile clients
        auth_header = request.httprequest.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
            _logger.info("Swift API Auth Header found. Token: %s", token)
            if token and token != request.session.sid:
                new_session = odoo.http.root.session_store.get(token)
                _logger.info("Swift API Extracted Session: %s, uid: %s, db: %s", bool(new_session), new_session.uid if new_session else 'None', new_session.db if new_session else 'None')
                if new_session:
                    new_session.sid = token  # MUST BE SET: Werkzeug does not set .sid on restored sessions!
                    request.session = new_session
                    if new_session.uid:
                        request.update_env(user=new_session.uid, context=new_session.context)
                        _logger.info("Swift API Environment Updated: Env UID is now %s", request.env.uid)
        
        return super(IrHttp, cls)._authenticate(endpoint)
