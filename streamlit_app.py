"""Streamlit UI for the Photo Data Puller.

Run with: streamlit run streamlit_app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from photo_data_puller import PhotoVerdict, analyze_photo


def _save_upload(upload) -> Path:
    temp_path = Path(st.session_state.get("_temp_dir", ".")) / upload.name
    temp_path.write_bytes(upload.getbuffer())
    return temp_path


def _render_report(result: PhotoVerdict) -> None:
    st.subheader("Result")
    st.success(result.verdict) if result.score >= 3 else st.warning(result.verdict)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Device make**")
        st.write(result.make or "Unknown")
        st.markdown("**Device model**")
        st.write(result.model or "Unknown")
        st.markdown("**Resolution**")
        st.write(result.resolution or "Unknown")
    with col2:
        st.markdown("**Timestamp**")
        st.write(result.timestamp or "Not found")
        st.markdown("**GPS info present**")
        st.write("Yes" if result.gps_info_present else "No")
        st.markdown("**Screenshot detected**")
        st.write("Yes" if result.screenshot_detected else "No")

    if result.reasons:
        st.markdown("**Notes**")
        st.write("\n".join(f"• {note}" for note in result.reasons))

    st.markdown("**Full JSON**")
    st.code(json.dumps(result.as_dict(), indent=2))


def main() -> None:
    st.set_page_config(page_title="Photo Data Puller", page_icon="📸")
    st.title("Photo Data Puller")
    st.write("Drop a photo to check for real-world camera traits.")

    upload = st.file_uploader("Drop or select a JPEG photo", type=["jpg", "jpeg"])
    if upload:
        path = _save_upload(upload)
        result = analyze_photo(path)
        _render_report(result)


if __name__ == "__main__":
    main()
