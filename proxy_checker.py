import streamlit as st
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd
import time
import datetime
from streamlit_gsheets import GSheetsConnection

# 1. 页面基本配置
st.set_page_config(page_title="哈密瓜科技 - 私有检测工具", layout="wide")

st.title("🛡️ SOCKS5 代理批量检测")
st.caption("请按以下提示的格式填写:72.1.133.228:7620:user:pass。")

# 2. 初始化 Google Sheets 连接
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 核心解析逻辑 ---
def parse_proxy(proxy_str):
    p = proxy_str.strip()
    if not p: return None
    # 支持 IP:Port:User:Pass 格式
    parts = p.split(':')
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f"socks5://{user}:{pwd}@{ip}:{port}"
    # 支持 User:Pass@IP:Port 或 IP:Port 格式
    return f"socks5://{p}"

async def fetch_ip_info(session):
    """获取 IP 地理位置信息"""
    try:
        async with session.get("http://ip-api.com/json/?lang=zh-CN", timeout=10) as resp:
            if resp.status == 200:
                return await resp.json()
    except:
        return None
    return None

async def check_single_proxy(raw_proxy, semaphore, test_url, timeout):
    """检测单个代理"""
    async with semaphore:
        formatted_url = parse_proxy(raw_proxy)
        if not formatted_url: return None
        
        start_time = time.time()
        try:
            connector = ProxyConnector.from_url(formatted_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                # 1. 获取地理位置 (同时也证明了代理是通的)
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
    """批量运行异步检测"""
    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [check_single_proxy(p, semaphore, test_url, timeout) for p in proxies]
    return await asyncio.gather(*tasks)

# --- 侧边栏设置 ---
with st.sidebar:
    st.header("⚙️ 检测配置")
    test_url = st.text_input("测试地址", value="http://www.google.com/generate_204")
    timeout = st.slider("超时时间 (秒)", 1, 30, 15)
    max_c = st.number_input("并发线程数", 1, 100, 20)
    st.divider()
    st.write("制作单位：哈密瓜科技")

# --- 主界面 ---
input_text = st.text_area("请输入代理列表 (每行一个)", placeholder="72.1.133.228:7620:user:pass", height=200)

if st.button("🚀 开始批量检测并去重同步", type="primary"):
    proxies = [p.strip() for p in input_text.split('\n') if p.strip()]
    
    if not proxies:
        st.warning("请先输入代理地址列表！")
    else:
        with st.spinner("正在检测中，请稍候..."):
            # A. 执行检测任务
            results = asyncio.run(run_checks(proxies, max_c, test_url, timeout))
            df_new = pd.DataFrame(results)
            
            # B. 提取成功的结果
            success_df = df_new[df_new["状态"] == "✅ 成功"].copy()
            
            if not success_df.empty:
                # 添加当前时间戳
                success_df["保存时间"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                try:
                    # C. 读取 Google Sheets 现有数据
                    existing_df = conn.read().dropna(how="all")
                    
                    # D. 合并数据并去重
                    # subset=['原始地址'] 表示根据代理地址判断重复
                    # keep='last' 表示如果有重复，保留新检测到的这一条
                    combined_df = pd.concat([existing_df, success_df], ignore_index=True)
                    final_df = combined_df.drop_duplicates(subset=['原始地址'], keep='last')
                    
                    # E. 写回 Google Sheets
                    conn.update(data=final_df)
                    st.toast("数据同步成功！已自动去重。", icon="✅")
                except Exception as e:
                    st.error(f"同步至 Google Sheets 失败：{e}")
            
            # F. 展示本次检测结果
            st.success(f"检测完成！本次成功：{len(success_df)} / 总数：{len(proxies)}")
            st.dataframe(df_new, use_container_width=True)
            
            # 提供本地下载
            csv = df_new.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下载本次检测报告 (CSV)", csv, "proxy_results.csv", "text/csv")