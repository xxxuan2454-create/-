"""A股智能选股与六爻预测系统 - Streamlit 入口"""

import streamlit as st

# 页面配置
st.set_page_config(
    page_title="A股选股与预测系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 隐藏 Streamlit 默认样式中的一些干扰项
st.markdown("""
<style>
    .stApp { max-width: 100%; }
    .block-container { padding-top: 1rem; }
    .css-1d391kg { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

from db.models import init_db
from ui.auth import show as auth_page
from ui.dashboard import show as dashboard
from ui.screener import show as screener
from ui.search import show as search
from ui.divination import show as divination
from ui.history import show as history
from ui.multi_agent import show as multi_agent
from ui.backtest import show as backtest


def _ensure_stock_pool():
    """确保全A股股票池已同步到数据库，并更新 config.STOCK_POOL。
    同步失败时静默跳过，使用内置140只股票池。
    """
    import config
    from data.stock_list import sync_full_stock_list, get_stock_count

    try:
        count = get_stock_count()
    except Exception:
        count = 0

    if count < 1000:
        try:
            synced = sync_full_stock_list()
        except Exception as e:
            print(f"全A股同步失败（将使用内置池）: {e}")
            return
        if synced > 0:
            new_pool = config.get_full_stock_pool()
            config.STOCK_POOL.clear()
            config.STOCK_POOL.update(new_pool)


def main():
    try:
        init_db()
    except Exception as e:
        st.error(f"数据库初始化失败: {e}")

    try:
        _ensure_stock_pool()
    except Exception as e:
        st.warning(f"股票池同步跳过: {e}")

    # ── 认证检查 ──
    if "user_id" not in st.session_state:
        auth_page()
        return

    # ── 侧边栏导航 ──
    with st.sidebar:
        st.markdown("# 📈 A股预测系统")

        # 用户信息
        st.markdown(f"👤 **{st.session_state.get('username', '')}**")
        if st.button("退出登录", key="logout"):
            for key in ["user_id", "username"]:
                st.session_state.pop(key, None)
            st.rerun()

        st.markdown("---")

        # 导航菜单
        page = st.radio(
            "导航",
            options=[
                "📊 仪表盘",
                "🔎 股票搜索",
                "🔍 选股筛选",
                "🤖 多智能体分析",
                "🔮 六爻占卜",
                "⚡ 策略回测",
                "📋 历史记录",
            ],
            index=0,
        )

        st.markdown("---")
        st.markdown("### 📌 功能说明")

        if page == "📊 仪表盘":
            st.caption("查看大盘概览、今日推荐、预测统计")
        elif page == "🔎 股票搜索":
            st.caption("按名称或代码搜索任意A股，查看详情")
        elif page == "🔍 选股筛选":
            st.caption("Sequoia-X技术面 + qstock多因子评分")
        elif page == "🤖 多智能体分析":
            st.caption("AI多角色分析: 技术/基本面/情绪/辩论")
        elif page == "🔮 六爻占卜":
            st.caption("六爻起卦 → AI解卦 → 涨跌预测")
        elif page == "⚡ 策略回测":
            st.caption("均线/RSI/布林带 交易策略回测")
        elif page == "📋 历史记录":
            st.caption("预测记录、准确率统计、手动回测")

        st.markdown("---")
        st.markdown("### ⚙️ 集成来源")
        st.caption("- Sequoia-X: 7大技术策略")
        st.caption("- qstock: RPS多因子评分")
        st.caption("- TradingAgents: 多智能体")
        st.caption("- liu-yao: 六爻排盘系统")
        st.caption("- akquant: 回测引擎 + TA-Lib 103指标")

        st.markdown("---")
        st.caption(f"数据源: yfinance + 腾讯行情")
        st.caption("AI: DeepSeek | 回测: akquant")
        st.caption("指标: akquant TA-Lib (103项)")

    # 路由到对应页面
    if page == "📊 仪表盘":
        dashboard()
    elif page == "🔎 股票搜索":
        search()
    elif page == "🔍 选股筛选":
        screener()
    elif page == "🤖 多智能体分析":
        multi_agent()
    elif page == "🔮 六爻占卜":
        divination()
    elif page == "⚡ 策略回测":
        backtest()
    elif page == "📋 历史记录":
        history()


if __name__ == "__main__":
    main()
