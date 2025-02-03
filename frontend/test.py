import requests
import streamlit as st

st.write("🔍 Testing Internet Access:")

try:
    google_response = requests.get("https://www.google.com", timeout=10)
    if google_response.status_code == 200:
        st.success("✅ Internet access is working.")
    else:
        st.error(f"🚨 Google access failed: {google_response.status_code}")
except requests.exceptions.RequestException as e:
    st.error(f"⚠️ Internet access failed: {str(e)}")
