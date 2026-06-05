import yfinance as yf
import requests
import time
from datetime import datetime

BOT_TOKEN = "BURAYA_YENI_BIST_BOT_TOKEN"
CHAT_IDS = [BURAYA_CHAT_ID]

HISSELER = [
    "ASELS.IS", "THYAO.IS", "TUPRS.IS", "KCHOL.IS", "SAHOL.IS",
    "EREGL.IS", "SISE.IS", "GARAN.IS", "AKBNK.IS", "YKBNK.IS",
    "BIMAS.IS", "FROTO.IS", "TOASO.IS", "KONTR.IS", "SASA.IS",
    "ASTOR.IS", "HEKTS.IS", "KOZAL.IS", "PETKM.IS", "PGSUS.IS"
]

ENDEKS = "XU100.IS"
TEKRAR_SURESI = 3 * 60 * 60
gonderilenler = {}


def telegram_gonder(mesaj):
    for chat_id in CHAT_IDS:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": chat_id,
            "text": mesaj,
            "parse_mode": "HTML"
        })


def veri_cek(sembol):
    try:
        data = yf.download(
            sembol,
            period="40d",
            interval="1d",
            progress=False,
            auto_adjust=False
        )
        if data.empty or len(data) < 25:
            return None
        return data
    except Exception as e:
        print(sembol, "veri hatası:", e)
        return None


def hisse_analiz(hisse, endeks_data):
    data = veri_cek(hisse)
    if data is None:
        return None

    son = data.iloc[-1]
    onceki = data.iloc[-2]

    fiyat = float(son["Close"])
    onceki_fiyat = float(onceki["Close"])
    high = float(son["High"])
    low = float(son["Low"])
    close = float(son["Close"])

    hacim = float(son["Volume"])
    ort_hacim = float(data["Volume"].tail(20).mean())
    hacim_orani = hacim / ort_hacim if ort_hacim > 0 else 0

    gunluk = ((fiyat - onceki_fiyat) / onceki_fiyat) * 100

    endeks_son = endeks_data.iloc[-1]
    endeks_onceki = endeks_data.iloc[-2]
    endeks_gunluk = (
        (float(endeks_son["Close"]) - float(endeks_onceki["Close"]))
        / float(endeks_onceki["Close"])
    ) * 100

    endekse_gore_guc = gunluk - endeks_gunluk

    son20_high = float(data["High"].tail(20).max())
    son20_low = float(data["Low"].tail(20).min())

    zirve_uzaklik = ((son20_high - fiyat) / fiyat) * 100
    aralik = ((son20_high - son20_low) / son20_low) * 100

    kapanis_gucu = ((close - low) / (high - low)) * 100 if high > low else 0

    kategori = None
    skor = 0
    nedenler = []

    # HAZIRLANIYOR
    hazir_skor = 0
    if aralik <= 12:
        hazir_skor += 2
    if hacim_orani >= 1.3:
        hazir_skor += 2
    if 0 <= gunluk <= 3.5:
        hazir_skor += 2
    if zirve_uzaklik <= 5:
        hazir_skor += 2
    if endekse_gore_guc >= -0.5:
        hazir_skor += 1

    if hazir_skor >= 7:
        kategori = "🏆 HAZIRLANIYOR"
        skor = hazir_skor
        nedenler.append("Sıkışma bölgesinde")
        nedenler.append("Hacim artmaya başlamış")
        nedenler.append("Henüz çok gitmemiş")

    # GÜÇLÜ HİSSE
    guclu_skor = 0
    if hacim_orani >= 2:
        guclu_skor += 3
    if endekse_gore_guc >= 1.5:
        guclu_skor += 3
    if gunluk >= 2:
        guclu_skor += 2
    if kapanis_gucu >= 70:
        guclu_skor += 2

    if guclu_skor >= 7 and guclu_skor > skor:
        kategori = "🔥 GÜÇLÜ HİSSE"
        skor = guclu_skor
        nedenler = [
            "Endeksten güçlü",
            "Hacim belirgin artmış",
            "Kapanış güçlü bölgede"
        ]

    # SÜPER HİSSE
    super_skor = 0
    if hacim_orani >= 3:
        super_skor += 3
    if endekse_gore_guc >= 2.5:
        super_skor += 3
    if fiyat >= son20_high * 0.995:
        super_skor += 3
    if kapanis_gucu >= 80:
        super_skor += 2
    if 2 <= gunluk <= 8:
        super_skor += 1

    if super_skor >= 9:
        kategori = "🚀 SÜPER HİSSE"
        skor = super_skor
        nedenler = [
            "Hacim patlaması var",
            "Endeksten çok güçlü",
            "20 günlük zirveye çok yakın veya kırmış"
        ]

    if kategori is None:
        return None

    return {
        "hisse": hisse.replace(".IS", ""),
        "kategori": kategori,
        "fiyat": fiyat,
        "gunluk": gunluk,
        "endeks": endeks_gunluk,
        "guc": endekse_gore_guc,
        "hacim_orani": hacim_orani,
        "zirve_uzaklik": zirve_uzaklik,
        "kapanis_gucu": kapanis_gucu,
        "skor": skor,
        "nedenler": nedenler
    }


def alarm_kontrol():
    endeks_data = veri_cek(ENDEKS)
    if endeks_data is None:
        print("BIST 100 verisi alınamadı.")
        return

    sonuclar = []

    for hisse in HISSELER:
        sonuc = hisse_analiz(hisse, endeks_data)
        if sonuc:
            sonuclar.append(sonuc)

    sonuclar = sorted(sonuclar, key=lambda x: x["skor"], reverse=True)

    for s in sonuclar:
        anahtar = s["hisse"] + s["kategori"]
        simdi = time.time()

        if anahtar in gonderilenler and simdi - gonderilenler[anahtar] < TEKRAR_SURESI:
            continue

        mesaj = f"""
{s['kategori']}

📌 Hisse: <b>{s['hisse']}</b>
💰 Fiyat: {s['fiyat']:.2f} TL
📈 Günlük: %{s['gunluk']:.2f}
📊 BIST100: %{s['endeks']:.2f}
💪 Endekse Göre Güç: %{s['guc']:.2f}
🔥 Hacim: {s['hacim_orani']:.2f}x
🎯 Zirve Uzaklığı: %{s['zirve_uzaklik']:.2f}
⭐ Skor: {s['skor']}/10

✅ Nedenler:
{chr(10).join(["• " + n for n in s["nedenler"]])}

⚠️ Yatırım tavsiyesi değildir.
"""

        telegram_gonder(mesaj)
        gonderilenler[anahtar] = simdi


telegram_gonder("✅ BIST BOT BAŞLADI\nTarama aktif.")

while True:
    print("BİST taraması başladı:", datetime.now())
    alarm_kontrol()
    print("15 dakika bekleniyor...")
    time.sleep(15 * 60)
