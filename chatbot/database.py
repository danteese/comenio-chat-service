import os
import sqlite3
from flask import g

DATABASE = os.getenv("DATABASE_URL")

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


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