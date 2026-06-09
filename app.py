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
# 2. %100 GERÇEK ZAMANLI API FONKSİYONLARI
# =============================================================================

def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    """Cüzdanın gerçek ERC20 token transfer geçmişini çeker."""
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
            
            # Moralis bazen usd_value'yi string veya None döndürür. 
            # Gerçek veri yoksa transferi listeye eklemiyoruz ki grafikler kirlenmesin.
            usd_val_raw = tx.get("usd_value")
            if usd_val_raw is not None and str(usd_val_raw).strip() != "":
                value_usd = round(float(usd_val_raw), 2)
            else:
                # Eğer USD değeri API'den gelmiyorsa analizin doğruluğu için bu tx'i atlıyoruz
                continue

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
    """Cüzandaki ERC20 token bakiyelerini ve canlı USD değerlerini çeker."""
    url = f"{BASE_URL}/{address}/erc20"
    params = {"chain": chain}
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code != 200:
            return {}
        
        data = response.json()
        balances = {}
        
        for token in data:
            symbol = token.get("symbol")
            usd_value = token.get("usd_value")
            
            # Sadece gerçek değere sahip tokenları ekle
            if usd_value and float(usd_value) > 0.01:
                balances[symbol] = round(float(usd_value), 2)
                
        return balances
    except Exception:
        return {}


def calculate_dynamic_metrics(transfers: List[Dict]) -> Dict[str, float]:
    """
    Sallama verileri yok etmek için transfer geçmişinden 
    matematiksel olarak gerçek hacim ve akış metrikleri üretir.
    """
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

    if df.empty:
        return {
            "summary":        "Bu cüzdanın seçilen ağda USD karşılığı olan güncel bir ERC20 transferi bulunamadı.",
            "traits":         [],
            "strategy_label": "Bilinmiyor / Pasif",
            "risk_label":     "Bilinmiyor",
            "df":             df,
            "balance":        balance,
            "metrics":        metrics,
        }

    swap_count = metrics["total_tx"]
    ts_range  = df["timestamp"].max() - df["timestamp"].min()
    day_range = max(ts_range / 86_400, 1)
    avg_tx_per_day = round(swap_count / day_range, 2)
    token_count = df["token_symbol"].nunique()

    mean_value = df["value_usd"].mean()
    std_value  = df["value_usd"].std() if len(df) > 1 else 0

    total_balance = sum(balance.values())
    share_top     = max(balance.values()) / total_balance if total_balance > 0 else 0

    # Tamamen dinamik strateji tespiti
    T = THRESHOLDS
    if swap_count > T["bot_freq"] and std_value > mean_value * 2:
        strategy_label = "Bot / MEV / Arbitraj"
    elif swap_count > T["high_freq"] and token_count > 5:
        strategy_label = "Aktif Kısa Vadeli Trader"
    elif total_balance > T["hodl_balance_usd"] and swap_count <= 10:
        strategy_label = "HODL / Balina Yatırımcı"
    else:
        strategy_label = "Bireysel / Düzenli Kullanıcı"

    if share_top > T["concentration"]:
        risk_label = "Yüksek Risk (Tek Varlık Yoğunluğu)"
    elif std_value > mean_value * T["volatility"]:
        risk_label = "Yüksek Risk (Yüksek Volatilite)"
    else:
        risk_label = "Düşük/Orta Risk (Dengeli)"

    parts = [
        f"Bu cüzdan on-chain cüzdan hareketlerine göre **{strategy_label}** profilindedir.",
        f"Son hareketlerinde toplam **{swap_count}** adet USD değerli transfer saptandı.",
        f"Cüzdana giren toplam hacim **${metrics['total_in_usd']:,.2f}**, çıkan toplam hacim ise **${metrics['total_out_usd']:,.2f}**.",
        f"Net cüzdan sermaye akışı: **${metrics['net_flow_usd']:,.2f}**."
    ]

    summary = " ".join(parts)

    traits = [
        f"Günlük Ortala İşlem: {avg_tx_per_day} tx",
        f"Etkileşimdeki Farklı Token: {token_count} adet",
        f"En Büyük Varlık Konsantrasyonu: %{share_top*100:.1f}",
        f"Risk Grubu: {risk_label}"
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

    st.title("🔍 %100 Canlı Kripto Cüzdan Analizörü")
    st.markdown(
        "Moralis API kullanarak **gerçek zamanlı** on-chain verileri listeler. USD karşılığı olmayan veya boş cüzdanlar filtrelenir."
    )

    with st.form("search_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            address = st.text_input(
                "Cüzdan Adresi (0x...)",
                placeholder="Örn: 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            )
        with col2:
            chain_options = [f"{code} ({name})" for code, name in SUPPORTED_CHAINS]
            chain_str     = st.selectbox("Blokzincir Ağ Seçimi", chain_options)
            chain         = chain_str.split(" (")[0]
        
        submit_button = st.form_submit_button("Canlı Verileri Sorgula", type="primary")

    if not address:
        st.info("Lütfen analiz etmek istediğiniz, içinde hareket olan bir EVM adresi girin.")
        return

    cache_key = f"{address.strip()}:{chain}"

    if submit_button or st.session_state.get("cache_key") == cache_key:
        if submit_button:
            with st.spinner("Blokzincir ağından veriler canlı olarak filtrelenerek çekiliyor..."):
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
        m3.metric("Toplam Canlı Varlık", f"${sum(profile['balance'].values()):,.2f}")
        m4.metric("Net Giriş/Çıkış Dengesi", f"${m['net_flow_usd']:,.2f}")

        st.divider()

        # --- Özet ---
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
                df,
                x="datetime",
                y="value_usd",
                color="type",
                hover_data=["token_symbol", "amount"],
                title="İşlem Hacimleri Grafiği (USD)",
                labels={"datetime": "Zaman", "value_usd": "Hacim (USD)"}
            )
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📊 En Çok Transfer Edilen Token Hacimleri")
            vol_df = (
                df.groupby("token_symbol")["value_usd"]
                .sum()
                .reset_index()
                .sort_values("value_usd", ascending=False)
                .head(10)
            )
            fig2 = px.bar(
                vol_df, 
                x="token_symbol", 
                y="value_usd", 
                title="Token Bazlı Kümülatif Transfer Dağılımı",
                labels={"token_symbol": "Token", "value_usd": "Hacim (USD)"}
            )
            st.plotly_chart(fig2, use_container_width=True)

        # --- Portföy Pasta Grafiği ---
        st.subheader("🍰 Güncel Portföy Varlık Dağılımı")
        bal_df = pd.DataFrame({
            "token":       list(profile["balance"].keys()),
            "balance_usd": list(profile["balance"].values()),
        })
        if not bal_df.empty and bal_df["balance_usd"].sum() > 0:
            fig3 = px.pie(bal_df, names="token", values="balance_usd", title="Tokenların Portföy Oranları")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Bu cüzdanda USD karşılığı bulunan güncel bir ERC20 tokenı tespit edilemedi.")


if __name__ == "__main__":
    main()
