import io, zipfile, numpy as np, pandas as pd, streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

st.set_page_config(page_title="BIST AI Trader", page_icon="📈", layout="wide")
st.title("📈 BIST AI Trader")

TICKERS = ["THYAO","ASELS","GARAN","AKBNK","EREGL","SISE","KCHOL","TUPRS","BIMAS","FROTO"]

@st.cache_data(show_spinner=False)
def sample(t, n=800, seed=42):
    rng = np.random.default_rng(seed + abs(hash(t)) % 9999)
    d = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    p = 10*np.exp(np.cumsum(rng.normal(rng.uniform(-0.0002,0.0006), rng.uniform(0.012,0.028), n)))
    return pd.DataFrame({"Open":p*(1+rng.normal(0,0.004,n)), "High":p*(1+rng.uniform(0.002,0.02,n)),
        "Low":p*(1-rng.uniform(0.002,0.02,n)), "Close":p,
        "Volume":rng.integers(500_000,5_000_000,n)}, index=d)

@st.cache_data(show_spinner=False, ttl=600)
def fetch_yf(t, period="5y", _n=0):
    try:
        import yfinance as yf
        s = t if "." in t else f"{t}.IS"
        df = yf.download(s, period=period, auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df[["Open","High","Low","Close","Volume"]].dropna()
    except: return None

def ind(df):
    df = df.copy()
    df['ret1'] = df['Close'].pct_change()
    for L in [2,3,5,10,20]: df[f'lag{L}'] = df['Close'].pct_change(L)
    df['sma20']=df['Close'].rolling(20).mean()
    df['sma50']=df['Close'].rolling(50).mean()
    e12=df['Close'].ewm(span=12,adjust=False).mean(); e26=df['Close'].ewm(span=26,adjust=False).mean()
    df['macd']=e12-e26; df['macd_sig']=df['macd'].ewm(span=9,adjust=False).mean()
    dl=df['Close'].diff(); g=dl.clip(lower=0); l=-dl.clip(upper=0)
    df['rsi']=100-100/(1+g.rolling(14).mean()/(l.rolling(14).mean()+1e-9))
    m=df['Close'].rolling(20).mean(); s=df['Close'].rolling(20).std()
    df['bb_pos']=(df['Close']-(m-2*s))/((m+2*s)-(m-2*s)+1e-9)
    tr=pd.concat([df['High']-df['Low'],(df['High']-df['Close'].shift()).abs(),(df['Low']-df['Close'].shift()).abs()],axis=1).max(axis=1)
    df['atr_pct']=tr.rolling(14).mean()/(df['Close']+1e-9)
    df['vol_ratio']=df['Volume']/(df['Volume'].rolling(20).mean()+1e-9)
    df['close_sma20']=df['Close']/df['sma20']; df['close_sma50']=df['Close']/df['sma50']
    df['mom20']=df['Close']/df['Close'].shift(20)-1; df['mom60']=df['Close']/df['Close'].shift(60)-1
    return df

F = ['ret1','lag2','lag3','lag5','lag10','lag20','macd','macd_sig','rsi','bb_pos',
     'atr_pct','vol_ratio','close_sma20','close_sma50','mom20','mom60']

@st.cache_data(show_spinner=False)
def train(df, th=0.005):
    df = ind(df)
    df['y'] = (df['Close'].shift(-1)/df['Close']-1 > th).astype(int)
    d = df[F+['y']].dropna()
    if len(d) < 100 or d['y'].nunique() < 2: return None, None
    X, y = d[F], d['y']
    rf = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=10,
                                class_weight='balanced', random_state=42, n_jobs=-1)
    xgb = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                        eval_metric='logloss', use_label_encoder=False, random_state=42, n_jobs=-1)
    rf.fit(X, y); xgb.fit(X, y)
    last = df[F].iloc[[-1]]
    if last.isna().any().any(): return None, None
    p = 0.5*rf.predict_proba(last)[0,1] + 0.5*xgb.predict_proba(last)[0,1]
    return float(p), df

def bt(df, sl=0.05, tp=0.10, c=0.001):
    df = ind(df).dropna().copy()
    df['sig'] = (df['rsi']<30).astype(int)
    cap, pos, ent = 1.0, 0.0, 0.0; eq = []; tr = 0; wins = 0
    for _, r in df.iterrows():
        pr = r['Close']
        if pos > 0:
            ret = pr/ent - 1
            if ret <= -sl or ret >= tp:
                cap = pos*pr*(1-c); pos = 0.0; tr += 1
                if ret > 0: wins += 1
        if pos == 0 and r['sig'] == 1:
            pos = cap/(pr*(1+c)); ent = pr; cap = 0.0
        eq.append(cap + pos*pr)
    if pos > 0: cap = pos*df['Close'].iloc[-1]*(1-c)
    e = pd.Series(eq, index=df.index)
    return {"eq": e, "ret": float(e.iloc[-1]/e.iloc[0]-1),
            "sh": float((e.pct_change().mean()/e.pct_change().std()*np.sqrt(252))) if e.pct_change().std()>0 else 0,
            "dd": float((e/e.cummax()-1).min()),
            "tr": tr, "wr": float(wins/tr) if tr else 0}

with st.sidebar:
    st.header("⚙️ Ayarlar")
    src = st.radio("Veri Kaynağı", ["Örnek Veri", "Gerçek Veri (internet)"], index=0)
    sel = st.multiselect("Hisse", TICKERS, default=TICKERS)
    th = st.slider("Hedef Getiri (%)", 0.1, 3.0, 0.5, 0.1)/100
    sl = st.slider("Stop-Loss (%)", 1, 15, 5)/100
    tp = st.slider("Take-Profit (%)", 2, 30, 10)/100
    run = st.button("🚀 TARA", use_container_width=True, type="primary")

if run and sel:
    res, dfs = [], {}
    pg = st.progress(0, "Taranıyor...")
    for i, t in enumerate(sel):
        df = fetch_yf(t) if src.startswith("Gerçek") else sample(t)
        if df is None or len(df) < 100: pg.progress((i+1)/len(sel)); continue
        p, dff = train(df, th)
        if p is None: pg.progress((i+1)/len(sel)); continue
        b = bt(dff, sl, tp)
        res.append({"Hisse":t, "Olasılık":round(p,3), "Son":round(float(dff['Close'].iloc[-1]),2),
                    "Getiri":f"{b['ret']*100:.1f}%", "Sharpe":round(b['sh'],2),
                    "MaxDD":f"{b['dd']*100:.1f}%", "WinRate":f"{b['wr']*100:.0f}%"})
        dfs[t] = dff
        pg.progress((i+1)/len(sel), f"{t} ✓")
    pg.empty()
    if res:
        r = pd.DataFrame(res).sort_values("Olasılık", ascending=False)
        r["Sinyal"] = np.where(r["Olasılık"]>0.6, "🟢 AL", np.where(r["Olasılık"]<0.4, "🔴 ZAYIF", "🟡 NÖTR"))
        st.subheader("📊 Sonuçlar"); st.dataframe(r, use_container_width=True, hide_index=True)
        f1 = go.Figure(go.Bar(x=r["Hisse"], y=r["Olasılık"],
            marker_color=["#2ecc71" if p>0.6 else "#e74c3c" if p<0.4 else "#f39c12" for p in r["Olasılık"]]))
        f1.add_hline(y=0.5, line_dash="dash"); f1.update_layout(height=320, yaxis_range=[0,1])
        st.plotly_chart(f1, use_container_width=True)
        s = st.selectbox("Detay", r["Hisse"].tolist())
        d = dfs[s]
        f2 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7,0.3],
                           subplot_titles=(f"{s} Fiyat", "RSI"))
        f2.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'],
                                    low=d['Low'], close=d['Close']), 1, 1)
        f2.add_trace(go.Scatter(x=d.index, y=d['sma20'], name="SMA20"), 1, 1)
        f2.add_trace(go.Scatter(x=d.index, y=d['rsi'], name="RSI"), 2, 1)
        f2.update_layout(height=550, xaxis_rangeslider_visible=False)
        st.plotly_chart(f2, use_container_width=True)
        st.subheader("💰 Backtest")
        st.line_chart(bt(d, sl, tp)["eq"])

st.divider()
with st.expander("⬇️ İndirme Merkezi"):
    req = "streamlit\npandas\nnumpy\nscikit-learn\nxgboost\nplotly\nyfinance\n"
    readme = "# BIST AI Trader\n\nStreamlit ile BIST hisse tarama, tahmin, backtest.\n"
    st.download_button("⬇️ requirements.txt", req, "requirements.txt")
    st.download_button("⬇️ README.md", readme, "README.md")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        try:
            with open(__file__, "r", encoding="utf-8") as f: src_code = f.read()
        except: src_code = "# kaynak okunamadı"
        z.writestr("app.py", src_code)
        z.writestr("requirements.txt", req)
        z.writestr("README.md", readme)
    buf.seek(0)
    st.download_button("⬇️ bist_ai_trader.zip", buf.getvalue(), "bist_ai_trader.zip", "application/zip", type="primary")
