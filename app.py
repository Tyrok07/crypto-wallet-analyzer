import streamlit as st
import pandas as pd
import plotly.express as px
import hashlib
import random
from typing import Dict, List

# =============================================================================
# 1. CONFIG
# =============================================================================

SUPPORTED_CHAINS = [
    ("ethereum", "Ethereum"),
    ("bsc", "BSC"),
    ("polygon", "Polygon"),
    ("arbitrum", "Arbitrum"),
    ("optimism", "Optimism"),
    ("base", "Base"),
    ("avalanche", "Avalanche"),
    ("solana", "Solana"),
    ("tron", "Tron"),
    ("bitcoin", "Bitcoin"),
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

# =============================================================================
# 2. YARDIMCI: adrese göre deterministik seed
# =============================================================================

def _seed(address: str, chain: str) -> int:
    key = f"{address.lower().strip()}:{chain}"
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2 ** 32)


# =============================================================================
# 3. MOCK VERİ FONKSİYONLARI
# Her fonksiyon artık adres+chain'e göre farklı, tutarlı veri üretiyor.
# Gerçek kullanımda bu fonksiyonlar API çağrısıyla değiştirilecek.
# =============================================================================

def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    rng = random.Random(_seed(address, chain))

    dex_map = {
        "ethereum": ["Uniswap", "Curve", "Balancer"],
        "arbitrum": ["Uniswap", "Camelot", "GMX"],
        "base":     ["Uniswap", "Aerodrome"],
        "bsc":      ["PancakeSwap", "BiSwap"],
        "polygon":  ["QuickSwap", "Uniswap"],
        "optimism": ["Velodrome", "Uniswap"],
        "solana":   ["Jupiter", "Raydium"],
        "tron":     ["SunSwap"],
        "avalanche":["Trader Joe", "Pangolin"],
        "bitcoin":  [],
    }
    dexes = dex_map.get(chain, ["UnknownDEX"])

    token_pool = ["ETH", "USDT", "USDC", "WBTC", "PEPE", "SHIB", "ARB",
                  "OP", "MATIC", "SOL", "BNB", "TOKEN_A", "TOKEN_B", "MEME1", "MEME2"]

    tx_count = rng.randint(5, 120)
    base_ts  = 1_712_000_000
    span     = rng.randint(3, 60) * 86_400   # 3–60 günlük aktivite

    transfers = []
    ts_offsets = sorted(rng.randint(0, span) for _ in range(tx_count))

    for i, offset in enumerate(ts_offsets):
        tx_type = rng.choice(["swap_in", "swap_out", "transfer_in", "transfer_out"])
        token   = rng.choice(token_pool)
        amount  = round(rng.uniform(0.01, 500.0), 4)
        price   = round(rng.uniform(0.001, 5_000.0), 4)
        transfers.append({
            "tx_hash":       f"0x{hashlib.md5(f'{address}{i}'.encode()).hexdigest()}",
            "timestamp":     base_ts + offset,
            "type":          tx_type,
            "token_symbol":  token,
            "token_address": f"0x{hashlib.md5(token.encode()).hexdigest()[:40]}",
            "amount":        amount,
            "price_usd":     price,
            "value_usd":     round(amount * price, 2),
            "dex":           rng.choice(dexes) if dexes else "N/A",
        })

    return transfers


def fetch_wallet_balance(address: str, chain: str) -> Dict[str, float]:
    rng = random.Random(_seed(address, chain) + 1)
    tokens = ["ETH", "USDT", "USDC", "TOKEN_A", "TOKEN_B", "MEME1"]
    n = rng.randint(2, len(tokens))
    selected = rng.sample(tokens, n)
    return {t: round(rng.uniform(10.0, 50_000.0), 2) for t in selected}


def fetch_wallet_pnl(address: str, chain: str) -> Dict[str, float]:
    rng = random.Random(_seed(address, chain) + 2)
    realized    = round(rng.uniform(-20_000.0, 80_000.0), 2)
    unrealized  = round(rng.uniform(-10_000.0, 30_000.0), 2)
    win_rate    = round(rng.uniform(0.30, 0.85), 2)
    closed      = rng.randint(5, 200)
    return {
        "realized_pnl_usd":   realized,
        "unrealized_pnl_usd": unrealized,
        "win_rate":           win_rate,
        "closed_trades":      closed,
    }


# =============================================================================
# 4. ANALİZ FONKSİYONU
# =============================================================================

def analyze_wallet_profile(transfers, balance, pnl, chain: str) -> Dict:
    df = pd.DataFrame(transfers)

    if df.empty:
        return {
            "summary":        "Bu cüzdan için işlem verisi bulunamadı.",
            "traits":         [],
            "strategy_label": "Bilinmiyor",
            "risk_label":     "Bilinmiyor",
            "df":             df,
            "balance":        balance,
            "pnl":            pnl,
        }

    # --- Temel metrikler ---
    swap_count = len(df)

    ts_range  = df["timestamp"].max() - df["timestamp"].min()
    day_range = max(ts_range / 86_400, 1)
    avg_tx_per_day = round(swap_count / day_range, 2)

    token_count = df["token_symbol"].nunique()

    in_mask  = df["type"].isin(["transfer_in",  "swap_in"])
    out_mask = df["type"].isin(["transfer_out", "swap_out"])
    in_count  = int(in_mask.sum())
    out_count = int(out_mask.sum())

    mean_value = df["value_usd"].mean()
    max_value  = df["value_usd"].max()
    std_value  = df["value_usd"].std()

    dex_counts = df["dex"].value_counts().to_dict()

    # --- PnL ---
    realized    = pnl.get("realized_pnl_usd",   0)
    unrealized  = pnl.get("unrealized_pnl_usd",  0)
    win_rate    = pnl.get("win_rate",             0)
    closed      = pnl.get("closed_trades",        0)

    # --- Balance ---
    total_balance = sum(balance.values())
    share_top     = max(balance.values()) / total_balance if total_balance > 0 else 0

    # --- Strateji etiketi ---
    T = THRESHOLDS
    if swap_count > T["bot_freq"] and std_value > mean_value * 2:
        strategy_label = "Bot / MEV / Arbitraj"
    elif swap_count > T["high_freq"] and win_rate > T["win_high"] and token_count > 5:
        strategy_label = "Meme / Early-Gainer Trader"
    elif swap_count > T["mid_freq"] and realized > 0 and win_rate > T["win_mid"]:
        strategy_label = "Swing Trader"
    elif swap_count <= 10 and total_balance > T["hodl_balance_usd"]:
        strategy_label = "HODL / Long-Term"
    else:
        strategy_label = "Karışık / Belirsiz"

    # --- Risk etiketi ---
    if share_top > T["concentration"]:
        risk_label = "Yüksek Risk (Tek Token Bağımlı)"
    elif std_value > mean_value * T["volatility"]:
        risk_label = "Yüksek Risk (Volatil Pozisyonlar)"
    elif win_rate > T["win_high"] and realized > 0:
        risk_label = "Orta Risk (Dengeli)"
    else:
        risk_label = "Düşük Risk (Konservatif)"

    # --- Özet metin ---
    parts = [
        f"Bu cüzdan **{strategy_label}** tipli bir trader.",
        f"Toplam **{swap_count}** işlem var; ortalama günde **{avg_tx_per_day:.1f}** işlem"
        f" ({int(day_range)} günlük pencere).",
        f"**{token_count}** farklı token ile işlem yapıyor.",
    ]

    if win_rate >= T["win_high"]:
        parts.append(f"Win rate **%{win_rate*100:.1f}** yüksek; realized PnL **${realized:,.0f}**.")
    elif win_rate >= T["win_mid"]:
        parts.append(f"Win rate **%{win_rate*100:.1f}** orta; realized PnL **${realized:,.0f}**.")
    else:
        parts.append(f"Win rate **%{win_rate*100:.1f}** düşük; realized PnL **${realized:,.0f}**.")

    parts.append(
        f"Balance içinde en büyük token payı **%{share_top*100:.1f}**."
    )
    parts.append(
        "DEX kullanımı: " + ", ".join(f"{d} ({c} tx)" for d, c in dex_counts.items())
    )

    # Token bazlı net akış
    in_by_token  = df[in_mask].groupby("token_symbol")["value_usd"].sum()
    out_by_token = df[out_mask].groupby("token_symbol")["value_usd"].sum()
    examples = []
    for token in list(in_by_token.index)[:3]:
        in_v  = in_by_token[token]
        out_v = out_by_token.get(token, 0)
        net   = in_v - out_v
        direction = "net alımlı" if net >= 0 else "net satımlı"
        examples.append(f"**{token}** {direction} (alım ${in_v:,.0f} / satım ${out_v:,.0f})")
    if examples:
        parts.append("Token eğilimleri: " + ", ".join(examples))

    summary = " ".join(parts)

    traits = [
        f"Swap sıklığı: {'yüksek' if swap_count > T['high_freq'] else 'orta' if swap_count > T['mid_freq'] else 'düşük'}",
        f"Günlük ort. işlem: {avg_tx_per_day:.1f}",
        f"Win rate: %{win_rate*100:.1f}",
        f"Realized PnL: ${realized:,.0f}",
        f"Unrealized PnL: ${unrealized:,.0f}",
        f"Token çeşitliliği: {token_count}",
        f"Tek token bağımlılığı: %{share_top*100:.1f}",
        f"Risk profili: {risk_label}",
    ]

    return {
        "summary":        summary,
        "traits":         traits,
        "strategy_label": strategy_label,
        "risk_label":     risk_label,
        "df":             df,
        "balance":        balance,
        "pnl":            pnl,
    }


# =============================================================================
# 5. STREAMLIT UI
# =============================================================================

def main():
    st.set_page_config(page_title="Kripto Cüzdan Analiz", page_icon="🔍", layout="wide")

    st.title("Kripto Cüzdan Analiz")
    st.markdown(
        "Public cüzdan adresini girerek işlem tarzı, strateji tipi, risk profili ve PnL özetini görüntüle.\n\n"
        "Desteklenen ağlar: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Avalanche, Solana, Tron, Bitcoin."
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        address = st.text_input(
            "Cüzdan Adresi (public)",
            placeholder="0x... veya Solana adresi",
        )
    with col2:
        chain_options = [f"{code} ({name})" for code, name in SUPPORTED_CHAINS]
        chain_str     = st.selectbox("Ağ", chain_options)
        chain         = chain_str.split(" (")[0]

    if not address:
        st.info("Lütfen bir cüzdan adresi girin.")
        return

    # Session state: aynı adres+chain için tekrar çekme
    cache_key = f"{address.strip()}:{chain}"
    if st.button("Analiz Başlat") or st.session_state.get("cache_key") != cache_key:
        with st.spinner("Veri çekiliyor..."):
            transfers = fetch_wallet_transfers(address, chain)
            balance   = fetch_wallet_balance(address, chain)
            pnl_data  = fetch_wallet_pnl(address, chain)
            profile   = analyze_wallet_profile(transfers, balance, pnl_data, chain)

        st.session_state["cache_key"] = cache_key
        st.session_state["profile"]   = profile

    profile = st.session_state.get("profile")
    if not profile:
        return

    # --- Üst metrik kartları ---
    p = profile["pnl"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Strateji",         profile["strategy_label"])
    m2.metric("Risk Profili",     profile["risk_label"])
    m3.metric("Realized PnL",     f"${p.get('realized_pnl_usd', 0):,.0f}")
    m4.metric("Win Rate",         f"%{p.get('win_rate', 0)*100:.1f}")

    st.divider()

    # --- Özet ve özellikler ---
    st.subheader("Cüzdan Profil Özeti")
    st.markdown(profile["summary"])

    with st.expander("Tüm özellikler"):
        for t in profile["traits"]:
            st.markdown(f"- {t}")

    df = profile["df"]

    if not df.empty:
        st.subheader("Swap İşlemleri Zaman Serisi")
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
        fig = px.scatter(
            df,
            x="datetime",
            y="value_usd",
            color="type",
            hover_data=["token_symbol", "amount", "dex"],
            title="İşlem Değerleri (USD)",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Token Dağılımı — İşlem Hacmi")
        vol_df = (
            df.groupby("token_symbol")["value_usd"]
            .sum()
            .reset_index()
            .sort_values("value_usd", ascending=False)
            .head(10)
        )
        fig2 = px.bar(vol_df, x="token_symbol", y="value_usd", title="Token Bazlı Hacim (USD)")
        st.plotly_chart(fig2, use_container_width=True)

    # --- Balance ---
    st.subheader("Token Bakiye Dağılımı")
    bal_df = pd.DataFrame({
        "token":       list(profile["balance"].keys()),
        "balance_usd": list(profile["balance"].values()),
    })
    if not bal_df.empty:
        fig3 = px.pie(bal_df, names="token", values="balance_usd", title="Bakiye Dağılımı")
        st.plotly_chart(fig3, use_container_width=True)

    # --- PnL detay ---
    st.subheader("PnL ve İşlem İstatistikleri")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Realized PnL",    f"${p.get('realized_pnl_usd',   0):,.0f}")
    c2.metric("Unrealized PnL",  f"${p.get('unrealized_pnl_usd', 0):,.0f}")
    c3.metric("Win Rate",        f"%{p.get('win_rate', 0)*100:.1f}")
    c4.metric("Kapanış İşlemi",  p.get("closed_trades", 0))


if __name__ == "__main__":
    main()
