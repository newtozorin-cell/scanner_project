from flask import Flask, jsonify, render_template, request
from apscheduler.schedulers.background import BackgroundScheduler
from scanner import run_all_scanners
from trade_logger import load_trades
from fyers_auth import generate_auth_url, exchange_auth_code, is_token_valid
import pytz

app = Flask(__name__)
IST = pytz.timezone("Asia/Kolkata")

scheduler = BackgroundScheduler(timezone=IST)
scheduler.add_job(run_all_scanners, "interval", minutes=1, id="scanner_job")
scheduler.start()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/trades")
def api_trades():
    trades = load_trades()
    trades_sorted = sorted(trades, key=lambda x: x.get("logged_at", ""), reverse=True)
    return jsonify(trades_sorted)


@app.route("/api/run")
def manual_run():
    run_all_scanners()
    return jsonify({"status": "ok", "message": "Scanner run triggered manually."})


@app.route("/api/auth/url")
def auth_url():
    url = generate_auth_url()
    return jsonify({"url": url})


@app.route("/api/auth/token", methods=["POST"])
def auth_token():
    body = request.get_json()
    pasted_url = body.get("url", "").strip()

    # Extract auth_code from the pasted redirect URL
    auth_code = None
    if "auth_code=" in pasted_url:
        for part in pasted_url.split("&"):
            if part.startswith("auth_code=") or "auth_code=" in part:
                auth_code = part.split("auth_code=")[-1].split("&")[0]
                break

    if not auth_code:
        return jsonify({"status": "error", "message": "Could not extract auth_code from URL. Please paste the full redirect URL."})

    success, result = exchange_auth_code(auth_code)
    if success:
        return jsonify({"status": "ok", "message": "Login successful! Scanner is now active."})
    return jsonify({"status": "error", "message": result})


@app.route("/api/auth/status")
def auth_status():
    valid = is_token_valid()
    return jsonify({"logged_in": valid})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
