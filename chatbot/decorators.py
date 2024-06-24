from functools import wraps
from flask import request, g, abort
from .authorization import verify_jwt
from .constants import API_KEY

def authorization_required(f):
    @wraps(f)
    def authorization(*args, **kwargs):
        if "Authorization" not in request.headers:
            abort(403, description="Authorization header is required")
        
        token = request.headers.get("Authorization").split(" ")[1]
        # This function also trigger abort(403) if the token is invalid
        payload = verify_jwt(token)

        if payload is not None:
            user_id = payload["ur"]
        else:
            abort(403, description="Invalid user ID")

        g.user_id = user_id
        g.token = token
        return f(*args, **kwargs)
    
    return authorization


def api_key_required(f):
    @wraps(f)
    def authorization_api_key(*args, **kwargs):
        if "Authorization" not in request.headers:
            abort(403, description="Authorization header is required")

        token = request.headers.get("Authorization").split(" ")[1]
        if token != API_KEY:
            abort(403, description="Invalid API key")

        return f(*args, **kwargs)

    return authorization_api_key
