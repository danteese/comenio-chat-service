from flask.views import MethodView
from flask import jsonify, g, abort
from ..database import get_db, is_conversation_valid
from ..decorators import authorization_required

# TODO: implement marshmallow for validation


class ConversationListController(MethodView):
    @authorization_required
    def get(self):
        user_id = g.user_id

        cursor = get_db().cursor()
        cursor.execute(
            """
            SELECT id, uuid, DATETIME(created_at,'localtime') as created_at 
            FROM conversations 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 30
            """,
            (user_id,),
        )
        conversations = cursor.fetchall()
        column_names = list(map(lambda x: x[0], cursor.description))
        result = [dict(zip(column_names, row)) for row in conversations]
        return jsonify({"conversations": result})

    @authorization_required
    def post(self):
        user_id = g.user_id
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO conversations(user_id) VALUES(?)", (user_id,))
        conn.commit()
        conversation_id = cursor.lastrowid
        print(type(conversation_id), conversation_id)
        cursor.execute(
            "SELECT uuid FROM conversations WHERE id = ? ",
            (conversation_id,),
        )
        conversations = cursor.fetchone()
        return jsonify({"conversation": conversations[0]})


class ConversationController(MethodView):
    @authorization_required
    def get(self, conversation_uuid):
        user_id = g.user_id

        if not is_conversation_valid(conversation_uuid):
            abort(404, description="Invalid conversation ID")

        cursor = get_db().cursor()
        cursor.execute(
            "SELECT uuid FROM conversations WHERE uuid = ? and user_id = ? ORDER BY created_at DESC",
            (conversation_uuid, user_id),
        )
        conversation = cursor.fetchone()
        if conversation is None or len(conversation) == 0:
            return {"status": False, "message": "Conversation is not valid"}, 403

        return jsonify({"conversation": conversation[0]})


class ConversationMessageController(MethodView):
    @authorization_required
    def get(self, conversation_uuid):
        user_id = g.user_id

        if not is_conversation_valid(conversation_uuid):
            abort(404, description="Invalid conversation ID")

        cursor = get_db().cursor()
        cursor.execute(
            """
            SELECT id, conversation_id, message, type, DATETIME(created_at,'localtime') as created_at 
            FROM messages 
            WHERE conversation_id = (SELECT id FROM conversations WHERE uuid = ?) 
            AND user_id = ? 
            ORDER BY created_at ASC
            -- LIMIT 3
            """,
            (conversation_uuid, user_id),
        )
        messages = cursor.fetchall()
        column_names = list(map(lambda x: x[0], cursor.description))
        result = [dict(zip(column_names, row)) for row in messages]
        print(messages)
        return jsonify({"messages": result})
