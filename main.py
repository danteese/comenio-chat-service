import os
from flask import (
    Flask,
    request,
    jsonify,
    g,
    stream_with_context,
    Response,
)
from flask_cors import CORS
from llama_index.llms.openai import OpenAI
from llama_index.core.chat_engine import SimpleChatEngine
from llama_index.core.llms import ChatMessage, MessageRole
from dotenv import load_dotenv
from chatbot.authorization import get_user_has_subscription, verify_jwt, get_user_messages_count
from chatbot.database import get_db
from chatbot.constants import comenio_personality, MESSAGE_LIMIT, API_KEY

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


def is_conversation_valid(conversation_uuid) -> bool:
    """
    Check if the conversation exists in the database
    @param conversation_id: The conversation ID to check
    @return: True if the conversation exists, False otherwise
    """
    cursor = get_db().cursor()
    cursor.execute("SELECT * FROM conversations WHERE uuid = ?", (conversation_uuid,))
    conversations = cursor.fetchone()
    return conversations is not None


@app.route("/api/chat/<conversation_uuid>/preflight", methods=["POST"])
def preflight(conversation_uuid=None):
    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403

    token = request.headers.get("Authorization").split(" ")[1]
    payload = verify_jwt(token)

    if payload is not None:
        user_id = payload["ur"]
    else:
        return {"status": False, "message": "Invalid user ID"}, 403

    if not is_conversation_valid(conversation_uuid):
        return {"error": "Invalid conversation ID"}, 403

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


@app.route(
    "/api/chat/<conversation_uuid>/<int:message_id>/query",
    methods=["POST"],
)
def ask(conversation_uuid=None, message_id=None):
    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403

    token = request.headers.get("Authorization").split(" ")[1]
    payload = verify_jwt(token)

    if payload is not None:
        user_id = payload["ur"]
    else:
        return {"status": False, "message": "Invalid user ID"}, 403

    if not is_conversation_valid(conversation_uuid):
        return {"error": "Invalid conversation ID"}, 403

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



@app.route("/api/chat", methods=["GET"])
def get_chat():
    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403

    token = request.headers.get("Authorization").split(" ")[1]
    payload = verify_jwt(token)

    if payload is not None:
        user_id = payload["ur"]
    else:
        return {"status": False, "message": "Invalid user ID"}, 403

    cursor = get_db().cursor()
    cursor.execute(
        "SELECT id, uuid, DATETIME(created_at,'localtime') as created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    conversations = cursor.fetchall()
    column_names = list(map(lambda x: x[0], cursor.description))
    result = [dict(zip(column_names, row)) for row in conversations]
    return jsonify({"conversations": result})


@app.route("/api/chat", methods=["POST"])
def post_chat():
    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403

    token = request.headers.get("Authorization").split(" ")[1]
    payload = verify_jwt(token)

    if payload is not None:
        user_id = payload["ur"]
    else:
        return {"status": False, "message": "Invalid user ID"}, 403

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


@app.route("/api/chat/<conversation_uuid>", methods=["GET"])
def get_conversation(conversation_uuid=None):
    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403

    token = request.headers.get("Authorization").split(" ")[1]
    payload = verify_jwt(token)

    if payload is not None:
        user_id = payload["ur"]
    else:
        return {"status": False, "message": "Invalid user ID"}, 403

    if not is_conversation_valid(conversation_uuid):
        return {"error": "Invalid conversation ID"}, 403

    cursor = get_db().cursor()
    cursor.execute(
        "SELECT uuid FROM conversations WHERE uuid = ? and user_id = ? ORDER BY created_at DESC",
        (conversation_uuid, user_id),
    )
    conversation = cursor.fetchone()
    if conversation is None or len(conversation) == 0:
        return {"status": False, "message":  "Conversation is not valid"}, 403
    
    return jsonify({"conversation": conversation[0]})


@app.route("/api/chat/<conversation_uuid>/messages", methods=["GET"])
def get_conversation_messages(conversation_uuid=None):
    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403

    token = request.headers.get("Authorization").split(" ")[1]
    payload = verify_jwt(token)

    if payload is not None:
        user_id = payload["ur"]
    else:
        return {"status": False, "message": "Invalid user ID"}, 403

    if not is_conversation_valid(conversation_uuid):
        return {"error": "Invalid conversation ID"}, 403

    cursor = get_db().cursor()
    cursor.execute(
        """
        SELECT id, conversation_id, message, type, DATETIME(created_at,'localtime') as created_at 
        FROM messages 
        WHERE conversation_id = (SELECT id FROM conversations WHERE uuid = ?) 
        AND user_id = ? 
        ORDER BY created_at ASC
        """,
        (conversation_uuid, user_id),
    )
    messages = cursor.fetchall()
    column_names = list(map(lambda x: x[0], cursor.description))
    result = [dict(zip(column_names, row)) for row in messages]
    print(messages)
    return jsonify({"messages": result})


@app.route("/api/user/<int:user_id>", methods=["GET"]) 
def get_message_count_from_user(user_id=None):
    if user_id is None:
        return {"status": False, "message": "User ID is required"}, 400

    if "Authorization" not in request.headers:
        return {"status": False, "message": "Authorization header is required"}, 403 
    
    token = request.headers.get("Authorization").split(" ")[1]
    if token != API_KEY:
        return {"status": False, "message": "Invalid API Key"}, 403
    
    message_count = get_user_messages_count(user_id)
    return jsonify({"status": True, "message_count": message_count, "monthly_limit": MESSAGE_LIMIT})



@app.route("/", methods=["GET"])
def index():
    return "Closed on sunday"


@app.route("/healthz", methods=["GET"])
def healthz():
    return "OK"


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="8005", debug=True)
