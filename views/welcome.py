"""Welcome screen: Hoomi's greeting, optional local voice, and the Leadership Hub / GTM Team choice.

Choosing a role is NAVIGATION ONLY. It is not authentication: there are no accounts or passwords, and it does not restrict any data.
"""
import json
import re

import streamlit as st

import theme
from views import mascot

ROLES = {
    "Leadership Hub": {"icon": "🧭", "blurb": "See where the GTM is headed.",
                       "bullets": ["Executive Pulse: KPIs, charts and a plain-language summary", "Ask Hoomi about the numbers and approved documents",
                                   "Open the GTM Workspace to drill into any record"],
                       "landing": "📊  Executive Pulse", "order": ["📊  Executive Pulse", "🤖  Ask Hoomi", "🗂️  GTM Workspace"]},
    "GTM Team": {"icon": "🚀", "blurb": "Run the day-to-day pipeline.",
                 "bullets": ["GTM Workspace: accounts, prospects, outreach, opportunities", "Follow-ups with dates, channels, outcomes and stop rules",
                             "Ask Hoomi about services, ICPs, positioning and KYC profiles"],
                 "landing": "🗂️  GTM Workspace", "order": ["🗂️  GTM Workspace", "🤖  Ask Hoomi", "📊  Executive Pulse"]},
}
GREETING = "Hey, I'm Hoomi! Your GTM copilot. Ready to make some moves?"


def clean_name(text):
    """The optional display name ends up in HTML and in a script. Only plain names are accepted (letters, spaces, hyphens, apostrophes, dots;
    max 30). Anything containing other characters, such as markup, is rejected outright rather than partly kept."""
    name = re.sub(r"\s+", " ", str(text or "")).strip()
    return name if len(name) <= 30 and re.fullmatch(r"[A-Za-z\u00C0-\u024F' .-]*", name) else ""


def greeting(name=""):
    name = clean_name(name)
    return GREETING if not name else GREETING.replace("Hey,", f"Hey {name},", 1)


VOICE_HTML = """
<div style="font-family:system-ui,sans-serif;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
<button id="play" style="padding:.45rem .9rem;border-radius:12px;border:1px solid #9aaaf0;background:#fff;cursor:pointer;font-weight:700">▶ Play greeting</button>
<button id="mute" style="padding:.45rem .9rem;border-radius:12px;border:1px solid #9aaaf0;background:#fff;cursor:pointer;font-weight:700">🔇 Mute</button>
<span id="msg" style="font-size:.8rem;color:#58679A"></span></div>
<script>
const TEXT = __TEXT__;
const FEMININE = /samantha|karen|moira|tessa|victoria|ava|allison|susan|fiona|veena|serena|kate|zira|aria|jenny|hazel|libby|sonia|female|woman/i;
const play = document.getElementById('play'), mute = document.getElementById('mute'), msg = document.getElementById('msg');
let muted = false;
try {{ muted = localStorage.getItem('hoomiMuted') === '1'; }} catch (e) {{}}
const supported = 'speechSynthesis' in window;
function voice() {{
  const local = (speechSynthesis.getVoices() || []).filter(v => v.localService && /^en/i.test(v.lang));   // on-device only: the text never goes to an online voice
  return local.find(v => FEMININE.test(v.name)) || null;
}}
function refresh() {{
  mute.textContent = muted ? '🔊 Unmute' : '🔇 Mute';
  if (!supported) {{ play.disabled = mute.disabled = true; msg.textContent = 'Voice is not supported in this browser.'; return; }}
  if (!voice()) {{ play.disabled = true; msg.textContent = 'No suitable on-device voice found, so the greeting stays silent.'; return; }}
  play.disabled = muted; msg.textContent = muted ? 'Muted.' : 'Ready (on-device voice, no online service).';
}}
play.onclick = () => {{
  const v = voice(); if (!v || muted) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(TEXT); u.voice = v; u.pitch = 1.2; u.rate = 0.95; u.volume = 1;   // a little brighter and slower reads more melodic
  speechSynthesis.speak(u);
}};
mute.onclick = () => {{
  muted = !muted; try {{ localStorage.setItem('hoomiMuted', muted ? '1' : '0'); }} catch (e) {{}}
  if (muted && supported) speechSynthesis.cancel();
  refresh();
}};
if (supported) {{ speechSynthesis.onvoiceschanged = refresh; }}
refresh();
</script>"""


def voice_button(text):
    """Optional spoken greeting with Play and Mute. Runs entirely in the browser (Web Speech API): only a recognised feminine ON-DEVICE
    English voice is ever used, so the text is never sent to an online or paid voice service. No suitable voice means the controls are
    disabled with a short note. Nothing plays until you click."""
    safe_text = json.dumps(text).replace("</", "<\\/")                  # a literal "</script>" must not be able to end the script block
    st.iframe(VOICE_HTML.replace("{{", "{").replace("}}", "}").replace("__TEXT__", safe_text), height=64)


def choose(role):
    st.session_state.role = role
    landing = ROLES[role]["landing"]
    st.session_state.nav = landing
    st.session_state.nav_primary = landing
    st.session_state.nav_classic = None


def render():
    name = st.session_state.get("user_name", "")
    left, right = st.columns([1.1, 2.4], vertical_alignment="center")
    with left:
        mascot.render(300)
    with right:
        st.markdown(f'<div class="hero" style="margin:0">{theme.sparkles()}<div class="eyebrow">Kai\'s GTM V2.0</div>'
                    f'<h1>Welcome. Meet Hoomi.</h1><p>{theme.safe(greeting(name))}</p></div>', unsafe_allow_html=True)
        st.write("")
        st.text_input("What should Hoomi call you? (optional)", key="user_name", placeholder="Your first name")
        voice_button(greeting(name))
    st.write("")
    theme.section("Choose your view", "navigation only: this is not a login")
    cols = st.columns(2)
    for col, (role, spec) in zip(cols, ROLES.items()):
        with col:
            bullets = "".join(f"<li>{b}</li>" for b in spec["bullets"])
            st.markdown(f'<div class="role-card"><div style="font-size:1.8rem">{spec["icon"]}</div><h3>{role}</h3><p>{spec["blurb"]}</p><ul>{bullets}</ul></div>',
                        unsafe_allow_html=True)
            st.button(f"Enter the {role}", key=f"role_{role}", type="primary", width="stretch", on_click=choose, args=(role,))
    st.markdown('<div class="note"><b>Good to know.</b> Picking a role only changes which pages come first. There is no authentication, '
                'and every page is open to both views.</div>', unsafe_allow_html=True)
