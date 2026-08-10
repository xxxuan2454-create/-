"""Shared stock search + market selector (A-share / US)."""

from __future__ import annotations

import random

import streamlit as st

from config import STOCK_POOL, US_STOCK_POOL
from data.markets import (
    MARKET_CN,
    MARKET_US,
    currency_symbol,
    detect_market,
    market_label,
)


def get_pool_for_market(market: str) -> dict[str, str]:
    return US_STOCK_POOL if market == MARKET_US else STOCK_POOL


def render_market_selector(key: str = "market") -> str:
    """Render CN/US radio and return selected market code."""
    return st.radio(
        "市场",
        options=[MARKET_CN, MARKET_US],
        format_func=market_label,
        horizontal=True,
        key=key,
    )


def resolve_stock_selection(
    page_key: str,
    *,
    show_random: bool = False,
    linked: dict | None = None,
) -> tuple[str, str, str]:
    """
    Search + default pool selection for 六爻 / 多智能体 / 回测.

    Returns (name, code, market).
    """
    market = render_market_selector(key=f"{page_key}_market")
    pool = get_pool_for_market(market)
    sym = currency_symbol(market)

    col_main, col_rand = st.columns([3, 1] if show_random else [1, 0.001])

    with col_main:
        placeholder = (
            "A股: 茅台 / 600519 / 宁德时代"
            if market == MARKET_CN
            else "US: Apple / AAPL / NVIDIA"
        )
        search_query = st.text_input(
            "搜索股票名称或代码",
            placeholder=placeholder,
            key=f"{page_key}_search",
        )

    with col_rand:
        use_random = show_random and st.checkbox("随机选股", value=False, key=f"{page_key}_random")

    selected_name: str | None = None
    selected_code: str | None = None

    if search_query:
        from data.stock_list import search_all_stocks

        results = search_all_stocks(search_query, limit=15, market=market)
        if results:
            stock_options = {r["name"]: r["code"] for r in results}
            default_idx = 0
            if linked:
                for i, r in enumerate(results):
                    if r["code"] == linked.get("code"):
                        default_idx = i
                        break
            selected_name = st.selectbox(
                "选择股票",
                options=list(stock_options.keys()),
                index=default_idx,
                key=f"{page_key}_select",
            )
            selected_code = stock_options[selected_name]
        else:
            st.warning("无匹配股票，请换关键词或直接输入 ticker/代码")
            if market == MARKET_US and search_query.strip():
                ticker = search_query.strip().upper()
                selected_name = ticker
                selected_code = ticker
                st.info(f"未在索引中找到，将直接使用 ticker: **{ticker}**")

    if selected_code is None and linked:
        linked_market = detect_market(linked.get("code", ""))
        if linked_market == market:
            selected_name = linked["name"]
            selected_code = linked["code"]
            st.info(
                f"📌 从其他页面联动: **{linked['name']}** ({linked['code']})，"
                "上方搜索框可随时更换股票"
            )

    if selected_code is None:
        selected_name = list(pool.keys())[0]
        selected_code = pool[selected_name]
        st.info(
            "输入股票名称或代码搜索；"
            + ("联动「🤖 多智能体分析」" if page_key == "div" else "联动「🔮 六爻占卜」")
        )

    if use_random:
        names = list(pool.keys())
        selected_name = random.choice(names)
        selected_code = pool[selected_name]
        st.info(f"随机选中: **{selected_name}**")

    st.session_state["active_stock"] = {
        "name": selected_name,
        "code": selected_code,
        "market": market,
    }

    return selected_name, selected_code, market


def format_price(value: float, market: str | None = None, code: str | None = None) -> str:
    sym = currency_symbol(market, code)
    return f"{sym}{value:.2f}"
