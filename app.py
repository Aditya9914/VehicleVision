import json
from google import genai
from google.genai import types
import streamlit as st
from prompt import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT
from twilio.rest import Client

GEMINI_API_KEY = st.secrets["GENAI_API_KEY"]
TWILIO_ACCOUNT_SID = st.secrets["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = st.secrets["TWILIO_WHATSAPP_FROM"]   
TWILIO_CONTENT_SID = st.secrets["TWILIO_CONTENT_SID"]


@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_twilio_client():
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)  

twilio_client = get_twilio_client()
gemini_client = get_gemini_client()


def clean_whatsapp_text(text):
    if not text:
        return "No summary available."
    text = " ".join(text.split())
    return text[:1500] + "..." if len(text) > 1500 else text

def send_whatsapp(to_number, user_name, summary):
    try:
        content_variables = json.dumps(
            {"1": user_name, "2": clean_whatsapp_text(summary)}, ensure_ascii=False
        )
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_number}",
            content_sid=TWILIO_CONTENT_SID,
            content_variables=content_variables,
        )
        return True, message.sid
    except Exception as error:
        return False, str(error)

def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])

def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"

def add_message(role, kind, content):
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})
    render_message(st.session_state.messages[-1])


#Step 1: onboarding
if "onboarded" not in st.session_state:
    st.title("VehicleVision AI")
    st.caption("Welcome to VehicleVision AI! Please enter your details to get started.")

    with st.form("onboarding_form"):
        username = st.text_input("Username")
        whatsapp_number = st.text_input(
            "WhatsApp Number",
            placeholder="Enter your WhatsApp number (e.g., +911234567890)",
            help="Please include your country code.",
        )
        submitted = st.form_submit_button("Submit")

    if submitted:
        if username.strip() and whatsapp_number.strip():
            st.session_state.username = username.strip()
            st.session_state.whatsapp_number = (
                whatsapp_number.strip().replace(" ", "").replace("-", "")
            )
            st.session_state.chat = gemini_client.chats.create(
                model="gemini-3.8-flash",   
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
        else:
            st.error("Please fill in both fields to proceed.")

    st.stop()   


# Step 2: chat interface
header_col, button_col = st.columns([5, 2], vertical_alignment="center")

with header_col:
    st.title("VehicleVision AI Chat")

with button_col:
    send_disabled = len(st.session_state.messages) <= 1
    if st.button("📤 Send to WhatsApp", disabled=send_disabled, use_container_width=True):
        with st.spinner("Preparing your summary..."):
            summary = ask_gemini([SUMMARY_REQUEST_PROMPT])
        if summary.startswith("Sorry, something went wrong"):
            st.error(summary)
        else:
            success, info = send_whatsapp(
                st.session_state.whatsapp_number, st.session_state.username, summary
            )
            if success:
                st.success("Sent! Check your WhatsApp 📲")
            else:
                st.error(f"Couldn't send that: {info}")

st.caption(
    f"Logged in as {st.session_state.username} - updates go to {st.session_state.whatsapp_number}"
)

if not st.session_state.messages:
    add_message(
        "assistant", "text",
        WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.username),
    )
else:
    for message in st.session_state.messages:
        render_message(message)

user_input = st.chat_input(
    "Ask a question, or attach a photo of a vehicle",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))

    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append("What is this vehicle? Give me details about it.")

    with st.spinner("Analyzing..."):
        answer = ask_gemini(parts)
    add_message("assistant", "text", answer)