import requests
import os
import jwt
from flask import request, abort
from .database import get_db


def verify_jwt(token):
    """
    Verify the JWT token and return the payload

    :param token: The JWT token to verify
    :return: The payload of the JWT token
    :raises: 403 if the token is invalid
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
        abort(403, description="Invalid Token") 
    except jwt.InvalidSignatureError as e:
        print(str(e))
        abort(403, description="Invalid Token(2)") 
    except jwt.InvalidTokenError as e:
        print(str(e))
        abort(403, description="Invalid Token(3)")


def get_user_has_subscription(token):
    """
    Check if the user has a subscription
    either to school or stripe

    :param token: The JWT token
    :return: True if the user has a subscription, False otherwise
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

    :param user_id: The user ID
    :return: The number of messages sent by the AI in the current month
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
