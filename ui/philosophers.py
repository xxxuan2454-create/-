"""西方哲学家全景网络图 - 交互式可视化"""

import streamlit as st
from pathlib import Path


def show():
    st.markdown("# 🏛 西方哲学家全景网络图")

    html_path = Path(__file__).parent / "philosophers.html"
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    st.components.v1.html(html_content, height=750, scrolling=False)

    st.markdown("""
    <style>
    iframe { border: none; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)
