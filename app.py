import datetime
import requests
import streamlit as st

st.set_page_config(page_title="Cüzdan Takipçisi", layout="wide")
st.title("🔗 Akıllı Çoklu Ağ Cüzdan Paneli")
st.caption("Ethereum • Base • Solana")

# ====================== SECRETS ======================
try:
    ETHERSCAN_KEY = st.secrets["ETHERSCAN_API_KEY"]
    SOLSCAN_KEY = st.secrets.get("SOLSCAN_API_KEY")
except KeyError:
    st.error("API anahtarlarını secrets.toml dosyasına ekleyin!")
    st.stop()


def detect_network(address: str):
    addr = address.strip().lower()
    if not addr.startswith("0x"):
        # Solana
        if 32 <= len(addr) <= 44:
            return "Solana"
        return None
    else:
        # 0x ile başlayanlar için varsayılan Ethereum, kullanıcı Base seçebilir
        return "Ethereum"


# ====================== FONKSİYONLAR ======================
def get_balance_and_txs(chain, address):
    if chain == "Solana":
        # SOL Bakiye + Tokenler
        tokens_url = "https://public-api.solscan.io/account/tokens"
        tx_url = "https://public-api.solscan.io/account/transactions"
        headers = {"accept": "application/json"}
        if SOLSCAN_KEY:
            headers["Authorization"] = f"Bearer {SOLSCAN_KEY}"
        
        try:
            tokens = requests.get(tokens_url, params={"address": address}, headers=headers, timeout=15).json()
            txs = requests.get(tx_url, params={"address": address, "limit": 10}, headers=headers, timeout=15).json()
            
            sol_balance = 0
            for t in tokens if isinstance(tokens, list) else []:
                if t.get("tokenAddress") is None:
                    sol_balance = float(t.get("balance", 0)) / 10**9
            return {"balance": sol_balance, "txs": txs, "tokens": tokens}
        except:
            return {"balance": 0, "txs": [], "tokens": []}

    else:
        # Ethereum & Base (Basescan)
        base_url = "https://api.basescan.org/api" if chain == "Base" else "https://api.etherscan.io/v2/api"
        chainid = 8453 if chain == "Base" else 1   # Base chain ID

        # Bakiye
        bal_params = {"chainid": chainid, "module": "account", "action": "balance", "address": address, "apikey": ETHERSCAN_KEY}
        # İşlemler
        tx_params = {"chainid": chainid, "module": "account", "action": "txlist", "address": address, 
                     "page": 1, "offset": 10, "sort": "desc", "apikey": ETHERSCAN_KEY}

        try:
            bal_resp = requests.get(base_url, params=bal_params, timeout=15).json()
            balance = float(bal_resp.get("result", 0)) / 10**18

            tx_resp = requests.get(base_url, params=tx_params, timeout=15).json()
            return {"balance": balance, "txs": tx_resp, "tokens": []}
        except:
            return {"balance": 0, "txs": {"status": "0"}, "tokens": []}


# ====================== UI ======================
address = st.text_input("Cüzdan Adresini Yapıştır:", placeholder="0x... veya Solana adresi")

col1, col2 = st.columns([3, 1])
with col1:
    network = st.radio("Ağ Seçimi (0x adresler için):", 
                      ["Otomatik", "Ethereum", "Base"], 
                      horizontal=True)

if st.button("🔍 Analiz Et", type="primary"):
    if not address.strip():
        st.warning("Adres giriniz")
        st.stop()

    detected = detect_network(address)
    
    if network == "Otomatik":
        selected_network = detected or "Ethereum"
    else:
        selected_network = network

    if selected_network == "Solana" and detected != "Solana":
        st.warning("Bu adres Solana formatında değil.")
    
    st.subheader(f"📍 {selected_network} Cüzdanı")
    st.code(address)

    with st.spinner(f"{selected_network} sorgulanıyor..."):
        data = get_balance_and_txs(selected_network, address.strip())

        # Özet
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Bakiye", f"{data['balance']:.6f} { 'SOL' if selected_network == 'Solana' else 'ETH' }")
        with col2:
            tx_count = len(data['txs'].get("result", [])) if selected_network != "Solana" else len(data['txs'][:10])
            st.metric("Son İşlem", tx_count)

        st.divider()
        st.subheader("Son 10 İşlem")

        if selected_network == "Solana":
            for idx, tx in enumerate(data['txs'][:10], 1):
                sig = tx.get("txHash") or tx.get("signature", "")
                dt = datetime.datetime.fromtimestamp(int(tx.get("blockTime") or 0)) if tx.get("blockTime") else "Bilinmiyor"
                with st.expander(f"#{idx} {str(sig)[:12]}... | {dt}"):
                    st.write(f"**Fee:** `{float(tx.get('fee',0))/1e9:.6f} SOL`")
                    st.markdown(f"[Solscan](https://solscan.io/tx/{sig})")
        else:
            tx_list = data['txs'].get("result", [])
            for idx, tx in enumerate(tx_list, 1):
                dt = datetime.datetime.fromtimestamp(int(tx["timeStamp"]))
                value = float(tx.get("value", 0)) / 10**18
                explorer = "basescan.org" if selected_network == "Base" else "etherscan.io"
                with st.expander(f"#{idx} {tx['hash'][:12]}... | {dt.strftime('%Y-%m-%d %H:%M')}"):
                    st.write(f"**Gönderen:** `{tx['from']}`")
                    st.write(f"**Alıcı:** `{tx['to']}`")
                    st.write(f"**Miktar:** `{value:.6f} ETH`")
                    st.markdown(f"[🔗 {selected_network} Explorer](https://{explorer}/tx/{tx['hash']})")

st.info("**Not:** Base ve Ethereum aynı API anahtarını (Etherscan) kullanıyor. BaseScan API'si ücretsiz tier'de çalışıyor.")
