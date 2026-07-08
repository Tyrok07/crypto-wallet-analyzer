import datetime
import requests
import streamlit as st

st.set_page_config(page_title="Blokzincir Cüzdan Takipçisi", layout="wide")
st.title("🔗 Akıllı Cüzdan Analiz Paneli")
st.caption("Adresi yapıştır → Hem özet hem işlem geçmişi")

# ====================== API KEYS ======================
try:
    ETHERSCAN_KEY = st.secrets["ETHERSCAN_API_KEY"]
    SOLSCAN_KEY = st.secrets.get("SOLSCAN_API_KEY")
except KeyError:
    st.error("❌ secrets.toml dosyasında API anahtarlarını tanımlayın!")
    st.stop()


def detect_network(address: str):
    addr = address.strip()
    if addr.startswith("0x") and len(addr) == 42:
        return "Ethereum"
    elif 32 <= len(addr) <= 44 and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in addr):
        return "Solana"
    return None


# ====================== ETHEREUM FONKSİYONLARI ======================
def get_eth_balance(address):
    url = "https://api.etherscan.io/v2/api"
    params = {"chainid": 1, "module": "account", "action": "balance", "address": address, "apikey": ETHERSCAN_KEY}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        return float(data.get("result", 0)) / 10**18
    except:
        return 0

def get_eth_transactions(address):
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": 1, "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 10, "sort": "desc", "apikey": ETHERSCAN_KEY
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json()
    except:
        return {"status": "0"}


# ====================== SOLANA FONKSİYONLARI ======================
def get_sol_balance_and_tokens(address):
    # Bakiye + Tokenler
    url = "https://public-api.solscan.io/account/tokens"
    params = {"address": address}
    headers = {"accept": "application/json"}
    if SOLSCAN_KEY:
        headers["Authorization"] = f"Bearer {SOLSCAN_KEY}"
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        return r.json()
    except:
        return []

def get_sol_transactions(address):
    url = "https://public-api.solscan.io/account/transactions"
    params = {"address": address, "limit": 10}
    headers = {"accept": "application/json"}
    if SOLSCAN_KEY:
        headers["Authorization"] = f"Bearer {SOLSCAN_KEY}"
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        return r.json()
    except:
        return []


# ====================== ANA ARAYÜZ ======================
target_address = st.text_input(
    "Cüzdan Adresini Yapıştırın:",
    placeholder="0x... veya Solana adresi",
    key="address_input"
)

if st.button("🔍 Analiz Et", type="primary"):
    if not target_address.strip():
        st.warning("Adres giriniz.")
        st.stop()

    network = detect_network(target_address)
    if not network:
        st.error("❌ Geçersiz adres formatı!")
        st.stop()

    st.subheader(f"📍 {network} Cüzdan Analizi")
    st.caption(target_address)

    with st.spinner("Cüzdan bilgileri çekiliyor..."):
        if network == "Ethereum":
            balance = get_eth_balance(target_address)
            tx_data = get_eth_transactions(target_address)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("ETH Bakiyesi", f"{balance:.6f} ETH")
            with col2:
                st.metric("İşlem Sayısı (Son 10)", len(tx_data.get("result", [])))

            st.divider()
            st.subheader("Son 10 İşlem")
            tx_list = tx_data.get("result", [])
            for idx, tx in enumerate(tx_list, 1):
                dt = datetime.datetime.fromtimestamp(int(tx["timeStamp"]))
                value = float(tx.get("value", 0)) / 10**18
                with st.expander(f"#{idx} {tx['hash'][:10]}... | {dt.strftime('%Y-%m-%d %H:%M')}"):
                    st.write(f"**Gönderen:** `{tx['from']}`")
                    st.write(f"**Alıcı:** `{tx['to']}`")
                    st.write(f"**Miktar:** `{value:.6f} ETH`")
                    st.markdown(f"[🔗 Etherscan](https://etherscan.io/tx/{tx['hash']})")

        elif network == "Solana":
            tokens = get_sol_balance_and_tokens(target_address)
            tx_list = get_sol_transactions(target_address)

            # SOL Bakiyesi
            sol_balance = 0
            if tokens and isinstance(tokens, list):
                for t in tokens:
                    if t.get("tokenAddress") is None:  # Native SOL
                        sol_balance = float(t.get("balance", 0)) / 10**9

            col1, col2 = st.columns(2)
            with col1:
                st.metric("SOL Bakiyesi", f"{sol_balance:.6f} SOL")
            with col2:
                st.metric("Token Çeşidi", len([t for t in tokens if t.get("tokenAddress")]))

            st.divider()
            st.subheader("Son 10 İşlem")
            for idx, tx in enumerate(tx_list[:10], 1):
                sig = tx.get("txHash") or tx.get("signature", "")
                block_time = tx.get("blockTime") or tx.get("time")
                dt = datetime.datetime.fromtimestamp(int(block_time)) if block_time else "Bilinmiyor"
                
                with st.expander(f"#{idx} {str(sig)[:10]}... | {dt.strftime('%Y-%m-%d %H:%M')}"):
                    fee = float(tx.get("fee", 0)) / 1_000_000_000
                    st.write(f"**Fee:** `{fee:.6f} SOL`")
                    st.markdown(f"[🔗 Solscan](https://solscan.io/tx/{sig})")

    st.success("Analiz tamamlandı!")

st.info("💡 Daha fazla özellik istersen (tüm token bakiyeleri tablosu, toplam giren/çıkan para, grafik vs.) söyle, hemen ekleyeyim.")
