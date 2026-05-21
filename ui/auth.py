"""用户登录/注册页面"""

import streamlit as st
from db.auth import register_user, login_user


def show():
    st.markdown("# 📈 A股选股与六爻预测系统")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["登录", "注册"])

        with tab_login:
            with st.form("login_form"):
                username = st.text_input("用户名", key="login_username")
                password = st.text_input("密码", type="password", key="login_password")
                submitted = st.form_submit_button("登录", type="primary", use_container_width=True)

                if submitted:
                    user_id, msg = login_user(username, password)
                    if user_id:
                        st.session_state["user_id"] = user_id
                        st.session_state["username"] = username
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        with tab_register:
            with st.form("register_form"):
                new_username = st.text_input("用户名 (至少2字符)", key="reg_username")
                new_password = st.text_input("密码 (至少4字符)", type="password", key="reg_password")
                confirm_password = st.text_input("确认密码", type="password", key="reg_confirm")
                submitted = st.form_submit_button("注册", type="primary", use_container_width=True)

                if submitted:
                    if new_password != confirm_password:
                        st.error("两次密码不一致")
                    else:
                        ok, msg = register_user(new_username, new_password)
                        if ok:
                            st.success(msg + "，请切换到登录页签登录。")
                        else:
                            st.error(msg)
