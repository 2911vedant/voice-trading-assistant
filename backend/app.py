"""
app.py
Flask backend for the Voice-Driven Conditional Trading Assistant.
Run: python app.py   (defaults to port 5004, matching the AutoDebug/5001,
Mechanical Fault Analyzer/5002, Driver Behavior/5003 port convention)
"""

import os
import tempfile

from flask import Flask, jsonify, request
from flask_cors import CORS
from groq import Groq

import broker_adapter
import condition_monitor
import nlu_engine
import price_feed
import trade_log

app = Flask(__name__)
CORS(app)

_groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "broker_mode": os.environ.get("BROKER_MODE", "PAPER")})


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    """
    Accepts multipart/form-data with an 'audio' file field (webm/wav/mp3/m4a).
    Uses Groq's hosted Whisper (whisper-large-v3-turbo) for STT, which
    handles Hindi/Marathi/English/mixed audio without needing a local
    Whisper model.
    """
    if "audio" not in request.files:
        return jsonify({"error": "no audio file provided"}), 400

    audio_file = request.files["audio"]
    suffix = os.path.splitext(audio_file.filename or "audio.webm")[1] or ".webm"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcription = _groq_client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), f.read()),
                model="whisper-large-v3-turbo",
                response_format="json",
                # language left unset intentionally: Whisper auto-detects
                # Hindi/Marathi/English/mixed input rather than being
                # forced into one fixed language.
            )
        return jsonify({"text": transcription.text})
    except Exception as e:
        return jsonify({"error": f"transcription failed: {e}"}), 500
    finally:
        os.remove(tmp_path)


@app.route("/api/parse", methods=["POST"])
def parse():
    """
    Body: {"text": "buy 20 shares of tata motors if price is less than 500"}
    Returns structured trade intent JSON (not yet executed).
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    parsed = nlu_engine.parse_command(text)
    return jsonify(parsed)


@app.route("/api/confirm", methods=["POST"])
def confirm():
    """
    Body: the (possibly user-edited) parsed order JSON from /api/parse,
    plus the required top-level field "confirmed": true.
    This is the ONLY endpoint that can lead to an order being placed or
    a conditional watch being armed — nothing executes without hitting
    this endpoint with confirmed=true.
    """
    order = request.get_json(silent=True) or {}

    if not order.get("confirmed"):
        return jsonify({"error": "order not confirmed by user"}), 400

    action = order.get("action")
    asset = order.get("asset")
    quantity = order.get("quantity")
    condition = order.get("condition")

    if action not in ("BUY", "SELL"):
        return jsonify({"error": f"unsupported or unrecognized action: {action}"}), 400
    if not asset:
        return jsonify({"error": "asset is required"}), 400
    if not quantity or quantity <= 0:
        return jsonify({"error": "quantity must be a positive number"}), 400

    broker = broker_adapter.get_broker()

    # No condition (or condition disabled) -> execute immediately.
    if not condition or condition.get("type") in (None, "none"):
        result = broker.place_order(action=action, symbol=asset, quantity=quantity)
        explanation = nlu_engine.explain_execution(order, result.get("fill_price") or price_feed.get_price(asset))
        entry = {**result, "explanation": explanation, "condition_id": None}
        trade_log.log_trade(entry)
        return jsonify({"status": "executed", "trade": entry})

    # Conditional -> arm a watch, condition_monitor fires it later.
    cid = trade_log.add_condition(order)
    return jsonify({
        "status": "armed",
        "message": f"Condition armed. Will execute automatically when price {condition.get('operator')} ₹{condition.get('value')}.",
        "condition_id": cid,
    })


@app.route("/api/cancel/<int:condition_id>", methods=["POST"])
def cancel_condition(condition_id):
    trade_log.remove_condition(condition_id)
    return jsonify({"status": "cancelled", "condition_id": condition_id})


@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    return jsonify({
        "prices": price_feed.get_all_prices(),
        "active_conditions": trade_log.list_active_conditions(),
        "trade_history": trade_log.list_trade_history(),
    })


@app.route("/api/price/<symbol>", methods=["GET"])
def price(symbol):
    return jsonify({"symbol": symbol.upper(), "price": price_feed.get_price(symbol)})


if __name__ == "__main__":
    price_feed.start_price_feed()
    condition_monitor.start_monitor()
    app.run(host="0.0.0.0", port=5004, debug=True, use_reloader=False)
