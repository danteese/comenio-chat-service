import os
from flask import (
    Flask,
    jsonify,
    g,
)
from flask_cors import CORS
from dotenv import load_dotenv
from chatbot.controllers.conversations import ConversationController, ConversationListController, ConversationMessageController
from chatbot.controllers.users import UserController
from chatbot.controllers.chatbot import ChatbotPreflightController, ChatbotController

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.route("/", methods=["GET"])
def index():
    return "Closed on sunday"

@app.route("/healthz", methods=["GET"])
def healthz():
    return "OK"


@app.errorhandler(403)
def forbidden(error):
    print(error)
    return jsonify({"status": False, "message": str(error)}), 403


@app.errorhandler(404)
def not_found(error):
    print(error)
    return jsonify({"status": False, "message": str(error)}), 404

# Routes
app.add_url_rule(
    "/api/chat",
    view_func=ConversationListController.as_view("conversation_list"),
    methods=["GET", "POST"],
)
app.add_url_rule(
    "/api/chat/<conversation_uuid>",
    view_func=ConversationController.as_view("conversation"),
    methods=["GET"],
)
app.add_url_rule(
    "/api/chat/<conversation_uuid>/messages",
    view_func=ConversationMessageController.as_view("conversation_message"),
    methods=["GET"],
)

app.add_url_rule(
    "/api/chat/<conversation_uuid>/preflight",
    view_func=ChatbotPreflightController.as_view("chatbot_preflight"),
    methods=["POST"],
)

app.add_url_rule(
    "/api/chat/<conversation_uuid>/<int:message_id>/query",
    view_func=ChatbotController.as_view("chatbot_query"),
    methods=["POST"],
)

app.add_url_rule(
    "/api/user/<int:user_id>",
    view_func=UserController.as_view("user"),
    methods=["GET"],
)

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port="8005", debug=True)
