import datetime
import requests
import streamlit as st

# Sayfa Genişlik ve Başlık Ayarları
st.set_page_config(page_title="Blokzincir İşlem Takipçisi", layout="wide")
st.title("🔗 Çoklu Ağ (Ethereum & Solana) İşlem Takip Paneli")
st.caption(
    "Etherscan ve Solscan API'lerini kullanarak güvenli bir şekilde adres geçmişini listeler."
)

# Streamlit Secrets üzerinden API anahtarlarını güvenli bir şekilde çekme
try:
    ETHERSCAN_KEY = st.secrets["ETHERSCAN_API_KEY"]
    SOLSCAN_KEY = st.secrets["SOLSCAN_API_KEY"]
except KeyError:
    st.error(
        "Hata: API anahtarları `.streamlit/secrets.toml` veya Streamlit Cloud ayarlarında bulunamadı!"
    )
    st.stop()


# --- ETHEREUM İŞLEM FONKSiyonu (Güvenli Versiyon) ---
def get_ethereum_tx(address):
    url = "https://etherscan.io"
    params = {
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 10,
        "sort": "desc",
        "apikey": ETHERSCAN_KEY,
    }

    # Streamlit Cloud'un bot korumalarına (Cloudflare) takılmasını önlemek için tarayıcı başlığı
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(
            url, params=params, headers=headers, timeout=15
        )

        # HTTP Hata kodu kontrolü
        if response.status_code != 200:
            return {
                "status": "0",
                "message": f"Etherscan sunucusu HTTP {response.status_code} hatası döndürdü. Lütfen daha sonra tekrar deneyin.",
            }

        # JSON ayrıştırma doğrulaması
        return response.json()

    except requests.exceptions.JSONDecodeError:
        return {
            "status": "0",
            "message": "Etherscan API'sinden geçersiz veri (HTML) alındı. Streamlit Cloud IP adresi engellenmiş veya API anahtarınız hatalı olabilir.",
        }
    except requests.exceptions.RequestException as e:
        return {"status": "0", "message": f"Bağlantı hatası oluştu: {str(e)}"}


# --- SOLANA İŞLEM FONKSİYONU ---
def get_solana_tx(address):
    url = "https://solscan.io"
    params = {"account": address, "limit": 10}
    headers = {
        "token": SOLSCAN_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Solscan sunucusu HTTP {response.status_code} hatası döndürdü.",
            }
        return response.json()
    except Exception as e:
        return {"status": "error", "message": f"Bağlantı hatası: {str(e)}"}


# --- KULLANICI ARAYÜZÜ (UI) ---
network = st.radio("Sorgulanacak Ağı Seçin:", ("Ethereum (ETH)", "Solana (SOL)"))
target_address = st.text_input(
    "Cüzdan veya Sözleşme Adresini Girin:",
    placeholder="0x... veya Solana adresi",
)

if st.button("İşlemleri Getir"):
    if not target_address:
        st.warning("Lütfen geçerli bir adres giriniz.")
    else:
        # --- ETHEREUM SORGUSU ---
        if network == "Ethereum (ETH)":
            with st.spinner("Ethereum ağı sorgulanıyor..."):
                data = get_ethereum_tx(target_address)

                if data.get("status") == "1":
                    tx_list = data.get("result", [])
                    st.success(
                        f"Son {len(tx_list)} Ethereum işlemi başarıyla getirildi!"
                    )

                    for idx, tx in enumerate(tx_list, 1):
                        dt = datetime.datetime.fromtimestamp(
                            int(tx["timeStamp"])
                        )
                        eth_value = float(tx["value"]) / 10**18

                        with st.expander(
                            f"İşlem {idx}: {tx['hash'][:15]}... | {dt.strftime('%Y-%m-%d %H:%M')}"
                        ):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Gönderen:** `{tx['from']}`")
                                st.write(f"**Alıcı:** `{tx['to']}`")
                                st.write(f"**Miktar:** {eth_value:.6f} ETH")
                            with col2:
                                st.write(f"**Blok No:** {tx['blockNumber']}")
                                st.write(
                                    f"**Tx Hash:** [Etherscan'de Gör](https://etherscan.io{tx['hash']})"
                                )
                else:
                    st.error(
                        f"Hata Açıklaması: {data.get('message', 'Bilinmeyen hata')}"
                    )

        # --- SOLANA SORGUSU ---
        elif network == "Solana (SOL)":
            with st.spinner("Solana ağı sorgulanıyor..."):
                data = get_solana_tx(target_address)

                if "data" in data:
                    tx_list = data.get("data", [])
                    st.success(
                        f"Son {len(tx_list)} Solana işlemi başarıyla getirildi!"
                    )

                    for idx, tx in enumerate(tx_list, 1):
                        b_time = tx.get("block_time", tx.get("time"))
                        dt = (
                            datetime.datetime.fromtimestamp(int(b_time))
                            if b_time
                            else "Bilinmiyor"
                        )
                        signature = tx.get("txHash", tx.get("signature", ""))

                        with st.expander(
                            f"İşlem {idx}: {signature[:15]}... | {dt if isinstance(dt, str) else dt.strftime('%Y-%m-%d %H:%M')}"
                        ):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(
                                    f"**Durum:** `{tx.get('status', 'N/A')}`"
                                )
                                fee_sol = (
                                    float(tx.get("fee", 0)) / 10**9
                                    if tx.get("fee")
                                    else 0
                                )
                                st.write(f"**İşlem Ücreti (Fee):** {fee_sol} SOL")
                            with col2:
                                st.write(
                                    f"**Slot No:** {tx.get('slot', 'N/A')}"
                                )
                                if signature:
                                    st.write(
                                        f"**İmza (Signature):** [Solscan'de Gör](https://solscan.io{signature})"
                                    )
                else:
                    st.error(
                        f"Solscan Hatası: {data.get('message', 'API yanıtı alınamadı veya geçersiz anahtar.')}"
                    )
