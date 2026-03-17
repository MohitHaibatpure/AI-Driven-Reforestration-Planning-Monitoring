import streamlit as st
import requests
import pandas as pd
from streamlit_folium import st_folium
import folium
import time

# --- Config ---
st.set_page_config(
    page_title="EcoMonitor AI", 
    page_icon="🌳", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# --- Constants ---
API_URL = "http://127.0.0.1:8000/api"
PRIMARY_COLOR = "#10B981"  # Emerald Green
BG_COLOR = "#F8FAFC"       # Light Slate Background
TEXT_COLOR = "#1E293B"

# --- 🎨 CUSTOM CSS ---
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Manrope', sans-serif;
        background-color: {BG_COLOR}; 
        color: {TEXT_COLOR};
    }}
    
    /* --- SIDEBAR STYLING --- */
    [data-testid="stSidebar"] {{
        background-color: #FFFFFF;
        border-right: 1px solid #E2E8F0;
    }}
    [data-testid="stSidebar"] .stRadio > div[role="radiogroup"] > label > div:first-child {{
        display: none;
    }}
    [data-testid="stSidebar"] .stRadio > div[role="radiogroup"] label {{
        padding: 12px 20px;
        border-radius: 10px;
        margin-bottom: 8px;
        border: 1px solid transparent;
        font-weight: 600;
        color: #64748B;
        transition: all 0.2s;
        cursor: pointer;
    }}
    [data-testid="stSidebar"] .stRadio > div[role="radiogroup"] label:hover {{
        background: #ECFDF5;
        color: {PRIMARY_COLOR};
    }}
    [data-testid="stSidebar"] .stRadio > div[role="radiogroup"] label[data-checked="true"] {{
        background: {PRIMARY_COLOR} !important;
        color: white !important;
        box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.3);
    }}
    
    /* --- CARD STYLING --- */
    .card {{
        background: white;
        padding: 24px;
        border-radius: 16px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -1px rgba(0,0,0,0.02);
        border: 1px solid #F1F5F9;
        margin-bottom: 24px;
        height: 100%;
    }}
    
    /* --- METRICS --- */
    .metric-box {{
        background: white;
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }}
    .metric-label {{ font-size: 0.85rem; font-weight: 600; color: #94A3B8; text-transform: uppercase; }}
    .metric-value {{ font-size: 1.8rem; font-weight: 700; color: #0F172A; margin: 5px 0; }}
    .metric-delta {{ font-size: 0.8rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }}
    
    .stButton button {{
        background-color: {PRIMARY_COLOR};
        color: white;
        font-weight: 600;
        border-radius: 10px;
        border: none;
        height: 48px;
        width: 100%;
        transition: 0.2s;
    }}
    .stButton button:hover {{ background-color: #059669; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.2); }}
    .block-container {{ padding-top: 2rem; }}
    h1, h2, h3 {{ color: #064E3B; font-weight: 700; }}
</style>
""", unsafe_allow_html=True)

# --- API Helper ---
def fetch(endpoint, method="GET", payload=None):
    try:
        url = f"{API_URL}{endpoint}"
        if method == "POST":
            r = requests.post(url, json=payload, timeout=8)
        else:
            r = requests.get(url, timeout=8)
        return r.json() if r.status_code == 200 else None
    except: return None

# --- Session State ---
if 'coords' not in st.session_state: st.session_state.coords = {"lat": 19.2296, "lon": 72.8711}
if 'report_data' not in st.session_state: st.session_state.report_data = None
if "messages" not in st.session_state: 
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your Reforestation Expert. Ask me about your land analysis or carbon credits."}]

# ==========================================
# 📍 SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:20px; padding: 0 10px;">
            <div style="background:#ECFDF5; padding:10px; border-radius:10px; color:#10B981; font-size:1.5rem;">🌳</div>
            <div>
                <div style="font-weight:800; font-size:1.1rem; color:#064E3B;">EcoMonitor</div>
                <div style="font-size:0.75rem; color:#64748B;">AI Reforestation Ops</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # FIXED: Added label "Navigation" to fix warning
    selected_tab = st.radio(
        "Navigation", 
        ["Dashboard", "Smart Analysis", "AI Assistant", "Register Zone", "Carbon Credits", "Live Alerts", "Community"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    
    st.markdown("""
        <div style="background:#F1F5F9; padding:12px; border-radius:12px; display:flex; gap:10px; align-items:center;">
            <div style="background:#CBD5E1; width:36px; height:36px; border-radius:50%; display:flex; justify-content:center; align-items:center;">👤</div>
            <div>
                <div style="font-weight:600; font-size:0.9rem;">Admin User</div>
                <div style="font-size:0.75rem; color:#64748B;">View Profile</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    health = fetch("/health")
    status = "Online" if health and health.get("database_status") else "Offline"
    dot_color = "#10B981" if status == "Online" else "#EF4444"
    st.markdown(f"<div style='margin-top:10px; font-size:0.75rem; color:#94A3B8; text-align:center'>System Status: <span style='color:{dot_color}'>● {status}</span></div>", unsafe_allow_html=True)


# ==========================================
# 1. DASHBOARD
# ==========================================
if selected_tab == "Dashboard":
    st.title("Overview")
    st.markdown("<div style='margin-bottom:20px; color:#64748B;'>Welcome back. Here is your reforestation impact summary.</div>", unsafe_allow_html=True)
    
    stats = fetch("/monitoring/stats") or {"total_zones": 12, "total_hectares": 450.5, "total_carbon_per_year": 1200, "active_alerts": 0}
    
    c1, c2, c3, c4 = st.columns(4)
    
    def metric_card(label, value, delta, is_alert=False):
        color = "#EF4444" if is_alert and value > 0 else "#10B981"
        return f"""
        <div class="metric-box" style="{f'border-color:{color};' if is_alert and value > 0 else ''}">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-delta" style="color:{color}">
                {delta}
            </div>
        </div>
        """
    
    c1.markdown(metric_card("Total Zones", stats["total_zones"], "↑ 2 New"), unsafe_allow_html=True)
    c2.markdown(metric_card("Hectares Restored", f"{stats['total_hectares']}ha", "↑ 12% Growth"), unsafe_allow_html=True)
    c3.markdown(metric_card("Carbon Offset", f"{stats['total_carbon_per_year']}t", "↑ 8% YTD"), unsafe_allow_html=True)
    c4.markdown(metric_card("Active Alerts", stats["active_alerts"], "Live Status", is_alert=True), unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col_map, col_feed = st.columns([2.5, 1])
    
    with col_map:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("🗺️ Live Monitoring Map")
        m = folium.Map(location=[20, 78], zoom_start=4.5, tiles="CartoDB positron")
        folium.Marker([19.22, 72.87], popup="Active Site", icon=folium.Icon(color="green", icon="leaf")).add_to(m)
        st_folium(m, height=450, width="100%")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col_feed:
        st.markdown('<div class="card" style="height:100%">', unsafe_allow_html=True)
        st.subheader("📢 Recent Activity")
        activities = [
            {"title": "System Scan Completed", "time": "2 mins ago", "icon": "🛡️"},
            {"title": "New User Registered", "time": "1 hour ago", "icon": "👤"},
            {"title": "High Temp Warning", "time": "3 hours ago", "icon": "☀️"},
            {"title": "Report Generated", "time": "5 hours ago", "icon": "📄"},
        ]
        for act in activities:
            st.markdown(f"""
            <div style="display:flex; gap:12px; margin-bottom:20px; border-bottom:1px solid #F1F5F9; padding-bottom:12px;">
                <div style="background:#F1F5F9; width:32px; height:32px; border-radius:50%; display:flex; justify-content:center; align-items:center;">{act['icon']}</div>
                <div>
                    <div style="font-weight:600; font-size:0.9rem;">{act['title']}</div>
                    <div style="color:#94A3B8; font-size:0.8rem;">{act['time']}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# 2. ANALYSIS
# ==========================================
elif selected_tab == "Smart Analysis":
    st.title("Site Analysis")
    c_left, c_right = st.columns([1.5, 1])
    
    with c_left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("📍 Select Region")
        m = folium.Map(location=[st.session_state.coords['lat'], st.session_state.coords['lon']], zoom_start=12, tiles="CartoDB positron")
        folium.Marker(
            [st.session_state.coords['lat'], st.session_state.coords['lon']], 
            icon=folium.Icon(color="green", icon="info-sign"), draggable=True
        ).add_to(m)
        map_data = st_folium(m, height=500, width="100%")
        if map_data and map_data.get('last_clicked'):
            clicked = map_data['last_clicked']
            # Folium returns 'lng', but we use 'lon'. We must normalize it here.
            st.session_state.coords = {"lat": clicked["lat"], "lon": clicked["lng"]}
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with c_right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("⚙️ Configuration")
        c_lat, c_lon = st.columns(2)
        lat = c_lat.number_input("Latitude", value=st.session_state.coords['lat'], format="%.4f")
        lon = c_lon.number_input("Longitude", value=st.session_state.coords['lon'], format="%.4f")
        st.markdown("---")
        use_mock = st.toggle("Enable Dev Mode (Mock Data)", value=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✨ Generate Smart Report"):
            with st.spinner("Analyzing satellite imagery & soil data..."):
                payload = {
                    "latitude": lat, "longitude": lon, 
                    "dev_mode": use_mock, 
                    "mock_site": "Sanjay Park, India (Degraded)" if use_mock else None
                }
                res = fetch("/get-full-report", "POST", payload)
                if res:
                    st.session_state.report_data = res
                    st.toast("Analysis Successful!", icon="✅")
                else:
                    st.error("Server connection failed.")
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.report_data:
        data = st.session_state.report_data
        st.markdown("### 📊 Analysis Results")
        is_suitable = "Suitable" in data.get('suitability_assessment', '')
        status_color = "#10B981" if is_suitable else "#EF4444"
        bg_status = "#ECFDF5" if is_suitable else "#FEF2F2"
        icon = "✅" if is_suitable else "⚠️"
        st.markdown(f"""
        <div class="card" style="border-left: 6px solid {status_color}; background: {bg_status};">
            <div style="display:flex; align-items:start; gap:20px;">
                <div style="font-size:2.5rem;">{icon}</div>
                <div>
                    <h2 style="margin:0; color:{status_color}">{data.get('suitability_assessment')}</h2>
                    <p style="font-size:1.05rem; color:#334155; margin-top:5px;">{data.get('suitability_reason')}</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        g1, g2, g3 = st.columns(3)
        with g1:
            st.markdown(f"""
            <div class="card">
                <div style="color:#64748B; font-weight:600; font-size:0.9rem;">RECOMMENDED CROP</div>
                <div style="color:#10B981; font-weight:800; font-size:1.8rem; margin:10px 0;">{data.get('recommended_crop', 'N/A')}</div>
                <div style="font-size:0.85rem; color:#94A3B8;">Optimized for local soil.</div>
            </div>
            """, unsafe_allow_html=True)
        with g2:
            w = data['fetched_weather_data']
            st.markdown(f"""
            <div class="card">
                <div style="color:#64748B; font-weight:600; font-size:0.9rem;">WEATHER CONDITIONS</div>
                <div style="display:flex; justify-content:space-between; margin-top:10px;">
                    <div><span style="font-size:1.2rem; font-weight:700;">{w.get('temperature')}°C</span><br><span style="font-size:0.8rem; color:#94A3B8">Temp</span></div>
                    <div><span style="font-size:1.2rem; font-weight:700;">{w.get('rainfall')}mm</span><br><span style="font-size:0.8rem; color:#94A3B8">Rain</span></div>
                    <div><span style="font-size:1.2rem; font-weight:700;">{w.get('humidity')}%</span><br><span style="font-size:0.8rem; color:#94A3B8">Hum</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with g3:
            s = data['fetched_soil_data']
            st.markdown(f"""
            <div class="card">
                <div style="color:#64748B; font-weight:600; font-size:0.9rem;">SOIL COMPOSITION</div>
                <div style="margin-top:10px;">
                    <div style="display:flex; justify-content:space-between; border-bottom:1px solid #F1F5F9; padding-bottom:5px;">
                        <span>Nitrogen (N)</span> <strong>{s.get('N', {}).get('value')}</strong>
                    </div>
                    <div style="display:flex; justify-content:space-between; padding-top:5px;">
                        <span>pH Level</span> <strong>{s.get('ph', {}).get('value')}</strong>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ==========================================
# 3. AI ASSISTANT
# ==========================================
elif selected_tab == "AI Assistant":
    st.title("Reforestation Assistant")
    col_chat, col_suggestions = st.columns([3, 1])
    
    with col_suggestions:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("#### 💡 Quick Actions")
        suggestions = ["Recommended crop?", "Soil nutrient status?", "Explain carbon credits", "Fire risks nearby?"]
        for s in suggestions:
            if st.button(s, key=s):
                st.session_state.messages.append({"role": "user", "content": s})
                with st.spinner("AI is thinking..."):
                    res = fetch("/chat", "POST", {"message": s, "context": st.session_state.report_data})
                    reply = res.get("response") if res else "Server unavailable."
                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col_chat:
        chat_box = st.container(height=550)
        with chat_box:
            for msg in st.session_state.messages:
                avatar = "🤖" if msg["role"] == "assistant" else "👤"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.write(msg["content"])
        
        if prompt := st.chat_input("Type your question here..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with chat_box:
                with st.chat_message("user", avatar="👤"):
                    st.write(prompt)
                
                with st.chat_message("assistant", avatar="🤖"):
                    with st.spinner("..."):
                        res = fetch("/chat", "POST", {"message": prompt, "context": st.session_state.report_data})
                        reply = res.get("response") if res else "Error."
                        st.write(reply)
            st.session_state.messages.append({"role": "assistant", "content": reply})

# ==========================================
# 4. REGISTER
# ==========================================
elif selected_tab == "Register Zone":
    c_spacer_l, c_main, c_spacer_r = st.columns([1, 2, 1])
    with c_main:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.title("📝 Register New Zone")
        st.markdown("Register your land to enable **automatic satellite fire monitoring** and alerts.")
        
        with st.form("reg_form"):
            st.markdown("#### Zone Details")
            name = st.text_input("Zone Name", placeholder="e.g. Green Valley Plot 1")
            phone = st.text_input("WhatsApp Number", placeholder="+91 9876543210")
            st.markdown("#### Location Confirmation")
            c1, c2 = st.columns(2)
            c1.info(f"Lat: {st.session_state.coords['lat']:.4f}")
            c2.info(f"Lon: {st.session_state.coords['lon']:.4f}")
            
            if st.form_submit_button("✅ Complete Registration"):
                payload = {"zone_name": name, "phone_number": phone, "latitude": st.session_state.coords['lat'], "longitude": st.session_state.coords['lon']}
                res = fetch("/register-zone", "POST", payload)
                if res:
                    st.success("Registration Successful! You will receive a WhatsApp confirmation.")
                else:
                    st.error("Failed to register. Try again.")
        st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# 5. CARBON
# ==========================================
elif selected_tab == "Carbon Credits":
    st.title("💰 Carbon Credit Estimator")
    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Project Inputs")
        crop = st.selectbox("Select Crop/Tree Type", ["Teak", "Coffee", "Bamboo", "Mango", "Neem"])
        area = st.slider("Land Area (Hectares)", 0.5, 100.0, 1.0)
        age = st.slider("Project Duration (Years)", 5, 50, 10)
        calc_btn = st.button("Calculate Value")
        st.markdown('</div>', unsafe_allow_html=True)
    with col_out:
        if calc_btn:
            res = fetch("/estimate-carbon-credits", "POST", {"crop_type": crop, "area_hectares": area, "age_years": age})
            val = res['total_at_end_of_period_tonnes'] if res else 0
            money = val * 15 
            st.markdown(f"""
            <div class="card" style="text-align:center; border: 2px dashed #10B981; background:#F0FDF4;">
                <div style="font-size:1rem; font-weight:600; color:#064E3B; margin-bottom:10px;">ESTIMATED SEQUESTRATION</div>
                <div style="font-size:3.5rem; font-weight:800; color:#059669; line-height:1;">{val:,.1f}</div>
                <div style="font-size:1.2rem; color:#047857; margin-bottom:20px;">Tonnes CO₂</div>
                <div style="background:white; padding:15px; border-radius:12px; display:inline-block; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
                    <div style="font-size:0.9rem; color:#64748B;">Potential Market Value</div>
                    <div style="font-size:1.5rem; font-weight:700; color:#059669;">${money:,.2f} USD</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="card" style="display:flex; align-items:center; justify-content:center; height:100%; color:#94A3B8;">
                <div>
                    <div style="font-size:3rem; text-align:center;">🌱</div>
                    <p>Enter details to estimate earnings.</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ==========================================
# 6. ALERTS
# ==========================================
elif selected_tab == "Live Alerts":
    st.title("🚨 Alert Center")
    col_main, col_side = st.columns([3, 1])
    with col_side:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("**Actions**")
        if st.button("🔄 Trigger Manual Scan"):
            fetch("/trigger-fire-check", "POST")
            st.toast("Manual scan initiated.")
        st.caption("Last system scan: 2 mins ago")
        st.markdown('</div>', unsafe_allow_html=True)
    with col_main:
        alerts = fetch("/alerts") or []
        if not alerts:
             st.markdown('<div class="card" style="text-align:center; color:#94A3B8;">No active alerts found. All zones are safe.</div>', unsafe_allow_html=True)
        else:
            for a in alerts:
                is_fire = "fire" in a.get('alert_type', '').lower()
                icon = "🔥" if is_fire else "ℹ️"
                bg = "#FEF2F2" if is_fire else "white"
                border = "#EF4444" if is_fire else "#E2E8F0"
                st.markdown(f"""
                <div style="background:{bg}; border:1px solid {border}; padding:20px; border-radius:12px; margin-bottom:15px; display:flex; gap:15px; align-items:start;">
                    <div style="font-size:1.5rem; background:white; width:40px; height:40px; border-radius:50%; display:flex; justify-content:center; align-items:center; box-shadow:0 1px 2px rgba(0,0,0,0.1);">{icon}</div>
                    <div style="flex-grow:1;">
                        <div style="font-weight:700; color:#1E293B; font-size:1.05rem;">{a.get('zone_name')}</div>
                        <div style="color:#475569; margin-top:4px;">{a.get('message')}</div>
                    </div>
                    <div style="font-size:0.8rem; color:#94A3B8; white-space:nowrap;">{a.get('timestamp', '')[:10]}</div>
                </div>
                """, unsafe_allow_html=True)

# ==========================================
# 7. COMMUNITY
# ==========================================
elif selected_tab == "Community":
    st.title("🏆 Leaderboard")
    leaders = fetch("/community/leaderboard")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if leaders:
        df = pd.DataFrame(leaders)
        df = df.rename(columns={"rank": "Rank", "name": "User", "zones": "Zones Protected"})
        # Fixed: Removed use_container_width deprecation for standard width behavior
        st.dataframe(
            df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Rank": st.column_config.NumberColumn(format="#%d"),
                "User": st.column_config.TextColumn("Champion"),
                "Zones Protected": st.column_config.ProgressColumn(format="%d Zones", min_value=0, max_value=20)
            }
        )
    else:
        st.info("Leaderboard data unavailable.")
    st.markdown('</div>', unsafe_allow_html=True)