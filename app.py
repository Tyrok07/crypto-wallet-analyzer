import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict, List
import json

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

# =============================================================================
# 2. MOCK VERİ FONKSİYONLARI
# Gerçek kullanımda buraya API çağrıları gelecek.
# =============================================================================

def fetch_wallet_transfers(address: str, chain: str) -> List[Dict]:
    mock = []
    tokens = ["ETH", "USDT", "TOKEN1", "TOKEN2", "MEME1", "MEME2", "SOL", "BNB"]
    for i in range(30):
        t = {
            "tx_hash": f"tx_{i}",
            "timestamp": 1712000000 + i * 3600,
            "type": "swap_in" if i % 2 == 0 else "swap_out",
            "token_symbol": tokens[i % len(tokens)],
            "token_address": "0xmock",
            "amount": 1.0 + i * 0.1,
            "price_usd": 100.0 + i * 10.0,
            "value_usd": (1.0 + i * 0.1) * (100.0 + i * 10.0),
            "dex": "Uniswap" if chain in ["ethereum", "arbitrum", "base"] else "PancakeSwap",
        }
        mock.append(t)
    return mock


def fetch_wallet_balance(address: str, chain: str) -> Dict[str, float]:
    return {
        "ETH": 5.0,
        "USDT": 10000.0,
        "TOKEN1": 2000.0,
        "TOKEN2": 1500.0,
        "MEME1": 50000.0,
    }


def fetch_wallet_pnl(address: str, chain: str) -> Dict[str, float]:
    return {
        "realized_pnl_usd": 15000.0,
        "unrealized_pnl_usd": 5000.0,
        "win_rate": 0.68,
        "closed_trades": 85,
    }


# =============================================================================
# 3. ANALİZ FONKSİYONU (AKIL YÜRÜTME)
# =============================================================================

def analyze_wallet_profile(transfers, balance, pnl, chain: str):
    df = pd.DataFrame(transfers)

    if df.empty:
        return {
            "summary": "Bu cüzdan için işlem verisi bulunamadı.",
            "traits": [],
            "strategy_label": "Bilinmiyor",
            "risk_label": "Bilinmiyor",
            "df": df,
            "balance": balance,
            "pnl": pnl,
        }

    swap_count = len(df)
    avg_tx_per_day = swap_count / 5.0

    token_symbols = df["token_symbol"].unique()
    token_count = len(token_symbols)

    in_mask = df["type"].isin(["transfer_in", "swap_in"])
    out_mask = df["type"].isin(["transfer_out", "swap_out"])
    in_count = in_mask.sum()
    out_count = out_mask.sum()

    mean_value = df["value_usd"].mean()
    max_value = df["value_usd"].max()
    std_value = df["value_usd"].std()

    dex_counts = df["dex"].value_counts().to_dict()

    realized_pnl = pnl.get("realized_pnl_usd", 0)
    unrealized_pnl = pnl.get("unrealized_pnl_usd", 0)
    win_rate = pnl.get("win_rate", 0)
    closed_trades = pnl.get("closed_trades", 0)

    total_balance = sum(balance.values())
    share_top = max(balance.values()) / total_balance if total_balance > 0 else 0

    # Strateji label
    if swap_count > 50 and win_rate > 0.6 and token_count > 5:
        strategy_label = "Meme / Early-Gainer Trader"
    elif swap_count > 20 and realized_pnl > 0 and win_rate > 0.55:
        strategy_label = "Swing Trader"
    elif swap_count <= 10 and total_balance > 50000:
        strategy_label = "HODL / Long-Term"
    elif swap_count > 100 and std_value > mean_value * 2:
        strategy_label = "Bot / MEV / Arbitraj"
    else:
        strategy_label = "Karışık / Belirsiz"

    # Risk label
    if share_top > 0.7:
        risk_label = "Yüksek Risk (Tek Token Bağımlı)"
    elif std_value > mean_value * 1.5:
        risk_label = "Yüksek Risk (Volatil Pozisyonlar)"
    elif win_rate > 0.65 and realized_pnl > 0:
        risk_label = "Orta Risk (Dengeli)"
    else:
        risk_label = "Düşük Risk (Konservatif)"

    summary_parts = []
    summary_parts.append(f"Bu cüzdan **{strategy_label}** tipli bir trader.")
    summary_parts.append(
        f"Toplam **{swap_count}** swap işlemi var, ortalama günde **{avg_tx_per_day:.1f}** işlem."
    )
    summary_parts.append(
        f"{token_count} farklı token ile işlem yapıyor, diversifikasyon **orta-yüksek**."
    )

    if win_rate > 0.6:
        summary_parts.append(f"Win rate **%{win_rate*100:.1f}** ile yüksek, realised PnL **${realized_pnl:.0f}** pozitif.")
    elif win_rate > 0.5:
        summary_parts.append(f"Win rate **%{win_rate*100:.1f}** ile orta-yüksek, realised PnL **${realized_pnl:.0f}**.")
    else:
        summary_parts.append(f"Win rate **%{win_rate*100:.1f}** ile düşük-orta, realised PnL **${realized_pnl:.0f}**.")

    summary_parts.append(
        f"Balance dağılımında en büyük token payı **%{share_top*100:.1f}**, tek token'a aşırı bağımlı değil."
    )

    summary_parts.append(
        "DEX kullanımı: " + ", ".join(f"{dex} ({cnt} tx)" for dex, cnt in dex_counts.items())
    )

    in_by_token = df[in_mask].groupby("token_symbol")["value_usd"].sum()
    out_by_token = df[out_mask].groupby("token_symbol")["value_usd"].sum()

    examples = []
    for token in in_by_token.index[:3]:
        in_val = in_by_token[token]
        out_val = out_by_token.get(token, 0)
        if out_val > 0:
            net = in_val - out_val
            if net > 0:
                examples.append(f"**{token}**'da net alımlı (toplam alım ${in_val:.0f}, satım ${out_val:.0f})")
            else:
                examples.append(f"**{token}**'da net satımlı (toplam alım ${in_val:.0f}, satım ${out_val:.0f})")
        else:
            examples.append(f"**{token}**'da sadece alım (toplam ${in_val:.0f})")

    if examples:
        summary_parts.append("Token bazında örnek eğilimler: " + ", ".join(examples[:3]))

    summary = " ".join(summary_parts)

    traits = [
        f"Swap sıklığı: {'yüksek' if swap_count > 30 else 'orta' if swap_count > 10 else 'düşük'}",
        f"Win rate: %{win_rate*100:.1f}",
        f"Realized PnL: ${realized_pnl:.0f}",
        f"Token çeşitliliği: {token_count}",
        f"Tek token bağımlılığı: %{share_top*100:.1f}",
        f"Risk profili: {risk_label}",
    ]

    return {
        "summary": summary,
        "traits": traits,
        "strategy_label": strategy_label,
        "risk_label": risk_label,
        "df": df,
        "balance": balance,
        "pnl": pnl,
    }


# =============================================================================
# 4. STREAMLIT UI
# =============================================================================

def main():
    st.set_page_config(page_title="Kripto Cüzdan Analiz", page_icon="🔍")

    st.title("Kripto Cüzdan Analiz: İşlem Tarzı ve Profil")
    st.markdown(
        """
        Bu araç, **public cüzdan adresini** girerek:
        - ne alıyor ne satıyor,
        - işlem sıklığı,
        - strateji tipi (meme, swing, HODL, bot),
        - risk profili,
        - PnL ve win rate,
        gibi özellikleri **akıl yürütmeyle özet**ler.
        
        Desteklenen ağlar: Ethereum, BSC, Polygon, Arbitrum, Optimism, Base, Avalanche, Solana, Tron, Bitcoin.
        """
    )

    address = st.text_input(
        "Cüzdan Adresi (public)",
        placeholder="0x... veya Solana adresi",
    )

    chain_options = [f"{code} ({name})" for code, name in SUPPORTED_CHAINS]
    chain_selected_str = st.selectbox("Ağ seç", chain_options)
    chain_selected = chain_selected_str.split(" (")[0]

    if not address:
        st.info("Lütfen bir cüzdan adresi girin.")
        return

    if st.button("Analiz Başlat"):
        transfers = fetch_wallet_transfers(address, chain_selected)
        balance = fetch_wallet_balance(address, chain_selected)
        pnl = fetch_wallet_pnl(address, chain_selected)

        profile = analyze_wallet_profile(transfers, balance, pnl, chain_selected)

        st.subheader("🧠 Cüzdan Profil Özeti (Akıl Yürütme)")
        st.markdown(profile["summary"])

        st.subheader("📌 Özellikler")
        for t in profile["traits"]:
            st.markdown(f"- {t}")

        df = profile["df"]
        if not df.empty:
            st.subheader("📈 Swap İşlemleri Zaman Serisi")
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")

            fig = px.scatter(
                df,
                x="datetime",
                y="value_usd",
                color="type",
                hover_data=["token_symbol", "amount", "dex"],
                title="Swap İşlemleri (USD)",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("🪙 Token Bakiye Dağılımı")
        balance_df = pd.DataFrame(
            {"token": list(profile["balance"].keys()), "balance_usd": list(profile["balance"].values())}
        )
        if not balance_df.empty:
            fig_bar = px.bar(
                balance_df,
                x="token",
                y="balance_usd",
                title="Token Bakiyesi (USD)",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("💰 PnL ve Win Rate")
        pnl_data = profile["pnl"]
        st.markdown(f"- **Realized PnL:** ${pnl_data.get('realized_pnl_usd', 0):.0f}")
        st.markdown(f"- **Unrealized PnL:** ${pnl_data.get('unrealized_pnl_usd', 0):.0f}")
        st.markdown(f"- **Win Rate:** %{pnl_data.get('win_rate', 0)*100:.1f}")
        st.markdown(f"- **Kapanış İşlem Sayısı:** {pnl_data.get('closed_trades', 0)}")

        st.subheader("🏷️ Strateji ve Risk Etiketi")
        st.markdown(f"- **Strateji Tipi:** {profile['strategy_label']}")
        st.markdown(f"- **Risk Profili:** {profile['risk_label']}")


if __name__ == "__main__":
    main()
