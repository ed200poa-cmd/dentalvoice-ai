# DentalVoice AI Demo

A production-ready AI Voice Agent for dental and medical practices. Patients call a real phone number and speak naturally — the AI handles appointment booking, FAQs, and warm transfers to human staff, all without a single button press.

Built with **Python FastAPI**, **Twilio Voice**, **Anthropic Claude** (claude-haiku), and **ElevenLabs TTS**.

---

## What This Demo Does

- **Answers inbound calls** automatically via a Twilio phone number
- **Understands natural speech** — no menus, no "press 1 for..."
- **Books appointments** by collecting patient name, preferred time, and appointment type
- **Answers FAQs** — office hours, location, insurance, pricing
- **Detects emergencies** and fast-tracks to human transfer
- **Warm transfers** when caller says "speak to someone" or "representative"
- **Logs every call** to SQLite — caller number, intent, outcome, full transcript
- **ElevenLabs TTS** for lifelike voice (falls back to Twilio Polly if no key)
- **Railway-ready** — single `Procfile` deploy

---

## Architecture

```
Inbound Call (Twilio)
        │
        ▼
POST /webhook/voice          ← TwiML greeting + <Gather speech>
        │
        ▼ (caller speaks)
POST /webhook/gather
        │
        ├─► agent.process_speech()
        │         │
        │         ├─► Claude claude-haiku-20240307  (< 40 word responses)
        │         └─► Fallback rule engine          (if no API key)
        │
        ├─► tts.generate_elevenlabs_audio()         (or Twilio Polly TTS)
        │
        ├─► call_log.log_turn()                     (SQLite)
        │
        └─► TwiML Response
              ├── Normal turn  → <Play/Say> + <Gather> (loop)
              ├── Transfer     → <Dial> office number
              └── Booking done → <Hangup>
```

---

## Quick Start (Local)

### 1. Clone and install

```bash
git clone <repo-url>
cd dental_voice_agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY at minimum
```

### 3. Run the server

```bash
uvicorn main:app --reload --port 8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "DentalVoice AI",
  "practice": "Smile Care Dental",
  "available_slots": ["Tuesday at 2:00 PM", "..."],
  "integrations": {
    "anthropic": true,
    "elevenlabs": false,
    "twilio": false
  }
}
```

---

## Connect Twilio Webhook

### Step 1 — Expose local server with ngrok

```bash
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io
```

Set `BASE_URL=https://abc123.ngrok.io` in your `.env`, then restart uvicorn.

### Step 2 — Configure Twilio

1. Log in to [twilio.com/console](https://twilio.com/console)
2. Go to **Phone Numbers → Manage → Active Numbers**
3. Click your number
4. Under **Voice & Fax → A Call Comes In**, set:
   - **Webhook:** `https://abc123.ngrok.io/webhook/voice`
   - **Method:** `POST`
5. Under **Call Status Changes**, set:
   - **Webhook:** `https://abc123.ngrok.io/webhook/status`
6. Save

### Step 3 — Call your Twilio number

The agent picks up immediately.

---

## Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

# Deploy
railway init
railway up

# Set environment variables in Railway dashboard
# BASE_URL = https://your-app.up.railway.app
```

Railway detects the `Procfile` automatically:
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/voice` | Twilio inbound call entry point |
| `POST` | `/webhook/gather` | Handles speech/DTMF from caller |
| `POST` | `/webhook/status` | Twilio call status callback |
| `GET`  | `/audio/{file}` | Serves cached ElevenLabs audio |
| `GET`  | `/logs` | View all call records (JSON) |
| `GET`  | `/logs/{call_sid}` | Full conversation transcript |
| `GET`  | `/health` | Health check + integration status |

---

## Sample Conversation Transcript

```
[RING]

Sarah (AI):  "Thank you for calling Smile Care Dental. This is Sarah.
              How can I help you today?"

Patient:     "Hi, I'd like to book an appointment for a cleaning."

Sarah (AI):  "I'd be happy to help schedule that! May I have your name please?"

Patient:     "Sure, it's Michael Torres."

Sarah (AI):  "Great, Michael! We have openings Tuesday at 2pm, Wednesday at 10am,
              or Thursday at 3pm. Which works for you?"

Patient:     "Thursday at 3 works."

Sarah (AI):  "Perfect! I've booked Thursday at 3:00 PM for a teeth cleaning for
              Michael Torres. You'll receive a confirmation text. Anything else?"

Patient:     "No that's great, thank you!"

Sarah (AI):  "We look forward to seeing you, Michael! Goodbye!"

[CALL ENDS — logged to SQLite, outcome: booking_confirmed]
```

---

## Demo Data (Hardcoded)

| Detail | Value |
|--------|-------|
| Practice | Smile Care Dental |
| Address | 123 Main Street, Annapolis MD 21401 |
| Hours | Mon–Fri 8am–6pm, Sat 9am–2pm |
| Insurance | Delta Dental, Cigna, Aetna, BlueCross |
| Services | Cleaning, Whitening, Fillings, Emergency Care |
| Open Slots | Tue 2pm, Wed 10am, Thu 3pm, Fri 11am, Sat 9am |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ELEVENLABS_API_KEY` | No | ElevenLabs TTS (falls back to Polly) |
| `ELEVENLABS_VOICE_ID` | No | ElevenLabs voice ID (default: Bella) |
| `TWILIO_ACCOUNT_SID` | No* | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | No* | Twilio auth token |
| `BASE_URL` | Yes | Public URL of this server |
| `OFFICE_PHONE` | No | Transfer destination number |

*Required for production call handling; not needed for local API testing.

---

## Technologies Used

| Technology | Purpose |
|-----------|---------|
| **Python 3.12** | Runtime |
| **FastAPI + Uvicorn** | Async web framework |
| **Twilio Voice API** | Phone call handling, TwiML |
| **Anthropic Claude API** | Conversational AI (claude-haiku-20240307) |
| **ElevenLabs TTS** | Lifelike voice synthesis |
| **SQLite** | Call logging and transcripts |
| **Railway** | Cloud deployment platform |

---

## Project Structure

```
dental_voice_agent/
├── main.py              # FastAPI app — all routes + TwiML builders
├── agent.py             # Claude conversation engine + session state
├── tts.py               # ElevenLabs + Twilio TTS handler
├── call_log.py          # SQLite call logger
├── knowledge_base.py    # FAQ, office info, demo slots
├── requirements.txt     # Python dependencies
├── Procfile             # Railway/Heroku deployment
├── .env.example         # Environment variable template
└── README.md
```

---

## Extending for Production

- **Real calendar integration:** Swap `knowledge_base.get_available_slots()` with Google Calendar API or Acuity Scheduling
- **Patient lookup:** Connect `agent.py` to your PMS (Dentrix, Eaglesoft, etc.) via REST API
- **SMS confirmation:** Add Twilio SMS after `booking_confirmed` event
- **Multi-language:** ElevenLabs + Claude both support Spanish — add language detection
- **Analytics dashboard:** Build on top of the `/logs` SQLite data

---

Built by **Edward Kim** — AI Voice Assistant Developer
