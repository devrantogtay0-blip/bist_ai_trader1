# ============================================================
# ULTIMATE TARAYICI v10
# BIST + Kripto + ABD + Emtia
# ============================================================
import io, zipfile, sqlite3, time, hashlib, warnings, os
from datetime import datetime
import numpy as np, pandas as pd, streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.ensemble import (RandomForestClassifier, GradientBoostingClassifier,
                              StackingClassifier, ExtraTreesClassifier, MLPClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.cluster import AgglomerativeClustering
from xgboost import XGBClassifier
from scipy.optimize import minimize
warnings.filterwarnings("ignore")

st.set_page_config(page_title="Ultimate v10", page_icon="🎯", layout="wide")

# ============================================================
# KENDİ KAYNAĞI
# ============================================================
def read_self():
    try:
        with open(__file__, "r", encoding="utf-8") as f: return f.read()
    except: return "# kaynak okunamadı\n"

# ============================================================
# SQLITE
# ============================================================
DB = "ultimate.db"
def init_db():
    con = sqlite3.connect(DB); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, user TEXT, piyasa TEXT, varlik TEXT,
        olasilik REAL, auc REAL, sharpe REAL, getiri REAL, sinyal TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, user TEXT, varlik TEXT, tip TEXT,
        esik REAL, tg_chat TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tg (
        user TEXT PRIMARY KEY, token TEXT, chat TEXT, aktif INTEGER)""")
    con.commit(); con.close()

def save_scan(user, rows):
    con = sqlite3.connect(DB); c = con.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    for r in rows:
        c.execute("""INSERT INTO scans (ts,user,piyasa,varlik,olasilik,auc,sharpe,getiri,sinyal)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (now, user, r.get("Piyasa",""), r.get("Varlık",""),
                   r.get("Olasılık",0), r.get("AUC",0), r.get("Sharpe",0),
                   float(str(r.get("Getiri","0%")).replace("%","")), r.get("Sinyal","")))
    con.commit(); con.close()

def load_scans(user=None, limit=200):
    con = sqlite3.connect(DB)
    q = "SELECT ts,user,piyasa,varlik,olasilik,auc,sharpe,getiri,sinyal FROM scans"
    p = []
    if user: q += " WHERE user=?"; p.append(user)
    q += " ORDER BY id DESC LIMIT ?"; p.append(limit)
    df = pd.read_sql_query(q, con, params=p); con.close(); return df

def save_alert(user, varlik, tip, esik, tg_chat=""):
    con = sqlite3.connect(DB); c = con.cursor()
    c.execute("INSERT INTO alerts (ts,user,varlik,tip,esik,tg_chat) VALUES (?,?,?,?,?,?)",
              (datetime.utcnow().isoformat(timespec="seconds"), user, varlik, tip, esik, tg_chat))
    con.commit(); con.close()

def load_alerts(user=None, limit=100):
    con = sqlite3.connect(DB)
    q = "SELECT ts,user,varlik,tip,esik,tg_chat FROM alerts"; p = []
    if user: q += " WHERE user=?"; p.append(user)
    q += " ORDER BY id DESC LIMIT ?"; p.append(limit)
    df = pd.read_sql_query(q, con, params=p); con.close(); return df

def get_tg(user):
    con = sqlite3.connect(DB); c = con.cursor()
    c.execute("SELECT token,chat,aktif FROM tg WHERE user=?", (user,))
    row = c.fetchone(); con.close()
    return {"token":row[0] if row else "", "chat":row[1] if row else "",
            "aktif":bool(row[2]) if row else False}

def set_tg(user, token, chat, aktif):
    con = sqlite3.connect(DB); c = con.cursor()
    c.execute("""INSERT INTO tg (user,token,chat,aktif) VALUES (?,?,?,?)
                 ON CONFLICT(user) DO UPDATE SET token=excluded.token,
                 chat=excluded.chat, aktif=excluded.aktif""",
              (user, token, chat, 1 if aktif else 0))
    con.commit(); con.close()
init_db()

# ============================================================
# LOGIN
# ============================================================
CFG = "config.yaml"
def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def default_auth():
    return {"credentials":{"usernames":{
        "admin":{"name":"Admin","password":hash_pw("admin123"),"email":"a@e.com","role":"admin"},
        "demo":{"name":"Demo","password":hash_pw("demo123"),"email":"d@e.com","role":"user"}}},
        "cookie":{"expiry_days":30,"key":"ultra_secret_2026","name":"ultra_cookie"},
        "preauthorized":{"emails":[]}}

def load_cfg():
    import yaml
    if not os.path.exists(CFG):
        with open(CFG,"w",encoding="utf-8") as f:
            yaml.safe_dump(default_auth(), f, allow_unicode=True, sort_keys=False)
    with open(CFG,"r",encoding="utf-8") as f: return yaml.safe_load(f)

def auth():
    try:
        import streamlit_authenticator as stauth
        cfg = load_cfg()
        a = stauth.Authenticate(cfg["credentials"], cfg["cookie"]["name"],
                                cfg["cookie"]["key"], cfg["cookie"]["expiry_days"])
        n, s, u = a.login("Giriş", "main")
        return a, n, s, u
    except Exception:
        with st.sidebar:
            st.subheader("🔐 Giriş")
            u = st.text_input("Kullanıcı", key="fu")
            p = st.text_input("Şifre", type="password", key="fp")
            if st.button("Giriş"):
                try:
                    cfg = load_cfg()
                    users = cfg["credentials"]["usernames"]
                    if u in users and users[u]["password"] == hash_pw(p):
                        st.session_state["authed"] = (users[u]["name"], u)
                    else:
                        st.session_state["authed"] = None
                except: st.session_state["authed"] = None
        if st.session_state.get("authed"):
            n,u = st.session_state["authed"]; return None, n, True, u
        return None, None, False, None

authenticator, name, status, username = auth()
if not status:
    st.warning("🔐 Giriş: **admin / admin123** veya **demo / demo123**")
    st.stop()
user = username or "anon"
with st.sidebar:
    st.success(f"👤 {name or user}")
    if authenticator:
        try: authenticator.logout("Çıkış", "sidebar")
        except: pass

# ============================================================
# TELEGRAM
# ============================================================
def tg_send(token, chat, msg):
    try:
        import requests
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id":chat,"text":msg,"parse_mode":"HTML"}, timeout=10)
        return r.status_code==200, r.text[:150]
    except Exception as e: return False, str(e)

# ============================================================
# VARLIK EVRENI
# ============================================================
BIST = {"THYAO":"Havacılık","PGSUS":"Havacılık","ASELS":"Savunma","OTKAR":"Savunma",
        "GARAN":"Bankacılık","AKBNK":"Bankacılık","ISCTR":"Bankacılık","VAKBN":"Bankacılık",
        "EREGL":"Demir-Çelik","KRDMD":"Demir-Çelik","SISE":"Cam","KCHOL":"Holding",
        "SAHOL":"Holding","TUPRS":"Petrol","PETKM":"Petrokimya","BIMAS":"Perakende",
        "MGROS":"Perakende","FROTO":"Otomotiv","TOASO":"Otomotiv","KOZAL":"Madencilik",
        "TCELL":"Telekom","TTKOM":"Telekom","ARCLK":"Beyaz Eşya","AEFES":"Gıda",
        "CCOLA":"Gıda","ULKER":"Gıda","ENKAI":"İnşaat"}

KRIPTO = {"BTC-USD":"Bitcoin","ETH-USD":"Ethereum","BNB-USD":"BNB","SOL-USD":"Solana",
          "XRP-USD":"XRP","ADA-USD":"Cardano","DOGE-USD":"Dogecoin","AVAX-USD":"Avalanche",
          "DOT-USD":"Polkadot","MATIC-USD":"Polygon","LINK-USD":"Chainlink",
          "ATOM-USD":"Cosmos","LTC-USD":"Litecoin","TRX-USD":"TRON","UNI-USD":"Uniswap"}

ABD = {"AAPL":"Apple","MSFT":"Microsoft","GOOGL":"Google","AMZN":"Amazon",
       "TSLA":"Tesla","NVDA":"NVIDIA","META":"Meta","AMD":"AMD",
       "NFLX":"Netflix","INTC":"Intel"}

EMTIA = {"GC=F":"Altın","SI=F":"Gümüş","CL=F":"Petrol WTI","BZ=F":"Brent",
         "NG=F":"Doğalgaz","HG=F":"Bakır","ZC=F":"Mısır","ZW=F":"Buğday",
         "PL=F":"Platin","PA=F":"Paladyum"}

PIYASALAR = {"🇹🇷 BIST": BIST, "₿ Kripto": KRIPTO, "🇺🇸 ABD": ABD, "🥇 Emtia": EMTIA}

# ============================================================
# HABER NLP
# ============================================================
POZ = ["rekor","büyüme","kâr","anlaşma","ihale","yatırım","temettü","yükseliş",
       "güçlü","olumlu","artış","kazanç","pozitif","iyileşme","hedef","başarı",
       "ihracat","genişleme","ortaklık","satın alma","birleşme","rally","boğa"]
NEG = ["zarar","düşüş","kriz","ceza","soruşturma","iptal","borç","zayıf",
       "olumsuz","azalış","iflas","uyarı","negatif","kayıp","risk","sorun",
       "daralma","küçülme","dava","gecikme","saldırı","gerileme","ayı","çöküş"]

def sentiment(basliklar):
    if not basliklar: return 0.0
    s = 0
    for h in basliklar:
        h = h.lower()
        s += sum(w in h for w in POZ) - sum(w in h for w in NEG)
    return float(np.tanh(s/max(len(basliklar),1)))

@st.cache_data(show_spinner=False, ttl=1800)
def rss_cek(ticker, limit=8):
    try:
        import feedparser
        if "-USD" in ticker: q = ticker.replace("-USD","") + " crypto"
        elif "=F" in ticker: q = ticker.replace("=F","") + " commodity"
        else: q = ticker + " stock"
        url = f"https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"
        return [e.title for e in feedparser.parse(url).entries[:limit]]
    except: return []
# ============================================================
# VERİ
# ============================================================
@st.cache_data(show_spinner=False)
def ornek_veri(t, n=1000):
    rng = np.random.default_rng(abs(hash(t)) % 9999)
    d = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    if "-USD" in t: vol, dr = 0.045, 0.0008
    elif "=F" in t: vol, dr = 0.018, 0.0002
    elif t in BIST: vol, dr = 0.020, 0.0003
    else: vol, dr = 0.018, 0.0004
    p = 10*np.exp(np.cumsum(rng.normal(dr, vol, n)))
    return pd.DataFrame({"Open":p*(1+rng.normal(0,0.005,n)),
        "High":p*(1+rng.uniform(0.002,0.03,n)),
        "Low":p*(1-rng.uniform(0.002,0.03,n)),
        "Close":p,"Volume":rng.integers(1_000_000,20_000_000,n)}, index=d)

@st.cache_data(show_spinner=False, ttl=600)
def gercek_veri(t, _n=0):
    try:
        import yfinance as yf
        if "-USD" in t or "=F" in t: symbol = t
        elif "." in t: symbol = t
        else: symbol = f"{t}.IS"
        df = yf.download(symbol, period="5y", auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[["Open","High","Low","Close","Volume"]].dropna()
    except: return None

@st.cache_data(show_spinner=False, ttl=60)
def canli_fiyat(t, _n=0):
    try:
        import yfinance as yf
        if "-USD" in t or "=F" in t: sym = t
        elif "." in t: sym = t
        else: sym = f"{t}.IS"
        h = yf.Ticker(sym).history(period="1d", interval="5m", auto_adjust=True)
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except: return None

# ============================================================
# 80+ ÖZELLİK
# ============================================================
def ozellikler(df):
    df = df.copy()
    df['ret1'] = df['Close'].pct_change()
    for L in [2,3,5,10,20,50,100,200]:
        df[f'lag{L}'] = df['Close'].pct_change(L)
    for w in [5,10,20,50,100,200]:
        df[f'sma{w}'] = df['Close'].rolling(w).mean()
    for w in [12,26]:
        df[f'ema{w}'] = df['Close'].ewm(span=w,adjust=False).mean()
    df['close_sma20'] = df['Close']/df['sma20']
    df['close_sma50'] = df['Close']/df['sma50']
    df['close_sma200'] = df['Close']/df['sma200']
    df['sma20_sma50'] = df['sma20']/df['sma50']
    df['sma50_sma200'] = df['sma50']/df['sma200']
    df['macd'] = df['ema12']-df['ema26']
    df['macd_sig'] = df['macd'].ewm(span=9,adjust=False).mean()
    df['macd_hist'] = df['macd']-df['macd_sig']
    for w in [7,14,21]:
        dl = df['Close'].diff(); g = dl.clip(lower=0); l = -dl.clip(upper=0)
        df[f'rsi{w}'] = 100-100/(1+g.rolling(w).mean()/(l.rolling(w).mean()+1e-9))
    lo = df['Low'].rolling(14).min()
    hi = df['High'].rolling(14).max()
    df['stoch'] = 100*(df['Close']-lo)/(hi-lo+1e-9)
    df['willr'] = -100*(hi-df['Close'])/(hi-lo+1e-9)
    m = df['Close'].rolling(20).mean()
    s = df['Close'].rolling(20).std()
    df['bb_pos'] = (df['Close']-(m-2*s))/((m+2*s)-(m-2*s)+1e-9)
    df['bb_width'] = ((m+2*s)-(m-2*s))/(m+1e-9)
    tr = pd.concat([df['High']-df['Low'],
                    (df['High']-df['Close'].shift()).abs(),
                    (df['Low']-df['Close'].shift()).abs()], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = df['atr']/(df['Close']+1e-9)
    df['atr_ratio'] = tr.rolling(14).mean()/tr.rolling(50).mean()
    df['vol20'] = df['ret1'].rolling(20).std()
    df['vol60'] = df['ret1'].rolling(60).std()
    df['vol_ratio_vol'] = df['vol20']/(df['vol60']+1e-9)
    df['vol_sma20'] = df['Volume'].rolling(20).mean()
    df['vol_ratio'] = df['Volume']/(df['vol_sma20']+1e-9)
    df['obv'] = (np.sign(df['ret1'])*df['Volume']).cumsum()
    df['obv_slope'] = df['obv'].pct_change(10)
    tp = (df['High']+df['Low']+df['Close'])/3
    mf = tp*df['Volume']
    pos_mf = mf.where(tp>tp.shift(),0).rolling(14).sum()
    neg_mf = mf.where(tp<tp.shift(),0).rolling(14).sum()
    df['mfi'] = 100-100/(1+pos_mf/(neg_mf+1e-9))
    clv = ((df['Close']-df['Low'])-(df['High']-df['Close']))/(df['High']-df['Low']+1e-9)
    df['cmf'] = (clv*df['Volume']).rolling(20).sum()/(df['Volume'].rolling(20).sum()+1e-9)
    df['mom20'] = df['Close']/df['Close'].shift(20)-1
    df['mom60'] = df['Close']/df['Close'].shift(60)-1
    df['mom120'] = df['Close']/df['Close'].shift(120)-1
    df['hi20'] = df['Close']/df['High'].rolling(20).max()
    df['lo20'] = df['Close']/df['Low'].rolling(20).min()
    df['sma_slope'] = df['sma50'].pct_change(20)
    df['above_sma200'] = (df['Close']>df['sma200']).astype(int)
    df['trend_strength'] = (df['sma20']-df['sma50'])/(df['sma50']+1e-9)
    df['close_pos'] = (df['Close']-df['Low'])/(df['High']-df['Low']+1e-9)
    df['gap'] = (df['Open']-df['Close'].shift(1))/(df['Close'].shift(1)+1e-9)
    return df

FEATURES = (['ret1']+[f'lag{L}' for L in [2,3,5,10,20,50,100,200]]
            +['close_sma20','close_sma50','close_sma200','sma20_sma50','sma50_sma200']
            +['macd','macd_sig','macd_hist']
            +['rsi7','rsi14','rsi21','stoch','willr','bb_pos','bb_width']
            +['atr_pct','atr_ratio','vol20','vol60','vol_ratio_vol']
            +['vol_ratio','obv_slope','mfi','cmf']
            +['mom20','mom60','mom120','hi20','lo20']
            +['sma_slope','above_sma200','trend_strength','close_pos','gap'])

# ============================================================
# STACKING + MLP
# ============================================================
@st.cache_data(show_spinner=False)
def egit(df_raw, t, esik=0.005, sent=0.0):
    df = ozellikler(df_raw)
    df['y'] = (df['Close'].shift(-1)/df['Close']-1 > esik).astype(int)
    df['sent'] = sent
    feats = FEATURES + ['sent']
    d = df[feats+['y']].dropna()
    if len(d) < 250 or d['y'].nunique() < 2: return None
    X, y = d[feats].values, d['y'].values
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    tscv = TimeSeriesSplit(n_splits=5)
    aucs, accs = [], []
    base = [
        ('rf', RandomForestClassifier(n_estimators=200, max_depth=7, n_jobs=-1, random_state=42)),
        ('xgb', XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.05,
                              subsample=0.9, eval_metric='logloss',
                              use_label_encoder=False, random_state=42, n_jobs=-1)),
        ('gb', GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)),
        ('et', ExtraTreesClassifier(n_estimators=200, max_depth=8, n_jobs=-1, random_state=42)),
    ]
    for tr, te in tscv.split(Xs):
        if len(np.unique(y[tr]))<2 or len(np.unique(y[te]))<2: continue
        stk = StackingClassifier(estimators=base,
                                 final_estimator=LogisticRegression(max_iter=500),
                                 cv=3, n_jobs=-1)
        stk.fit(Xs[tr], y[tr])
        p = stk.predict_proba(Xs[te])[:,1]
        aucs.append(roc_auc_score(y[te], p))
        accs.append(accuracy_score(y[te], (p>0.5).astype(int)))
    stk_final = StackingClassifier(estimators=base,
                                   final_estimator=LogisticRegression(max_iter=500),
                                   cv=5, n_jobs=-1)
    stk_final.fit(Xs, y)
    mlp = MLPClassifier(hidden_layer_sizes=(100,50), max_iter=400, random_state=42)
    mlp.fit(Xs, y)
    last = scaler.transform(df[feats].iloc[[-1]].values)
    if np.isnan(last).any(): return None
    p_stk = stk_final.predict_proba(last)[0,1]
    p_mlp = mlp.predict_proba(last)[0,1]
    p = 0.65*p_stk + 0.35*p_mlp
    base_p = {}
    for n_, e_ in stk_final.named_estimators_.items():
        try: base_p[n_] = float(e_.predict_proba(last)[0,1])
        except: pass
    return {"p":float(p), "p_stk":float(p_stk), "p_mlp":float(p_mlp),
            "base":base_p, "auc":float(np.mean(aucs) if aucs else 0.5),
            "acc":float(np.mean(accs) if accs else 0.5), "df":df,
            "feats":feats, "model":stk_final}

def feat_importance(res, top=15):
    try:
        rf = res["model"].named_estimators_.get("rf")
        if rf is None: return None
        imp = pd.Series(rf.feature_importances_, index=res["feats"])
        return imp.sort_values(ascending=False).head(top)
    except: return None

# ============================================================
# MONTE CARLO
# ============================================================
def monte_carlo(df, gun=30, sim=800):
    d = ozellikler(df).dropna()
    if len(d) < 100: return None
    rets = d['ret1'].tail(250).dropna()
    mu, sg = rets.mean(), rets.std()
    son = d['Close'].iloc[-1]
    sims = np.zeros((sim, gun))
    for i in range(sim):
        sims[i] = son * np.exp(np.cumsum(np.random.normal(mu, sg, gun)))
    var95 = np.percentile(sims[:,-1], 5) - son
    cvar95 = sims[:,-1][sims[:,-1] <= np.percentile(sims[:,-1], 5)].mean() - son
    return {"sims":sims, "son":son, "var95":float(var95), "cvar95":float(cvar95),
            "beklenen":float(np.mean(sims[:,-1])), "medyan":float(np.median(sims[:,-1]))}

# ============================================================
# BACKTEST
# ============================================================
def backtest(df, sl=0.05, tp=0.10, c=0.001, kayma=0.0005):
    df = ozellikler(df).dropna().copy()
    df['sig'] = ((df['rsi14']<35) & (df['macd']>df['macd_sig']) &
                 (df['above_sma200']==1)).astype(int)
    cap, pos, ent = 1.0, 0.0, 0.0
    eq = []; trades = []
    for _, r in df.iterrows():
        pr = r['Close']
        if pos > 0:
            ret = pr/ent - 1
            if ret <= -sl or ret >= tp:
                ep = pr*(1-kayma)
                cap = pos*ep*(1-c)
                trades.append({"giris":ent,"cikis":ep,"getiri":ret})
                pos = 0.0
        if pos == 0 and r['sig'] == 1:
            ep = pr*(1+kayma)
            pos = cap/(ep*(1+c))
            ent = ep; cap = 0.0
        eq.append(cap+pos*pr)
    if pos > 0:
        cap = pos*df['Close'].iloc[-1]*(1-c)
    e = pd.Series(eq, index=df.index)
    daily = e.pct_change().dropna()
    sh = (daily.mean()/daily.std()*np.sqrt(252)) if daily.std()>0 else 0
    dd = (e/e.cummax()-1).min()
    wins = [t for t in trades if t['getiri']>0]
    return {"eq":e, "ret":float(e.iloc[-1]/e.iloc[0]-1), "sh":float(sh),
            "dd":float(dd), "tr":len(trades),
            "wr":float(len(wins)/len(trades)) if trades else 0, "trades":trades}

# ============================================================
# PORTFÖY
# ============================================================
def risk_parity(rets):
    cov = rets.cov().values * 252
    n = len(cov)
    def obj(w):
        w = np.abs(w); w = w/w.sum()
        pv = np.sqrt(w @ cov @ w)
        mar = (cov @ w)/pv
        return np.sum((mar - mar.mean())**2)
    res = minimize(obj, np.ones(n)/n, method='SLSQP',
                   bounds=[(0.01,1)]*n,
                   constraints={'type':'eq','fun': lambda w: w.sum()-1})
    s = pd.Series(res.x, index=rets.columns)
    return (s/s.sum()).round(4)

def kumeleme(rets, k=4):
    if len(rets.columns) < k: return None
    corr = rets.corr()
    dist = 1-corr.abs()
    try:
        m = AgglomerativeClustering(n_clusters=k, metric='precomputed', linkage='average')
        return pd.Series(m.fit_predict(dist.values), index=rets.columns)
    except: return None

def kelly(p, wr):
    b = wr/(1-wr+1e-9) if wr < 1 else 1
    f = (p*b - (1-p))/(b+1e-9)
    return max(0, min(f, 0.25))
# ============================================================
# ARAYÜZ
# ============================================================
st.title("🎯 Ultimate Tarayıcı — v10")
st.caption("BIST + Kripto + ABD + Emtia • Stacking + MLP + Monte Carlo + Telegram")

with st.sidebar:
    st.header("⚙️ Ayarlar")
    veri = st.radio("Veri", ["Örnek Veri", "Gerçek (yfinance)"], index=0)
    piyasa_sec = st.multiselect("Piyasalar", list(PIYASALAR.keys()),
                                default=list(PIYASALAR.keys())[:2])
    havuz = []
    for p in piyasa_sec:
        havuz.extend(list(PIYASALAR[p].keys()))
    hisseler = st.multiselect("Varlık", havuz, default=havuz[:8])
    canli_haber = st.checkbox("Canlı RSS haber", value=False)
    st.divider()
    esik = st.slider("Hedef Getiri (%)", 0.1, 5.0, 0.5, 0.1)/100
    sl = st.slider("Stop-Loss (%)", 1, 20, 5)/100
    tp = st.slider("Take-Profit (%)", 2, 50, 10)/100
    min_p = st.slider("Min Olasılık", 0.0, 0.8, 0.0, 0.05)
    tara = st.button("🎯 TARA", use_container_width=True, type="primary")

if tara and hisseler:
    sonuc, dfs, rets, det = [], {}, {}, {}
    pg = st.progress(0, "Taranıyor...")
    t0 = time.time()
    for i, t in enumerate(hisseler):
        df = gercek_veri(t) if veri.startswith("Gerçek") else ornek_veri(t)
        if df is None or len(df) < 250:
            pg.progress((i+1)/len(hisseler), f"{t} veri yok")
            continue
        basliklar = rss_cek(t) if canli_haber else []
        sent = sentiment(basliklar)
        res = egit(df, t, esik, sent)
        if res is None:
            pg.progress((i+1)/len(hisseler), f"{t} hata")
            continue
        b = backtest(res['df'], sl, tp)
        k = kelly(res['p'], b['wr'])
        piy = "🇹🇷 BIST" if t in BIST else ("₿ Kripto" if "-USD" in t else
                                            ("🇺🇸 ABD" if t in ABD else "🥇 Emtia"))
        isim = BIST.get(t) or KRIPTO.get(t) or ABD.get(t) or EMTIA.get(t) or "-"
        sonuc.append({
            "Varlık":t, "Piyasa":piy, "İsim":isim,
            "Olasılık":round(res['p'],3),
            "Stacking":round(res['p_stk'],2),
            "MLP":round(res['p_mlp'],2),
            "AUC":round(res['auc'],3),
            "Acc":round(res['acc'],3),
            "Sent":round(sent,2),
            "Son":round(float(res['df']['Close'].iloc[-1]), 4 if "-USD" in t else 2),
            "Getiri":f"{b['ret']*100:.1f}%",
            "Sharpe":round(b['sh'],2),
            "MaxDD":f"{b['dd']*100:.1f}%",
            "WinRate":f"{b['wr']*100:.0f}%",
            "İşlem":b['tr'],
            "Kelly":f"{k*100:.1f}%"
        })
        dfs[t] = res['df']
        rets[t] = res['df']['Close'].pct_change()
        det[t] = {"res":res, "bt":b, "haber":basliklar}
        pg.progress((i+1)/len(hisseler), f"{t} ✓ ({time.time()-t0:.0f}s)")
    pg.empty()

    if sonuc:
        r = pd.DataFrame(sonuc).sort_values("Olasılık", ascending=False)
        def sg(x):
            if x['Olasılık']>0.62 and x['AUC']>0.55: return "🟢 GÜÇLÜ AL"
            if x['Olasılık']>0.55: return "🟢 AL"
            if x['Olasılık']<0.40: return "🔴 ZAYIF"
            return "🟡 NÖTR"
        r["Sinyal"] = r.apply(sg, axis=1)
        if min_p > 0:
            r = r[r["Olasılık"] >= min_p]
        try:
            save_scan(user, sonuc)
        except Exception as e:
            st.warning(f"Kayıt hatası: {e}")

        st.subheader("📊 Özet")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Toplam", len(r))
        c2.metric("Güçlü AL", (r["Sinyal"]=="🟢 GÜÇLÜ AL").sum())
        c3.metric("Ort. Sharpe", f"{r['Sharpe'].mean():.2f}")
        c4.metric("Ort. AUC", f"{r['AUC'].mean():.3f}")

        st.subheader("📋 Sonuçlar")
        st.dataframe(r, use_container_width=True, hide_index=True)

        # Piyasa bazlı
        cols = st.columns(min(len(piyasa_sec), 4))
        for i, p in enumerate(piyasa_sec):
            with cols[i % 4]:
                sub = r[r["Piyasa"]==p].head(5)
                st.markdown(f"**{p} — En İyi 5**")
                if not sub.empty:
                    st.dataframe(sub[["Varlık","Olasılık","Sharpe","Kelly","Sinyal"]],
                                 use_container_width=True, hide_index=True)

        # Grafik
        renkler = {"🇹🇷 BIST":"#3498db", "₿ Kripto":"#f39c12",
                   "🇺🇸 ABD":"#e74c3c", "🥇 Emtia":"#9b59b6"}
        fig = go.Figure(go.Bar(
            x=r["Varlık"], y=r["Olasılık"],
            marker_color=[renkler.get(p,"#95a5a6") for p in r["Piyasa"]],
            text=[f"{p:.2f}" for p in r["Olasılık"]], textposition="outside"))
        fig.add_hline(y=0.5, line_dash="dash", line_color="gray")
        fig.add_hline(y=0.6, line_dash="dot", line_color="green")
        fig.update_layout(height=420, yaxis_range=[0,1.1],
                          title="Olasılıklar — 🟦BIST 🟧Kripto 🟥ABD 🟪Emtia")
        st.plotly_chart(fig, use_container_width=True)

        # Canlı fiyat
        st.subheader("⚡ Canlı Fiyatlar")
        cols = st.columns(min(len(r), 5))
        for idx, row in r.reset_index(drop=True).iterrows():
            live = canli_fiyat(row["Varlık"], _n=int(time.time()//60))
            with cols[idx % len(cols)]:
                f = ".4f" if "-USD" in row["Varlık"] else ".2f"
                st.metric(row["Varlık"], f"{live:{f}}" if live else "-",
                          delta=f"Model: {row['Olasılık']:.2f}")

        # Detay
        st.subheader("🔍 Detaylı Analiz")
        sel = st.selectbox("Varlık", r["Varlık"].tolist())
        d = dfs[sel]
        row = r[r["Varlık"]==sel].iloc[0]
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Olasılık", f"{row['Olasılık']:.3f}")
        c2.metric("AUC", f"{row['AUC']:.3f}")
        c3.metric("Sharpe", f"{row['Sharpe']:.2f}")
        c4.metric("Win Rate", row['WinRate'])
        c5.metric("Kelly", row['Kelly'])

        if det[sel]['res']['base']:
            st.write("**Base Model Oyları:**")
            bp = det[sel]['res']['base']
            cc = st.columns(len(bp))
            for i,(k_,v_) in enumerate(bp.items()):
                cc[i].metric(k_.upper(), f"{v_:.2f}")

        if det[sel]['haber']:
            with st.expander(f"📰 Canlı Haberler ({len(det[sel]['haber'])})"):
                for h in det[sel]['haber']:
                    st.write(f"• {h}")

        # Mum grafiği
        f2 = make_subplots(rows=4, cols=1, shared_xaxes=True,
                           row_heights=[0.4,0.2,0.2,0.2],
                           vertical_spacing=0.04,
                           subplot_titles=(f"{sel}","RSI","MACD","Hacim"))
        f2.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'],
                                    low=d['Low'], close=d['Close']),1,1)
        f2.add_trace(go.Scatter(x=d.index, y=d['sma20'], name="SMA20",
                                line=dict(color="orange")),1,1)
        f2.add_trace(go.Scatter(x=d.index, y=d['sma50'], name="SMA50",
                                line=dict(color="blue")),1,1)
        f2.add_trace(go.Scatter(x=d.index, y=d['sma200'], name="SMA200",
                                line=dict(color="red")),1,1)
        f2.add_trace(go.Scatter(x=d.index, y=d['rsi14'], name="RSI",
                                line=dict(color="purple")),2,1)
        f2.add_hline(y=70, line_dash="dot", row=2, col=1)
        f2.add_hline(y=30, line_dash="dot", row=2, col=1)
        f2.add_trace(go.Scatter(x=d.index, y=d['macd'], name="MACD"),3,1)
        f2.add_trace(go.Scatter(x=d.index, y=d['macd_sig'], name="Sinyal"),3,1)
        f2.add_trace(go.Bar(x=d.index, y=d['Volume'], name="Hacim"),4,1)
        f2.update_layout(height=900, xaxis_rangeslider_visible=False)
        st.plotly_chart(f2, use_container_width=True)

        # Feature importance
        fi = feat_importance(det[sel]['res'])
        if fi is not None:
            st.subheader("🎯 En Etkili 15 Özellik")
            st.plotly_chart(
                go.Figure(go.Bar(x=fi.values, y=fi.index, orientation='h',
                                  marker_color='#2ecc71')).update_layout(height=450),
                use_container_width=True)

        # Monte Carlo
        st.subheader("🎲 Monte Carlo (30 gün)")
        mc = monte_carlo(d, 30, 500)
        if mc:
            c1,c2,c3 = st.columns(3)
            c1.metric("Beklenen", f"{mc['beklenen']:.2f}")
            c2.metric("VaR 95%", f"{mc['var95']:.2f}")
            c3.metric("CVaR 95%", f"{mc['cvar95']:.2f}")
            fmc = go.Figure()
            for i in range(min(50, len(mc['sims']))):
                fmc.add_trace(go.Scatter(y=mc['sims'][i], mode='lines',
                                          line=dict(color='rgba(46,204,113,0.15)'),
                                          showlegend=False))
            fmc.add_hline(y=mc['son'], line_dash="dash", line_color="white")
            fmc.update_layout(height=400)
            st.plotly_chart(fmc, use_container_width=True)

        # Backtest
        st.subheader("💰 Backtest")
        st.line_chart(det[sel]['bt']['eq'])
        if det[sel]['bt']['trades']:
            st.subheader("📋 İşlem Günlüğü")
            tdf = pd.DataFrame(det[sel]['bt']['trades'])
            tdf['giris'] = tdf['giris'].round(2)
            tdf['cikis'] = tdf['cikis'].round(2)
            tdf['getiri'] = (tdf['getiri']*100).round(2).astype(str)+"%"
            st.dataframe(tdf.tail(20), use_container_width=True)

        # Portföy
        ret_df = pd.DataFrame(rets).dropna()
        if len(ret_df.columns) >= 3:
            st.subheader("💼 Risk Parity Portföy")
            try:
                rp = risk_parity(ret_df)
                c1,c2 = st.columns([1,1])
                with c1:
                    st.dataframe(rp.rename("Ağırlık"))
                with c2:
                    pie = go.Figure(go.Pie(labels=rp.index, values=rp.values, hole=0.4))
                    pie.update_layout(height=350)
                    st.plotly_chart(pie, use_container_width=True)
            except Exception as e:
                st.warning(f"Portföy: {e}")

            st.subheader("🔗 Korelasyon")
            corr = ret_df.corr().round(2)
            st.plotly_chart(
                go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index,
                                      colorscale='RdYlGn_r', zmid=0)).update_layout(height=500),
                use_container_width=True)

            st.subheader("🧩 Kümeler")
            km = kumeleme(ret_df, min(4,len(ret_df.columns)))
            if km is not None:
                st.dataframe(pd.DataFrame({"Varlık":km.index, "Küme":km.values}),
                             use_container_width=True, hide_index=True)
# ============================================================
# SEKMELER
# ============================================================
st.divider()
tabs = st.tabs(["🕘 Geçmiş", "🔔 Alarmlar", "📨 Telegram", "⬇️ İndir"])

with tabs[0]:
    h = load_scans(user, 200)
    if h.empty:
        st.info("Kayıt yok.")
    else:
        st.dataframe(h, use_container_width=True, hide_index=True)
        st.download_button("⬇️ CSV indir",
                           h.to_csv(index=False).encode(),
                           f"gecmis_{user}.csv", "text/csv")

with tabs[1]:
    a = load_alerts(user, 200)
    if a.empty:
        st.info("Alarm yok.")
    else:
        st.dataframe(a, use_container_width=True, hide_index=True)
    with st.form("yeni_alarm"):
        c1,c2,c3 = st.columns(3)
        v = c1.text_input("Varlık (örn: THYAO, BTC-USD)")
        tip = c2.selectbox("Tip", ["fiyat_üstü","fiyat_altı","olasılık_üstü"])
        e = c3.number_input("Eşik", value=100.0, step=1.0)
        if st.form_submit_button("Kaydet"):
            save_alert(user, v, tip, float(e))
            st.success("Alarm kaydedildi ✓")

with tabs[2]:
    st.subheader("📨 Telegram Bot")
    st.caption("BotFather → /newbot → token al. getUpdates ile chat_id.")
    s = get_tg(user)
    with st.form("tg_form"):
        tk = st.text_input("Bot Token", value=s["token"], type="password")
        ch = st.text_input("Chat ID", value=s["chat"])
        ak = st.checkbox("Aktif", value=s["aktif"])
        c1,c2 = st.columns(2)
        if c1.form_submit_button("💾 Kaydet"):
            set_tg(user, tk, ch, ak)
            st.success("Kaydedildi ✓")
        if c2.form_submit_button("🧪 Test Mesajı"):
            ok, msg = tg_send(tk, ch, "🧪 Ultimate v10 test")
            (st.success if ok else st.error)(msg)

with tabs[3]:
    st.subheader("📦 Proje Dosyaları")
    req = ("streamlit\npandas\nnumpy\nscikit-learn\nxgboost\nplotly\n"
           "yfinance\nscipy\nfeedparser\nstreamlit-authenticator\n"
           "pyyaml\nrequests\n")
    readme = ("# Ultimate Tarayıcı v10\n\n"
              "BIST + Kripto + ABD + Emtia • Stacking + MLP + Monte Carlo\n\n"
              "```\npip install -r requirements.txt\nstreamlit run app_v10.py\n```\n")
    src = read_self()

    st.download_button("⬇️ app_v10.py", src.encode(), "app_v10.py",
                       "text/x-python", use_container_width=True)
    st.download_button("⬇️ requirements.txt", req.encode(), "requirements.txt",
                       use_container_width=True)
    st.download_button("⬇️ README.md", readme.encode(), "README.md",
                       use_container_width=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("app_v10.py", src)
        z.writestr("requirements.txt", req)
        z.writestr("README.md", readme)
    buf.seek(0)
    st.download_button("⬇️ ultimate_v10.zip", buf.getvalue(),
                       "ultimate_v10.zip", "application/zip",
                       use_container_width=True, type="primary")
# ============================================================
# SON
# ============================================================
st.caption("v10 • Stacking + MLP • 4 Piyasa • Monte Carlo • Risk Parity • Telegram")
st.caption("⚠️ Bu uygulama eğitim amaçlıdır. Yatırım tavsiyesi değildir.")
