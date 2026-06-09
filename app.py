import os
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

SUPPORTED_CHAINS = {
    "ethereum": {"label": "Ethereum", "type": "evm", "chainid": "1", "explorer": "Etherscan"},
    "base": {"label": "Base", "type": "evm", "chainid": "8453", "explorer": "BaseScan/Etherscan API"},
    "bsc": {"label": "BSC", "type": "evm", "chainid": "56", "explorer": "BscScan"},
    "polygon": {"label": "Polygon", "type": "evm", "chainid": "137", "explorer": "PolygonScan"},
    "arbitrum": {"label": "Arbitrum", "type": "evm", "chainid": "42161", "explorer": "Arbiscan"},
    "optimism": {"label": "Optimism", "type": "evm", "chainid": "10", "explorer": "Optimistic Etherscan"},
    "avalanche": {"label": "Avalanche", "type": "evm", "chainid": "43114", "explorer": "Snowtrace"},
    "solana": {"label": "Solana", "type": "solana"},
}

def get_api_key(name: str):
    try:
        return st.secrets.get(name, None)
    except Exception:
        return os.getenv(name)

def fetch_evm_transactions(address: str, chain_key: str):
    cfg = SUPPORTED_CHAINS[chain_key]
    api_key = get_api_key("ETHERSCAN_API_KEY")
    if not api_key:
        return [], "ETHERSCAN_API_KEY bulunamadı"

    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": cfg["chainid"],
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 100,
        "sort": "desc",
        "apikey": api_key,
    }
    r = requests.get(url, params=params, timeout=30)
    data = r.json()

    if str(data.get("status")) != "1":
        return [], data.get("message", "EVM transaction fetch failed")

    rows = []
    for tx in data.get("result", []):
        rows.append({
            "tx_hash": tx.get("hash"),
            "timestamp": int(tx.get("timeStamp", 0)),
            "from": tx.get("from"),
            "to": tx.get("to"),
            "value_native": float(tx.get("value", 0)) / 1e18,
            "gas_used": int(tx.get("gasUsed", 0)),
            "gas_price_wei": int(tx.get("gasPrice", 0)),
            "token_symbol": cfg["label"],
            "type": "transfer",
            "dex": "On-chain transfer",
        })
    return rows, None

def fetch_solana_transactions(address: str):
    api_key = get_api_key("SOLSCAN_API_KEY")
    if not api_key:
        return [], "SOLSCAN_API_KEY bulunamadı"

    url = "https://pro-api.solscan.io/v2.0/account/transactions"
    headers = {"token": api_key}
    params = {"address": address, "limit": 100}

    r = requests.get(url, headers=headers, params=params, timeout=30)
    data = r.json()

    if not isinstance(data, dict):
        return [], "Solscan response parse error"

    items = data.get("data") or data.get("result") or []
    rows = []
    for tx in items:
        rows.append({
            "tx_hash": tx.get("signature") or tx.get("txHash"),
            "timestamp": int(tx.get("blockTime", 0)),
            "from": tx.get("owner"),
            "to": tx.get("feePayer"),
            "value_native": None,
            "gas_used": None,
            "gas_price_wei": None,
            "token_symbol": "SOL",
            "type": "transfer",
            "dex": tx.get("source") or "Solana transaction",
        })
    return rows, None

def fetch_balance_placeholder(address: str, chain_key: str):
    return {
        "native": 0,
        "token_count": 0,
        "note": "Bu sürümde bakiye özeti provider'a göre genişletilebilir"
    }

def analyze_profile(df: pd.DataFrame):
    if df.empty:
        return {
            "summary": "Bu adres için işlem bulunamadı.",
            "traits": [],
            "strategy_label": "Bilinmiyor",
            "risk_label": "Bilinmiyor",
            "signals": [],
        }

    tx_count = len(df)
    token_count = df["token_symbol"].nunique() if "token_symbol" in df.columns else 0
    days = max((df["timestamp"].max() - df["timestamp"].min()) / 86400, 1)
    tx_per_day = tx_count / days

    if tx_count >= 100:
        strategy_label = "Yüksek aktivite / Bot benzeri"
    elif tx_per_day >= 5:
        strategy_label = "Aktif trader"
    elif tx_count >= 10:
        strategy_label = "Orta aktivite"
    else:
        strategy_label = "Düşük aktivite / HODL eğilimi"

    risk_label = "Bilinmiyor (PnL yok)"

    signals = [
        f"Toplam işlem: {tx_count}",
        f"Farklı token/ağ sayısı: {token_count}",
        f"Günlük ortalama işlem: {tx_per_day:.1f}",
    ]

    summary = (
        f"Bu adres {strategy_label} profiline yakın görünüyor. "
        f"Toplam {tx_count} işlem var ve günlük ortalama {tx_per_day:.1f} işlem yapıyor. "
        f"{token_count} farklı token/ağ ile temas etmiş. "
        f"İşlem yoğunluğu artarsa bu adres daha çok aktif trader veya bot davranışı gösterebilir."
    )

    traits = [
        f"Toplam işlem: {tx_count}",
        f"Token çeşitliliği: {token_count}",
        f"Günlük işlem ortalaması: {tx_per_day:.1f}",
        f"Strateji etiketi: {strategy_label}",
        f"Risk etiketi: {risk_label}",
    ]

    return {
        "summary": summary,
        "traits": traits,
        "strategy_label": strategy_label,
        "risk_label": risk_label,
        "signals": signals,
    }

st.set_page_config(page_title="Kripto Cüzdan Analiz", page_icon="🔍", layout="wide")
st.title("Kripto Cüzdan Analiz: Gerçek Veri")

st.caption("Public adres üzerinden işlem geçmişi ve davranış analizi.")

address = st.text_input("Cüzdan Adresi (public)", placeholder="0x... veya Solana adresi")
chain_key = st.selectbox("Ağ seç", list(SUPPORTED_CHAINS.keys()), format_func=lambda k: SUPPORTED_CHAINS[k]["label"])

run = st.button("Analiz Başlat")

if run:
    if not address:
        st.error("Adres gir.")
        st.stop()

    chain_type = SUPPORTED_CHAINS[chain_key]["type"]

    with st.spinner("Veri çekiliyor..."):
        if chain_type == "evm":
            rows, err = fetch_evm_transactions(address, chain_key)
        elif chain_type == "solana":
            rows, err = fetch_solana_transactions(address)
        else:
            rows, err = [], "Unsupported chain type"

    if err and not rows:
        st.error(err)
        st.stop()

    df = pd.DataFrame(rows)

    if df.empty:
        st.warning("İşlem bulunamadı.")
        st.stop()

    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
    df = df.sort_values("datetime", ascending=True)

    profile = analyze_profile(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("İşlem Sayısı", len(df))
    c2.metric("Token/Ağ", df["token_symbol"].nunique())
    c3.metric("İlk İşlem", str(df["datetime"].min())[:19])
    c4.metric("Son İşlem", str(df["datetime"].max())[:19])

    st.subheader("🧠 Özet")
    st.write(profile["summary"])

    st.subheader("📌 Özellikler")
    for t in profile["traits"]:
        st.write(f"- {t}")

    st.subheader("🔎 İşlem Davranışı")
    st.write("İşlem tipi dağılımı ve zaman serisi aşağıda.")

    fig = px.scatter(
        df,
        x="datetime",
        y="value_native" if "value_native" in df.columns else "timestamp",
        color="type" if "type" in df.columns else None,
        hover_data=[c for c in ["tx_hash", "from", "to", "token_symbol", "dex"] if c in df.columns],
        title="İşlem Zaman Serisi"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📄 İşlem Tablosu")
    show_cols = [c for c in ["datetime", "tx_hash", "from", "to", "token_symbol", "value_native", "dex"] if c in df.columns]
    st.dataframe(df[show_cols].head(100), use_container_width=True)

    st.download_button(
        "CSV indir",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{address[:8]}_{chain_key}_txs.csv",
        mime="text/csv",
    )
