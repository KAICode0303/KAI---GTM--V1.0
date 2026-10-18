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
GREETING = "Hi, I'm Hoomi, your GTM assistant. Where's your GTM headed? Let's find out."


def clean_name(text):
    """The optional display name ends up in HTML and in a script, so keep letters, spaces, hyphens and apostrophes only (max 30)."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z\u00C0-\u024F' -]", "", str(text or ""))).strip()[:30]


def greeting(name=""):
    name = clean_name(name)
    return GREETING if not name else GREETING.replace("Hi,", f"Hi {name},", 1)


def voice_button(text):
    """Optional spoken greeting. Runs entirely in the browser (Web Speech API), uses ONLY voices the device reports as local so the
    text is never sent to an online voice service, and speaks only after a click. If no local voice exists the button says so."""
    safe_text = json.dumps(text).replace("</", "<\\/")                 # a literal "</script>" must not be able to end the script block
    st.iframe(f"""
<div style="font-family:system-ui,sans-serif">
<button id="v" style="padding:.45rem .9rem;border-radius:12px;border:1px solid #9aaaf0;background:#fff;cursor:pointer;font-weight:600">🔊 Hear Hoomi's greeting</button>
<span id="m" style="margin-left:.6rem;font-size:.8rem;color:#58679A"></span></div>
<script>
const text = {safe_text};
const btn = document.getElementById('v'), msg = document.getElementById('m');
function localVoice() {{ return (speechSynthesis.getVoices() || []).find(v => v.localService && /^en/i.test(v.lang)) || (speechSynthesis.getVoices() || []).find(v => v.localService); }}
if (!('speechSynthesis' in window)) {{ btn.disabled = true; msg.textContent = 'Voice is not supported in this browser.'; }}
btn.onclick = () => {{
  const v = localVoice();
  if (!v) {{ msg.textContent = 'No on-device voice available, so nothing was spoken (text is never sent to an online voice).'; return; }}
  speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text); u.voice = v; u.rate = 1; speechSynthesis.speak(u);
  msg.textContent = 'Speaking with an on-device voice.';
}};
</script>""", height=60)


def choose(role):
    st.session_state.role = role
    landing = ROLES[role]["landing"]
    st.session_state.nav = landing
    st.session_state.nav_primary = landing
    st.session_state.nav_classic = None


def render():
    name = st.session_state.get("user_name", "")
    left, right = st.columns([1, 2.4], vertical_alignment="center")
    with left:
        mascot.render(230)
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
