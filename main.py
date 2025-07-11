from fastapi import FastAPI
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel
import requests
import json
import yagmail
import re
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware


class ScheduleRequest(BaseModel):
    message: str

SCOPES = ['https://www.googleapis.com/auth/calendar']
MODEL_URL = "http://localhost:11434/api/chat"  # Ollama Gamma

app = FastAPI()

# Google Calendar Authentication
flow = InstalledAppFlow.from_client_secrets_file('D:/TurkTelekom/Projeler/Active Projeler/Agentic AI/Kod/ai_meeting_assistant/client_secret.json', SCOPES)
creds = flow.run_local_server(port=0)
calendar_service = build('calendar', 'v3', credentials=creds)



# Function: Use Ollama Gamma to extract meeting info/ # 🔍 Extract info from LLM
def extract_meeting_info(text: str):
    prompt = f"""
You are a meeting assistant. Extract the meeting details and return ONLY valid JSON:

Expected format:
{{
  "person_name": "Reza",
  "start_date": "2025-07-15T18:00:00Z",
  "end_date": "2025-07-15T19:30:00Z",
  "duration_minutes": 30
}}

Now extract from: "{text}"
"""

    try:
        res = requests.post("http://localhost:11434/api/chat", json={
            "model": "gemma:2b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        })

        res_json = res.json()
        print("🔍 Raw Ollama response:", res_json)
        content = res_json.get("message", {}).get("content", "")
        print("🔍 Raw content:", content)

        
        # Extract only the first JSON-like block
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            print("✅ Parsed JSON:", parsed)
            return parsed
        else:
            print("❌ No JSON structure found in LLM response.")
            return {}
    except Exception as e:
        print("❌ Final parse error:", e)
        return {}

# Function: Check availability
def get_calendar_events(email, start_date, end_date):
    result = calendar_service.events().list(
        calendarId=email,
        timeMin=start_date,
        timeMax=end_date,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    return result.get('items', [])

# Function: Create meeting and return link
def create_meeting(email, start, end, attendees):
    event = {
        'summary': 'Scheduled Meeting',
        'start': {'dateTime': start, 'timeZone': 'UTC'},
        'end': {'dateTime': end, 'timeZone': 'UTC'},
        'attendees': [{'email': e} for e in attendees],
        'conferenceData': {
            'createRequest': {
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                'requestId': 'meeting-123'
            }
        }
    }
    created_event = calendar_service.events().insert(
        calendarId=email,
        body=event,
        conferenceDataVersion=1
    ).execute()
    return created_event.get('hangoutLink')

# Function: Send confirmation email
def send_email(to, subject, content):
    try:
        yag = yagmail.SMTP("niinaa.aalami@gmail.com", "UYGULAMA_ŞİFRESİ")  # ← Buraya App Password gelecek!
        yag.send(to=to, subject=subject, contents=content)
    except Exception as e:
        print("❌ Email sending failed:", e)

# API Endpoint
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.post("/schedule")
async def schedule_meeting(request: ScheduleRequest):
    user_message = request.message

    info = extract_meeting_info(user_message)
    if not info:
        return {"error": "Could not extract meeting info"}

    # Skipping availability check for now — just take first gap manually:
    try:
        print("📌 Extracted info:", info)
        start = info['start_date']
        duration = info['duration_minutes']

        start_dt = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
        end_dt = start_dt + timedelta(minutes=duration)
        end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        print("📅 Meeting time:", start, "to", end)
    except Exception as e:
        print("❌ Date handling failed:", e)
        return {"error": "Invalid start time format or missing field"}
    try:
        meet_link = create_meeting("primary", start, end, ["niinaa.aalami@gmail.com"])
        send_email("niinaa.aalami@gmail.com", "Meeting Confirmed", f"Join via: {meet_link}")
        return {"status": "Meeting scheduled", "link": meet_link}
    except Exception as e:
        print("❌ Calendar or email failed:", e)
        return {"error": "Meeting creation or email failed"}
