import requests
import os
import jwt
from flask import request
from .database import get_db


def verify_jwt(token):
    """
    Verify the JWT token and return the payload
    """

    try:
        url = request.url_root
        url = url[: url.rfind("/")]
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET"),
            audience=[url],
            algorithms=["HS256"],
            options={"verify_signature": True, "verify_exp": True},
        )
        return payload
    except jwt.ExpiredSignatureError as e:
        print(str(e))
        return None
    except jwt.InvalidSignatureError as e:
        print(str(e))
        return None
    except jwt.InvalidTokenError as e:
        print(str(e))
        return None


def get_user_has_subscription(token):
    """
    Check if the user has a subscription
    either to school or stripe
    """
    r = requests.post(
        os.getenv("COMENIO_API_URL") + "/api/user",
        headers={"Authorization": "Bearer " + token},
    )
    if r.status_code != 200:
        return None
    response = r.json()

    if "status" not in response:
        return False

    if (
        response["subscribed_school"] is False
        and response["subscribed_stripe"] is False
    ):
        return False
    else:
        return True


def get_user_messages_count(user_id) -> int:
    """
    Get the number of messages sent by the AI in the current month
    """
    conn = get_db()
    cursor = conn.cursor()

    # Fech the conversation associated with the UUID
    cursor.execute(
        """
        SELECT COUNT(*) FROM messages 
        WHERE user_id = ?
        AND type = 2
        AND DATE(created_at) BETWEEN DATE('now', 'start of month') AND DATE('now', 'start of month', '+1 month', '-1 day')
        """,
        (user_id,),
    )
    messages_count = cursor.fetchone()[0]
    if messages_count is None:
        return 0

    return int(messages_count)
