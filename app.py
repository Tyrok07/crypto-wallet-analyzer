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

THRESHOLDS = {
    "high_freq":        50,
    "mid_freq":         20,
    "hodl_balance_usd": 50_000,
    "bot_freq":         100,
    "win_high":         0.60,
    "win_mid":          0.50,
    "concentration":    0.70,
    "volatility":       1.50,
}

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
# 2. %100 GERÇEK VE FİLTRELENMİŞ API FONKSİYONLARI
# =============================================================================

def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    """Cüzdanın ERC20 transfer geçmişini çeker, sahte/fiyatsız tokenları eler."""
    url = f"{BASE_URL}/{address}/erc20/transfers"
    params = {"chain": chain, "limit": 100}
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code != 200:
            return []
        
        data = response.json().get("result", [])
        transfers = []
        
        for tx in data:
            is_inbound = tx.get("to_address", "").lower() == address.lower()
            tx_type = "transfer_in" if is_inbound else "transfer_out"
            
            decimals = int(tx.get("token_decimals", 18))
            value_raw = int(tx.get("value", 0))
            amount = value_raw / (10 ** decimals)
            
            if amount <= 0:
                continue

            # KESİN FİLTRE: Eğer Moralis bu transfere gerçek bir USD değeri atamadıysa,
            # bu muhtemelen değersiz/sahte bir tokendir. Analize dahil etmiyoruz!
            usd_val_raw = tx.get("usd_value")
            if usd_val_raw is not None and str(usd_val_raw).strip() != "":
                value_usd = round(float(usd_val_raw), 2)
            else:
                continue  # Tahmini fiyatlama kaldırıldı, fiyatsızsa pas geç.

            transfers.append({
                "tx_hash": tx.get("transaction_hash"),
                "timestamp": int(pd.to_datetime(tx.get("block_timestamp")).timestamp()),
                "type": tx_type,
                "token_symbol": tx.get("token_symbol", "UNKNOWN"),
                "token_address": tx.get("address"),
                "amount": amount,
                "price_usd": value_usd / amount if amount > 0 else 0,
                "value_usd": value_usd,
                "dex": "On-Chain Transfer"
            })
        return transfers
    except Exception:
        return []


def fetch_wallet_balance(address: str, chain: str) -> Dict[str, float]:
    """Cüzandaki sadece GERÇEK USD DEĞERİ olan ERC20 ve Native (Ana) varlıkları çeker."""
    balances = {}
    
    # 1. ADIM: Native Bakiye Çekimi (ETH, BNB vb.)
    try:
        native_url = f"{BASE_URL}/{address}/balance"
        native_res = requests.get(native_url, headers=HEADERS, params={"chain": chain})
        if native_res.status_code == 200:
            n_data = native_res.json()
            # Bazı Moralis sürümlerinde native bakiyenin de usd değeri doğrudan gelir
            n_usd = n_data.get("usd_value")
            if n_usd and float(n_usd) > 0.5:
                # Ağın ana coini (ETH, BNB vb.) ismiyle ekleyelim
                chain_main_tokens = {"eth": "ETH", "bsc": "BNB", "polygon": "POL/MATIC", "arbitrum": "ETH (Arb)", "optimism": "ETH (Op)", "base": "ETH (Base)"}
                symbol = chain_main_tokens.get(chain, "NATIVE")
                balances[symbol] = round(float(n_usd), 2)
    except Exception:
        pass

    # 2. ADIM: ERC20 Token Bakiyeleri
    try:
        url = f"{BASE_URL}/{address}/erc20"
        response = requests.get(url, headers=HEADERS, params={"chain": chain})
        if response.status_code == 200:
            data = response.json()
            for token in data:
                symbol = token.get("symbol", "UNKNOWN")
                usd_value = token.get("usd_value")
                
                # KESİN FİLTRE: Sadece Moralis tarafından doğrulanmış gerçek USD değeri olan tokenlar
                if usd_value and float(usd_value) > 0.5:
                    # Aynı sembolden varsa (örn hem native hem erc20) üst üste binmesin
                    balances[symbol] = balances.get(symbol, 0) + round(float(usd_value), 2)
    except Exception:
        pass
                
    return balances


def calculate_dynamic_metrics(transfers: List[Dict]) -> Dict[str, float]:
    """Gerçek transfer geçmişinden cüzdan hacmini hesaplar."""
    if not transfers:
        return {"total_in_usd": 0, "total_out_usd": 0, "net_flow_usd": 0, "total_tx": 0}
        
    total_in = sum(tx["value_usd"] for tx in transfers if tx["type"] == "transfer_in")
    total_out = sum(tx["value_usd"] for tx in transfers if tx["type"] == "transfer_out")
    
    return {
        "total_in_usd": round(total_in, 2),
        "total_out_usd": round(total_out, 2),
        "net_flow_usd": round(total_in - total_out, 2),
        "total_tx": len(transfers)
    }

# =============================================================================
# 3. ANALİZ MOTORU
# =============================================================================

def analyze_wallet_profile(transfers, balance, metrics, chain: str) -> Dict:
    df = pd.DataFrame(transfers)
    total_balance = sum(balance.values())

    if df.empty and total_balance <= 0:
        return {
            "summary":        "Bu cüzdanın seçilen ağda doğrulanmış, piyasa değeri olan aktif bir varlığı veya transferi bulunamadı.",
            "traits":         [],
            "strategy_label": "Pasif / İzleyici Cüzdan",
            "risk_label":     "Düşük Risk (Hareketsiz)",
            "df":             df,
            "balance":        balance,
            "metrics":        metrics,
        }

    swap_count = metrics["total_tx"]
    token_count = df["token_symbol"].nunique() if not df.empty else 0
    share_top     = max(balance.values()) / total_balance if total_balance > 0 else 0

    # Strateji tespiti
    if total_balance > THRESHOLDS["hodl_balance_usd"] and swap_count <= 5:
        strategy_label = "HODL / Balina Yatırımcı"
    elif swap_count > THRESHOLDS["high_freq"]:
        strategy_label = "Aktif Kısa Vadeli Trader"
    elif swap_count > 0:
        strategy_label = "Standart DeFi Kullanıcısı"
    else:
        strategy_label = "Sadece HODL (İşlemsiz)"

    risk_label = "Yüksek Risk (Yoğunlaşma)" if share_top > THRESHOLDS["concentration"] else "Düşük/Orta Risk (Dengeli)"

    parts = [
        f"Bu cüzdan on-chain hareketlerine göre **{strategy_label}** profilindedir.",
        f"Cüzdanda şu an doğrulanmış toplam **${total_balance:,.2f}** değerinde varlık bulunuyor.",
        f"İncelenen son dönemde piyasa değeri net olan **{swap_count}** adet transfer işlemi tespit edildi."
    ]

    summary = " ".join(parts)
    traits = [
        f"Toplam Gerçek Hacim Verisi: {swap_count} tx",
        f"Farklı Gerçek Token Etkileşimi: {token_count} adet",
        f"En Büyük Varlık Oranı: %{share_top*100:.1f}",
        f"Güncel Risk Durumu: {risk_label}"
    ]

    return {
        "summary":        summary,
        "traits":         traits,
        "strategy_label": strategy_label,
        "risk_label":     risk_label,
        "df":             df,
        "balance":        balance,
        "metrics":        metrics,
    }

# =============================================================================
# 4. STREAMLIT UI (ARAYÜZ)
# =============================================================================

def main():
    st.set_page_config(page_title="Canlı Kripto Cüzdan Analizi", page_icon="🔍", layout="wide")

    st.title("🔍 Canlı Kripto Cüzdan Analizörü")
    st.markdown(
        "Moralis API ile **%100 Gerçek ve Doğrulanmış** veriler listelenir. Fiyatı olmayan spam/airdrop tokenlar otomatik elenir."
    )

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
        st.info("Analiz için geçerli bir cüzdan adresi girin.")
        return

    cache_key = f"{address.strip()}:{chain}"

    if submit_button or st.session_state.get("cache_key") == cache_key:
        if submit_button:
            with st.spinner("Blokzincir ağından sadece gerçek piyasa verileri süzülüyor..."):
                transfers = fetch_wallet_transfers(address.strip(), chain)
                balance   = fetch_wallet_balance(address.strip(), chain)
                metrics   = calculate_dynamic_metrics(transfers)
                profile   = analyze_wallet_profile(transfers, balance, metrics, chain)

            st.session_state["cache_key"] = cache_key
            st.session_state["profile"]   = profile
        else:
            profile = st.session_state.get("profile")

        if not profile:
            return

        # --- Üst metrik kartları ---
        m = profile["metrics"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Hesaplanan Strateji", profile["strategy_label"])
        m2.metric("Risk Durumu",         profile["risk_label"])
        m3.metric("Toplam Gerçek Varlık", f"${sum(profile['balance'].values()):,.2f}")
        m4.metric("Net Giriş/Çıkış Dengesi", f"${m['net_flow_usd']:,.2f}")

        st.divider()

        st.subheader("📋 Canlı Hesaplama Özeti")
        st.markdown(profile["summary"])

        with st.expander("Gelişmiş Metrik Verileri"):
            for t in profile["traits"]:
                st.markdown(f"- {t}")

        df = profile["df"]

        if not df.empty:
            st.subheader("📈 Gerçek Transfer İşlemleri Zaman Serisi")
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
            fig = px.scatter(
                df, x="datetime", y="value_usd", color="type",
                hover_data=["token_symbol", "amount"], title="İşlem Hacimleri Grafiği (USD)"
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📊 En Çok Transfer Edilen Token Hacimleri")
            vol_df = df.groupby("token_symbol")["value_usd"].sum().reset_index().sort_values("value_usd", ascending=False).head(10)
            fig2 = px.bar(vol_df, x="token_symbol", y="value_usd", title="Token Bazlı Kümülatif Transfer Dağılımı")
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("🍰 Güncel Portföy Varlık Dağılımı")
        bal_df = pd.DataFrame({"token": list(profile["balance"].keys()), "balance_usd": list(profile["balance"].values())})
        if not bal_df.empty and bal_df["balance_usd"].sum() > 0:
            fig3 = px.pie(bal_df, names="token", values="balance_usd", title="Tokenların Portföy Oranları")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Bu cüzdanda piyasa değeri saptanabilen bir varlık bulunamadı.")

if __name__ == "__main__":
    main()
