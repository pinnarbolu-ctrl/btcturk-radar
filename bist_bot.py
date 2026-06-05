print("BIST BOT V2.1 AKTIF - BIST100 + KAP + ELIT + RSI")

import time
from datetime import datetime, timedelta

import requests
import yfinance as yf


BOT_TOKEN = "8855467313:AAHYdR1ts-liJ0hMwxxPGpgmrPne6ydFOpI"
CHAT_IDS = [2097448038]

# İlk sürümde güvenli başlamak için likiditesi yüksek hisseler.
# İstersen sonraki adımda bunu tam BIST100 listesine genişletiriz.
HISSELER = [
    "ADEL.IS", "AEFES.IS", "AGHOL.IS", "AHGAZ.IS", "AKBNK.IS",
    "AKCNS.IS", "AKFGY.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS",
    "ALBRK.IS", "ALFAS.IS", "ALTNY.IS", "ANHYT.IS", "ANSGR.IS",
    "ARCLK.IS", "ASELS.IS", "ASTOR.IS", "AVPGY.IS", "BERA.IS",
    "BIMAS.IS", "BRSAN.IS", "BRYAT.IS", "BSOKE.IS", "BTCIM.IS",
    "CANTE.IS", "CCOLA.IS", "CIMSA.IS", "CLEBI.IS", "CWENE.IS",
    "DOAS.IS", "DOHOL.IS", "DSTKF.IS", "EFORC.IS", "EGEEN.IS",
    "EKGYO.IS", "ENERY.IS", "ENJSA.IS", "ENKAI.IS", "ENTRA.IS",
    "EREGL.IS", "EUPWR.IS", "FROTO.IS", "GARAN.IS", "GESAN.IS",
    "GOLTS.IS", "GRSEL.IS", "GUBRF.IS", "HALKB.IS", "HEKTS.IS",
    "IEYHO.IS", "ISCTR.IS", "ISGYO.IS", "ISMEN.IS", "KCAER.IS",
    "KCHOL.IS", "KLSER.IS", "KMPUR.IS", "KONTR.IS", "KOZAA.IS",
    "KOZAL.IS", "KRDMD.IS", "KTLEV.IS", "MAVI.IS", "MGROS.IS",
    "MIATK.IS", "MPARK.IS", "OBAMS.IS", "ODAS.IS", "OTKAR.IS",
    "OYAKC.IS", "PASEU.IS", "PATEK.IS", "PETKM.IS", "PGSUS.IS",
    "QUAGR.IS", "RALYH.IS", "REEDR.IS", "SAHOL.IS", "SASA.IS",
    "SISE.IS", "SKBNK.IS", "SMRTG.IS", "SOKM.IS", "TABGD.IS",
    "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TOASO.IS",
    "TSKB.IS", "TTKOM.IS", "TTRAK.IS", "TUPRS.IS", "TURSG.IS",
    "ULKER.IS", "VAKBN.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS",
    "ZOREN.IS",
]

# Tekrarlı sembol varsa temizle.
HISSELER = list(dict.fromkeys(HISSELER))

ENDEKS = "XU100.IS"

TARAMA_SURESI = 15 * 60
TEKRAR_SURESI = 24 * 60 * 60       # Aynı hisse/kategori 24 saat tekrar atmasın
MAX_SINYAL = 8                     # Bir taramada en fazla 8 sinyal
MIN_GUCLU_HACIM = 1.2              # Güçlü hisse için minimum hacim oranı

KAP_API_URL = "https://www.kap.org.tr/tr/api/disclosures"

gonderilenler = {}
son_kap_cache = {"zaman": 0, "veri": {}}


def sayi_al(deger):
    """yfinance bazen scalar, Series veya tek elemanlı yapı döndürüyor; güvenli float çevirir."""
    try:
        if hasattr(deger, "iloc"):
            return float(deger.iloc[0])
        return float(deger)
    except Exception:
        return None


def telegram_gonder(mesaj):
    for chat_id in CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(
                url,
                data={"chat_id": chat_id, "text": mesaj, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception as e:
            print("Telegram hata:", e)


def kolon_duzelt(data):
    """Yahoo Finance bazı durumlarda MultiIndex kolon döndürür. Tek sembol için sadeleştirir."""
    try:
        if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
            # Önce ilk seviye OHLCV ise ikinci seviyeyi at.
            ilk_seviye = list(data.columns.get_level_values(0))
            if "Close" in ilk_seviye:
                data.columns = data.columns.get_level_values(0)
            else:
                data.columns = data.columns.get_level_values(-1)
        return data
    except Exception:
        return data


def veri_cek(sembol):
    try:
        data = yf.download(
            sembol,
            period="60d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        if data is None or data.empty or len(data) < 30:
            return None

        data = kolon_duzelt(data)

        gerekli = ["Open", "High", "Low", "Close", "Volume"]
        for k in gerekli:
            if k not in data.columns:
                print(sembol, "eksik kolon:", k)
                return None

        return data

    except Exception as e:
        print(sembol, "veri çekme hatası:", e)
        return None


def rsi_hesapla(close_series, period=14):
    try:
        delta = close_series.diff()
        kazanc = delta.clip(lower=0)
        kayip = -delta.clip(upper=0)
        ort_kazanc = kazanc.rolling(period).mean()
        ort_kayip = kayip.rolling(period).mean()
        rs = ort_kazanc / ort_kayip
        rsi = 100 - (100 / (1 + rs))
        return sayi_al(rsi.iloc[-1])
    except Exception:
        return None


def kap_puan_hesapla(baslik):
    """KAP başlığından olumlu/olumsuz haber puanı üretir."""
    if not baslik:
        return 0, []

    t = baslik.lower()
    puan = 0
    nedenler = []

    pozitifler = {
        "yeni iş": 3,
        "iş ilişkisi": 3,
        "sözleşme": 3,
        "ihale": 3,
        "sipariş": 2,
        "yatırım": 2,
        "kapasite": 2,
        "üretim": 2,
        "geri alım": 2,
        "pay alım": 2,
        "bedelsiz": 2,
        "temettü": 2,
        "kar payı": 2,
        "finansal duran varlık": 1,
        "bağlı ortaklık": 1,
    }

    negatifler = {
        "dava": -2,
        "ceza": -3,
        "tedbir": -2,
        "soruşturma": -3,
        "zarar": -2,
        "faaliyetlerin durdurulması": -4,
        "iflas": -5,
    }

    for kelime, deger in pozitifler.items():
        if kelime in t:
            puan += deger
            nedenler.append(kelime)

    for kelime, deger in negatifler.items():
        if kelime in t:
            puan += deger
            nedenler.append("negatif: " + kelime)

    if puan > 6:
        puan = 6
    if puan < -5:
        puan = -5

    return puan, nedenler[:4]


def kap_bildirimlerini_cek():
    """
    KAP resmi sitedeki güncel bildirimleri okumayı dener.
    KAP tarafında API cevabı değişirse bot çökmesin diye tüm hatalar yakalanır.
    """
    simdi = time.time()

    # 10 dakika cache
    if simdi - son_kap_cache["zaman"] < 10 * 60:
        return son_kap_cache["veri"]

    kap_skorlari = {}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }
        r = requests.get(KAP_API_URL, headers=headers, timeout=12)
        if r.status_code != 200:
            print("KAP API status:", r.status_code)
            son_kap_cache["zaman"] = simdi
            son_kap_cache["veri"] = kap_skorlari
            return kap_skorlari

        veri = r.json()

        if isinstance(veri, dict):
            liste = veri.get("data") or veri.get("result") or veri.get("disclosures") or []
        elif isinstance(veri, list):
            liste = veri
        else:
            liste = []

        sembol_set = {h.replace(".IS", "") for h in HISSELER}

        for item in liste[:120]:
            if not isinstance(item, dict):
                continue

            baslik = (
                item.get("title")
                or item.get("disclosureType")
                or item.get("subject")
                or item.get("summary")
                or item.get("basicDisclosureTemplate")
                or ""
            )

            # KAP cevabında sembol farklı alanlarda gelebilir.
            kod_adaylari = [
                item.get("stockCode"),
                item.get("ticker"),
                item.get("companyCode"),
                item.get("issuerCode"),
                item.get("mkkMemberOid"),
                item.get("companyTitle"),
                item.get("companyName"),
            ]

            metin = " ".join([str(x) for x in kod_adaylari if x]) + " " + str(baslik)
            metin_upper = metin.upper()

            for sembol in sembol_set:
                if sembol in metin_upper:
                    puan, nedenler = kap_puan_hesapla(str(baslik))
                    if puan == 0:
                        puan = 1
                        nedenler = ["KAP bildirimi var"]

                    eski = kap_skorlari.get(sembol, {"puan": 0, "baslik": "", "nedenler": []})
                    yeni_puan = eski["puan"] + puan

                    kap_skorlari[sembol] = {
                        "puan": max(-5, min(8, yeni_puan)),
                        "baslik": str(baslik)[:120],
                        "nedenler": list(set(eski.get("nedenler", []) + nedenler))[:5],
                    }

        son_kap_cache["zaman"] = simdi
        son_kap_cache["veri"] = kap_skorlari
        print("KAP tarandı, eşleşen:", len(kap_skorlari))
        return kap_skorlari

    except Exception as e:
        print("KAP veri hatası:", e)
        son_kap_cache["zaman"] = simdi
        son_kap_cache["veri"] = kap_skorlari
        return kap_skorlari


def hedef_stop_hesapla(kategori):
    if "ELİT" in kategori or "KAP DESTEKLİ" in kategori:
        return 4, 8, 2.5
    if "SÜPER" in kategori:
        return 3.5, 7, 2.3
    if "GÜÇLÜ" in kategori:
        return 3, 6, 2
    return 2.5, 5, 1.8


def hisse_analiz(hisse, endeks_data, kap_skorlari):
    try:
        data = veri_cek(hisse)
        if data is None:
            return None

        son = data.iloc[-1]
        onceki = data.iloc[-2]

        fiyat = sayi_al(son["Close"])
        onceki_fiyat = sayi_al(onceki["Close"])
        high = sayi_al(son["High"])
        low = sayi_al(son["Low"])
        hacim = sayi_al(son["Volume"])

        if not fiyat or not onceki_fiyat or not high or not low or not hacim:
            return None

        ort_hacim = sayi_al(data["Volume"].tail(20).mean())
        if not ort_hacim or ort_hacim == 0:
            return None

        hacim_orani = hacim / ort_hacim
        gunluk = ((fiyat - onceki_fiyat) / onceki_fiyat) * 100

        endeks_son = endeks_data.iloc[-1]
        endeks_onceki = endeks_data.iloc[-2]

        endeks_fiyat = sayi_al(endeks_son["Close"])
        endeks_onceki_fiyat = sayi_al(endeks_onceki["Close"])

        if not endeks_fiyat or not endeks_onceki_fiyat:
            return None

        endeks_gunluk = ((endeks_fiyat - endeks_onceki_fiyat) / endeks_onceki_fiyat) * 100
        endekse_gore_guc = gunluk - endeks_gunluk

        son20_high = sayi_al(data["High"].tail(20).max())
        son20_low = sayi_al(data["Low"].tail(20).min())
        ema20 = sayi_al(data["Close"].ewm(span=20).mean().iloc[-1])
        ema50 = sayi_al(data["Close"].ewm(span=50).mean().iloc[-1])
        rsi = rsi_hesapla(data["Close"], 14)

        if not son20_high or not son20_low or not ema20 or not ema50:
            return None

        zirve_uzaklik = ((son20_high - fiyat) / fiyat) * 100
        sikisma_araligi = ((son20_high - son20_low) / son20_low) * 100
        kapanis_gucu = ((fiyat - low) / (high - low)) * 100 if high > low else 0
        trend_pozitif = fiyat > ema20 and ema20 >= ema50 * 0.98

        sembol = hisse.replace(".IS", "")
        kap = kap_skorlari.get(sembol, {"puan": 0, "baslik": "", "nedenler": []})
        kap_puan = kap.get("puan", 0)
        kap_nedenler = kap.get("nedenler", [])

        kategori = None
        skor = 0
        nedenler = []

        # 🏆 HAZIRLANIYOR: henüz uçmamış, sıkışma + hacim ilk kıpırtı
        hazir_skor = 0
        if sikisma_araligi <= 12:
            hazir_skor += 2
        if hacim_orani >= 1.25:
            hazir_skor += 2
        if 0 <= gunluk <= 3.5:
            hazir_skor += 2
        if zirve_uzaklik <= 7:
            hazir_skor += 2
        if endekse_gore_guc >= -0.5:
            hazir_skor += 1
        if trend_pozitif:
            hazir_skor += 1
        if rsi is not None and 45 <= rsi <= 65:
            hazir_skor += 1
        if kap_puan > 0:
            hazir_skor += min(2, kap_puan)

        if hazir_skor >= 8 and hacim_orani >= 1.2 and gunluk <= 4:
            kategori = "🏆 HAZIRLANIYOR"
            skor = hazir_skor
            nedenler = [
                "Henüz çok gitmemiş",
                "Hacim artmaya başlamış",
                "Sıkışma sonrası hareket potansiyeli var",
            ]
            if trend_pozitif:
                nedenler.append("Trend toparlanıyor")
            if rsi is not None and 45 <= rsi <= 65:
                nedenler.append("RSI sağlıklı bölgede")

        # 🔥 GÜÇLÜ HİSSE: hareket başlamış ama hacim şartı var
        guclu_skor = 0
        if hacim_orani >= 1.2:
            guclu_skor += 2
        if hacim_orani >= 2:
            guclu_skor += 2
        if endekse_gore_guc >= 1.5:
            guclu_skor += 3
        if gunluk >= 2:
            guclu_skor += 2
        if kapanis_gucu >= 70:
            guclu_skor += 2
        if trend_pozitif:
            guclu_skor += 1
        if rsi is not None and 50 <= rsi <= 75:
            guclu_skor += 1
        if kap_puan > 0:
            guclu_skor += min(3, kap_puan)

        if guclu_skor >= 8 and guclu_skor > skor and hacim_orani >= MIN_GUCLU_HACIM:
            kategori = "🔥 GÜÇLÜ HİSSE"
            skor = guclu_skor
            nedenler = [
                "Endeksten güçlü",
                "Hacim şartı sağlandı",
                "Kapanış güçlü bölgede",
            ]
            if trend_pozitif:
                nedenler.append("EMA trendi olumlu")

        # 🚀 SÜPER HİSSE: hacim + güç + zirve
        super_skor = 0
        if hacim_orani >= 2:
            super_skor += 2
        if hacim_orani >= 3:
            super_skor += 2
        if endekse_gore_guc >= 2.5:
            super_skor += 3
        if fiyat >= son20_high * 0.995:
            super_skor += 3
        if kapanis_gucu >= 80:
            super_skor += 2
        if 2 <= gunluk <= 8:
            super_skor += 1
        if trend_pozitif:
            super_skor += 1
        if rsi is not None and 55 <= rsi <= 78:
            super_skor += 1
        if kap_puan > 0:
            super_skor += min(4, kap_puan)

        if super_skor >= 10 and hacim_orani >= 1.8:
            kategori = "🚀 SÜPER HİSSE"
            skor = super_skor
            nedenler = [
                "Hacim güçlü",
                "Endeksten çok güçlü",
                "20 günlük zirveye yakın veya kırmış",
                "Kapanış güçlü",
            ]

        # 💎 ELİT / ⭐ KAP DESTEKLİ: en seçici kategori
        elit_skor = 0
        if hacim_orani >= 2.5:
            elit_skor += 3
        if endekse_gore_guc >= 3:
            elit_skor += 3
        if fiyat >= son20_high * 0.99:
            elit_skor += 2
        if kapanis_gucu >= 80:
            elit_skor += 2
        if trend_pozitif:
            elit_skor += 1
        if rsi is not None and 55 <= rsi <= 75:
            elit_skor += 1
        if kap_puan >= 3:
            elit_skor += 4

        if elit_skor >= 11 and hacim_orani >= 2:
            if kap_puan >= 3:
                kategori = "⭐ KAP DESTEKLİ ELİT HİSSE"
            else:
                kategori = "💎 ELİT HİSSE"
            skor = elit_skor
            nedenler = [
                "Endeksten çok güçlü",
                "Hacim yüksek",
                "Trend ve kapanış güçlü",
                "Zirve bölgesine yakın",
            ]

        if kap_puan > 0 and kategori is not None:
            nedenler.append("KAP desteği var: " + ", ".join(kap_nedenler[:3]))

        if kategori is None:
            return None

        hedef1, hedef2, stop = hedef_stop_hesapla(kategori)

        return {
            "hisse": sembol,
            "kategori": kategori,
            "fiyat": fiyat,
            "gunluk": gunluk,
            "endeks": endeks_gunluk,
            "guc": endekse_gore_guc,
            "hacim_orani": hacim_orani,
            "zirve_uzaklik": zirve_uzaklik,
            "kapanis_gucu": kapanis_gucu,
            "sikisma": sikisma_araligi,
            "rsi": rsi,
            "kap_puan": kap_puan,
            "kap_baslik": kap.get("baslik", ""),
            "skor": skor,
            "nedenler": nedenler,
            "hedef1": hedef1,
            "hedef2": hedef2,
            "stop": stop,
        }

    except Exception as e:
        print(hisse, "analiz hatası:", e)
        return None


def mesaj_olustur(s):
    rsi_text = f"%{s['rsi']:.1f}" if s.get("rsi") is not None else "Yok"
    kap_satiri = ""
    if s.get("kap_puan", 0) > 0:
        kap_satiri = f"\n📢 KAP Puanı: {s['kap_puan']}\n📰 KAP: {s.get('kap_baslik', '')}"

    return f"""
{s['kategori']}

📌 Hisse: <b>{s['hisse']}</b>
💰 Fiyat: {s['fiyat']:.2f} TL
📈 Günlük: %{s['gunluk']:.2f}
📊 BIST100: %{s['endeks']:.2f}
💪 Endekse Göre Güç: %{s['guc']:.2f}
🔥 Hacim: {s['hacim_orani']:.2f}x
🎯 Zirve Uzaklığı: %{s['zirve_uzaklik']:.2f}
📉 RSI: {rsi_text}
📦 Sıkışma: %{s['sikisma']:.2f}{kap_satiri}
⭐ Skor: {s['skor']}/14

✅ Nedenler:
{chr(10).join(["• " + n for n in s["nedenler"]])}

🎯 Hedef 1: +%{s['hedef1']}
🎯 Hedef 2: +%{s['hedef2']}
🛑 Stop: -%{s['stop']}

⚠️ Yatırım tavsiyesi değildir.
"""


def alarm_kontrol():
    print("BİST V2 taraması başladı:", datetime.now())

    endeks_data = veri_cek(ENDEKS)
    if endeks_data is None:
        print("BIST100 verisi alınamadı.")
        return

    kap_skorlari = kap_bildirimlerini_cek()

    sonuclar = []
    for hisse in HISSELER:
        sonuc = hisse_analiz(hisse, endeks_data, kap_skorlari)
        if sonuc:
            sonuclar.append(sonuc)

    sonuclar = sorted(sonuclar, key=lambda x: x["skor"], reverse=True)

    if not sonuclar:
        print("Şu an uygun BİST V2 adayı yok.")
        return

    sayac = 0
    for s in sonuclar:
        if sayac >= MAX_SINYAL:
            break

        anahtar = s["hisse"] + "_" + s["kategori"]
        simdi = time.time()

        if anahtar in gonderilenler and simdi - gonderilenler[anahtar] < TEKRAR_SURESI:
            continue

        telegram_gonder(mesaj_olustur(s))
        gonderilenler[anahtar] = simdi
        sayac += 1

    print("Gönderilen sinyal sayısı:", sayac)


telegram_gonder("✅ BIST BOT V2.1 BAŞLADI\nBIST100 + KAP + ELİT + RSI aktif.")

while True:
    try:
        alarm_kontrol()
    except Exception as e:
        print("Genel hata:", e)

    print("15 dakika bekleniyor...")
    time.sleep(TARAMA_SURESI)
