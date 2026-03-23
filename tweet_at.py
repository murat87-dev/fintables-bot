"""
Fintables -> Twitter
- Google Sheets'teki "Secili Hisseler" sayfasından en son haberi alır
- Daha önce tweetlenmemiş haberi Twitter'a atar
- "Tweetlendi" sütununa işaret koyar
- 09:00-15:00 arası GitHub Actions ile çalışır
"""

import os
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import tweepy

# --- AYARLAR ---
SHEETS_ID        = "17_8lCsJ2P8v0hgSBbWtD3T8kyof_DCHD1H9t3yr1izk"
SAYFA_SECILI     = "Secili Hisseler"
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# Twitter keyleri GitHub Secrets'tan gelir
TWITTER_API_KEY              = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET           = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN         = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET  = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")


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


def twitter_baglan():
    client = tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
    )
    return client


def tweet_metni_olustur(satir):
    """
    Satırdan tweet metni oluştur.
    Sütunlar: [Haber ID, Kaynak, Hisse, Tarih, Icerik, URL, Eklenme Zamani, Tweetlendi]
    """
    kaynak = satir[1] if len(satir) > 1 else ""
    hisse  = satir[2] if len(satir) > 2 else ""
    tarih  = satir[3] if len(satir) > 3 else ""
    icerik = satir[4] if len(satir) > 4 else ""
    url    = satir[5] if len(satir) > 5 else ""

    # Hisse kodlarını hashtag yap
    hisse_hashtagler = " ".join([f"#{h.strip()}" for h in hisse.split(",") if h.strip()])

    # Tweet metni (280 karakter limiti)
    metin = f"📊 {hisse_hashtagler}\n\n{icerik}\n\n🔗 {url}"

    # 280 karakteri geçerse içeriği kısalt
    if len(metin) > 280:
        max_icerik = 280 - len(f"📊 {hisse_hashtagler}\n\n...\n\n🔗 {url}") - 3
        icerik     = icerik[:max_icerik] + "..."
        metin      = f"📊 {hisse_hashtagler}\n\n{icerik}\n\n🔗 {url}"

    return metin


def main():
    log("Tweet scripti baslatildi.")

    # 1) Sheets'e baglan
    client      = google_sheets_baglan()
    spreadsheet = client.open_by_key(SHEETS_ID)

    try:
        sayfa = spreadsheet.worksheet(SAYFA_SECILI)
    except gspread.WorksheetNotFound:
        log(f"HATA: '{SAYFA_SECILI}' sayfasi bulunamadi!")
        return

    # 2) Tüm verileri oku
    tum_veri = sayfa.get_all_values()
    if len(tum_veri) < 2:
        log("Sayfada haber yok.")
        return

    baslik_satiri = tum_veri[0]

    # "Tweetlendi" sütunu yoksa ekle
    if "Tweetlendi" not in baslik_satiri:
        yeni_sutun = len(baslik_satiri) + 1
        sayfa.update_cell(1, yeni_sutun, "Tweetlendi")
        baslik_satiri.append("Tweetlendi")
        log("'Tweetlendi' sutunu eklendi.")

    tweet_col = baslik_satiri.index("Tweetlendi") + 1  # 1-indexed

    # 3) Tweetlenmemiş en son haberi bul (alttan üste tara)
    hedef_satir = None
    hedef_idx   = None

    for i in range(len(tum_veri) - 1, 0, -1):  # Sondan başa
        satir = tum_veri[i]
        # Tweetlendi sütunu boş mu?
        tweet_degeri = satir[tweet_col - 1] if len(satir) >= tweet_col else ""
        if not tweet_degeri.strip():
            hedef_satir = satir
            hedef_idx   = i + 1  # Sheets 1-indexed
            break

    if not hedef_satir:
        log("Tweetlenecek yeni haber yok.")
        return

    # 4) Tweet at
    metin = tweet_metni_olustur(hedef_satir)
    log(f"Tweet atiliyor:\n{metin}")

    try:
        twitter = twitter_baglan()
        response = twitter.create_tweet(text=metin)
        tweet_id = response.data["id"]
        log(f"Tweet atildi! ID: {tweet_id}")

        # 5) Sheets'e "Tweetlendi" işaretle
        eklenme = datetime.now().strftime("%d.%m.%Y %H:%M")
        sayfa.update_cell(hedef_idx, tweet_col, eklenme)
        log(f"Sheets guncellendi: {hedef_idx}. satir tweetlendi olarak isaretlendi.")

    except tweepy.TweepyException as e:
        log(f"Twitter hatasi: {e}")


if __name__ == "__main__":
    main()