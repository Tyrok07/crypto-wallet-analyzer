import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from typing import Dict, List

# =============================================================================
# 1. CONFIG & API KURULUMU
# =============================================================================

SUPPORTED_CHAINS = [
    ("eth", "Ethereum"),
    ("bsc", "BSC"),
    ("polygon", "Polygon"),
    ("arbitrum", "Arbitrum"),
    ("optimism", "Optimism"),
    ("base", "Base"),
    ("avalanche", "Avalanche"),
]

try:
    MORALIS_API_KEY = st.secrets["MORALIS_API_KEY"]
except KeyError:
    st.error("HATA: Streamlit Secrets alanında 'MORALIS_API_KEY' bulunamadı.")
    st.stop()

BASE_URL = "https://deep-index.moralis.io/api/v2.2"
HEADERS = {
    "Accept": "application/json",
    "X-API-Key": MORALIS_API_KEY
}

# =============================================================================
# 2. DOĞRULANMIŞ CANLI API FONKSİYONLARI
# =============================================================================

def fetch_wallet_balance(address: str, chain: str) -> Dict[str, float]:
    """Cüzandaki doğrulanmış, spam olmayan ve gerçek USD değerli varlıkları çeker."""
    balances = {}
    url = f"{BASE_URL}/wallets/{address}/tokens"
    # exclude_spam ve exclude_unverified_contracts ile sahte airdropları kökten eliyoruz!
    params = {
        "chain": chain, 
        "exclude_spam": "true",
        "exclude_unverified_contracts": "true"
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 200:
            tokens = response.json()
            if isinstance(tokens, dict):
                tokens = tokens.get("result", [])
                
            for token in tokens:
                symbol = token.get("symbol", "UNKNOWN")
                usd_value = token.get("usd_value")
                
                # Sadece piyasada karşılığı olan (0.1 dolardan büyük) gerçek varlıklar
                if usd_value and float(usd_value) > 0.1:
                    balances[symbol] = balances.get(symbol, 0) + round(float(usd_value), 2)
    except Exception:
        pass
                
    return balances


def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    """Cüzdanın transfer geçmişini çeker. Ücretsiz planda USD fiyatı gelmediği için adet bazlı çalışır."""
    url = f"{BASE_URL}/wallets/{address}/transfers"
    params = {"chain": chain, "limit": 40}
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code != 200:
            return []
        
        data = response.json().get("result", [])
        transfers = []
        
        for tx in data:
            if tx.get("possible_spam") == True:
                continue # Şüpheli spam transferlerini filtrele
                
            is_inbound = tx.get("to_address", "").lower() == address.lower()
            tx_type = "Giriş (Inbound)" if is_inbound else "Çıkış (Outbound)"
            
            decimals = int(tx.get("token_decimals", 18))
            value_raw = int(tx.get("value", 0))
            amount = value_raw / (10 ** decimals)
            
            if amount <= 0:
                continue

            transfers.append({
                "tx_hash": tx.get("transaction_hash"),
                "datetime": pd.to_datetime(tx.get("block_timestamp")),
                "type": tx_type,
                "token_symbol": tx.get("token_symbol", "TOKEN"),
                "amount": amount
            })
        return transfers
    except Exception:
        return []

# =============================================================================
# 3. ANALİZ MOTORU (SADECE GERÇEKLER)
# =============================================================================

def analyze_wallet_profile(transfers, balance) -> Dict:
    df = pd.DataFrame(transfers)
    total_balance = sum(balance.values())
    tx_count = len(transfers)

    if total_balance <= 0 and tx_count == 0:
        return {
            "summary": "Bu cüzdanın seçilen ağda doğrulanmış herhangi bir piyasa varlığı veya güncel transfer aktivitesi bulunamadı.",
            "strategy_label": "Aktif Olmayan / Boş Cüzdan",
            "df": df,
            "balance": balance
        }

    # Gerçekçi Strateji Etiketlemesi
    if total_balance > 50000:
        strategy_label = "Balina / Büyük Yatırımcı"
    elif tx_count > 25:
        strategy_label = "Sık İşlem Yapan DeFi Kullanıcısı"
    elif total_balance > 0 and tx_count == 0:
        strategy_label = "Pasif HODL Yatırımcısı"
    else:
        strategy_label = "Standart Cüzdan"

    summary = f"Bu cüzdanın on-chain kayıtlarında doğrulanmış **${total_balance:,.2f}** değerinde portföyü bulunmaktadır. Son dönemde **{tx_count}** adet onaylanmış transfer işlemi gerçekleştirmiştir."

    return {
        "summary": summary,
        "strategy_label": strategy_label,
        "df": df,
        "balance": balance
    }

# =============================================================================
# 4. STREAMLIT ARAYÜZÜ
# =============================================================================

def main():
    st.set_page_config(page_title="Gerçek Zamanlı Cüzdan Analizörü", layout="wide")

    st.title("🔍 Canlı Kripto Cüzdan Analizörü")
    st.markdown("Moralis API v2.2 filtreleriyle **sahte varlıklar ve reklam tokenları tamamen temizlenmiş** gerçek portföy verileri.")

    with st.form("search_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            address = st.text_input("Cüzdan Adresi (0x...)", placeholder="Örn: 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
        with col2:
            chain_options = [f"{code} ({name})" for code, name in SUPPORTED_CHAINS]
            chain_str     = st.selectbox("Blokzincir Ağ Seçimi", chain_options)
            chain         = chain_str.split(" (")[0]
        submit_button = st.form_submit_button("Canlı Verileri Sorgula", type="primary")

    if not address:
        st.info("Lütfen analiz etmek istediğiniz geçerli bir cüzdan adresi girin.")
        return

    cache_key = f"{address.strip()}:{chain}"

    if submit_button or st.session_state.get("cache_key") == cache_key:
        if submit_button:
            with st.spinner("Blokzincirden spamlar ayıklanarak veriler çekiliyor..."):
                balance   = fetch_wallet_balance(address.strip(), chain)
                transfers = fetch_wallet_transfers(address.strip(), chain)
                profile   = analyze_wallet_profile(transfers, balance)

            st.session_state["cache_key"] = cache_key
            st.session_state["profile"]   = profile
        else:
            profile = st.session_state.get("profile")

        if not profile:
            return

        # Metrik Kartları
        m1, m2, m3 = st.columns(3)
        m1.metric("Cüzdan Profili", profile["strategy_label"])
        m2.metric("Toplam Doğrulanmış Varlık (USD)", f"${sum(profile['balance'].values()):,.2f}")
        m3.metric("Son Transfer Sayısı", f"{len(profile['df'])} İşlem")

        st.divider()
        st.subheader("📋 Portföy Durum Özeti")
        st.markdown(profile["summary"])

        # Grafik 1: Portföy Dağılımı
        st.subheader("🍰 Doğrulanmış Varlık Dağılımı (Portföy)")
        bal_df = pd.DataFrame({"Token": list(profile["balance"].keys()), "Değer (USD)": list(profile["balance"].values())})
        if not bal_df.empty and bal_df["Değer (USD)"].sum() > 0:
            fig1 = px.pie(bal_df, names="Token", values="Değer (USD)", title="Cüzdandaki Gerçek Paranın Dağılımı")
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Bu cüzdanda piyasa değeri olan bir ERC20 veya Native bakiye bulunamadı.")

        # Grafik 2: Transfer Aktivitesi
        df = profile["df"]
        if not df.empty:
            st.subheader("📊 Son Dönem Transfer İşlemleri Aktivitesi (Adet Bazlı)")
            fig2 = px.histogram(
                df, x="datetime", color="type", 
                title="Zaman İçindeki İşlem Sıklığı",
                labels={"datetime": "Tarih", "count": "İşlem Adedi"}
            )
            st.plotly_chart(fig2, use_container_width=True)

            st.subheader("🔄 En Çok İşlem Gören Tokenlar (Miktar Bazlı)")
            vol_df = df.groupby(["token_symbol", "type"])["amount"].sum().reset_index()
            fig3 = px.bar(
                vol_df, x="token_symbol", y="amount", color="type", barmode="group",
                title="Token Bazlı Transfer Miktarları (Adet)",
                labels={"token_symbol": "Token", "amount": "Miktar (Adet)"}
            )
            st.plotly_chart(fig3, use_container_width=True)


if __name__ == "__main__":
    main()
