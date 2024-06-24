from flask.views import MethodView
from flask import jsonify, request, g, abort, stream_with_context, Response
from ..authorization import get_user_has_subscription, get_user_messages_count
from ..decorators import authorization_required
from ..database import get_db, is_conversation_valid
from ..constants import MESSAGE_LIMIT, comenio_personality
from llama_index.llms.openai import OpenAI
from llama_index.core.chat_engine import SimpleChatEngine
from llama_index.core.llms import ChatMessage, MessageRole

class ChatbotPreflightController(MethodView):
    @authorization_required
    def post(self, conversation_uuid=None):
        user_id = g.user_id
        token = g.token

        if not is_conversation_valid(conversation_uuid):
            abort(404, description="Invalid conversation ID")

        conn = get_db()
        cursor = conn.cursor()

        # Fech the conversation associated with the UUID
        cursor.execute("SELECT id FROM conversations WHERE uuid = ?", (conversation_uuid,))
        conversation_id = cursor.fetchone()[0]
        if conversation_id is None:
            return {"error": "Invalid conversation ID"}, 404

        # Validate all messages logic
        has_paid_subscription = get_user_has_subscription(token)
        messages_count = get_user_messages_count(user_id)
        if not has_paid_subscription and messages_count >= MESSAGE_LIMIT:
            return {"error": "Exceded credit quota"}, 200

        cursor.execute(
            "INSERT INTO messages(conversation_id, user_id, type, message) VALUES(?,?,?,?)",
            (conversation_id, user_id, 1, request.json["message"]),
        )
        conn.commit()
        human_message = cursor.lastrowid
        cursor.execute(
            "INSERT INTO messages(conversation_id, user_id, type, message) VALUES(?,?,?,?)",
            (conversation_id, user_id, 2, ""),
        )
        conn.commit()
        ai_message = cursor.lastrowid

        cursor.execute(
            """SELECT id, conversation_id, message, type, DATETIME(created_at,'localtime') as created_at 
                    FROM messages WHERE id IN (?,?) ORDER BY created_at ASC""",
            (human_message, ai_message),
        )
        messages = cursor.fetchall()
        column_names = list(map(lambda x: x[0], cursor.description))
        result = [dict(zip(column_names, row)) for row in messages]
        return jsonify({"messages": result})
    

class ChatbotController(MethodView):
    @authorization_required
    def post(self, conversation_uuid=None, message_id=None):

        user_id = g.user_id
        token = g.token

        if not is_conversation_valid(conversation_uuid):
            abort(404, description="Invalid conversation ID")

        # Validate all messages logic
        has_paid_subscription = get_user_has_subscription(token)
        messages_count = get_user_messages_count(user_id)

        if not has_paid_subscription and messages_count >= MESSAGE_LIMIT:
            return {"error": "Exceded credit quota"}, 403

        def retrieve_last_two_messages_as_chat_message(
            conversation_uuid, user_id, message_id
        ):
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                """
                    SELECT id, conversation_id, message, type, DATETIME(created_at,'localtime') as created_at 
                    FROM messages 
                    WHERE conversation_id = (SELECT id FROM conversations WHERE uuid = ?)
                    AND user_id = ?
                    AND id < ?
                    ORDER BY id DESC LIMIT 10
                """,
                (conversation_uuid, user_id, message_id),
            )
            messages = cursor.fetchall()
            if messages is None:
                return []

            chat_history = []
            for message in messages:
                print(
                    message[2],
                    MessageRole.USER if message[3] == 1 else MessageRole.ASSISTANT,
                )
                chat_history.append(
                    ChatMessage(
                        content=message[2],
                        role=MessageRole.USER if message[3] == 1 else MessageRole.ASSISTANT,
                    )
                )
            return chat_history

        @stream_with_context
        def generate():
            data = request.json
            full_response = ""
            llm = OpenAI(temperature=0.2, model="gpt-4o")
            chat_engine = SimpleChatEngine.from_defaults(
                llm=llm, system_prompt=comenio_personality
            )
            message = data["message"] if "message" in data else ""

            chat_history = retrieve_last_two_messages_as_chat_message(
                conversation_uuid, user_id, message_id
            )

            response_stream = chat_engine.stream_chat(message, chat_history=chat_history)
            for response in response_stream.response_gen:
                full_response += response.replace("```markdown", "\n").replace("```", "\n")
                yield response

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE messages SET message = ? WHERE id = ?",
                (
                    full_response,
                    message_id,
                ),
            )
            conn.commit()
            print(full_response)

        return Response(
            generate(),
            mimetype="text/event-stream",
            content_type="charset=UTF-8",
            headers={"X-Accel-Buffering": "no"},
        )