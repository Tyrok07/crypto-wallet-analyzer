import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from typing import Dict, List

# =============================================================================
# CONFIG & API
# =============================================================================
SUPPORTED_CHAINS = {
    "eth": "Ethereum",
    "bsc": "BSC",
    "polygon": "Polygon",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
    "avalanche": "Avalanche",
}

try:
    MORALIS_API_KEY = st.secrets["MORALIS_API_KEY"]
except KeyError:
    st.error("❌ Streamlit Secrets'ta 'MORALIS_API_KEY' bulunamadı.")
    st.stop()

BASE_URL = "https://deep-index.moralis.io/api/v2.2"
HEADERS = {
    "Accept": "application/json",
    "X-API-Key": MORALIS_API_KEY
}

# =============================================================================
# API FONKSİYONLARI
# =============================================================================
def fetch_wallet_balance(address: str, chain: str) -> Dict[str, float]:
    """Token + Native bakiyeyi birlikte çeker."""
    balances = {}
    url = f"{BASE_URL}/wallets/{address}/tokens"
    
    params = {
        "chain": chain,
        "exclude_spam": "true",
        "exclude_unverified_contracts": "true"
    }
    
    try:
        # ERC20 Tokenler
        response = requests.get(url, headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        tokens = data.get("result", []) if isinstance(data, dict) else data
        
        for token in tokens:
            symbol = token.get("symbol", "UNKNOWN")
            usd_value = token.get("usd_value")
            if usd_value and float(usd_value) > 0.1:
                balances[symbol] = balances.get(symbol, 0) + round(float(usd_value), 2)
        
        # Native Token (ETH, BNB vb.)
        native_url = f"{BASE_URL}/wallets/{address}/balance"
        native_resp = requests.get(native_url, headers=HEADERS, params={"chain": chain}, timeout=15)
        if native_resp.status_code == 200:
            native = native_resp.json()
            native_usd = native.get("usd_value") or 0
            if native_usd and float(native_usd) > 0.1:
                native_symbol = "ETH" if chain == "eth" else chain.upper()
                balances[native_symbol] = round(float(native_usd), 2)
    except Exception as e:
        st.error(f"Bakiye sorgusunda hata: {str(e)}")
    
    return balances


def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    """Wallet History endpoint ile daha kapsamlı işlem geçmişi çeker (Swap + Transfer)."""
    url = f"{BASE_URL}/wallets/{address}/history"
    params = {
        "chain": chain,
        "limit": 40,
        "order": "DESC"
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=25)
        response.raise_for_status()
        data = response.json().get("result", [])
        
        transfers = []
        for tx in data:
            if tx.get("possible_spam"):
                continue
            
            # İşlem tipi
            category = tx.get("category", "unknown").capitalize()
            is_inbound = tx.get("to_address", "").lower() == address.lower()
            
            # Token sembolü
            token_symbol = tx.get("token_symbol") or ("ETH" if chain == "eth" else chain.upper())
            
            # Miktar ve USD değeri
            amount = float(tx.get("value") or 0)
            usd_value = tx.get("usd_value")
            
            if amount <= 0 and tx.get("raw_value"):
                decimals = int(tx.get("token_decimals", 18))
                amount = int(tx.get("raw_value", 0)) / (10 ** decimals)
            
            transfers.append({
                "tx_hash": tx.get("transaction_hash"),
                "datetime": pd.to_datetime(tx.get("block_timestamp")).tz_convert(None),
                "type": f"{category} ({'↑ Inbound' if is_inbound else '↓ Outbound'})",
                "token_symbol": token_symbol,
                "amount": round(amount, 6),
                "usd_value": round(float(usd_value), 2) if usd_value else None
            })
        return transfers
    except Exception as e:
        st.warning(f"History endpoint hatası: {str(e)}. Eski yöntem deneniyor...")
        return fetch_wallet_transfers_fallback(address, chain)


def fetch_wallet_transfers_fallback(address: str, chain: str) -> List[Dict]:
    """Eski transfers endpoint (fallback)."""
    url = f"{BASE_URL}/wallets/{address}/transfers"
    params = {"chain": chain, "limit": 40}
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("result", [])
        
        transfers = []
        for tx in data:
            if tx.get("possible_spam"):
                continue
            is_inbound = tx.get("to_address", "").lower() == address.lower()
            decimals = int(tx.get("token_decimals", 18))
            amount = int(tx.get("value", 0)) / (10 ** decimals)
            
            if amount <= 0:
                continue
                
            transfers.append({
                "tx_hash": tx.get("transaction_hash"),
                "datetime": pd.to_datetime(tx.get("block_timestamp")).tz_convert(None),
                "type": "Giriş (Inbound)" if is_inbound else "Çıkış (Outbound)",
                "token_symbol": tx.get("token_symbol", "TOKEN"),
                "amount": round(amount, 6),
                "usd_value": None
            })
        return transfers
    except:
        return []


# =============================================================================
# ANALİZ MOTORU
# =============================================================================
def analyze_wallet_profile(transfers: List, balance: Dict, chain: str) -> Dict:
    total_balance = sum(balance.values())
    tx_count = len(transfers)
    chain_name = SUPPORTED_CHAINS.get(chain, chain.upper())
    
    if total_balance <= 0 and tx_count == 0:
        return {
            "summary": f"Bu cüzdanda **{chain_name}** ağında aktif varlık veya işlem bulunamadı.",
            "strategy_label": "Aktif Olmayan / Boş Cüzdan",
            "total_balance": 0,
            "df": pd.DataFrame(),
            "balance": balance
        }
    
    # Strateji
    if total_balance > 100000:
        strategy = "🐳 Balina / Büyük Yatırımcı"
    elif total_balance > 20000:
        strategy = "Büyük Yatırımcı"
    elif tx_count > 25:
        strategy = "🔄 Aktif Trader"
    elif tx_count > 8:
        strategy = "Orta Seviye Kullanıcı"
    elif total_balance > 0 and tx_count <= 5:
        strategy = "HODL Yatırımcısı"
    else:
        strategy = "Standart Cüzdan Kullanıcısı"
    
    summary = f"""
    Bu cüzdanın **{chain_name}** ağındaki doğrulanmış portföy değeri **${total_balance:,.2f}**'dir. 
    Son dönemde **{tx_count}** adet işlem tespit edildi.
    """
    
    return {
        "summary": summary.strip(),
        "strategy_label": strategy,
        "total_balance": total_balance,
        "df": pd.DataFrame(transfers),
        "balance": balance
    }


# =============================================================================
# STREAMLIT ARAYÜZÜ
# =============================================================================
def main():
    st.set_page_config(page_title="Cüzdan Analizörü", layout="wide", page_icon="🔍")
    st.title("🔍 Gerçek Zamanlı Cüzdan Analizörü")
    st.markdown("**Moralis Wallet History** ile swap + transfer işlemleri daha iyi tespit ediliyor.")

    with st.form("search_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            address = st.text_input("Cüzdan Adresi (0x...)", 
                                  placeholder="0x95480d3f27658E73b2785D30beb0c847D78294c7",
                                  help="SERV token alıp satan adresi test etmek için ideal")
        with col2:
            chain = st.selectbox("Blokzincir", 
                               options=list(SUPPORTED_CHAINS.keys()),
                               format_func=lambda x: f"{x.upper()} — {SUPPORTED_CHAINS[x]}")
        
        submitted = st.form_submit_button("🔎 Analiz Et", type="primary")

    if submitted and address:
        address = address.strip().lower()
        with st.spinner("Veriler çekiliyor... (Wallet History aktif)"):
            balance = fetch_wallet_balance(address, chain)
            transfers = fetch_wallet_transfers(address, chain)
            profile = analyze_wallet_profile(transfers, balance, chain)
        
        st.session_state.last_analysis = {
            "address": address,
            "chain": chain,
            "profile": profile
        }

    if "last_analysis" in st.session_state:
        profile = st.session_state.last_analysis["profile"]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Cüzdan Profili", profile["strategy_label"])
        c2.metric("Toplam Portföy Değeri", f"${profile['total_balance']:,.2f}")
        c3.metric("İşlem Sayısı", f"{len(profile['df'])} işlem")
        
        st.divider()
        st.subheader("📋 Özet")
        st.markdown(profile["summary"])
        
        # Portföy Grafiği
        st.subheader("🍰 Portföy Dağılımı")
        bal_df = pd.DataFrame({
            "Token": list(profile["balance"].keys()),
            "Değer (USD)": list(profile["balance"].values())
        })
        if not bal_df.empty and bal_df["Değer (USD)"].sum() > 0:
            fig = px.pie(bal_df, names="Token", values="Değer (USD)")
            st.plotly_chart(fig, use_container_width=True)
        
        # Transferler
        df = profile["df"]
        if not df.empty:
            st.subheader("📊 Son İşlemler")
            st.dataframe(df.sort_values("datetime", ascending=False), use_container_width=True, hide_index=True)
            
            col1, col2 = st.columns(2)
            with col1:
                fig2 = px.histogram(df, x="datetime", color="type", title="İşlem Zaman Dağılımı")
                st.plotly_chart(fig2, use_container_width=True)
            with col2:
                vol = df.groupby("token_symbol")["amount"].sum().reset_index()
                fig3 = px.bar(vol, x="token_symbol", y="amount", title="Token Bazlı Hacim")
                st.plotly_chart(fig3, use_container_width=True)

if __name__ == "__main__":
    main()
