"""
Fintables One Cikanlar -> Google Sheets
- Sayfa 1 "Tum Haberler": tum haberler
- Sayfa 2 "Secili Hisseler": sadece hisse listesindeki haberler
- Sayfa 3 "Hisse Listesi": takip edilecek hisse kodlari
- GitHub Actions ile her 20 dakikada calisir
"""

import os
import json
from datetime import datetime
from curl_cffi import requests
import gspread
from google.oauth2.service_account import Credentials

# --- AYARLAR ---
SHEETS_ID            = "17_8lCsJ2P8v0hgSBbWtD3T8kyof_DCHD1H9t3yr1izk"
SAYFA_TUM            = "Tum Haberler"
SAYFA_SECILI         = "Secili Hisseler"
SAYFA_HISSE_LISTESI  = "Hisse Listesi"
API_URL              = "https://api.fintables.com/topic-feed/?page_size=50&for_everyone=1&only_pro=1"
CREDENTIALS_JSON     = os.environ.get("GOOGLE_CREDENTIALS_JSON")

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "referer": "https://fintables.com/",
    "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
}

SUTUNLAR = ["Haber ID", "Kaynak", "Hisse", "Tarih", "Icerik", "URL", "Eklenme Zamani"]

HEADER_FORMAT = {
    "backgroundColor": {"red": 0.1, "green": 0.235, "blue": 0.369},
    "textFormat": {
        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
        "bold": True
    },
    "horizontalAlignment": "CENTER",
}


def log(mesaj):
    print(f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] {mesaj}")


def google_sheets_baglan():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if CREDENTIALS_JSON:
        creds = Credentials.from_service_account_info(
            json.loads(CREDENTIALS_JSON), scopes=scopes
        )
    else:
        creds = Credentials.from_service_account_file(
            "service_account.json", scopes=scopes
        )
    return gspread.authorize(creds)


def sayfayi_hazirla(spreadsheet, sayfa_adi, icerik_satirlari=None):
    """Sayfa yoksa olustur, baslik ekle."""
    try:
        sayfa = spreadsheet.worksheet(sayfa_adi)
    except gspread.WorksheetNotFound:
        sayfa = spreadsheet.add_worksheet(title=sayfa_adi, rows=5000, cols=10)
        if icerik_satirlari:
            # Hisse listesi sayfasi icin
            sayfa.append_row(icerik_satirlari[0])
            sayfa.format("A1:A1", HEADER_FORMAT)
            for satir in icerik_satirlari[1:]:
                sayfa.append_row(satir)
        else:
            sayfa.append_row(SUTUNLAR)
            sayfa.format(f"A1:{chr(64+len(SUTUNLAR))}1", HEADER_FORMAT)
        log(f"Yeni sayfa olusturuldu: {sayfa_adi}")
    return sayfa


def hisse_listesini_oku(spreadsheet):
    """Hisse Listesi sayfasindan hisse kodlarini oku."""
    try:
        sayfa = spreadsheet.worksheet(SAYFA_HISSE_LISTESI)
        degerler = sayfa.col_values(1)
        # Baslik satirini atla, bos olmayanlari al, buyuk harf yap
        hisseler = set(h.strip().upper() for h in degerler[1:] if h.strip())
        return hisseler
    except gspread.WorksheetNotFound:
        return set()


def mevcut_idleri_oku(sayfa):
    """Sayfadaki mevcut haber ID'lerini oku."""
    try:
        degerler = sayfa.col_values(1)
        return set(degerler[1:])
    except:
        return set()


def haberleri_cek():
    """Fintables API'den haberleri cek."""
    try:
        response = requests.get(
            API_URL, headers=HEADERS, timeout=15, impersonate="chrome110"
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        log(f"API hatasi: {e}")
        return []


def haberi_isle(item):
    """Ham API verisini satir formatina donustur."""
    news     = item.get("news") or {}
    haber_id = item.get("id", "")

    kaynak_map = {"ODA": "KAP", "BIST": "BIST", "FINTABLES": "Fintables"}
    kaynak = kaynak_map.get(news.get("type", ""), news.get("type", ""))

    hisseler = news.get("companies", [])
    hisse    = ", ".join(hisseler) if hisseler else ""

    tarih_raw = item.get("date", "")
    try:
        dt    = datetime.fromisoformat(tarih_raw.replace("Z", "+00:00"))
        tarih = dt.strftime("%d.%m.%Y %H:%M")
    except:
        tarih = tarih_raw

    icerik  = news.get("note") or news.get("summary") or item.get("title", "")
    url     = f"https://fintables.com/borsa-haber-akisi/{haber_id}"
    eklenme = datetime.now().strftime("%d.%m.%Y %H:%M")

    return [haber_id, kaynak, hisse, tarih, icerik, url, eklenme]


def main():
    log("Script baslatildi.")

    # 1) Baglan
    log("Google Sheets'e baglaniliyor...")
    client      = google_sheets_baglan()
    spreadsheet = client.open_by_key(SHEETS_ID)
    log("Baglanti basarili.")

    # 2) Sayfalari hazirla
    sayfa_tum    = sayfayi_hazirla(spreadsheet, SAYFA_TUM)
    sayfa_secili = sayfayi_hazirla(spreadsheet, SAYFA_SECILI)

    # Hisse listesi sayfasi yoksa ornek hisselerle olustur
    try:
        spreadsheet.worksheet(SAYFA_HISSE_LISTESI)
    except gspread.WorksheetNotFound:
        ornek_hisseler = [
            ["Hisse Kodu"],
            ["THYAO"], ["GARAN"], ["ASELS"], ["EREGL"], ["KCHOL"],
            ["AKBNK"], ["YKBNK"], ["TUPRS"], ["BIMAS"], ["SISE"],["TEZOL"],["VKING"],
        ]
        sayfayi_hazirla(spreadsheet, SAYFA_HISSE_LISTESI, ornek_hisseler)
        log("Hisse Listesi sayfasi ornek hisselerle olusturuldu. Lutfen duzenlyin.")

    # 3) Hisse listesini oku
    hisse_listesi = hisse_listesini_oku(spreadsheet)
    log(f"Takip edilen hisse sayisi: {len(hisse_listesi)}")

    # 4) Mevcut ID'leri oku
    mevcut_tum    = mevcut_idleri_oku(sayfa_tum)
    mevcut_secili = mevcut_idleri_oku(sayfa_secili)
    log(f"Mevcut haberler - Tum: {len(mevcut_tum)}, Secili: {len(mevcut_secili)}")

    # 5) API'den haberleri cek
    log("Fintables API'den haberler cekiliyor...")
    haberler = haberleri_cek()
    log(f"{len(haberler)} haber cekildi.")

    # 6) Yeni haberleri isle
    yeni_tum    = []
    yeni_secili = []

    for item in haberler:
        haber_id = item.get("id", "")
        if not haber_id:
            continue

        satir    = haberi_isle(item)
        hisseler = [h.strip().upper() for h in satir[2].split(",") if h.strip()]

        # Tum haberler sayfasi
        if haber_id not in mevcut_tum:
            yeni_tum.append(satir)

        # Secili hisseler sayfasi
        if haber_id not in mevcut_secili:
            if not hisse_listesi or any(h in hisse_listesi for h in hisseler):
                yeni_secili.append(satir)

    # 7) Sheets'e ekle
    if yeni_tum:
        sayfa_tum.append_rows(yeni_tum, value_input_option="USER_ENTERED")
        log(f"{len(yeni_tum)} yeni haber 'Tum Haberler' sayfasina eklendi.")
    else:
        log("'Tum Haberler' icin yeni haber yok.")

    if yeni_secili:
        sayfa_secili.append_rows(yeni_secili, value_input_option="USER_ENTERED")
        log(f"{len(yeni_secili)} yeni haber 'Secili Hisseler' sayfasina eklendi.")
    else:
        log("'Secili Hisseler' icin yeni haber yok.")

    log("Script tamamlandi.")


if __name__ == "__main__":
    main()