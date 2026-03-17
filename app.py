import streamlit as st

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("FX Pricer")
        st.subheader("Please enter the access password")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if password == st.secrets["password"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password")
        st.stop()

check_password()

st.title("FX Pricer")
st.markdown("Welcome. Use the menu on the left to navigate between modules.")
st.markdown("---")
col1, col2 = st.columns(2)
with col1:
    st.info("📈 **FX Forwards**\nLive forward rates with cross calculation")
with col2:
    st.info("🧮 **FX Options**\nManual volatility surface and option pricer")
