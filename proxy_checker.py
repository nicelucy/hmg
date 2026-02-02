import streamlit as st
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd
import time
import datetime
from streamlit_gsheets import GSheetsConnection  # 记得在 requirements.txt 加这行

# 1. 页面基本配置
st.set_page_config(page_title="HamiMelon 私有检测工具", layout="wide")

st.title("🛡️ SOCKS5 代理批量检测 (自动同步至 Google Sheets)")
st.info("数据将实时保存至后台表格。请确保已在 Secrets 中配置好凭据。")

# 2. 初始化 Google Sheets 连接
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心解析逻辑 ---
def parse_proxy(proxy_str):
    p = proxy_str.strip()
    if not p: return None
    parts = p.split(':')
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f"socks5://{user}:{pwd}@{ip}:{port}"
    return f"socks5://{p}"

async def fetch_ip_info(session):
    try:
        async with session.get("http://ip-api.com/json/?lang=zh-CN", timeout=10) as resp:
            if resp.status == 200:
                return await resp.json()
    except:
        return None
    return None

async def check_single_proxy(raw_proxy, semaphore, test_url, timeout):
    async with semaphore:
        formatted_url = parse_proxy(raw_proxy)
        if not formatted_url: return None
        
        start_time = time.time()
        try:
            connector = ProxyConnector.from_url(formatted_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                info = await fetch_ip_info(session)
                latency = int((time.time() - start_time) * 1000)
                
                if info and info.get("status") == "success":
                    return {
                        "原始地址": raw_proxy,
                        "状态": "✅ 成功",
                        "延迟": f"{latency}ms",
                        "出口 IP": info.get("query"),
                        "国家/地区": f"{info.get('country')} - {info.get('city')}",
                        "运营商": info.get("isp")
                    }
        except:
            pass
        return {"原始地址": raw_proxy, "状态": "❌ 失败", "延迟": "-", "出口 IP": "-", "国家/地区": "-", "运营商": "-"}

async def run_checks(proxies, max_concurrency, test_url, timeout):
    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [check_single_proxy(p, semaphore, test_url, timeout) for p in proxies]
    return await asyncio.gather(*tasks)

# --- 侧边栏 ---
with st.sidebar:
    st.header("设置")
    test_url = st.text_input("测试地址", value="http://www.google.com/generate_204")
    timeout = st.slider("超时 (秒)", 1, 30, 15)
    max_c = st.number_input("并发数", 1, 100, 20)

# --- 主界面 ---
input_text = st.text_area("粘贴代理列表 (IP:Port:User:Pass)", height=200)

if st.button("🚀 开始批量检测并保存", type="primary"):
    proxies = [p.strip() for p in input_text.split('\n') if p.strip()]
    if not proxies:
        st.warning("请输入代理地址")
    else:
        with st.spinner("正在检测并