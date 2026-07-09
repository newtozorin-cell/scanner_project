from flask import Flask, jsonify, render_template, request, redirect, send_file
from apscheduler.schedulers.background import BackgroundScheduler
from scanner import run_all_scanners
from trade_logger import load_trades, export_backup, import_backup
from fyers_auth import generate_auth_url, exchange_auth_code, is_token_valid
import pytz
import os

app = Flask(__name__)
IST = pytz.timezone("Asia/Kolkata")

scheduler = BackgroundScheduler(timezone=IST)
scheduler.add_job(run_all_scanners, "interval", minutes=1, id="scanner_job")
scheduler.start()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/auth/callback")
def auth_callback():
    # Fyers redirects here with auth_code in query params
    # We show a page that lets user copy the full URL
    return render_template("auth_callback.html")


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

    auth_code = None
    if "auth_code=" in pasted_url:
        for part in pasted_url.replace("?", "&").split("&"):
            if "auth_code=" in part:
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


@app.route("/api/backup/save", methods=["GET"])
def backup_save():
    """Save current trades to a JSON backup file and send it as a download."""
    backup_path = export_backup()
    return send_file(
        backup_path,
        mimetype="application/json",
        as_attachment=True,
        download_name=os.path.basename(backup_path)
    )


@app.route("/api/backup/load", methods=["POST"])
def backup_load():
    """Restore trades from an uploaded backup JSON file."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded."}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"status": "error", "message": "Empty filename."}), 400
    if not f.filename.lower().endswith(".json"):
        return jsonify({"status": "error", "message": "Please upload a .json backup file."}), 400

    tmp_path = os.path.join(os.path.dirname(__file__), "_uploaded_backup.json")
    f.save(tmp_path)
    try:
        count = import_backup(tmp_path)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Invalid backup file: {e}"}), 400
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return jsonify({"status": "ok", "message": f"Restored {count} trades from backup."})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
