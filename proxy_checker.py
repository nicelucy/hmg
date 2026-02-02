import streamlit as st
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd
import time

st.set_page_config(page_title="SOCKS5 跨境节点检测工具", layout="wide")

st.title("🌐 SOCKS5 跨境节点检测 (带地理位置)")
st.info("💡 提示：在大陆环境检测境外节点，建议先开启全局代理，否则流量会被防火墙拦截导致误报。")

def parse_proxy(proxy_str):
    p = proxy_str.strip()
    if not p: return None
    parts = p.split(':')
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f"socks5://{user}:{pwd}@{ip}:{port}"
    return f"socks5://{p}"

async def fetch_ip_info(session):
    """通过代理获取当前的 IP 和地理位置"""
    try:
        # 使用 ip-api.com (这个接口支持 HTTP，比较快)
        async with session.get("http://ip-api.com/json/?lang=zh-CN", timeout=10) as resp:
            if resp.status == 200:
                return await resp.json()
    except:
        return None
    return None

async def check_single_proxy(raw_proxy, semaphore):
    async with semaphore:
        formatted_url = parse_proxy(raw_proxy)
        if not formatted_url: return None
        
        start_time = time.time()
        try:
            connector = ProxyConnector.from_url(formatted_url)
            # 增加 TCP 握手限制
            async with aiohttp.ClientSession(connector=connector) as session:
                # 尝试获取 IP 信息
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
        except Exception as e:
            pass
        
        return {"原始地址": raw_proxy, "状态": "❌ 失败", "延迟": "-", "出口 IP": "-", "国家/地区": "-", "运营商": "-"}

async def run_checks(proxies, max_concurrency):
    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [check_single_proxy(p, semaphore) for p in proxies]
    return await asyncio.gather(*tasks)

# --- 界面部分 ---
input_text = st.text_area("输入代理列表 (每行一个)", height=200)

col1, col2 = st.columns(2)
with col1:
    max_c = st.number_input("并发线程数", 1, 100, 20)
with col2:
    btn = st.button("🚀 开始批量检测", type="primary", use_container_width=True)

if btn:
    proxies = [p.strip() for p in input_text.split('\n') if p.strip()]
    if not proxies:
        st.warning("列表为空")
    else:
        with st.spinner(f"正在检测 {len(proxies)} 个节点..."):
            results = asyncio.run(run_checks(proxies, max_c))
            df = pd.DataFrame(results)
            
            # 统计
            success_df = df[df["状态"] == "✅ 成功"]
            st.success(f"检测完成！可用节点：{len(success_df)} / 总数：{len(df)}")
            
            # 高亮显示结果
            st.dataframe(df, use_container_width=True)
            
            if not success_df.empty:
                csv = success_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 下载可用节点 CSV", csv, "valid_proxies.csv", "text/csv")