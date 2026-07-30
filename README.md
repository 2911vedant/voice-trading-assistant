# VoiceTrade — Voice-Driven Conditional Trading Assistant

Free-form voice/text commands in English, Hindi, Marathi, or Hinglish →
structured trade intent JSON → human confirmation → paper trade execution
(or real broker, if you wire in credentials).

No fixed command grammar — parsing is done by an LLM (Groq
`llama-3.3-70b-versatile`) prompted as an NLU engine, so it generalizes to
however you phrase the order instead of matching hardcoded templates.

## Architecture

```
voice (mic) ──► Groq Whisper (STT) ──► raw text
                                          │
                                          ▼
                              nlu_engine.py (Groq LLM)
                          intent + entities + condition → JSON
                                          │
                                          ▼
                         Confirmation UI (edit fields, Confirm/Cancel)
                                          │
                          confirmed=true  ▼
                              /api/confirm (Flask)
                         ┌────────────────┴─────────────────┐
                         ▼                                   ▼
                no condition → execute now         condition → arm watch
                         │                                   │
                         ▼                                   ▼
                 broker_adapter.place_order      condition_monitor.py polls
                         │                        price_feed every 3s, fires
                         ▼                        broker_adapter when met
                 trade_log.py (history)  ◄─────────────────┘
                         │
                         ▼
                 dashboard (prices, active conditions, trade log)
```

## Setup

```bash
cd voice_trading_assistant/backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `GROQ_API_KEY` (get one free at console.groq.com).
Leave `BROKER_MODE=PAPER` — this is the safe default and needs no other
credentials.

```bash
# still inside backend/, with venv active
export $(cat .env | xargs)        # or use python-dotenv / your shell's method
python app.py
```

Backend runs on `http://localhost:5004`.

Open `frontend/index.html` directly in a browser (double-click it, or
serve it with `python -m http.server 8080` from the `frontend/` folder
and visit `http://localhost:8080`). Grant microphone permission when
prompted.

## Using it

1. Tap the mic, say something like *"Buy 20 shares of Tata Motors if
   price is less than 500 rupees"* or *"Reliance 350 se kam ho to 10
   shares le lo"* — or just type it and hit **Parse command**.
2. Review the confirmation card: action, asset, quantity, condition,
   detected language, and the model's confidence. Edit any field that's
   wrong.
3. **Confirm & Execute** — market orders fill immediately (paper); the
   dashboard trade log will show the plain-English explanation.
   Conditional orders get armed and show up under **Active conditions**;
   they fire automatically once `condition_monitor.py` sees the
   simulated price cross your threshold, and the explanation is
   generated then (e.g. *"Trade executed: BUY 20 TATA MOTORS because the
   price dropped below ₹500"*).
4. Cancel an armed condition anytime from the dashboard before it fires.

## Going from paper to real brokers

**PAPER (default)** — everything above works standalone, no external
trading account needed. `price_feed.py` runs a simulated random-walk
price series seeded from a handful of NSE names; extend `_SEED_PRICES`
for more symbols.

**Zerodha (Kite Connect)** — real, documented API, but:
- It's a separate paid subscription from your trading account
  (register an app at developers.kite.trade).
- Auth requires a daily browser login/redirect flow to mint an
  `access_token` — this can't be done headlessly, so you (or a small
  separate login script following [Kite's login flow
  docs](https://kite.trade/docs/connect/v3/user/#login-flow)) need to
  refresh `KITE_ACCESS_TOKEN` in `.env` once a day.
- Set `BROKER_MODE=ZERODHA`, `KITE_API_KEY`, `KITE_ACCESS_TOKEN`, then
  `pip install kiteconnect` if you haven't already.
- `broker_adapter.ZerodhaBroker` places real market orders via
  `kite.place_order(...)` — test with tiny quantities first.

**Groww** — Groww has been rolling out an API for programmatic/algo
trading, separate from the retail app, but it's newer than what I can
verify with full confidence from here. `broker_adapter.GrowwBroker` is
left as an intentional stub (raises `NotImplementedError`) rather than
guessed method names — check Groww's current official developer docs
for the auth flow and SDK before filling it in.

**Either way**: nothing executes without hitting `/api/confirm` with
`confirmed: true`, which only happens when you click **Confirm &
Execute** in the UI. There is no code path that places a live order
straight from a voice command.

## Extending

- Swap `nlu_engine`'s Groq model for any other chat-completions-style
  endpoint by changing the client and `MODEL` constant — the JSON
  contract stays the same.
- `trade_log.py` is in-memory; swap for SQLite/Postgres for persistence
  across restarts.
- `price_feed.py`'s `get_price()` is the single seam to replace with a
  real broker's LTP (last traded price) call once you're live.
