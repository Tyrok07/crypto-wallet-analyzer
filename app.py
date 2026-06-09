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
    """Spam ve doğrulanmamış tokenleri hariç tutarak bakiye çeker."""
    balances = {}
    url = f"{BASE_URL}/wallets/{address}/tokens"
    
    params = {
        "chain": chain,
        "exclude_spam": "true",
        "exclude_unverified_contracts": "true"
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        tokens = data.get("result", []) if isinstance(data, dict) else data
        
        for token in tokens:
            symbol = token.get("symbol", "UNKNOWN")
            usd_value = token.get("usd_value")
            if usd_value and float(usd_value) > 0.1:
                balances[symbol] = balances.get(symbol, 0) + round(float(usd_value), 2)
    except Exception as e:
        st.error(f"Balance sorgusunda hata ({chain}): {str(e)}")
    
    return balances


def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    """Son transferleri çeker."""
    url = f"{BASE_URL}/wallets/{address}/transfers"
    params = {"chain": chain, "limit": 50}
    
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
            value_raw = int(tx.get("value", 0))
            amount = value_raw / (10 ** decimals)
            
            if amount <= 0:
                continue
                
            transfers.append({
                "tx_hash": tx.get("transaction_hash"),
                "datetime": pd.to_datetime(tx.get("block_timestamp")).tz_convert(None),
                "type": "Giriş (Inbound)" if is_inbound else "Çıkış (Outbound)",
                "token_symbol": tx.get("token_symbol", "TOKEN"),
                "amount": round(amount, 6)
            })
        return transfers
    except Exception:
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
            "summary": f"Bu cüzdanda **{chain_name}** ağında doğrulanmış piyasa değeri olan varlık veya transfer bulunamadı.",
            "strategy_label": "Aktif Olmayan / Boş Cüzdan",
            "total_balance": 0,
            "df": pd.DataFrame(),
            "balance": balance
        }
    
    # Strateji belirleme
    if total_balance > 100000:
        strategy = "🐳 Balina / Büyük Yatırımcı"
    elif total_balance > 20000:
        strategy = "Büyük Yatırımcı"
    elif tx_count > 30:
        strategy = "🔄 Aktif DeFi Trader"
    elif tx_count > 10:
        strategy = "Orta Seviye Kullanıcı"
    elif total_balance > 0 and tx_count <= 5:
        strategy = "HODL Yatırımcısı"
    else:
        strategy = "Standart Cüzdan Kullanıcısı"
    
    summary = f"""
    Bu cüzdanın **{chain_name}** ağındaki doğrulanmış portföy değeri **${total_balance:,.2f}**'dir. 
    Son dönemde **{tx_count}** adet onaylanmış transfer işlemi tespit edildi.
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
    st.set_page_config(
        page_title="Cüzdan Analizörü",
        layout="wide",
        page_icon="🔍"
    )
    
    st.title("🔍 Gerçek Zamanlı Cüzdan Analizörü")
    st.markdown("**Moralis API v2.2** ile spam temizlenmiş, gerçek portföy analizi")

    with st.form("search_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            address = st.text_input(
                "Cüzdan Adresi (0x...)", 
                placeholder="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                help="Ethereum, BSC, Polygon vb. adresleri destekler"
            )
        with col2:
            chain = st.selectbox(
                "Blokzincir Ağ", 
                options=list(SUPPORTED_CHAINS.keys()),
                format_func=lambda x: f"{x.upper()} — {SUPPORTED_CHAINS[x]}"
            )
        
        submitted = st.form_submit_button("🔎 Analiz Et", type="primary")

    if submitted and address:
        address = address.strip().lower()
        
        with st.spinner("Blokzincirden veriler çekiliyor... (Spam filtreleri aktif)"):
            balance = fetch_wallet_balance(address, chain)
            transfers = fetch_wallet_transfers(address, chain)
            profile = analyze_wallet_profile(transfers, balance, chain)
        
        # Son analizi kaydet
        st.session_state.last_analysis = {
            "address": address,
            "chain": chain,
            "profile": profile
        }

    # Önceki analizi göster
    if "last_analysis" in st.session_state:
        profile = st.session_state.last_analysis["profile"]
        chain = st.session_state.last_analysis["chain"]
        
        # Metrik Kartları
        c1, c2, c3 = st.columns(3)
        c1.metric("Cüzdan Profili", profile["strategy_label"])
        c2.metric("Toplam Portföy Değeri", f"${profile['total_balance']:,.2f}")
        c3.metric("Transfer Sayısı", f"{len(profile['df'])} işlem")
        
        st.divider()
        st.subheader("📋 Özet Rapor")
        st.markdown(profile["summary"])
        
        # Portföy Dağılımı
        st.subheader("🍰 Portföy Dağılımı")
        bal_df = pd.DataFrame({
            "Token": list(profile["balance"].keys()),
            "Değer (USD)": list(profile["balance"].values())
        })
        
        if not bal_df.empty and bal_df["Değer (USD)"].sum() > 0:
            fig1 = px.pie(bal_df, names="Token", values="Değer (USD)", 
                         title="Token Dağılımı")
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Bu cüzdanda piyasa değeri olan token bulunamadı.")
        
        # Transfer İşlemleri
        df = profile["df"]
        if not df.empty:
            st.subheader("📊 Son Transfer İşlemleri")
            st.dataframe(
                df.sort_values("datetime", ascending=False),
                use_container_width=True,
                hide_index=True
            )
            
            col1, col2 = st.columns(2)
            with col1:
                fig2 = px.histogram(
                    df, x="datetime", color="type",
                    title="Zaman İçinde İşlem Aktivitesi"
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            with col2:
                vol_df = df.groupby(["token_symbol", "type"])["amount"].sum().reset_index()
                fig3 = px.bar(
                    vol_df, x="token_symbol", y="amount", color="type",
                    title="Token Bazlı Transfer Hacmi"
                )
                st.plotly_chart(fig3, use_container_width=True)

if __name__ == "__main__":
    main()
