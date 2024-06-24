from flask import request, jsonify
from flask.views import MethodView
from ..constants import API_KEY, MESSAGE_LIMIT
from ..authorization import get_user_messages_count
from ..decorators import api_key_required

class UserController(MethodView):
    @api_key_required
    def get(self, user_id):
        if user_id is None:
            return {"status": False, "message": "User ID is required"}, 400

        if "Authorization" not in request.headers:
            return {"status": False, "message": "Authorization header is required"}, 403

        token = request.headers.get("Authorization").split(" ")[1]
        if token != API_KEY:
            return {"status": False, "message": "Invalid API Key"}, 403

        message_count = get_user_messages_count(user_id)
        return jsonify({"status": True, "message_count": message_count, "monthly_limit": MESSAGE_LIMIT})