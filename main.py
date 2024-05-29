import os
import sqlite3
from flask import Flask, request, jsonify, make_response, g, stream_with_context, Response
from flask_cors import CORS
from llama_index.llms.openai import OpenAI
from llama_index.core.chat_engine import SimpleChatEngine
from dotenv import load_dotenv

load_dotenv()

os.environ['OPENAI_API_KEY'] = os.getenv("OPENAI_API_KEY")
print(os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)
CORS(app)

comenio_personality = """
You are Comenio, an assistant with expertise in supporting teachers to enhance the educational experience and improve overall efficiency. Your main objectives are to provide instructional support, facilitate communication, and assist with administrative tasks. Your role is to act as a supportive, reliable, and efficient assistant, helping teachers streamline their tasks and improve the learning environment for their students.

To fulfill your role, you must follow these guidelines:

	1.	Give concise responses to very simple questions, but provide thorough responses to more complex and open-ended questions.
	2.	Answer the user in the language the user writes to you.
	3.	Treat all users with respect and avoid making any discriminatory or offensive statements.
	4.	Swiftly identify the user’s intent and tailor your responses accordingly.
	5.	If you find that the information at hand is inadequate to fulfill your role and objectives, please ask the user for further information.
    6.  Always answer in plain text, do not use any HTML or other markup languages.
"""

DATABASE = './chatbot.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


def is_user_valid():
    pass # TODO: Validate token with main service or query database :S 


def is_conversation_valid(conversation_id)->bool:
    """
    Check if the conversation exists in the database
    @param conversation_id: The conversation ID to check
    @return: True if the conversation exists, False otherwise
    """
    cursor = get_db().cursor()
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    conversations = cursor.fetchone()
    return conversations is not None

@app.route("/api/chat/<int:user_id>/<int:conversation_id>/preflight", methods=["POST"])
def preflight(user_id=None, conversation_id=None):
    if user_id is None or conversation_id is None:
        return {"error": "User ID is required"}, 400
    
    # TODO: Implement user validation
    if not is_conversation_valid(conversation_id):
        return {"error": "Invalid conversation ID"}, 400

    print(request.json["message"])

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages(conversation_id, user_id, type, message) VALUES(?,?,?,?)", 
                   (conversation_id, user_id, 1, request.json["message"]))
    conn.commit()
    human_message = cursor.lastrowid
    cursor.execute("INSERT INTO messages(conversation_id, user_id, type, message) VALUES(?,?,?,?)", 
                   (conversation_id, user_id, 2, ""))
    conn.commit()
    ai_message = cursor.lastrowid

    cursor.execute("""SELECT id, conversation_id, message, type, DATETIME(created_at,'localtime') as created_at 
                   FROM messages WHERE id IN (?,?) ORDER BY created_at ASC""", (human_message, ai_message))
    messages = cursor.fetchall()
    column_names = list(map(lambda x: x[0], cursor.description))
    result = [dict(zip(column_names, row)) for row in messages]
    return jsonify({"messages": result}) 


@app.route("/api/chat/<int:user_id>/<int:conversation_id>/<int:message_id>/query", methods=["POST"])
def ask(user_id=None, conversation_id=None, message_id=None):
    if user_id is None or conversation_id is None:
        return {"error": "User ID is required"}, 400
    
    if not request.json:
        return {"error": "Request body is required"}, 400
    
    # TODO: Implement user validation
    if not is_conversation_valid(conversation_id):
        return {"error": "Invalid conversation ID"}, 400

    @stream_with_context
    def generate():
        data = request.json
        full_response = ""
        llm = OpenAI(temperature=0.5, model="gpt-3.5-turbo")
        chat_engine = SimpleChatEngine.from_defaults(llm=llm, system_prompt=comenio_personality)
        message = data["message"] if "message" in data else ""
        response_stream = chat_engine.stream_chat(message)
        for response in response_stream.response_gen:
            full_response += response.replace('\n', '<br/>')
            yield response

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET message = ? WHERE id = ?", (full_response, message_id,))
        conn.commit()
        print(full_response)
    
    return Response(generate(), mimetype="text/event-stream", content_type="charset=UTF-8", headers={'X-Accel-Buffering': "no"})
    # return chat_engine.chat(data["message"]).response


@app.route('/api/chat/<int:user_id>', methods=['GET'])
def get_chat(user_id=None):
    cursor = get_db().cursor()
    cursor.execute("SELECT id, DATETIME(created_at,'localtime') as created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    conversations = cursor.fetchall()
    column_names = list(map(lambda x: x[0], cursor.description))
    result = [dict(zip(column_names, row)) for row in conversations]
    return jsonify({"conversations": result})


@app.route('/api/chat/<int:user_id>', methods=['POST'])
def post_chat(user_id=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO conversations(user_id) VALUES(?)", (user_id,))
    conn.commit()
    print(cursor.lastrowid)
    return jsonify({"conversation": cursor.lastrowid})


@app.route('/api/chat/<int:user_id>/<int:conversation_id>/messages', methods=['GET'])
def get_conversation(user_id=None, conversation_id=None):
    # TODO: Implement user validation
    if not is_conversation_valid(conversation_id):
        return {"error": "Invalid conversation ID"}, 400

    
    cursor = get_db().cursor()
    cursor.execute("SELECT id, conversation_id, message, type, DATETIME(created_at,'localtime') as created_at FROM messages WHERE conversation_id = ? and user_id = ? ORDER BY created_at ASC", (conversation_id, user_id))
    messages = cursor.fetchall()
    column_names = list(map(lambda x: x[0], cursor.description))
    result = [dict(zip(column_names, row)) for row in messages]
    print(messages)
    return jsonify({"messages": result})


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


if __name__ == '__main__':
    app.run(host="0.0.0.0", port="8005", debug=True)