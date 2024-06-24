import os
import sqlite3
from flask import g

DATABASE = os.getenv("DATABASE_URL")

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db