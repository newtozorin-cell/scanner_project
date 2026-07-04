import hashlib
import json
import os
import requests
from datetime import datetime
import pytz
from fyers_apiv3 import fyersModel
from config import CLIENT_ID, SECRET_KEY, REDIRECT_URI, STATE

IST = pytz.timezone("Asia/Kolkata")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")


def get_app_id_hash():
    raw = f"{CLIENT_ID}:{SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_auth_url():
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        state=STATE
    )
    return session.generate_authcode()


def exchange_auth_code(auth_code):
    payload = {
        "grant_type": "authorization_code",
        "appIdHash": get_app_id_hash(),
        "code": auth_code
    }
    resp = requests.post(
        "https://api-t1.fyers.in/api/v3/validate-authcode",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    data = resp.json()
    if data.get("s") == "ok":
        _save_token(data["access_token"])
        return True, data["access_token"]
    return False, data.get("message", "Token exchange failed")


def _save_token(access_token):
    now = datetime.now(IST)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": access_token,
            "saved_at": now.strftime("%Y-%m-%d %H:%M:%S")
        }, f)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        try:
            data = json.load(f)
            return data.get("access_token")
        except Exception:
            return None


def is_token_valid():
    if not os.path.exists(TOKEN_FILE):
        return False
    with open(TOKEN_FILE, "r") as f:
        try:
            data = json.load(f)
            saved_at = datetime.strptime(data["saved_at"], "%Y-%m-%d %H:%M:%S")
            saved_at = IST.localize(saved_at)
        except Exception:
            return False

    now = datetime.now(IST)
    # Token expires at 06:30 AM IST daily
    expiry = now.replace(hour=6, minute=30, second=0, microsecond=0)
    if saved_at < expiry <= now:
        return False
    return True


def get_fyers_client():
    token = load_token()
    if not token:
        return None
    return fyersModel.FyersModel(client_id=CLIENT_ID, token=token, is_async=False, log_path="")
