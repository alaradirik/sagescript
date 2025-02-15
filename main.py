import streamlit as st
from streamlit_oauth import OAuth2Component

st.set_page_config(page_title="SageScript AI", page_icon="🎙️", layout="wide")

# Custom CSS
st.markdown("""
    <style>
    .title {
        font-family: "SF Pro Display", -apple-system, BlinkMacSystemFont, sans-serif;
        background: linear-gradient(45deg, #1E3A8A, #3B82F6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    </style>
""", unsafe_allow_html=True)

# Title and logo
col1, col2 = st.columns([1, 8])
with col1:
    st.image("https://picsum.photos/100", width=80)
with col2:
    st.markdown("<h1 class='title'>SageScript AI</h1>", unsafe_allow_html=True)

# App description
st.markdown("""
### About SageScript AI
SageScript AI is an intelligent medical scribe that assists healthcare providers with consultation documentation. 
It transcribes medical consultations and generates structured clinical notes while incorporating patient history.

### Features
- **Voice Recording**: Record consultations directly or upload audio files
- **Smart Transcription**: Accurate transcription of medical conversations
- **Context-Aware Reports**: Generates reports based on transcribed consultation and patient history
- **FHIR Compatible**: Seamlessly integrates with FHIR-based health records
- **Editable Reports**: Review and modify generated reports
""")

# Authentication section
st.divider()
st.markdown("### Sign in to continue")

# OAuth setup
sign_in_options = [{'workspace_id': st.secrets["WORKSPACE_ID"], 'name': 'MeldRx', 'search_requirements': None}]
AUTHORIZE_URL = 'https://app.meldrx.com/connect/authorize'
TOKEN_URL = 'https://app.meldrx.com/connect/token'
REFRESH_TOKEN_URL = 'https://app.meldrx.com/connect/token'
REVOKE_TOKEN_URL = 'https://app.meldrx.com/connect/revocation'
REVOKE_TOKEN_URL = 'https://app.meldrx.com/connect/userinfo'
CLIENT_ID = st.secrets["CLIENT_ID"] 
CLIENT_SECRET = st.secrets["CLIENT_SECRET"] 
SCOPE = 'openid profile patient/*.read'

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_URL, TOKEN_URL, REFRESH_TOKEN_URL)

for option in sign_in_options:
    workspace_id = option['workspace_id']
    result = oauth2.authorize_button(
        name=option['name'],
        redirect_uri=f'https://sagescript-ai.streamlit.app/component/streamlit_oauth.authorize_button',
        scope=SCOPE,
        extras_params={'aud': f'https://app.meldrx.com/api/fhir/{workspace_id}'},
        pkce='S256'
    )

    if result and 'token' in result:
        st.session_state.token = result.get('token')
        st.session_state.workspace_id = workspace_id
        st.session_state.search_requirements = option['search_requirements']

if 'token' in st.session_state:
    st.success("Successfully logged in!")