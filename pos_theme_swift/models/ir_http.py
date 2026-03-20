# -*- coding: utf-8 -*-

import logging
import odoo
from odoo import models
from odoo.http import request
from odoo.exceptions import AccessDenied

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
                if new_session and new_session.uid:
                    new_session.sid = token  # MUST BE SET: Werkzeug does not set .sid on restored sessions!
                    request.session = new_session
                    request.update_env(user=new_session.uid, context=new_session.context)
                    _logger.info("Swift API Environment Updated: Env UID is now %s", request.env.uid)
                else:
                    # Token invalid or expired
                    if request.httprequest.path.startswith('/api/swift/'):
                        raise AccessDenied()
        elif request.httprequest.path.startswith('/api/swift/') and request.httprequest.path != '/api/swift/v1/auth/login':
            # Require Bearer token for all other Swift API endpoints
            _logger.warning("Swift API request missing Bearer token: %s", request.httprequest.path)
            raise AccessDenied("Missing or invalid Bearer token")

        return super(IrHttp, cls)._authenticate(endpoint)

    @classmethod
    def _handle_error(cls, exception):
        is_swift_api = request.httprequest.path.startswith('/api/swift/')
        
        # If the request is for our JSON API and it's an authentication error, return JSON 401
        if is_swift_api and isinstance(exception, (AccessDenied, odoo.http.SessionExpiredException)):
            _logger.warning("Swift API Authentication failed. Returning 401 JSON. Path: %s", request.httprequest.path)
            return request.make_json_response({
                "error": 401,
                "message": "Unauthorized or Session Expired. Please provide a valid Bearer token.",
                "data": None
            }, status=401)
            
        return super(IrHttp, cls)._handle_error(exception)
