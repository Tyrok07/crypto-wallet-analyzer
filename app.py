import datetime
import requests
import streamlit as st

st.set_page_config(page_title="Blokzincir İşlem Takipçisi", layout="wide")
st.title("🔗 Akıllı Blokzincir İşlem Takipçisi")
st.caption("Adresi yapıştır → Sistem otomatik olarak Ethereum veya Solana olduğunu anlar")

# API Keys
try:
    ETHERSCAN_KEY = st.secrets["ETHERSCAN_API_KEY"]
    SOLSCAN_KEY = st.secrets.get("SOLSCAN_API_KEY")
except KeyError:
    st.error("API anahtarları secrets.toml dosyasında bulunamadı!")
    st.stop()


def detect_network(address: str):
    """Adres formatından ağı tespit et"""
    addr = address.strip()
    
    if addr.startswith("0x") and len(addr) == 42:
        return "Ethereum"
    elif len(addr) >= 32 and len(addr) <= 44 and not addr.startswith("0x"):
        # Basit Solana kontrolü (base58 karakterleri)
        if all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in addr):
            return "Solana"
    return None


# ====================== ETHEREUM ======================
def get_ethereum_tx(address):
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": 1,
        "module": "account",
        "action": "txlist",
        "address": address,
        "page": 1,
        "offset": 10,
        "sort": "desc",
        "apikey": ETHERSCAN_KEY,
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "0", "message": str(e)}


# ====================== SOLANA ======================
def get_solana_tx(address):
    url = "https://public-api.solscan.io/account/transactions"
    params = {"address": address, "limit": 10}
    headers = {"accept": "application/json", "User-Agent": "Mozilla/5.0"}
    
    if SOLSCAN_KEY:
        headers["Authorization"] = f"Bearer {SOLSCAN_KEY}"

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ====================== UI ======================
target_address = st.text_input(
    "Cüzdan Adresini Yapıştır:",
    placeholder="0x... (Ethereum) veya Solana adresi",
    help="Sadece adresi yapıştırın, sistem otomatik algılayacak"
)

if st.button("🔍 İşlemleri Getir", type="primary"):
    if not target_address.strip():
        st.warning("Lütfen bir adres girin.")
        st.stop()

    network = detect_network(target_address)

    if not network:
        st.error("❌ Geçersiz adres formatı! Lütfen Ethereum (0x...) veya Solana adresi girin.")
        st.stop()

    with st.spinner(f"{network} ağı sorgulanıyor..."):
        if network == "Ethereum":
            data = get_ethereum_tx(target_address.strip())
            
            if data.get("status") == "1":
                tx_list = data.get("result", [])
                st.success(f"✅ Ethereum - Son {len(tx_list)} işlem getirildi")
                
                for idx, tx in enumerate(tx_list, 1):
                    dt = datetime.datetime.fromtimestamp(int(tx["timeStamp"]))
                    value = float(tx.get("value", 0)) / 10**18
                    with st.expander(f"#{idx} {tx['hash'][:12]}... | {dt.strftime('%Y-%m-%d %H:%M')}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Gönderen:** `{tx['from']}`")
                            st.write(f"**Alıcı:** `{tx['to']}`")
                            st.write(f"**Miktar:** `{value:.6f} ETH`")
                        with col2:
                            st.write(f"**Blok:** {tx['blockNumber']}")
                            st.markdown(f"[Etherscan](https://etherscan.io/tx/{tx['hash']})")
            else:
                st.error(f"Ethereum Hatası: {data.get('message')}")

        elif network == "Solana":
            data = get_solana_tx(target_address.strip())
            
            if isinstance(data, list) or (isinstance(data, dict) and not data.get("status") == "error"):
                tx_list = data if isinstance(data, list) else data.get("data", [])
                st.success(f"✅ Solana - Son {len(tx_list)} işlem getirildi")
                
                for idx, tx in enumerate(tx_list, 1):
                    sig = tx.get("txHash") or tx.get("signature", "")
                    block_time = tx.get("blockTime") or tx.get("time")
                    dt = datetime.datetime.fromtimestamp(int(block_time)) if block_time else "Bilinmiyor"
                    
                    with st.expander(f"#{idx} {str(sig)[:12]}... | {dt.strftime('%Y-%m-%d %H:%M') if isinstance(dt, datetime.datetime) else dt}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Durum:** {tx.get('status', 'N/A')}")
                            fee = float(tx.get("fee", 0)) / 1_000_000_000
                            st.write(f"**Fee:** `{fee:.6f} SOL`")
                        with col2:
                            st.markdown(f"[Solscan](https://solscan.io/tx/{sig})")
            else:
                st.error(f"Solana Hatası: {data.get('message', 'Veri alınamadı')}")

st.info("💡 **İpucu:** Ethereum adresleri `0x` ile başlar. Solana adresleri ise genellikle 32-44 karakter uzunluğunda base58 formatındadır.")
