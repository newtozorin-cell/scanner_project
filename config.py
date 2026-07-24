import os

CLIENT_ID    = os.environ.get("FYERS_APP_ID", "ABC-100")
SECRET_KEY   = os.environ.get("FYERS_SECRET_ID", "ABC")
REDIRECT_URI = os.environ.get("FYERS_REDIRECT_URI", "https://trade.fyers.in/api-login/redirect-uri/index.html")
STATE        = "scanner_state"
