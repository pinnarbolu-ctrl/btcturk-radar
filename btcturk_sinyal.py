# ==========================================
# S49 V52 | KOD KALİTESİ + 3 GÜNLÜK KEŞİF | EMİRSİZ RADAR
# Amaç: +%5 yapanların ortak güç yapısını bilgi/puan olarak kullanmak; iyi adayları sert eşiklerle boğmamak.
# AL/SAT yalnızca tarayıcı sinyali ve bilgilendirme etiketidir; emir, pozisyon ve zarar-kes takibi yoktur.
# Taban: main (21).py
# Teknik radar + 1-3-5-10 dk erken yakalama
# Giris/Devam skorları sadece bilgi, AL için veto DEGIL
# Fast Scan V1: 60 sn hızlı ön tarama + 5 dk tam tarama
# AL Relax V1: normal AL için ADX 27 / AI 80
# Kod Önerisi V52: 3dk/5dk momentum + S49'a özel Kod Öneri Kalitesi katmanı
# 3 Günlük Keşif Motoru: ilk rapor 06.10.2026 08:00 TR; sonra her 3 günde bir 08:00.
# AL olan/olmayan güçlü teknik adayları 3 saat izler;
# +%5 yapan, %1-5 gidip sönen ve zayıf kalan grupları karşılaştırır.
# Tekli eşik + ikili kombinasyon + rejim + en çok güçlenen coin profili üzerinden
# KOD ÖNERİSİ üretir; kodu otomatik değiştirmez.
# Not: V11 Genel Güç eşiği körlemesine taşınmadı; S49 kendi ölçeğinde normalize edilerek kalite katmanına alındı.
# Final Cleanup / Core Candidate Scanner
# Candidate thresholds synced with latest working Coin Radar
# ==========================================

import os
import time
import json
import requests
import feedparser
import statistics


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

CHAT_IDS = [2097448038]

TARAMA_SURESI = 60
KAR_TAKIP_SURESI = 15          # Açık AL sinyallerinde +%5 kontrolü
TAM_TARAMA_DONGUSU = 5          # 5 x 60 sn = yaklaşık 5 dk
HIZLI_HAREKET_ESIGI = 0.40      # 1 dakikalık fiyat değişimi %0.40+ ise hemen derin analiz
son_fiyatlar = {}
# Fast Scan V2: her coin icin son birkac ticker fiyatini API cagrisi yapmadan hafizada tut.
# Boylece tek dakikada %0.40 sicramayan ama 3-5 dakikada basamakli hizlanan hareketler de gorulur.
son_ticker_gecmisi = {}
TICKER_GECMIS_UZUNLUK = 6
tarama_sayaci = 0
SON_PIYASA_MEDYAN_60 = 0.0  # Son tam taramadaki TRY coinleri 60dk medyanı

# Early Capture V1: önceki taramadaki hızlanmayı ölçmek için hafıza.
onceki_tarama = {}

# Kalıcılık V1: yalnızca bilgi amaçlıdır; Radar/AL filtrelerini DEĞİŞTİRMEZ.
kalicilik_gecmisi = {}
KALICILIK_GECMIS_UZUNLUK = 5

# Çoklu Güç Havuzu:
# Güçlenme işareti veren coin 5 dakika boyunca, 1 dk fiyat hareketi %0.40 altında kalsa bile izlenir.
guc_izleme_havuzu = {}
GUC_IZLEME_SURESI = 5 * 60

# Aynı kararın tekrar Telegram gönderimini engeller.
son_ai_kararlar = {}

# =========================
# V57 KARAR IZİ / NEDEN ALINMADI
# Her aday için RADAR'ın neden AL verdiğini veya Telegram'a neden gitmediğini Railway loguna yazar.
# Telegram mesaj sayısını artırmaz.
# =========================
def al_karar_izi(symbol, asama, sonuc, **m):
    try:
        parcalar = [f"[AL KARAR] {symbol}", f"aşama={asama}", f"sonuç={sonuc}"]
        for k, v in m.items():
            if v is None:
                continue
            if isinstance(v, float):
                parcalar.append(f"{k}={v:.3f}")
            else:
                parcalar.append(f"{k}={v}")
        print(" | ".join(parcalar))
    except Exception as e:
        print(f"[AL KARAR LOG HATA] {symbol}: {e}")

# V52+ KOD ÖNERİ KALİTESİ
# Rapor bulguları seçicilik/öncelik puanına eklenir; tekil eşikler sert veto değildir.
# Genel Güç ve Kalıcılık bandı eşikleri yalnız Güçlü piyasa rejiminde bonus verir.
KOD_ONERI_KALITE_MIN = 76.0
KOD_ONERI_D3_ESIK = 0.31
KOD_ONERI_D5_ESIK = 0.50
KOD_ONERI_MOMENTUM_ESIK = 55.87
KOD_ONERI_GENEL_ESIK_GUCLU = 65.50
KOD_ONERI_KALICILIK_BANT_ESIK = 100.0

# AL Rejim / Seçicilik Öğrenmesi
# AL öğrenme verisini Railway Volume varsa kalıcı alanda tut.
# AL_OGRENME_DOSYA env ile özel yol verilmişse onu kullanır.
_RAILWAY_VOLUME = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
_AL_DEFAULT_DIR = _RAILWAY_VOLUME if _RAILWAY_VOLUME else "."
AL_OGRENME_DOSYA = os.getenv("AL_OGRENME_DOSYA", os.path.join(_AL_DEFAULT_DIR, "al_ogrenme_rejim.json"))
AL_OGRENME_SURESI = 3 * 60 * 60
AL_BILDIR_KAR_ESIK = 5.0  # AL sinyal fiyatından +%5 görülünce tek bilgilendirme mesajı
SINYAL_SIRA_PENCERE = 24 * 60 * 60
SINYAL_SIRA_DOSYA = os.path.join(_AL_DEFAULT_DIR, "s49_sinyal_sira.json")
REJIM_RAPOR_ARALIGI = 24 * 60 * 60
SON_REJIM_RAPOR_ZAMANI = time.time()

# 3 GÜNLÜK +%5 YAKALAMA BAŞARI RAPORU
# İlk ortak rapor: 06.10.2026 08:00 (Türkiye saati, UTC+3).
# Sonraki raporlar her 3 günde bir yine 08:00'de planlanır.
YUZDE5_RAPOR_ARALIGI = 3 * 24 * 60 * 60
S49_ILK_3GUN_RAPOR_TS = 1791262800.0  # 2026-10-06 05:00 UTC = 08:00 TR
YUZDE5_RAPOR_ETIKETI = "BTCTÜRK SİNYAL 49"
_YUZDE5_META_DOSYA = os.path.join(_AL_DEFAULT_DIR, "yuzde5_basariraporu_sinyal49.json")

# 3 GÜNLÜK KEŞİF / KOD GELİŞTİRME MOTORU
KESIF_RAPOR_ARALIGI = 3 * 24 * 60 * 60
KESIF_IZLEME_SURESI = 3 * 60 * 60
KESIF_ORNEKLEME_ARALIGI = 30 * 60   # aynı coin için en fazla 30 dk'da bir yeni gözlem
KESIF_DOSYA = os.path.join(_AL_DEFAULT_DIR, "s49_guc_kesif_3gun.json")
KESIF_META_DOSYA = os.path.join(_AL_DEFAULT_DIR, "s49_guc_kesif_meta.json")
KESIF_MAX_KAYIT = 4000


def _s49_planli_rapor_zamani(simdi, meta):
    """08:00 Türkiye saatine sabitlenmiş 3 günlük rapor çevrimini yönetir.

    Dönüş: (gonderilsin_mi, planli_ts). İlk rapor 06.10.2026 08:00 TR,
    sonra her 72 saatte bir aynı saatte. Aynı çevrim ikinci kez gönderilmez.
    """
    if simdi < S49_ILK_3GUN_RAPOR_TS:
        return False, S49_ILK_3GUN_RAPOR_TS
    idx = int((simdi - S49_ILK_3GUN_RAPOR_TS) // YUZDE5_RAPOR_ARALIGI)
    planli = S49_ILK_3GUN_RAPOR_TS + idx * YUZDE5_RAPOR_ARALIGI
    son_planli = float(meta.get("son_planli_rapor_ts", 0) or 0)
    return son_planli < planli, planli



def _yuzde5_meta_yukle():
    try:
        if os.path.exists(_YUZDE5_META_DOSYA):
            with open(_YUZDE5_META_DOSYA, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
    except Exception as e:
        print("+%5 rapor meta okunamadı:", e)
    return {}


def _yuzde5_meta_kaydet(meta):
    try:
        klasor = os.path.dirname(os.path.abspath(_YUZDE5_META_DOSYA))
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        with open(_YUZDE5_META_DOSYA, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    except Exception as e:
        print("+%5 rapor meta yazılamadı:", e)


def _sinyal_sira_yukle():
    try:
        if os.path.exists(SINYAL_SIRA_DOSYA):
            with open(SINYAL_SIRA_DOSYA, "r", encoding="utf-8") as f:
                veri = json.load(f)
                return veri if isinstance(veri, dict) else {}
    except Exception as e:
        print("Sinyal sıra dosyası okunamadı:", e)
    return {}


def _sinyal_sira_kaydet():
    try:
        klasor = os.path.dirname(os.path.abspath(SINYAL_SIRA_DOSYA))
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        with open(SINYAL_SIRA_DOSYA, "w", encoding="utf-8") as f:
            json.dump(SINYAL_SIRA_GECMISI, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Sinyal sıra dosyası yazılamadı:", e)


def _sinyal_sira_hazirla(symbol):
    simdi = time.time()
    gecmis = SINYAL_SIRA_GECMISI.get(symbol, [])
    aktif = [
        x for x in gecmis
        if simdi - float(x.get("ts", 0) or 0) <= SINYAL_SIRA_PENCERE
    ]
    SINYAL_SIRA_GECMISI[symbol] = aktif
    return len(aktif) + 1, any(bool(x.get("hit5")) for x in aktif)


def _sinyal_sira_ekle(symbol, fiyat):
    simdi = time.time()
    aktif = [
        x for x in SINYAL_SIRA_GECMISI.get(symbol, [])
        if simdi - float(x.get("ts", 0) or 0) <= SINYAL_SIRA_PENCERE
    ]
    event_id = f"{symbol}-{int(simdi * 1000)}"
    aktif.append({"id": event_id, "ts": simdi, "fiyat": float(fiyat or 0), "hit5": False})
    SINYAL_SIRA_GECMISI[symbol] = aktif
    _sinyal_sira_kaydet()
    return event_id


def _sinyal_sira_hit5_isaretle(symbol, event_id=None):
    degisti = False
    for olay in reversed(SINYAL_SIRA_GECMISI.get(symbol, [])):
        if event_id is None or olay.get("id") == event_id:
            if not olay.get("hit5"):
                olay["hit5"] = True
                degisti = True
            break
    if degisti:
        _sinyal_sira_kaydet()


def _sira_etiketi(n):
    return f"{int(n)}️⃣"


SINYAL_SIRA_GECMISI = _sinyal_sira_yukle()


_YUZDE5_META = _yuzde5_meta_yukle()
if not _YUZDE5_META.get("baslangic"):
    _YUZDE5_META["baslangic"] = time.time()
    _YUZDE5_META["son_rapor"] = _YUZDE5_META["baslangic"]
    _yuzde5_meta_kaydet(_YUZDE5_META)


def _pct(yeni, eski):
    try:
        yeni = float(yeni)
        eski = float(eski)
        return ((yeni / eski) - 1.0) * 100 if eski else 0.0
    except Exception:
        return 0.0


def dakika_veri_getir(symbol, dakika=20):
    simdi = int(time.time())
    url = (
        f"https://graph-api.btcturk.com/v1/klines/history?"
        f"symbol={symbol}&resolution=1&from={simdi - (dakika * 60)}&to={simdi}"
    )
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    return r.json()


def _pct_son(c, n):
    if len(c) <= n or not c[-1-n]:
        return 0.0
    return ((c[-1] - c[-1-n]) / c[-1-n]) * 100


def mikro_ivme_hesapla(symbol):
    """1-3-5-10 dk fiyat/hacim ivmesi. Ana motoru bozmaz, erken adayı destekler."""
    try:
        d = dakika_veri_getir(symbol, 20)
        c = d.get("c", [])
        l = d.get("l", [])
        v = d.get("v", [])
        if len(c) < 12 or len(v) < 12:
            return {}

        d1 = _pct_son(c, 1)
        d3 = _pct_son(c, 3)
        d5 = _pct_son(c, 5)
        d10 = _pct_son(c, 10)

        prev5 = sum(v[-6:-1]) / 5 if sum(v[-6:-1]) > 0 else 0
        hacim1x = (v[-1] / prev5) if prev5 > 0 else 0
        son3 = sum(v[-3:]) / 3
        once3 = sum(v[-6:-3]) / 3
        hacim_ivme = (son3 / once3) if once3 > 0 else 0

        basamak = False
        if len(c) >= 6:
            ks = c[-5:]
            ds = l[-5:] if len(l) >= 5 else ks
            yukselen_k = sum(1 for i in range(1, 5) if ks[i] >= ks[i-1]) >= 3
            yukselen_d = sum(1 for i in range(1, 5) if ds[i] >= ds[i-1]) >= 3
            basamak = yukselen_k and yukselen_d

        fiyat_ivme = d1 > 0 and d3 > 0 and (
            d1 >= (d3 / 3.0) * 1.15 or (d3 / 3.0) >= (d5 / 5.0) * 1.10
        )
        hacim_ivmeleniyor = hacim1x >= 1.35 or hacim_ivme >= 1.25
        sisti = d10 >= 6.5 or d5 >= 5.0 or d3 >= 4.0

        skor = 0
        if d1 >= 0.15: skor += 10
        if d1 >= 0.30: skor += 8
        if d3 >= 0.45: skor += 12
        if d3 >= 0.80: skor += 8
        if d5 >= 0.70: skor += 10
        if 0.8 <= d10 <= 5.5: skor += 8
        if hacim1x >= 1.35: skor += 12
        if hacim1x >= 1.80: skor += 8
        if hacim_ivme >= 1.25: skor += 10
        if fiyat_ivme: skor += 7
        if hacim_ivmeleniyor: skor += 7
        if basamak: skor += 10
        if sisti: skor -= 30

        return {
            "d1": round(d1, 3), "d3": round(d3, 3),
            "d5": round(d5, 3), "d10": round(d10, 3),
            "hacim1x": round(hacim1x, 2),
            "hacim_ivme": round(hacim_ivme, 2),
            "fiyat_ivme": fiyat_ivme,
            "hacim_ivmeleniyor": hacim_ivmeleniyor,
            "basamak": basamak,
            "sisti": sisti,
            "skor": max(0, min(100, skor)),
        }
    except Exception as e:
        print(f"[MIKRO] {symbol}: {e}")
        return {}


def destek_skorlari(aday):
    """Giriş/Devam puanları bilgi amaçlıdır; tek başına AL'ı engellemez."""
    t = aday.get("teknik") or {}
    m = aday.get("mikro") or {}
    rsi = t.get("rsi")
    adx = t.get("adx")
    macd = t.get("macd_hist")
    ema20, ema50 = t.get("ema20"), t.get("ema50")
    fiyat = float(aday.get("fiyat", 0) or 0)

    ema_ok = ema20 is not None and ema50 is not None and ema20 > ema50 and fiyat > ema20
    macd_ok = macd is not None and macd > 0

    giris = 40
    if ema_ok: giris += 15
    if macd_ok: giris += 12
    if rsi is not None and 50 <= rsi <= 68: giris += 12
    elif rsi is not None and 68 < rsi <= 75: giris += 5
    elif rsi is not None and rsi > 78: giris -= 12
    if adx is not None and adx >= 30: giris += 10
    elif adx is not None and adx >= 25: giris += 6
    if m.get("basamak"): giris += 6
    if float(m.get("hacim_ivme", 0) or 0) >= 1.25: giris += 5

    devam = 35
    devam += min(20, max(0, float(aday.get("ai_skoru", 0) or 0) - 70) * 0.5)
    devam += min(15, max(0, float(aday.get("radar_skoru", 0) or 0) - 55) * 0.35)
    if adx is not None and adx >= 30: devam += 10
    if macd_ok: devam += 8
    if aday.get("btcden_guclu"): devam += 6
    if aday.get("momentum_hizlaniyor"): devam += 4
    if aday.get("hacim_hizlaniyor"): devam += 4

    return round(max(0, min(100, giris)), 1), round(max(0, min(100, devam)), 1)


def kalicilik_skoru_hesapla(aday):
    """Kalıcılık skoru yalnızca bilgi üretir; karar ve filtreleri değiştirmez."""
    symbol = aday.get("symbol", "")
    t = aday.get("teknik") or {}
    m = aday.get("mikro") or {}

    fiyat = float(aday.get("fiyat", 0) or 0)
    hacim = float(aday.get("hacim", 0) or 0)
    d1 = float(m.get("d1", 0) or 0)
    d3m = float(m.get("d3", 0) or 0)
    d5m = float(m.get("d5", 0) or 0)
    d10m = float(m.get("d10", 0) or 0)
    degisim3 = float(aday.get("degisim3", 0) or 0)
    btc_fark3 = float(aday.get("btc_fark3", 0) or 0)
    adx = t.get("adx")
    rsi = t.get("rsi")
    macd = t.get("macd_hist")
    ema20, ema50 = t.get("ema20"), t.get("ema50")

    ema_ok = ema20 is not None and ema50 is not None and fiyat > 0 and ema20 > ema50 and fiyat > ema20
    macd_ok = macd is not None and macd > 0

    skor = 35.0
    nedenler = []

    if ema_ok:
        skor += 8; nedenler.append("EMA trendi korunuyor")
    if macd_ok:
        skor += 7; nedenler.append("MACD pozitif")
    if adx is not None:
        if adx >= 40:
            skor += 14; nedenler.append("ADX çok güçlü")
        elif adx >= 30:
            skor += 10; nedenler.append("ADX güçlü")
        elif adx >= 25:
            skor += 5
        elif adx < 20:
            skor -= 8

    if hacim >= 8:
        skor += 10; nedenler.append("hacim çok güçlü")
    elif hacim >= 5:
        skor += 8; nedenler.append("hacim güçlü")
    elif hacim >= 2:
        skor += 4
    elif hacim < 0.8:
        skor -= 6

    if aday.get("hacim_hizlaniyor"):
        skor += 5; nedenler.append("hacim hızlanıyor")
    if aday.get("momentum_hizlaniyor"):
        skor += 4; nedenler.append("momentum hızlanıyor")
    if aday.get("btc_farki_aciliyor"):
        skor += 4; nedenler.append("BTC farkı açılıyor")
    if aday.get("lider_gucleniyor"):
        skor += 4; nedenler.append("liderlik güçleniyor")
    if aday.get("basamakli_trend"):
        skor += 6; nedenler.append("basamaklı yapı")

    if btc_fark3 >= 2:
        skor += 7; nedenler.append("BTC'den belirgin güçlü")
    elif btc_fark3 >= 0.5:
        skor += 4
    elif btc_fark3 < -1:
        skor -= 7

    if d3m > 0 and d5m > 0 and d10m > 0:
        skor += 5
    if 0.5 <= d10m <= 5.5:
        skor += 4
    if m.get("basamak"):
        skor += 4
    if m.get("sisti") or d10m >= 7 or d5m >= 5:
        skor -= 12; nedenler.append("kısa vadede şişme riski")
    if d1 < -0.8 and d3m < 0:
        skor -= 5

    if rsi is not None:
        if 52 <= rsi <= 70:
            skor += 5
        elif 70 < rsi <= 77:
            skor += 1
        elif rsi > 82:
            skor -= 10; nedenler.append("RSI aşırı sıcak")
        elif rsi < 45:
            skor -= 6

    hist = kalicilik_gecmisi.setdefault(symbol, [])
    if hist:
        sonlar = hist[-3:]
        hacim_koruma = sum(1 for x in sonlar if hacim >= x.get("hacim", hacim) * 0.80)
        trend_koruma = sum(1 for x in sonlar if degisim3 >= x.get("degisim3", degisim3) - 0.50)
        btc_koruma = sum(1 for x in sonlar if btc_fark3 >= x.get("btc_fark3", btc_fark3) - 0.40)
        n = len(sonlar)
        if n >= 2 and hacim_koruma >= n - 1:
            skor += 6; nedenler.append("hacim birkaç taramadır korunuyor")
        if n >= 2 and trend_koruma >= n - 1:
            skor += 7; nedenler.append("3s güç birkaç taramadır korunuyor")
        if n >= 2 and btc_koruma >= n - 1:
            skor += 4
        if n >= 2 and hacim_koruma == 0 and trend_koruma == 0:
            skor -= 8; nedenler.append("güç hızlı sönüyor")

    hist.append({"zaman": time.time(), "hacim": hacim, "degisim3": degisim3, "btc_fark3": btc_fark3, "d1": d1, "d3m": d3m})
    if len(hist) > KALICILIK_GECMIS_UZUNLUK:
        del hist[:-KALICILIK_GECMIS_UZUNLUK]

    skor = round(max(0, min(100, skor)), 1)
    if skor >= 80:
        etiket = "Uzun devam adayı"
    elif skor >= 68:
        etiket = "Devam güçlü"
    elif skor >= 55:
        etiket = "Orta / izle"
    else:
        etiket = "Hızlı hareket / dönüş riski"
    return skor, etiket, nedenler[:4]



def bes_plus_profil_yumusak(aday):
    """+%5 ve üstü hareketlerde gözlenen ortak yapıyı 0-100 puanlar.
    Bu puan ASLA tek başına AL vetosu değildir; iyi adayları sert eşiklerle kaybetmemek için bilgi/öncelik amaçlıdır.
    """
    mikro = aday.get("mikro") or {}
    teknik = aday.get("teknik") or {}
    d1 = float(mikro.get("d1", 0) or 0)
    d3 = float(mikro.get("d3", 0) or 0)
    d5 = float(mikro.get("d5", 0) or 0)
    d10 = float(mikro.get("d10", 0) or 0)
    hacim = float(aday.get("hacim", 0) or 0)
    radar = float(aday.get("radar_skoru", 0) or 0)
    devam = float(aday.get("devam_gucu", 0) or 0)
    kal = float(aday.get("kalicilik_skoru", 0) or 0)
    rel = int(aday.get("goreceli_guc_bonus", 0) or 0)
    adx = teknik.get("adx")

    skor = 0.0
    nedenler = []

    if rel >= 2:
        skor += 18; nedenler.append("60dk göreceli güç +2")
    elif rel == 1:
        skor += 8; nedenler.append("60dk göreceli güç +1")

    if d1 > 0 and d3 > 0 and d5 > 0 and d10 > 0:
        skor += 18; nedenler.append("1/3/5/10dk birlikte pozitif")
    elif d3 > 0 and d5 > 0 and d10 > 0:
        skor += 12; nedenler.append("3/5/10dk birlikte pozitif")
    elif d3 > 0 and d5 > 0:
        skor += 6; nedenler.append("3/5dk pozitif")

    # Hacim ve Radar ayrı ayrı destek verir; biri düşük diye kazananı sert veto etmeyiz.
    if hacim >= 7:
        skor += 14; nedenler.append("hacim çok güçlü")
    elif hacim >= 5:
        skor += 11; nedenler.append("hacim güçlü")
    elif hacim >= 3:
        skor += 8
    elif hacim >= 2:
        skor += 4

    if radar >= 90:
        skor += 12; nedenler.append("Radar çok güçlü")
    elif radar >= 80:
        skor += 9
    elif radar >= 70:
        skor += 6
    elif radar >= 60:
        skor += 3

    if devam >= 85:
        skor += 14; nedenler.append("Devam çok yüksek")
    elif devam >= 75:
        skor += 10; nedenler.append("Devam yüksek")
    elif devam >= 65:
        skor += 6

    if kal >= 95:
        skor += 10; nedenler.append("Kalıcılık çok yüksek")
    elif kal >= 85:
        skor += 7
    elif kal >= 75:
        skor += 4

    if aday.get("momentum_hizlaniyor"):
        skor += 5; nedenler.append("momentum hızlanıyor")
    if aday.get("btc_farki_aciliyor"):
        skor += 4; nedenler.append("BTC farkı açılıyor")
    if aday.get("basamakli_trend"):
        skor += 4; nedenler.append("basamaklı trend")
    if aday.get("hacim_hizlaniyor"):
        skor += 3; nedenler.append("hacim hızlanıyor")
    if adx is not None and float(adx) >= 30:
        skor += 3

    skor = round(max(0.0, min(100.0, skor)), 1)
    if skor >= 80:
        etiket = "🔥 5+ güçlü benzerlik"
    elif skor >= 65:
        etiket = "✅ 5+ uyumlu"
    elif skor >= 50:
        etiket = "🟡 5+ orta"
    else:
        etiket = "⚪ 5+ zayıf benzerlik"
    return skor, etiket, nedenler[:6]

def _rejim_etiketi(x, guclu=1.0, zayif=-1.0):
    try:
        x = float(x)
    except Exception:
        x = 0.0
    if x >= guclu:
        return "Güçlü"
    if x <= zayif:
        return "Zayıf"
    return "Yatay"



def _kesif_json_yukle(path, varsayilan):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d
    except Exception as e:
        print("3 günlük keşif dosyası okunamadı:", e)
    return varsayilan


def _kesif_kaydet():
    try:
        klasor = os.path.dirname(os.path.abspath(KESIF_DOSYA))
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        # 7 günden eski tamamlanmış keşif kayıtlarını buda; disk büyümesini sınırla.
        simdi = time.time()
        esik = simdi - 7 * 24 * 60 * 60
        temiz = [x for x in KESIF_KAYITLARI if (not x.get("tamamlandi")) or float(x.get("zaman", 0) or 0) >= esik]
        if len(temiz) > KESIF_MAX_KAYIT:
            temiz = temiz[-KESIF_MAX_KAYIT:]
        KESIF_KAYITLARI[:] = temiz
        with open(KESIF_DOSYA, "w", encoding="utf-8") as f:
            json.dump(KESIF_KAYITLARI, f, ensure_ascii=False)
    except Exception as e:
        print("3 günlük keşif dosyası yazılamadı:", e)


def _kesif_meta_kaydet():
    try:
        klasor = os.path.dirname(os.path.abspath(KESIF_META_DOSYA))
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        with open(KESIF_META_DOSYA, "w", encoding="utf-8") as f:
            json.dump(KESIF_META, f, ensure_ascii=False)
    except Exception as e:
        print("3 günlük keşif meta yazılamadı:", e)


def kesif_gozlem_baslat(aday, btc_d, piyasa_medyan3):
    """AL şartı aramadan en güçlü teknik havuzdaki adayı gölge olarak izler."""
    symbol = aday.get("symbol")
    giris = float(aday.get("fiyat", 0) or 0)
    if not symbol or giris <= 0:
        return
    simdi = time.time()
    # Aynı coin için çok sık kayıt açıp aynı hareketi yüzlerce kez sayma.
    for k in reversed(KESIF_KAYITLARI[-300:]):
        if k.get("symbol") == symbol and simdi - float(k.get("zaman", 0) or 0) < KESIF_ORNEKLEME_ARALIGI:
            return

    m = aday.get("mikro") or {}
    teknik = aday.get("teknik") or {}
    try:
        adx = float(teknik.get("adx", 0) or 0)
    except (TypeError, ValueError):
        adx = 0.0
    rec = {
        "symbol": symbol, "zaman": simdi, "giris": giris,
        "max_getiri": 0.0, "min_getiri": 0.0, "son_getiri": None, "tamamlandi": False,
        "hedef4_sure_sn": None, "hedef5_sure_sn": None, "hedef7_sure_sn": None, "hedef20_sure_sn": None,
        "geri_verme_puan": None, "geri_verme_orani": None,
        "karar": aday.get("karar", ""), "kategori": aday.get("radar_kategori", ""),
        "piyasa_rejim": _rejim_etiketi(piyasa_medyan3),
        "btc_rejim": _rejim_etiketi(float(btc_d.get("3s", 0) or 0)),
        "radar": float(aday.get("radar_skoru", 0) or 0),
        "genel": float(aday.get("genel_skor", 0) or 0),
        "kalite": float(aday.get("kalite_skoru", 0) or 0),
        "kod_kalite": float(aday.get("kod_oneri_kalite", 0) or 0),
        "kod_genel": float(aday.get("kod_oneri_genel_norm", 0) or 0),
        "kod_momentum": float(aday.get("kod_oneri_momentum_kalite", 0) or 0),
        "kod_momentum_blok": float(aday.get("kod_oneri_momentum_blok", 0) or 0),
        "kod_kalicilik_bant": float(aday.get("kod_oneri_kalicilik_bant", 0) or 0),
        "kod_genel_bonus": float(aday.get("kod_oneri_genel_bonus", 0) or 0),
        "kod_momentum_bonus": float(aday.get("kod_oneri_momentum_bonus", 0) or 0),
        "kod_momentum_esik_uygun": bool(float(aday.get("kod_oneri_momentum_kalite", 0) or 0) >= KOD_ONERI_MOMENTUM_ESIK),
        "kod_genel_esik_guclu_uygun": bool(_rejim_etiketi(piyasa_medyan3) == "Güçlü" and float(aday.get("kod_oneri_genel_norm", 0) or 0) >= KOD_ONERI_GENEL_ESIK_GUCLU),
        "kod_kal_bant_guclu_uygun": bool(_rejim_etiketi(piyasa_medyan3) == "Güçlü" and float(aday.get("kod_oneri_kalicilik_bant", 0) or 0) >= KOD_ONERI_KALICILIK_BANT_ESIK),
        "kesif_v": 4,
        "ai": float(aday.get("ai_skoru", 0) or 0),
        "devam": float(aday.get("devam_gucu", 0) or 0),
        "kalicilik": float(aday.get("kalicilik_skoru", 0) or 0),
        "hacim": float(aday.get("hacim", 0) or 0),
        "degisim1": float(aday.get("degisim1", 0) or 0),
        "degisim3": float(aday.get("degisim3", 0) or 0),
        "btc_fark3": float(aday.get("btc_fark3", 0) or 0),
        "btc_guc": float(aday.get("btc_guc_skoru", 0) or 0),
        "lider": float(aday.get("lider_skoru", 0) or 0),
        "rel": int(aday.get("goreceli_guc_bonus", 0) or 0),
        "d1": float(m.get("d1", 0) or 0), "d3": float(m.get("d3", 0) or 0),
        "d5": float(m.get("d5", 0) or 0), "d10": float(m.get("d10", 0) or 0),
        "mikro_skor": float(m.get("skor", 0) or 0),
        "hacim_hiz": bool(aday.get("hacim_hizlaniyor")),
        "momentum_hiz": bool(aday.get("momentum_hizlaniyor")),
        "btc_fark_ac": bool(aday.get("btc_farki_aciliyor")),
        "lider_guc": bool(aday.get("lider_gucleniyor")),
        "basamak": bool(aday.get("basamakli_trend")),
        "trend_cok_guclu": adx >= 30.0,
    }
    KESIF_KAYITLARI.append(rec)
    _kesif_kaydet()


def kesif_gozlem_guncelle(ticker):
    if not KESIF_KAYITLARI:
        return
    simdi = time.time()
    fiyatlar = {}
    for c in ticker:
        try:
            sy = c.get("pair", "")
            f = float(c.get("last", 0) or 0)
            if sy and f > 0:
                fiyatlar[sy] = f
        except Exception:
            pass
    degisti = False
    for k in KESIF_KAYITLARI:
        if k.get("tamamlandi"):
            continue
        f = fiyatlar.get(k.get("symbol"))
        g = float(k.get("giris", 0) or 0)
        if f and g > 0:
            r = _pct(f, g)
            k["max_getiri"] = round(max(float(k.get("max_getiri", 0) or 0), r), 3)
            k["min_getiri"] = round(min(float(k.get("min_getiri", 0) or 0), r), 3)
            gecen_sn = max(0, int(simdi - float(k.get("zaman", simdi))))
            for hedef in (4, 5, 7, 20):
                alan = f"hedef{hedef}_sure_sn"
                if r >= hedef and k.get(alan) is None:
                    k[alan] = gecen_sn
            degisti = True
        if simdi - float(k.get("zaman", simdi)) >= KESIF_IZLEME_SURESI:
            if f and g > 0:
                k["son_getiri"] = round(_pct(f, g), 3)
            tepe = float(k.get("max_getiri", 0) or 0)
            son = float(k.get("son_getiri", 0) or 0)
            geri_puan = max(0.0, tepe - son)
            k["geri_verme_puan"] = round(geri_puan, 3)
            k["geri_verme_orani"] = round(min(100.0, geri_puan / tepe * 100.0), 1) if tepe > 0 else 0.0
            k["tamamlandi"] = True
            k["tamamlanma_zamani"] = simdi
            degisti = True
    if degisti:
        _kesif_kaydet()


def _oran5(grup):
    if not grup:
        return 0.0
    return sum(1 for x in grup if float(x.get("max_getiri", 0) or 0) >= 5.0) / len(grup) * 100.0


def _ortalama(grup, alan):
    vals = []
    for x in grup:
        try:
            vals.append(float(x.get(alan, 0) or 0))
        except Exception:
            pass
    return sum(vals) / len(vals) if vals else 0.0


def _medyan(grup, alan):
    vals = []
    for x in grup:
        try:
            vals.append(float(x.get(alan, 0) or 0))
        except Exception:
            pass
    return statistics.median(vals) if vals else 0.0


def _tekli_kesifler(grup):
    """Verinin kendi medyanında bölerek yüksek/alt grubun +%5 farkını bulur."""
    alanlar = [
        ("3dk momentum", "d3"), ("5dk momentum", "d5"), ("10dk momentum", "d10"),
        ("Kod Öneri Kalitesi", "kod_kalite"), ("Kod Genel Güç", "kod_genel"),
        ("Genel Güç / Momentum bloğu", "kod_momentum"), ("S49 Momentum Bloğu", "kod_momentum_blok"),
        ("Kod Kalıcılık Bandı", "kod_kalicilik_bant"),
        ("Devam Gücü", "devam"), ("Kalıcılık", "kalicilik"), ("Genel Güç", "genel"),
        ("Radar", "radar"), ("AI", "ai"), ("Hacim", "hacim"), ("Lider skoru", "lider"),
        ("BTC farkı 3s", "btc_fark3"), ("Mikro skor", "mikro_skor"),
    ]
    out = []
    for ad, key in alanlar:
        esik = _medyan(grup, key)
        hi = [x for x in grup if float(x.get(key, 0) or 0) >= esik]
        lo = [x for x in grup if float(x.get(key, 0) or 0) < esik]
        if len(hi) < 8 or len(lo) < 8:
            continue
        oh, ol = _oran5(hi), _oran5(lo)
        out.append((abs(oh-ol), oh-ol, ad, key, esik, oh, ol, len(hi), len(lo)))
    return sorted(out, reverse=True)


def _kombinasyon_kesifleri(grup):
    """Önceden yazılmış tek bir kombinasyona bağlı kalmadan ikili etkileşim tarar."""
    if len(grup) < 30:
        return []
    specs = []
    for ad, key in [
        ("3dk mom", "d3"), ("5dk mom", "d5"), ("Kod Kalitesi", "kod_kalite"),
        ("Kod Genel Güç", "kod_genel"), ("Genel Güç / Momentum bloğu", "kod_momentum"),
        ("S49 Momentum Bloğu", "kod_momentum_blok"), ("Kod Kalıcılık Bandı", "kod_kalicilik_bant"),
        ("Devam", "devam"), ("Kalıcılık", "kalicilik"), ("Genel Güç", "genel"), ("Hacim", "hacim"),
        ("Lider", "lider"), ("BTC farkı", "btc_fark3")
    ]:
        specs.append((ad, key, _medyan(grup, key), "num"))
    for ad, key in [
        ("momentum hızlanıyor", "momentum_hiz"), ("hacim hızlanıyor", "hacim_hiz"),
        ("BTC farkı açılıyor", "btc_fark_ac"), ("lider güçleniyor", "lider_guc"),
        ("basamaklı trend", "basamak")
    ]:
        specs.append((ad, key, True, "bool"))
    baz = _oran5(grup)
    sonuc = []
    for i in range(len(specs)):
        for j in range(i+1, len(specs)):
            a, b = specs[i], specs[j]
            def ok(x, sp):
                ad, key, es, typ = sp
                if typ == "bool": return bool(x.get(key))
                return float(x.get(key, 0) or 0) >= float(es)
            sec = [x for x in grup if ok(x,a) and ok(x,b)]
            if len(sec) < 8 or len(sec) > len(grup)*0.80:
                continue
            oran = _oran5(sec)
            lift = oran - baz
            sonuc.append((lift, oran, len(sec), a, b, baz))
    return sorted(sonuc, reverse=True)


def _rejim_kesifleri(grup):
    out=[]
    for rej in ("Güçlü", "Yatay", "Zayıf"):
        g=[x for x in grup if x.get("piyasa_rejim")==rej]
        if len(g) >= 12:
            out.append((rej, len(g), _oran5(g), _ortalama(g,"max_getiri")))
    return out


def kesif_raporu_gerekirse_gonder():
    """Her 3 günde bir saat 08:00 TR'de keşif + kod önerisi gönderir."""
    global KESIF_META
    simdi = time.time()
    gonder, planli_ts = _s49_planli_rapor_zamani(simdi, KESIF_META)
    if not gonder:
        return
    bas = planli_ts - KESIF_RAPOR_ARALIGI
    tamam = [x for x in KESIF_KAYITLARI if x.get("tamamlandi") and int(x.get("kesif_v", 0) or 0) >= 4 and float(x.get("zaman",0) or 0) >= bas]
    if len(tamam) < 20:
        mesaj = f"🧠 S49 3 GÜNLÜK KEŞİF RAPORU\n\nYeterli örnek yok: n={len(tamam)}. En az 20 tamamlanmış güçlü-aday gözlemi bekleniyor."
        print(mesaj); telegram_gonder(mesaj)
        KESIF_META["son_rapor"] = planli_ts
        KESIF_META["son_planli_rapor_ts"] = planli_ts
        _kesif_meta_kaydet(); return

    basarili=[x for x in tamam if float(x.get("max_getiri",0) or 0) >= 5]
    hedef20=[x for x in tamam if float(x.get("max_getiri",0) or 0) >= 20]
    sonen=[x for x in tamam if 1.0 <= float(x.get("max_getiri",0) or 0) < 5.0 and ((x.get("son_getiri") is not None and float(x.get("son_getiri",0) or 0) <= 0.5) or float(x.get("max_getiri",0) or 0)-float(x.get("son_getiri",0) or 0) >= 2.0)]
    zayif=[x for x in tamam if float(x.get("max_getiri",0) or 0) < 1.0]

    # En çok güçlenen üst %20: +5 eşiğine bağlı kalmadan verinin doğal kazananlarını gözlemler.
    sirali=sorted(tamam, key=lambda x: float(x.get("max_getiri",0) or 0), reverse=True)
    topn=max(5, int(round(len(sirali)*0.20)))
    guclenen=sirali[:topn]
    diger=sirali[topn:]

    sat=[
        "🧠 S49 3 GÜNLÜK KEŞİF + KOD ÖNERİSİ",
        "",
        f"Gözlenen güçlü teknik aday: {len(tamam)} | +%5: {len(basarili)} (%{_oran5(tamam):.1f})",
        f"Sönen (+%1-5 sonra geri veren): {len(sonen)} | Baştan zayıf (<+%1): {len(zayif)}",
        "",
        "🔎 EN ÇOK GÜÇLENEN COİNLERDEN SERBEST GÖZLEM",
        f"Üst %20 grubun ort. tepesi: %{_ortalama(guclenen,'max_getiri'):+.2f} | diğerleri: %{_ortalama(diger,'max_getiri'):+.2f}",
    ]
    prof_fields=[("3dk mom","d3"),("5dk mom","d5"),("Kod Kalitesi","kod_kalite"),("Kod Genel Güç","kod_genel"),("Genel Güç / Momentum bloğu","kod_momentum"),("S49 Momentum Bloğu","kod_momentum_blok"),("Devam","devam"),("Kalıcılık","kalicilik"),("Genel Güç","genel"),("Hacim","hacim"),("Lider","lider")]
    diffs=[]
    for ad,key in prof_fields:
        a,b=_ortalama(guclenen,key),_ortalama(diger,key)
        diffs.append((abs(a-b), ad, a, b))
    for _,ad,a,b in sorted(diffs, reverse=True)[:4]:
        sat.append(f"• {ad}: en güçlü %20 {a:.2f} | diğerleri {b:.2f}")

    sat += ["", "🚀 +%20 VE ÜZERİNE GİDENLER"]
    if len(hedef20) >= 5:
        sat.append(f"+%20 gören: {len(hedef20)}/{len(tamam)} (%{len(hedef20) / len(tamam) * 100:.1f})")
        diger20=[x for x in tamam if float(x.get("max_getiri",0) or 0) < 20]
        for ad,key in prof_fields:
            if len(diger20) < 5:
                break
            a,b=_ortalama(hedef20,key),_ortalama(diger20,key)
            sat.append(f"• {ad}: +%20 grubu {a:.2f} | diğerleri {b:.2f}")
        sat.append(f"• Medyan +%20 hedef süresi: {_sure_dk(hedef20, 20):.0f} dk" if _sure_dk(hedef20, 20) is not None else "• +%20 hedef süresi: hesaplanamadı")
    else:
        sat.append(f"Yeterli örnek yok: n={len(hedef20)}; özellikleri güvenilir biçimde ayırmak için en az 5 gözlem bekleniyor.")

    tek=_tekli_kesifler(tamam)
    sat += ["", "🧪 RAPOR EŞİKLERİNİN S49 SONUÇ TESTİ"]
    def _esik_karsilastir(etiket, sec, diger):
        if len(sec) < 5 or len(diger) < 5:
            sat.append(f"• {etiket}: örnek yetersiz (üst={len(sec)}, alt={len(diger)}; her grupta en az 5 gerekir)")
            return
        sat.append(
            f"• {etiket}: +%5 %{_oran5(sec):.1f} (n={len(sec)}) / alt %{_oran5(diger):.1f} (n={len(diger)})"
        )
    _esik_karsilastir("3dk momentum ≥0.31 [tüm rejimler]", [x for x in tamam if float(x.get("d3",0) or 0) >= 0.31], [x for x in tamam if float(x.get("d3",0) or 0) < 0.31])
    _esik_karsilastir("5dk momentum ≥0.50 [tüm rejimler]", [x for x in tamam if float(x.get("d5",0) or 0) >= 0.50], [x for x in tamam if float(x.get("d5",0) or 0) < 0.50])
    _esik_karsilastir("Genel Güç/Momentum Bloğu ≥55.87 [tüm rejimler]", [x for x in tamam if x.get("kod_momentum_esik_uygun")], [x for x in tamam if not x.get("kod_momentum_esik_uygun")])
    _guclu_tamam = [x for x in tamam if x.get("piyasa_rejim") == "Güçlü"]
    _esik_karsilastir("Genel Güç ≥65.50 [yalnız güçlü rejim]", [x for x in _guclu_tamam if x.get("kod_genel_esik_guclu_uygun")], [x for x in _guclu_tamam if not x.get("kod_genel_esik_guclu_uygun")])
    _esik_karsilastir("Kalıcılık bandı =100 [yalnız güçlü rejim]", [x for x in _guclu_tamam if x.get("kod_kal_bant_guclu_uygun")], [x for x in _guclu_tamam if not x.get("kod_kal_bant_guclu_uygun")])

    sat += ["", "🧪 VERİNİN KENDİ BULDUĞU TEKLİ EŞİKLER"]
    for _,yon,ad,key,es,oh,ol,nh,nl in tek[:5]:
        if yon >= 0:
            sat.append(f"• {ad} ≥ {es:.2f}: +%5 %{oh:.1f} | altı %{ol:.1f} (n={nh}/{nl}) → BONUS/GÜÇLENDİR adayı")
        else:
            sat.append(f"• {ad} ≥ {es:.2f}: +%5 %{oh:.1f} | altı %{ol:.1f} (n={nh}/{nl}) → yüksek değer ters etki; CEZA/BANT araştır")

    komb=_kombinasyon_kesifleri(tamam)
    sat += ["", "🧩 OTOMATİK BULUNAN İKİLİ İLİŞKİLER"]
    if komb:
        for lift,oran,n,a,b,baz in komb[:4]:
            if lift < 5: break
            sat.append(f"• {a[0]} + {b[0]} → +%5 %{oran:.1f} (n={n}), bazdan {lift:+.1f} puan")
    else:
        sat.append("• Yeterince güçlü ikili ilişki yok.")

    # LRC'de görülen ani genişleme örüntüsünü, Rel+2'yi ayırıcı saymadan test et.
    def _hedef_orani(grup, hedef):
        return sum(1 for x in grup if float(x.get("max_getiri", 0) or 0) >= hedef) / len(grup) * 100.0 if grup else 0.0

    def _sure_dk(grup, hedef):
        alan = f"hedef{hedef}_sure_sn"
        vals = [float(x[alan]) / 60.0 for x in grup if x.get(alan) is not None]
        return statistics.median(vals) if vals else None

    def _combo_satiri(etiket, grup):
        sureler = []
        for hedef in (4, 5, 7, 20):
            dk = _sure_dk(grup, hedef)
            sureler.append(f"+%{hedef} {dk:.0f}dk" if dk is not None else f"+%{hedef} —")
        geri = _ortalama(grup, "geri_verme_orani")
        return (
            f"• {etiket}: n={len(grup)} | +%4 %{_hedef_orani(grup, 4):.1f} | "
            f"+%5 %{_hedef_orani(grup, 5):.1f} | +%7 %{_hedef_orani(grup, 7):.1f} | "
            f"+%20 %{_hedef_orani(grup, 20):.1f} | "
            f"süre {' / '.join(sureler)} | ort. geri verme %{geri:.1f}"
        )

    trend_mom_hacim = [x for x in tamam if x.get("trend_cok_guclu") and x.get("momentum_hiz") and x.get("hacim_hiz")]
    trend_mom_hacim_btc = [x for x in trend_mom_hacim if x.get("btc_fark_ac")]
    trend_mom_hacim_lider = [x for x in trend_mom_hacim if x.get("lider_guc")]
    trend_mom_hacim_btc_lider = [x for x in trend_mom_hacim if x.get("btc_fark_ac") and x.get("lider_guc")]
    kal_esik = _medyan(tamam, "kalicilik")
    trend_mom_hacim_kal = [x for x in trend_mom_hacim if float(x.get("kalicilik", 0) or 0) >= kal_esik]
    rel2_taban = [x for x in tamam if int(x.get("rel", 0) or 0) >= 2]

    sat += ["", "🧪 GÜÇLÜ TREND + MOMENTUM + HACİM BİRLİKTE TESTİ"]
    sat.append("Rel +2 ortak taban olarak raporlanır; ayırıcı kombinasyona dahil edilmez.")
    for etiket, grup in [
        ("Trend güçlü + momentum hızlanıyor + hacim hızlanıyor", trend_mom_hacim),
        ("Yukarıdaki üçlü + BTC farkı açılıyor", trend_mom_hacim_btc),
        ("Yukarıdaki üçlü + lider güçleniyor", trend_mom_hacim_lider),
        ("Üçlü + BTC farkı + lider güçleniyor", trend_mom_hacim_btc_lider),
        (f"Üçlü + Kalıcılık medyan üstü (≥{kal_esik:.1f})", trend_mom_hacim_kal),
    ]:
        sat.append(_combo_satiri(etiket, grup) if len(grup) >= 8 else f"• {etiket}: yeterli örnek yok (n={len(grup)}, en az 8)")
    sat.append(_combo_satiri("Referans: Rel +2", rel2_taban) if len(rel2_taban) >= 8 else f"• Referans Rel +2: yeterli örnek yok (n={len(rel2_taban)}, en az 8)")

    rej=_rejim_kesifleri(tamam)
    if rej:
        sat += ["", "🌍 PİYASA REJİMİ"]
        for ad,n,o,t in rej:
            sat.append(f"• {ad}: n={n} | +%5 %{o:.1f} | ort. tepe %{t:+.2f}")

    if basarili and sonen:
        sat += ["", "↩️ +%5 YAPAN / SÖNEN AYRIMI"]
        ay=[]
        for ad,key in prof_fields + [("10dk mom","d10"),("BTC farkı","btc_fark3")]:
            a,b=_ortalama(basarili,key),_ortalama(sonen,key)
            ay.append((abs(a-b),ad,a,b))
        for _,ad,a,b in sorted(ay, reverse=True)[:4]:
            sat.append(f"• {ad}: +%5 {a:.2f} | sönen {b:.2f}")

    sat += ["", "📌 Motor sadece önerir; kodu otomatik değiştirmez. Bulgular 3 gün sonra yeniden sınanmalıdır."]
    mesaj="\n".join(sat)
    print(mesaj); telegram_gonder(mesaj)
    KESIF_META["son_rapor"] = planli_ts
    KESIF_META["son_planli_rapor_ts"] = planli_ts
    _kesif_meta_kaydet()


KESIF_KAYITLARI = _kesif_json_yukle(KESIF_DOSYA, [])
if not isinstance(KESIF_KAYITLARI, list):
    KESIF_KAYITLARI = []
KESIF_META = _kesif_json_yukle(KESIF_META_DOSYA, {})
if not isinstance(KESIF_META, dict):
    KESIF_META = {}
if not KESIF_META.get("baslangic"):
    KESIF_META["baslangic"] = time.time()
    KESIF_META["son_rapor"] = KESIF_META["baslangic"]
    _kesif_meta_kaydet()


def _al_ogrenme_yukle():
    try:
        if os.path.exists(AL_OGRENME_DOSYA):
            with open(AL_OGRENME_DOSYA, "r", encoding="utf-8") as f:
                veri = json.load(f)
                if isinstance(veri, list):
                    return veri
    except Exception as e:
        print("AL öğrenme dosyası okunamadı:", e)
    return []


def _al_ogrenme_kaydet():
    try:
        klasor = os.path.dirname(os.path.abspath(AL_OGRENME_DOSYA))
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        # Kümülatif öğrenme için geniş geçmiş tut.
        with open(AL_OGRENME_DOSYA, "w", encoding="utf-8") as f:
            json.dump(AL_OGRENME_KAYITLARI[-20000:], f, ensure_ascii=False)
    except Exception as e:
        print("AL öğrenme dosyası yazılamadı:", e)


def al_ogrenme_baslat(aday, btc_d, piyasa_fiyatlari, piyasa_medyan3, btc_giris):
    symbol = aday.get("symbol")
    giris = float(aday.get("fiyat", 0) or 0)
    if not symbol or giris <= 0:
        return

    # Aynı aktif AL için ikinci öğrenme kaydı açma.
    for k in reversed(AL_OGRENME_KAYITLARI[-100:]):
        if k.get("symbol") == symbol and not k.get("tamamlandi"):
            return

    simdi = time.time()
    kayit = {
        "symbol": symbol,
        "zaman": simdi,
        "giris": giris,
        "max_getiri": 0.0,
        "min_getiri": 0.0,
        "son_getiri": None,
        "tamamlandi": False,
        "kar_mesaji_gonderildi": False,
        "btc_rejim": _rejim_etiketi(btc_d.get("3s", 0)),
        "btc_3s": round(float(btc_d.get("3s", 0) or 0), 3),
        "piyasa_rejim": _rejim_etiketi(piyasa_medyan3),
        "piyasa_medyan_3s": round(float(piyasa_medyan3 or 0), 3),
        "piyasa_giris_fiyatlari": piyasa_fiyatlari,
        "btc_giris": float(btc_giris or 0),
        "ai": float(aday.get("ai_skoru", 0) or 0),
        "erken": float(aday.get("erken_puan", 0) or 0),
        "giris_skoru": float(aday.get("giris_kalitesi", 0) or 0),
        "devam": float(aday.get("devam_gucu", 0) or 0),
        "kalicilik": float(aday.get("kalicilik_skoru", 0) or 0),
        "kategori": aday.get("radar_kategori", ""),
        "sinyal_event_id": aday.get("_sinyal_event_id"),
        # 60dk göreceli güç bonusu AL filtresi değildir; yalnız ölçüm/öncelik bilgisidir.
        "goreceli_guc_bonus": int(aday.get("goreceli_guc_bonus", 0) or 0),
        "coin_btc_60": round(float(aday.get("coin_btc_60", 0) or 0), 3),
        "coin_piyasa_60": round(float(aday.get("coin_piyasa_60", 0) or 0), 3),
    }
    AL_OGRENME_KAYITLARI.append(kayit)
    _al_ogrenme_kaydet()


def al_ogrenme_guncelle(ticker):
    if not AL_OGRENME_KAYITLARI:
        return

    simdi = time.time()
    fiyatlar = {}
    for coin in ticker:
        try:
            sym = coin.get("pair", "")
            f = float(coin.get("last", 0) or 0)
            if sym and f > 0:
                fiyatlar[sym] = f
        except Exception:
            pass

    degisti = False
    for k in AL_OGRENME_KAYITLARI:
        if k.get("tamamlandi"):
            continue
        symbol = k.get("symbol")
        fiyat = fiyatlar.get(symbol)
        giris = float(k.get("giris", 0) or 0)
        if fiyat and giris > 0:
            getiri = _pct(fiyat, giris)
            k["max_getiri"] = round(max(float(k.get("max_getiri", 0) or 0), getiri), 3)
            k["min_getiri"] = round(min(float(k.get("min_getiri", 0) or 0), getiri), 3)
            degisti = True

            # Eski öğrenme kayıtları için varsayılan True: yeni deploy sonrası
            # geçmişteki AL sinyalleri adına geriye dönük mesaj gönderilmesini önler.
            if not k.get("kar_mesaji_gonderildi", True) and getiri >= AL_BILDIR_KAR_ESIK:
                coin_adi = symbol[:-3] if str(symbol).endswith("TRY") else symbol
                _sinyal_sira_hit5_isaretle(symbol, k.get("sinyal_event_id"))
                mesaj = (
                    f"💰 +%{AL_BILDIR_KAR_ESIK:.0f} KÂR BÖLGESİ - {coin_adi}\n"
                    f"İlk AL: {giris:.4f} | Güncel: {fiyat:.4f}\n"
                    f"Getiri: %{getiri:+.2f}\n"
                    "Not: Çık emri değil; kârı değerlendirmek / çıkışa hazırlanmak için ara uyarı."
                )
                k["kar_mesaji_gonderildi"] = True
                k["kar_mesaji_zamani"] = simdi
                telegram_gonder(mesaj)

        if simdi - float(k.get("zaman", simdi)) < AL_OGRENME_SURESI:
            continue

        if fiyat and giris > 0:
            k["son_getiri"] = round(_pct(fiyat, giris), 3)

        piyasa_getirileri = []
        for sym, ilk in (k.get("piyasa_giris_fiyatlari") or {}).items():
            son = fiyatlar.get(sym)
            try:
                ilk = float(ilk)
                if ilk > 0 and son:
                    piyasa_getirileri.append(_pct(son, ilk))
            except Exception:
                pass
        piyasa_3s = statistics.median(piyasa_getirileri) if piyasa_getirileri else 0.0
        k["piyasa_3s_getiri"] = round(piyasa_3s, 3)

        btc_giris = float(k.get("btc_giris", 0) or 0)
        btc_son = float(fiyatlar.get("BTCTRY", 0) or 0)
        k["btc_3s_son_getiri"] = round(_pct(btc_son, btc_giris), 3) if btc_giris > 0 and btc_son > 0 else None

        if k.get("son_getiri") is not None:
            k["piyasa_ustu"] = round(float(k["son_getiri"]) - piyasa_3s, 3)
        k["tamamlandi"] = True
        k["tamamlanma_zamani"] = simdi
        degisti = True

    if degisti:
        _al_ogrenme_kaydet()


def yuzde5_basariraporu_gerekirse_gonder():
    """Her 3 günde bir saat 08:00 TR'de +%5 yakalama raporunu gönderir."""
    global _YUZDE5_META

    simdi = time.time()
    gonder, planli_ts = _s49_planli_rapor_zamani(simdi, _YUZDE5_META)
    if not gonder:
        return

    pencere_bas = planli_ts - YUZDE5_RAPOR_ARALIGI
    pencere_son = planli_ts

    # Yalnız bu 3 günlük rapor penceresinde açılan AL kayıtları.
    tum = [
        x for x in AL_OGRENME_KAYITLARI
        if pencere_bas <= float(x.get("zaman", 0) or 0) < pencere_son
    ]

    tamam = [x for x in tum if x.get("tamamlandi")]
    acik = [x for x in tum if not x.get("tamamlandi")]
    basarili = [
        x for x in tamam
        if float(x.get("max_getiri", 0) or 0) >= 5.0
    ]
    basarisiz = [
        x for x in tamam
        if float(x.get("max_getiri", 0) or 0) < 5.0
    ]

    oran = (len(basarili) / len(tamam) * 100.0) if tamam else 0.0
    ort_tepe = (
        sum(float(x.get("max_getiri", 0) or 0) for x in tamam) / len(tamam)
        if tamam else 0.0
    )

    mesaj = (
        f"📊 3 GÜNLÜK +%5 YAKALAMA RAPORU — {YUZDE5_RAPOR_ETIKETI}\n\n"
        f"Tamamlanan sinyal: {len(tamam)}\n"
        f"+%5 yapan: {len(basarili)}\n"
        f"+%5 yapamayan: {len(basarisiz)}\n"
        f"🎯 +%5 başarı: %{oran:.1f}\n"
        f"Ortalama tepe getiri: %{ort_tepe:+.2f}\n"
        f"Henüz tamamlanmayan: {len(acik)}\n\n"
        f"Not: Başarı = AL fiyatından sonra izleme süresi içinde en az +%5 tepe görmek."
    )

    print(mesaj)
    telegram_gonder(mesaj)

    _YUZDE5_META["son_rapor"] = planli_ts
    _YUZDE5_META["son_planli_rapor_ts"] = planli_ts
    _yuzde5_meta_kaydet(_YUZDE5_META)


def _grup_satiri(baslik, kayitlar):
    if not kayitlar:
        return f"{baslik}: veri yok"
    n = len(kayitlar)
    p4 = sum(1 for x in kayitlar if float(x.get("max_getiri", 0) or 0) >= 4) / n * 100
    p7 = sum(1 for x in kayitlar if float(x.get("max_getiri", 0) or 0) >= 7) / n * 100
    p10 = sum(1 for x in kayitlar if float(x.get("max_getiri", 0) or 0) >= 10) / n * 100
    son = [float(x.get("son_getiri", 0) or 0) for x in kayitlar if x.get("son_getiri") is not None]
    ust = [float(x.get("piyasa_ustu", 0) or 0) for x in kayitlar if x.get("piyasa_ustu") is not None]
    ort_son = sum(son) / len(son) if son else 0.0
    ort_ust = sum(ust) / len(ust) if ust else 0.0
    return f"{baslik}: n={n} | +%4 %{p4:.1f} | +%7 %{p7:.1f} | +%10 %{p10:.1f} | 3s %{ort_son:+.2f} | piyasa üstü %{ort_ust:+.2f}"


def rejim_raporu_gerekirse_gonder():
    global SON_REJIM_RAPOR_ZAMANI
    simdi = time.time()
    if simdi - SON_REJIM_RAPOR_ZAMANI < REJIM_RAPOR_ARALIGI:
        return

    SON_REJIM_RAPOR_ZAMANI = simdi
    tamam = [x for x in AL_OGRENME_KAYITLARI if x.get("tamamlandi") and x.get("son_getiri") is not None]
    # Ana rapor artık KÜMÜLATİF: eldeki tüm tamamlanmış AL kayıtlarını kullanır.
    # Son 24 saat sayısı ayrıca bilgi olarak gösterilir.
    gunluk = [x for x in tamam if simdi - float(x.get("tamamlanma_zamani", 0) or 0) <= 24 * 60 * 60]
    if not tamam:
        return

    rapor_kayitlari = tamam

    btc_guclu = [x for x in rapor_kayitlari if x.get("btc_rejim") == "Güçlü"]
    btc_yatay = [x for x in rapor_kayitlari if x.get("btc_rejim") == "Yatay"]
    btc_zayif = [x for x in rapor_kayitlari if x.get("btc_rejim") == "Zayıf"]
    piy_guclu = [x for x in rapor_kayitlari if x.get("piyasa_rejim") == "Güçlü"]
    piy_yatay = [x for x in rapor_kayitlari if x.get("piyasa_rejim") == "Yatay"]
    piy_zayif = [x for x in rapor_kayitlari if x.get("piyasa_rejim") == "Zayıf"]

    # 60dk göreceli güç bonusunu da tüm geçmiş tamamlanmış AL'larda ölç.
    rel2 = [x for x in rapor_kayitlari if int(x.get("goreceli_guc_bonus", 0) or 0) >= 2]
    rel1 = [x for x in rapor_kayitlari if int(x.get("goreceli_guc_bonus", 0) or 0) == 1]
    rel0 = [x for x in rapor_kayitlari if int(x.get("goreceli_guc_bonus", 0) or 0) == 0]

    edge = [float(x.get("piyasa_ustu", 0) or 0) for x in rapor_kayitlari if x.get("piyasa_ustu") is not None]
    ort_edge = sum(edge) / len(edge) if edge else 0.0
    piy = [float(x.get("piyasa_3s_getiri", 0) or 0) for x in rapor_kayitlari]
    ort_piy = sum(piy) / len(piy) if piy else 0.0

    if ort_edge >= 1.0:
        secicilik = "Güçlü"
    elif ort_edge >= 0.30:
        secicilik = "Orta"
    elif ort_edge > 0:
        secicilik = "Zayıf pozitif"
    else:
        secicilik = "Yok / negatif"

    if ort_piy >= 1.0 and ort_edge < 0.5:
        piyasa_etkisi = "Yüksek"
    elif abs(ort_piy) < 0.5 and ort_edge >= 0.5:
        piyasa_etkisi = "Düşük"
    else:
        piyasa_etkisi = "Orta / karışık"

    mesaj = (
        "📊 AL REJİM / SEÇİCİLİK RAPORU\n\n"
        + _grup_satiri("BTC Güçlü", btc_guclu) + "\n"
        + _grup_satiri("BTC Yatay", btc_yatay) + "\n"
        + _grup_satiri("BTC Zayıf", btc_zayif) + "\n\n"
        + _grup_satiri("Piyasa Güçlü", piy_guclu) + "\n"
        + _grup_satiri("Piyasa Yatay", piy_yatay) + "\n"
        + _grup_satiri("Piyasa Zayıf", piy_zayif) + "\n\n"
        + "🎯 60dk GÖRECELİ GÜÇ BONUSU\n"
        + _grup_satiri("Bonus +2 (BTC ve piyasa eşiği birlikte)", rel2) + "\n"
        + _grup_satiri("Bonus +1 (eşiklerden biri)", rel1) + "\n"
        + _grup_satiri("Bonus 0", rel0) + "\n\n"
        + f"🤖 Bot seçiciliği: {secicilik}\n"
        + f"🌍 Piyasa etkisi: {piyasa_etkisi}\n"
        + f"AL coinlerinin ortalama piyasa üstü 3s getirisi: %{ort_edge:+.2f}\n"
        + f"Bugün tamamlanan AL: {len(gunluk)}\n"
        + f"Toplam öğrenilmiş AL: {len(tamam)}"
    )
    print(mesaj)
    telegram_gonder(mesaj)


AL_OGRENME_KAYITLARI = _al_ogrenme_yukle()


STABLE_COINLER = [
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "USDP"
]




RSS_KAYNAKLARI = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"
]

POZITIF = [
    "listing", "listed", "binance", "coinbase", "partnership",
    "etf", "airdrop", "burn", "launch", "mainnet", "upgrade",
    "integration", "support", "investment", "funding", "approval",
    "adoption", "bullish", "surge", "rally"
]

NEGATIF = [
    "hack", "exploit", "lawsuit", "delist", "sec", "attack",
    "scam", "fraud", "investigation", "outage", "halted",
    "stopped", "shutdown", "pressure", "bearish", "loss",
    "dump", "decline", "crash", "selloff", "down", "weakness"
]


def telegram_gonder(mesaj):
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN bulunamadı. Railway Variables kontrol et.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    for chat_id in CHAT_IDS:
        try:
            r = requests.get(
                url,
                params={"chat_id": chat_id, "text": mesaj},
                timeout=10
            )
            print(chat_id, r.text)
        except Exception as e:
            print(chat_id, e)


def veri_getir(symbol, saat=24):
    simdi = int(time.time())
    url = (
        f"https://graph-api.btcturk.com/v1/klines/history?"
        f"symbol={symbol}&resolution=60&from={simdi - (saat * 3600)}&to={simdi}"
    )
    return requests.get(url, timeout=10).json()



def btc_degisimleri():
    """
    V4.25 BTC Gücü V2 için BTC'nin 1s, 3s ve 24s değişimini hesaplar.
    """
    try:
        d = veri_getir("BTCTRY", 24)
        c = d["c"]

        if len(c) < 24:
            return {"1s": 0, "3s": 0, "24s": 0}

        return {
            "1s": ((c[-1] - c[-2]) / c[-2]) * 100,
            "3s": ((c[-1] - c[-4]) / c[-4]) * 100,
            "24s": ((c[-1] - c[-24]) / c[-24]) * 100
        }
    except Exception:
        return {"1s": 0, "3s": 0, "24s": 0}


def btc_gucu_v2_hesapla(degisim1, degisim3, degisim24, btc_d):
    """
    V4.25 BTC Gücü V2.
    Sadece BTC'den güçlü mü sorusuna bakmaz; 1s, 3s ve 24s farkını 0-10 puana çevirir.
    """
    fark1 = degisim1 - btc_d.get("1s", 0)
    fark3 = degisim3 - btc_d.get("3s", 0)
    fark24 = degisim24 - btc_d.get("24s", 0)

    puan = 0

    if fark1 >= 0.5:
        puan += 2
    elif fark1 >= 0:
        puan += 1

    if fark3 >= 3:
        puan += 4
    elif fark3 >= 1.5:
        puan += 3
    elif fark3 >= 0.5:
        puan += 2

    if fark24 >= 5:
        puan += 4
    elif fark24 >= 3:
        puan += 3
    elif fark24 >= 1:
        puan += 2

    return min(puan, 10), fark1, fark3, fark24


def lider_skoru_hesapla(hacim_kat, degisim1, degisim3, degisim24, btc_fark1, btc_fark3, btc_fark24, zirve_yakin, yeni_zirve):
    """
    V4.25 Lider Skoru.
    Coinin sadece hareket edip etmediğini değil, piyasanın liderlerinden biri olup olmadığını ölçer.
    """
    puan = 0

    if btc_fark24 >= 5:
        puan += 3
    elif btc_fark24 >= 2:
        puan += 2

    if btc_fark3 >= 2:
        puan += 2
    elif btc_fark3 >= 1:
        puan += 1

    if degisim24 >= 6:
        puan += 2
    elif degisim24 >= 3:
        puan += 1

    if hacim_kat >= 10 and degisim1 >= 0 and degisim3 > 0:
        puan += 2
    elif hacim_kat >= 5 and degisim3 > 0:
        puan += 1

    if yeni_zirve:
        puan += 1
    elif zirve_yakin:
        puan += 0.5

    return min(puan, 10)





def guc_skoru_hesapla(
    hacim_kat,
    degisim1,
    degisim3,
    degisim24,
    btc_guc_skoru,
    lider_skoru,
    haber_skoru,
    satis_baskisi,
    btc_fark3=0,
    zirve_yakin=False,
    yeni_zirve=False
):
    """
    Son çalışan Coin Radar eşiklerine uyarlanmış 0-100 aday skoru.
    Momentum daha ağır, yüksek hacim ise momentum/liderlik teyidi olmadan tek başına ödüllendirilmez.
    """
    hacim_puan = min(hacim_kat / 10, 1) * 18
    momentum_puan = min(max(degisim3, 0) / 6, 1) * 34
    btc_puan = (btc_guc_skoru / 10) * 20
    lider_puan = (lider_skoru / 10) * 15
    haber_puan = (min(haber_skoru, 20) / 20) * 10

    toplam = hacim_puan + momentum_puan + btc_puan + lider_puan + haber_puan

    # Son Coin Radar: 3s momentum ana ayırıcı.
    if degisim3 >= 6:
        toplam += 6
    elif degisim3 >= 4:
        toplam += 3
    elif degisim3 >= 2:
        toplam += 1

    # Çok yüksek hacim tek başına güçlü aday sayılmaz.
    if hacim_kat >= 15 and degisim3 >= 6:
        toplam += 2
    elif hacim_kat >= 10 and degisim3 >= 4:
        toplam += 1
    elif hacim_kat >= 10 and degisim3 < 4 and lider_skoru < 7:
        toplam -= 4

    if btc_fark3 >= 4:
        toplam += 2
    elif btc_fark3 >= 2:
        toplam += 1

    if lider_skoru >= 7:
        toplam += 2
    elif lider_skoru >= 5:
        toplam += 1

    if zirve_yakin or yeni_zirve:
        toplam += 1

    if satis_baskisi:
        toplam -= 12

    return round(max(min(toplam, 100), 0), 2)



def kod_onerisi_kalite_katmani(aday, piyasa_medyan3=0.0):
    """S49 yerel ölçeğinde haftalık rapor bulgularını birleşik kalite puanına uygular.

    Raporun önerdiği tekil kriterler bonus/puan katkısıdır; 3dk veya 5dk eşiğinden
    en az biri ve toplam kalite eşiği dışında yeni sert veto eklenmez.
    """
    mikro = aday.get("mikro") or {}
    d3 = float(mikro.get("d3", 0) or 0)
    d5 = float(mikro.get("d5", 0) or 0)
    kal = float(aday.get("kalicilik_skoru", 0) or 0)
    ai = float(aday.get("ai_skoru", 0) or 0)
    devam = float(aday.get("devam_gucu", 0) or 0)
    radar = float(aday.get("radar_skoru", 0) or 0)
    d3_ok = d3 >= KOD_ONERI_D3_ESIK
    d5_ok = d5 >= KOD_ONERI_D5_ESIK
    rejim = _rejim_etiketi(piyasa_medyan3)

    # S49'ın kendi Genel Güç formülü: aynı 0–100 ailesindeki AI, Devam,
    # Kalıcılık ve Radar puanlarından hesaplanır; ham genel_skor * 4 kullanılmaz.
    genel_guc = max(0.0, min(100.0,
        ai * 0.35 + devam * 0.25 + kal * 0.20 + radar * 0.20
    ))

    # S49 yerel Momentum Bloğu: 3dk/5dk hareketi ve ivme bayrakları.
    d3_parca = min(35.0, max(0.0, d3 / KOD_ONERI_D3_ESIK) * 35.0)
    d5_parca = min(35.0, max(0.0, d5 / KOD_ONERI_D5_ESIK) * 35.0)
    momentum_blok = d3_parca + d5_parca
    if aday.get("momentum_hizlaniyor"):
        momentum_blok += 15.0
    if aday.get("hacim_hizlaniyor"):
        momentum_blok += 15.0
    momentum_blok = max(0.0, min(100.0, momentum_blok))

    # 55.87 eşiği, haftalık rapordaki Genel Güç / Momentum bloğudur:
    # 1/3/5/10dk yüzdeleri V12 raporundaki 0-nötr=50 dönüşümüyle birleştirilir.
    def _momentum_100(x):
        return max(0.0, min(100.0, 50.0 + 12.0 * float(x or 0)))
    d1 = float(mikro.get("d1", 0) or 0)
    d10 = float(mikro.get("d10", 0) or 0)
    momentum_kalite = (
        0.15 * _momentum_100(d1) + 0.25 * _momentum_100(d3)
        + 0.30 * _momentum_100(d5) + 0.30 * _momentum_100(d10)
    )

    # V12 raporundaki Kalıcılık bandı S49 verisinden yeniden hesaplanır.
    if 88 <= kal <= 94:
        kal_bant = 100.0
    elif 84 <= kal < 88:
        kal_bant = 75.0
    elif 95 <= kal <= 97:
        kal_bant = 55.0
    elif kal > 97:
        kal_bant = 35.0
    else:
        kal_bant = 50.0

    # Temel 0–100 birleşik puan.
    if d3 >= 0.80: d3_puan = 25.0
    elif d3 >= 0.50: d3_puan = 22.0
    elif d3_ok: d3_puan = 18.0
    elif d3 >= 0.15: d3_puan = 8.0
    else: d3_puan = 0.0

    if d5 >= 1.20: d5_puan = 20.0
    elif d5 >= 0.80: d5_puan = 17.0
    elif d5_ok: d5_puan = 14.0
    elif d5 >= 0.25: d5_puan = 6.0
    else: d5_puan = 0.0

    # Rejimden bağımsız S49 Genel Güç ve Momentum Bloğu katkıları.
    genel_puan = genel_guc * 0.20
    momentum_puan = momentum_blok * 0.20

    # Kalıcılık için temel puan; güçlü rejimde rapor eşiklerine göre ek bonuslar.
    if rejim == "Güçlü":
        kal_puan = 15.0 if kal_bant >= KOD_ONERI_KALICILIK_BANT_ESIK else (9.0 if kal >= 80 else 3.0)
    else:
        kal_puan = 7.5

    # Raporun 55.87 / 65.50 / 100.00 eşikleri bonus verir, tek başına veto etmez.
    momentum_bonus = 5.0 if momentum_kalite >= KOD_ONERI_MOMENTUM_ESIK else 0.0
    genel_bonus = 5.0 if rejim == "Güçlü" and genel_guc >= KOD_ONERI_GENEL_ESIK_GUCLU else 0.0
    kalicilik_bonus = 5.0 if rejim == "Güçlü" and kal_bant >= KOD_ONERI_KALICILIK_BANT_ESIK else 0.0

    kalite = round(max(0.0, min(100.0,
        d3_puan + d5_puan + genel_puan + momentum_puan + kal_puan
        + momentum_bonus + genel_bonus + kalicilik_bonus
    )), 1)
    kalite_etiket = "🔥 ÇOK GÜÇLÜ" if kalite >= 85 else ("✅ GÜÇLÜ" if kalite >= KOD_ONERI_KALITE_MIN else "🟡 ZAYIF")

    aday["kod_oneri_d3_ok"] = d3_ok
    aday["kod_oneri_d5_ok"] = d5_ok
    aday["kod_oneri_genel_norm"] = round(genel_guc, 1)
    aday["kod_oneri_momentum_blok"] = round(momentum_blok, 1)
    aday["kod_oneri_momentum_kalite"] = round(momentum_kalite, 2)
    aday["kod_oneri_kalicilik_bant"] = round(kal_bant, 1)
    aday["kod_oneri_rejim"] = rejim
    aday["kod_oneri_kalicilik_uygun"] = kal_bant >= KOD_ONERI_KALICILIK_BANT_ESIK
    aday["kod_oneri_momentum_bonus"] = momentum_bonus
    aday["kod_oneri_genel_bonus"] = genel_bonus
    aday["kod_oneri_kalicilik_bonus"] = kalicilik_bonus
    aday["kod_oneri_kalite"] = kalite
    aday["kod_oneri_kalite_etiket"] = kalite_etiket

    if aday.get("karar") == "🟢 AL":
        nedenler = list(aday.get("nedenler", []))
        # Ana güvenli eşik: iki kısa momentum da zayıfsa mevcut AL, BEKLE olur.
        if not (d3_ok or d5_ok):
            aday["karar"] = "🟡 BEKLE"
            nedenler.append(f"Kısa momentum zayıf (3dk %{d3:+.2f}, 5dk %{d5:+.2f})")
            aday["nedenler"] = nedenler
            aday["kod_oneri_veto"] = True
            aday["kod_oneri_veto_nedeni"] = "momentum"
            return False
        if kalite < KOD_ONERI_KALITE_MIN:
            aday["karar"] = "🟡 BEKLE"
            nedenler.append(f"Birleşik kod öneri kalitesi düşük ({kalite:.1f} < {KOD_ONERI_KALITE_MIN:.0f})")
            aday["nedenler"] = nedenler
            aday["kod_oneri_veto"] = True
            aday["kod_oneri_veto_nedeni"] = "kalite"
            return False
        teyitler = []
        if d3_ok: teyitler.append("3dk")
        if d5_ok: teyitler.append("5dk")
        if momentum_bonus: teyitler.append("Genel Güç/Momentum Kalitesi ≥55.87")
        if genel_bonus: teyitler.append("Güçlü rejimde Genel Güç ≥65.50")
        if kalicilik_bonus: teyitler.append("Güçlü rejimde Kalıcılık bandı =100")
        if teyitler:
            nedenler.append("Kod öneri teyidi: " + " + ".join(teyitler))
        aday["nedenler"] = nedenler

    aday["kod_oneri_veto"] = False
    aday["kod_oneri_veto_nedeni"] = ""
    return True


def neden_kontrolu(aday):
    """Telegram AL nedenlerini 10 ölçütte sayar; 5 ana ölçütten en az 3'ü şarttır."""
    teknik = aday.get("teknik") or {}
    mikro = aday.get("mikro") or {}
    try:
        adx = float(teknik.get("adx", 0) or 0)
        ema20 = float(teknik.get("ema20", 0) or 0)
        ema50 = float(teknik.get("ema50", 0) or 0)
        fiyat = float(aday.get("fiyat", 0) or 0)
        macd_hist = float(teknik.get("macd_hist", 0) or 0)
        d3 = float(mikro.get("d3", 0) or 0)
        d5 = float(mikro.get("d5", 0) or 0)
    except (TypeError, ValueError):
        adx = ema20 = ema50 = fiyat = macd_hist = d3 = d5 = 0.0

    checks = [
        (adx >= 30.0, "Trend çok güçlü"),
        (bool(aday.get("momentum_hizlaniyor")), "Momentum hızlanıyor"),
        (bool(aday.get("hacim_hizlaniyor")), "Hacim hızlanıyor"),
        (bool(aday.get("btc_farki_aciliyor")), "BTC farkı açılıyor"),
        (bool(aday.get("lider_gucleniyor")), "Lider güçleniyor"),
        (bool(aday.get("basamakli_trend")), "Basamaklı trend korunuyor"),
        (d3 >= KOD_ONERI_D3_ESIK, "3dk momentum pozitif"),
        (d5 >= KOD_ONERI_D5_ESIK, "5dk momentum pozitif"),
        (ema20 > ema50 and fiyat > ema20, "EMA trendi yukarı"),
        (macd_hist > 0, "MACD pozitif"),
    ]
    ana_sayi = sum(1 for ok, _ in checks[:5] if ok)
    saglanan = [ad for ok, ad in checks if ok]
    aday["neden_saglanan"] = saglanan
    aday["neden_sayi"] = len(saglanan)
    aday["neden_toplam"] = len(checks)
    aday["neden_ana_sayi"] = ana_sayi
    return ana_sayi >= 3


def stable_coin_mi(symbol):
    coin = symbol.replace("TRY", "")
    return coin in STABLE_COINLER


def haber_puani(symbol):
    coin = symbol.replace("TRY", "").lower()
    puan = 0
    negatif_haber = False

    for kaynak in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(kaynak)

            for item in feed.entries[:25]:
                baslik = item.title.lower()

                if coin in baslik:
                    puan += 8

                    for kelime in POZITIF:
                        if kelime in baslik:
                            puan += 5

                    for kelime in NEGATIF:
                        if kelime in baslik:
                            puan -= 15
                            negatif_haber = True
        except:
            pass

    puan = max(min(puan, 20), 0)

    if negatif_haber and puan < 10:
        puan = 0

    return puan



# ==========================================
# H MANTIĞI - TEKNİK ANALİZ KATMANI
# Commit: AI AL V3.2 - Roket RSI ust siniri 75
# Bu katman aday seçimini değiştirmez; Top 10 adayı analiz için zenginleştirir.
# ==========================================

def ema_hesapla(veriler, periyot):
    if len(veriler) < periyot:
        return None
    ema = sum(veriler[:periyot]) / periyot
    k = 2 / (periyot + 1)
    for fiyat in veriler[periyot:]:
        ema = fiyat * k + ema * (1 - k)
    return ema


def ema_serisi(veriler, periyot):
    if len(veriler) < periyot:
        return []
    sonuc = [None] * (periyot - 1)
    ema = sum(veriler[:periyot]) / periyot
    sonuc.append(ema)
    k = 2 / (periyot + 1)
    for fiyat in veriler[periyot:]:
        ema = fiyat * k + ema * (1 - k)
        sonuc.append(ema)
    return sonuc


def rsi_hesapla(kapanislar, periyot=14):
    if len(kapanislar) < periyot + 1:
        return None
    farklar = [kapanislar[i] - kapanislar[i - 1] for i in range(1, len(kapanislar))]
    kazanclar = [max(x, 0) for x in farklar]
    kayiplar = [max(-x, 0) for x in farklar]
    ort_kazanc = sum(kazanclar[:periyot]) / periyot
    ort_kayip = sum(kayiplar[:periyot]) / periyot
    for i in range(periyot, len(farklar)):
        ort_kazanc = ((ort_kazanc * (periyot - 1)) + kazanclar[i]) / periyot
        ort_kayip = ((ort_kayip * (periyot - 1)) + kayiplar[i]) / periyot
    if ort_kayip == 0:
        return 100.0
    rs = ort_kazanc / ort_kayip
    return 100 - (100 / (1 + rs))


def macd_hesapla(kapanislar):
    ema12 = ema_serisi(kapanislar, 12)
    ema26 = ema_serisi(kapanislar, 26)
    if not ema12 or not ema26:
        return None, None, None
    macd_seri = []
    for i in range(len(kapanislar)):
        if i < len(ema12) and i < len(ema26) and ema12[i] is not None and ema26[i] is not None:
            macd_seri.append(ema12[i] - ema26[i])
    if len(macd_seri) < 9:
        return None, None, None
    sinyal = ema_hesapla(macd_seri, 9)
    macd = macd_seri[-1]
    histogram = macd - sinyal if sinyal is not None else None
    return macd, sinyal, histogram


def atr_adx_hesapla(yuksekler, dusukler, kapanislar, periyot=14):
    if len(kapanislar) < (periyot * 2) + 1:
        return None, None
    tr, arti_dm, eksi_dm = [], [], []
    for i in range(1, len(kapanislar)):
        yukari = yuksekler[i] - yuksekler[i - 1]
        asagi = dusukler[i - 1] - dusukler[i]
        arti_dm.append(yukari if yukari > asagi and yukari > 0 else 0)
        eksi_dm.append(asagi if asagi > yukari and asagi > 0 else 0)
        tr.append(max(
            yuksekler[i] - dusukler[i],
            abs(yuksekler[i] - kapanislar[i - 1]),
            abs(dusukler[i] - kapanislar[i - 1])
        ))

    atr = sum(tr[:periyot]) / periyot
    arti_s = sum(arti_dm[:periyot])
    eksi_s = sum(eksi_dm[:periyot])
    dxler = []

    for i in range(periyot, len(tr)):
        atr = ((atr * (periyot - 1)) + tr[i]) / periyot
        arti_s = arti_s - (arti_s / periyot) + arti_dm[i]
        eksi_s = eksi_s - (eksi_s / periyot) + eksi_dm[i]
        arti_di = 100 * (arti_s / (atr * periyot)) if atr else 0
        eksi_di = 100 * (eksi_s / (atr * periyot)) if atr else 0
        toplam = arti_di + eksi_di
        dxler.append(100 * abs(arti_di - eksi_di) / toplam if toplam else 0)

    if len(dxler) < periyot:
        return atr, None
    adx = sum(dxler[:periyot]) / periyot
    for dx in dxler[periyot:]:
        adx = ((adx * (periyot - 1)) + dx) / periyot
    return atr, adx


def teknik_analiz_hesapla(symbol):
    try:
        d = veri_getir(symbol, 120)
        c = d.get("c", [])
        h = d.get("h", [])
        l = d.get("l", [])
        if len(c) < 55 or len(h) != len(c) or len(l) != len(c):
            return None

        ema20 = ema_hesapla(c, 20)
        ema50 = ema_hesapla(c, 50)
        rsi = rsi_hesapla(c, 14)
        macd, macd_sinyal, macd_hist = macd_hesapla(c)
        atr, adx = atr_adx_hesapla(h, l, c, 14)
        fiyat = c[-1]
        atr_yuzde = (atr / fiyat) * 100 if atr is not None and fiyat else None

        return {
            "ema20": round(ema20, 6) if ema20 is not None else None,
            "ema50": round(ema50, 6) if ema50 is not None else None,
            "rsi": round(rsi, 2) if rsi is not None else None,
            "macd": round(macd, 6) if macd is not None else None,
            "macd_sinyal": round(macd_sinyal, 6) if macd_sinyal is not None else None,
            "macd_hist": round(macd_hist, 6) if macd_hist is not None else None,
            "adx": round(adx, 2) if adx is not None else None,
            "atr": round(atr, 6) if atr is not None else None,
            "atr_yuzde": round(atr_yuzde, 2) if atr_yuzde is not None else None
        }
    except Exception as e:
        print(f"Teknik analiz hata ({symbol}):", e)
        return None


# ==========================================
# H MANTIĞI - KARAR MOTORU
# Radar ilk adayları bulur; bu katman teknik yapıyı AL / BEKLE / SAT-PAS kararına çevirir.
# ==========================================

def h_karar_hesapla(aday):
    """
    AI karar motoru V3 - bağımsız AL teyidi.
    Amaç: Coin Radar adayını otomatik onaylamak yerine bağımsız teknik AL teyidi vermek.
    AVNT/ENA gibi zayıf devam teyitlerinde AL'ı zorlaştırır;
    NAP/MIRA gibi güçlü trendleri ve H gibi istisnai Yıldız devamlarını korur.
    """
    teknik = aday.get("teknik")
    if not teknik:
        return {
            "ai_skoru": 0,
            "karar": "🟡 BEKLE",
            "risk": "Bilinmiyor",
            "nedenler": ["Teknik veri yetersiz"]
        }

    ema20 = teknik.get("ema20")
    ema50 = teknik.get("ema50")
    rsi = teknik.get("rsi")
    macd_hist = teknik.get("macd_hist")
    adx = teknik.get("adx")
    atr_yuzde = teknik.get("atr_yuzde")

    fiyat = aday.get("fiyat", 0)
    radar = aday.get("radar_skoru", 0)
    kategori = aday.get("radar_kategori", "")
    lider = aday.get("lider_skoru", 0)
    deg1 = aday.get("degisim1", 0)
    deg3 = aday.get("degisim3", 0)
    deg24 = aday.get("degisim24", 0)

    skor = 20.0
    nedenler = []

    # 1) Radar kalitesi: artık taban skoru şişirmiyor.
    skor += max(0, min((radar - 55) * 0.50, 20))

    # Radar alarm seviyesine küçük kalite bonusu.
    if "Yıldız" in kategori:
        skor += 10
        nedenler.append("Radar Yıldız")
    elif "Elit" in kategori:
        skor += 6
    elif "Trader" in kategori:
        skor += 4
    elif "Roket" in kategori:
        skor += 2

    # 2) EMA: önemli ama tek başına veto değil.
    if ema20 is not None and ema50 is not None:
        if ema20 > ema50:
            skor += 12
            nedenler.append("EMA trendi yukarı")
        else:
            skor -= 8
            nedenler.append("EMA trendi aşağı")

        if fiyat and ema20:
            if fiyat > ema20:
                skor += 4
            else:
                skor -= 5

    # 3) RSI: 50-65 en temiz giriş bölgesi.
    if rsi is not None:
        if 50 <= rsi <= 65:
            skor += 12
            nedenler.append("RSI sağlıklı güçlü bölgede")
        elif 45 <= rsi < 50:
            skor += 5
        elif 65 < rsi <= 72:
            skor += 6
            nedenler.append("RSI güçlü ama ısınıyor")
        elif 72 < rsi <= 78:
            skor += 1
            nedenler.append("RSI yüksek")
        elif 78 < rsi <= 85:
            skor -= 7
            nedenler.append("RSI aşırı alıma yakın")
        elif rsi > 85:
            skor -= 12
            nedenler.append("RSI aşırı alım")
        elif rsi < 40:
            skor -= 10
            nedenler.append("RSI zayıf")

    # 4) MACD: devam teyidi.
    macd_pozitif = macd_hist is not None and macd_hist > 0
    if macd_hist is not None:
        if macd_pozitif:
            skor += 12
            nedenler.append("MACD pozitif")
        else:
            skor -= 14
            nedenler.append("MACD negatif")

    # 5) ADX: AL kararının ana ayırıcılarından biri.
    if adx is not None:
        if adx >= 40:
            skor += 18
            nedenler.append("Trend çok güçlü")
        elif adx >= 30:
            skor += 14
            nedenler.append("Trend çok güçlü")
        elif adx >= 25:
            skor += 9
            nedenler.append("Trend güçlü")
        elif adx >= 20:
            skor += 3
            nedenler.append("Trend orta")
        else:
            skor -= 8
            nedenler.append("Trend gücü düşük")

    # 6) ATR: sağlıklı hareketi ödüllendir, aşırı oynaklığı azalt.
    if atr_yuzde is not None:
        if 1 <= atr_yuzde <= 4.5:
            skor += 5
        elif atr_yuzde > 7:
            skor -= 10
            nedenler.append("Volatilite çok yüksek")
        elif atr_yuzde > 5:
            skor -= 5
            nedenler.append("Volatilite yüksek")

    # 7) Göreceli güç ve liderlik.
    if aday.get("btcden_guclu"):
        skor += 4

    if lider >= 7:
        skor += 5
    elif lider >= 5:
        skor += 2

    # 8) Momentum kalitesi.
    # Çok yükselmiş olmak tek başına kötü değildir; devam gücü varsa H gibi hareketler korunur.
    if 1 <= deg1 <= 4:
        skor += 5
    elif 4 < deg1 <= 8:
        skor += 2
    elif deg1 > 8:
        skor -= 4

    if 3 <= deg3 <= 8:
        skor += 7
    elif 8 < deg3 <= 15:
        skor += 4
    elif deg3 > 15:
        skor += 1

    if deg24 > 30:
        skor -= 5

    # ADX düşükken 100/100 görünmesini engelle.
    if adx is not None:
        if adx < 20:
            skor = min(skor, 74)
        elif adx < 25:
            skor = min(skor, 82)
        elif adx < 30 and "Yıldız" not in kategori:
            skor = min(skor, 90)

    skor = round(max(0, min(skor, 100)), 1)

    # --------------------------------------------------
    # AL KAPISI V3
    # Radar adayı bulur; AI Assistant bağımsız teknik teyit ister.
    # Amaç: Radar'a düşen her coine otomatik AL dememek.
    # --------------------------------------------------
    ema_yukari = (
        ema20 is not None
        and ema50 is not None
        and ema20 > ema50
        and fiyat > ema20
    )

    rsi_temiz = rsi is not None and 48 <= rsi <= 75
    rsi_kabul = rsi is not None and 45 <= rsi <= 75

    # Normal Radar adayında artık daha sıkı teknik teyit:
    # EMA yukarı + sağlıklı RSI + güçlü ADX + pozitif MACD + yüksek AI skoru.
    normal_al = (
        not aday.get("erken_aday", False)
        and ema_yukari
        and rsi_temiz
        and macd_pozitif
        and adx is not None
        and adx >= 27
        and skor >= 80
    )

    # Çok güçlü Elit sinyalde RSI biraz daha geniş olabilir,
    # ama EMA ve trend teyidi yine zorunlu.
    elit_al = (
        "Elit" in kategori
        and radar >= 82
        and ema_yukari
        and rsi_kabul
        and macd_pozitif
        and adx is not None
        and adx >= 28
        and skor >= 85
    )

    # Yıldız istisnası:
    # H örneğinde olduğu gibi çok güçlü devam hareketlerinde EMA aşağı olsa bile
    # Radar + liderlik + ADX + MACD + momentum birlikte güçlü ise AL korunabilir.
    yildiz_istisna = (
        "Yıldız" in kategori
        and radar >= 90
        and lider >= 7
        and aday.get("btcden_guclu")
        and macd_pozitif
        and adx is not None
        and adx >= 28
        and rsi is not None
        and rsi >= 50
        and deg3 >= 8
        and skor >= 85
    )

    # Early Capture ayrı tutulur:
    # erken yakalamanın amacı daha düşük Radar skorunda teknik güçlenmeyi yakalamak.
    # Bu yüzden Radar yüksekliği değil, temiz teknik yapı aranır.
    erken_al = (
        aday.get("erken_aday", False)
        and ema_yukari
        and rsi is not None
        and 48 <= rsi <= 70
        and macd_pozitif
        and adx is not None
        and adx >= 30
        and skor >= 80
    )

    # Mikro Erken istisnası:
    # Dakikalık hareket henüz saatlik Radar skorunu tam oluşturmadan yakalanabilir.
    # ADX gecikmeli bir gösterge olduğu için eşik biraz daha düşük; buna karşılık
    # güçlü mikro skor + fiyat/hacim ivmesi birlikte zorunludur.
    mikro = aday.get("mikro") or {}
    mikro_erken_al = (
        aday.get("mikro_aday", False)
        and "Mikro Erken" in kategori
        and ema_yukari
        and rsi is not None
        and 47 <= rsi <= 72
        and macd_pozitif
        and adx is not None
        and adx >= 24
        and skor >= 76
        and float(mikro.get("skor", 0) or 0) >= 62
        and float(mikro.get("d1", 0) or 0) >= 0.15
        and float(mikro.get("d3", 0) or 0) >= 0.35
        and float(mikro.get("d5", 0) or 0) >= 0.45
        and not mikro.get("sisti", False)
        and (mikro.get("fiyat_ivme") or mikro.get("basamak"))
        and (mikro.get("hacim_ivmeleniyor") or float(mikro.get("hacim1x", 0) or 0) >= 1.40)
    )

    if normal_al or elit_al or yildiz_istisna or erken_al or mikro_erken_al:
        karar = "🟢 AL"
    elif skor >= 55:
        karar = "🟡 BEKLE"
    else:
        karar = "🔴 SAT / PAS"

    # Risk sadece bilgilendirme; Telegram yalnızca AL kararında konuşuyor.
    if atr_yuzde is None:
        risk = "Bilinmiyor"
    elif atr_yuzde <= 3:
        risk = "Düşük"
    elif atr_yuzde <= 5:
        risk = "Orta"
    else:
        risk = "Yüksek"

    if not nedenler:
        nedenler.append("Teknik göstergeler karışık")

    return {
        "ai_skoru": skor,
        "karar": karar,
        "risk": risk,
        "nedenler": nedenler[:4]
    }


# Başlangıçta yalnızca tarayıcı durumunu bildirir; emir veya pozisyon yönetimi yoktur.
telegram_gonder("✅ BTCTÜRK RADAR başladı. Tarama başlıyor.")


while True:
    try:
        print()
        print("AI COIN ASSISTANT - CORE")
        print("--------------------------------")

        btc_d = btc_degisimleri()
        btc = btc_d.get("3s", 0)

        tarama_sayaci += 1
        tam_tarama = (tarama_sayaci == 1 or tarama_sayaci % TAM_TARAMA_DONGUSU == 0)

        if tam_tarama:
            print("Tarama modu: TAM PIYASA TARAMASI")
        else:
            print("Tarama modu: HIZLI HAREKET TARAMASI")

        ticker_response = requests.get(
            "https://api.btcturk.com/api/v2/ticker",
            timeout=10
        )
        ticker_response.raise_for_status()
        ticker = ticker_response.json().get("data", [])

        # Mevcut ticker cevabını öğrenme katmanında da kullan; ekstra API isteği yok.
        al_ogrenme_guncelle(ticker)
        kesif_gozlem_guncelle(ticker)
        rejim_raporu_gerekirse_gonder()
        yuzde5_basariraporu_gerekirse_gonder()
        kesif_raporu_gerekirse_gonder()

        ticker_fiyat_haritasi = {}
        for _coin in ticker:
            try:
                _sym = _coin.get("pair", "")
                _f = float(_coin.get("last", 0) or 0)
                if _sym and _f > 0:
                    ticker_fiyat_haritasi[_sym] = _f
            except Exception:
                pass

        piyasa_fiyatlari = {}
        piyasa_degisim1leri = []
        piyasa_degisim3leri = []
        adaylar = []

        for coin in ticker:
            try:
                symbol = coin.get("pair", "")

                if not symbol.endswith("TRY"):
                    continue
                if symbol == "BTCTRY":
                    continue
                if stable_coin_mi(symbol):
                    continue
                if len(symbol) > 15:
                    continue

                # 1 dakikalık hızlı ön tarama:
                # Ticker fiyatını önceki dakikayla karşılaştır.
                try:
                    ticker_fiyat = float(coin.get("last", 0) or 0)
                except (TypeError, ValueError):
                    ticker_fiyat = 0

                onceki_fiyat = son_fiyatlar.get(symbol)
                hizli_degisim = 0.0
                hizli_degisim3 = 0.0
                hizli_degisim5 = 0.0

                if ticker_fiyat > 0 and onceki_fiyat and onceki_fiyat > 0:
                    hizli_degisim = ((ticker_fiyat - onceki_fiyat) / onceki_fiyat) * 100

                # Sadece ticker verisiyle 3-5 dakikalik basamakli hizlanmayi izle.
                # Ek BTCTurk mum istegi yok; API yukunu artirmaz.
                gecmis = son_ticker_gecmisi.setdefault(symbol, [])
                if ticker_fiyat > 0:
                    gecmis.append(ticker_fiyat)
                    if len(gecmis) > TICKER_GECMIS_UZUNLUK:
                        del gecmis[:-TICKER_GECMIS_UZUNLUK]

                    if len(gecmis) >= 4 and gecmis[-4] > 0:
                        hizli_degisim3 = ((ticker_fiyat - gecmis[-4]) / gecmis[-4]) * 100
                    if len(gecmis) >= 6 and gecmis[-6] > 0:
                        hizli_degisim5 = ((ticker_fiyat - gecmis[-6]) / gecmis[-6]) * 100

                    son_fiyatlar[symbol] = ticker_fiyat

                # 5 dakikalık tam taramalar arasında:
                # - %0.40+ hızlı hareket eden coinler,
                # - veya Çoklu Güç Havuzu'nda bulunan coinler
                # derin analiz edilir.
                simdi = time.time()
                izleme_bitis = guc_izleme_havuzu.get(symbol, 0)
                havuzda = izleme_bitis > simdi

                if izleme_bitis and not havuzda:
                    guc_izleme_havuzu.pop(symbol, None)

                # Fast Scan V2:
                # Tek dakikada %0.40 yapmasa bile 3 dk +%0.75 veya 5 dk +%1.10
                # basamakli hizlanan coin derin incelemeye girer. TT tipi hareketleri kacirmamak icin.
                ticker_basamak_hizli = (hizli_degisim3 >= 0.75 or hizli_degisim5 >= 1.10)

                if (
                    not tam_tarama
                    and abs(hizli_degisim) < HIZLI_HAREKET_ESIGI
                    and not ticker_basamak_hizli
                    and not havuzda
                ):
                    continue

                if not tam_tarama:
                    if havuzda and abs(hizli_degisim) < HIZLI_HAREKET_ESIGI and not ticker_basamak_hizli:
                        kaynak = "HAVUZ"
                    elif ticker_basamak_hizli and abs(hizli_degisim) < HIZLI_HAREKET_ESIGI:
                        kaynak = "HIZLI3"
                    else:
                        kaynak = "HIZLI"
                    print(
                        f"[{kaynak}] {symbol} | 1dk: %{hizli_degisim:.2f} | "
                        f"3dk: %{hizli_degisim3:.2f} | 5dk: %{hizli_degisim5:.2f}"
                    )

                d = veri_getir(symbol, 24)
                o = d.get("o", [])
                h = d.get("h", [])
                c = d.get("c", [])
                v = d.get("v", [])

                if min(len(o), len(h), len(c), len(v)) < 24:
                    continue

                fiyat = c[-1]
                if not fiyat or not c[-2] or not c[-4] or not c[-24]:
                    continue

                degisim1 = ((c[-1] - c[-2]) / c[-2]) * 100
                degisim3 = ((c[-1] - c[-4]) / c[-4]) * 100
                degisim24 = ((c[-1] - c[-24]) / c[-24]) * 100

                piyasa_fiyatlari[symbol] = fiyat
                piyasa_degisim1leri.append(degisim1)
                piyasa_degisim3leri.append(degisim3)

                # Mikro veri artık tüm piyasada çağrılmaz.
                # Önce saatlik/Radar motoru adayları daraltır; 1-3-5-10 dk veri yalnız teknik havuza kalanlarda çekilir.
                mikro = {}
                mikro_skor = 0.0

                son_hacim = v[-1]
                ort_hacim = sum(v[-6:-1]) / 5
                if ort_hacim <= 0:
                    continue

                hacim_kat = son_hacim / ort_hacim

                btc_guc_skoru, btc_fark1, btc_fark3, btc_fark24 = btc_gucu_v2_hesapla(
                    degisim1, degisim3, degisim24, btc_d
                )

                btcden_guclu = btc_guc_skoru >= 4 and btc_fark3 >= 0.5
                son_mum_yesil = c[-1] > o[-1]
                zirve_yakin = fiyat > max(h[-12:-1]) * 0.995
                yeni_zirve = fiyat >= max(h[-24:-1])
                satis_baskisi = son_hacim > ort_hacim * 5 and degisim1 < 0
                haber_skoru = haber_puani(symbol)

                hacim_skoru = min(hacim_kat * 2, 10)
                momentum_skoru = max(0, degisim3 * 2)
                mum_skoru = 1 if son_mum_yesil else 0
                zirve_skoru = 1 if zirve_yakin else 0

                genel_skor = (
                    hacim_skoru * 0.50
                    + momentum_skoru * 0.20
                    + btc_guc_skoru * 0.15
                    + haber_skoru * 0.20
                    + mum_skoru
                    + zirve_skoru
                )

                kalite_skoru = (
                    hacim_skoru * 0.55
                    + momentum_skoru * 0.30
                    + btc_guc_skoru * 0.15
                    + mum_skoru
                    + zirve_skoru
                )

                if hacim_kat >= 5:
                    genel_skor += 4
                if hacim_kat >= 8:
                    genel_skor += 6

                if haber_skoru >= 15:
                    genel_skor += 4
                if haber_skoru > 0 and hacim_kat > 3:
                    genel_skor += 5

                if degisim24 > 10:
                    genel_skor -= 4
                if degisim3 > 7:
                    genel_skor -= 4
                if degisim1 > 4:
                    genel_skor -= 4
                if degisim24 > 0 and degisim3 > degisim24 * 0.85:
                    genel_skor -= 2
                if degisim3 > 0 and degisim1 > degisim3 * 0.65:
                    genel_skor -= 2
                if hacim_kat > 7 and degisim3 > 6:
                    genel_skor -= 3
                if satis_baskisi:
                    genel_skor -= 5

                if btc_fark3 >= 4:
                    genel_skor += 2
                elif btc_fark3 >= 2:
                    genel_skor += 1

                lider_skoru = lider_skoru_hesapla(
                    hacim_kat, degisim1, degisim3, degisim24,
                    btc_fark1, btc_fark3, btc_fark24,
                    zirve_yakin, yeni_zirve
                )

                if lider_skoru >= 7:
                    genel_skor += 2
                elif lider_skoru >= 5:
                    genel_skor += 1

                if zirve_yakin or yeni_zirve:
                    genel_skor += 1

                radar_skoru = guc_skoru_hesapla(
                    hacim_kat, degisim1, degisim3, degisim24,
                    btc_guc_skoru, lider_skoru, haber_skoru,
                    satis_baskisi, btc_fark3, zirve_yakin, yeni_zirve
                )

                # --------------------------------------------------
                # Early Capture V1 + gerçek Coin Radar alarm kapıları
                # --------------------------------------------------
                onceki = onceki_tarama.get(symbol)

                hacim_hizlaniyor = False
                momentum_hizlaniyor = False
                btc_farki_aciliyor = False
                lider_gucleniyor = False

                if onceki:
                    eski_hacim = onceki.get("hacim", hacim_kat)
                    eski_degisim3 = onceki.get("degisim3", degisim3)
                    eski_btc_fark3 = onceki.get("btc_fark3", btc_fark3)
                    eski_lider = onceki.get("lider_skoru", lider_skoru)

                    hacim_hizlaniyor = (
                        eski_hacim > 0
                        and hacim_kat >= eski_hacim * 1.25
                        and hacim_kat - eski_hacim >= 0.8
                    )
                    momentum_hizlaniyor = degisim3 - eski_degisim3 >= 0.45
                    btc_farki_aciliyor = btc_fark3 - eski_btc_fark3 >= 0.35
                    lider_gucleniyor = lider_skoru - eski_lider >= 1

                onceki_tarama[symbol] = {
                    "hacim": hacim_kat,
                    "degisim3": degisim3,
                    "btc_fark3": btc_fark3,
                    "lider_skoru": lider_skoru,
                    "zaman": time.time()
                }

                # Dinamik hareket teyitleri:
                # Bunlar RED/ATM tipi "nedenleri dolu" sinyallerin hareket tarafını oluşturur.
                dinamik_teyit_sayisi = sum([
                    bool(hacim_hizlaniyor),
                    bool(momentum_hizlaniyor),
                    bool(btc_farki_aciliyor),
                    bool(lider_gucleniyor),
                ])

                # Mevcut Early yolu korunuyor; sadece 3s üst sınırı 3'ten 5'e açıldı.
                # Böylece güçlenmeye devam eden coin Early ile Roket arasında boşluğa düşmez.
                erken_aday = (
                    2.5 <= hacim_kat < 8
                    and 0.5 <= degisim3 < 5
                    and degisim1 > 0
                    and btc_guc_skoru >= 3
                    and btc_fark3 >= 0
                    and radar_skoru >= 45
                    and kalite_skoru >= 6
                    and not satis_baskisi
                    and (
                        (hacim_hizlaniyor and momentum_hizlaniyor)
                        or (momentum_hizlaniyor and btc_farki_aciliyor)
                        or (hacim_hizlaniyor and lider_gucleniyor)
                    )
                )

                # ENA tipi basamaklı güçlenme:
                # Bir anda %0.40 sıçramasa bile 3s momentumunu koruyan,
                # hacmi canlı, BTC'ye göre zayıflamayan ve liderliği oluşan coinleri izler.
                basamakli_trend = False
                if onceki:
                    eski_degisim3 = onceki.get("degisim3", degisim3)
                    eski_hacim = onceki.get("hacim", hacim_kat)
                    basamakli_trend = (
                        1.0 <= degisim3 <= 10
                        and degisim1 > 0
                        and hacim_kat >= 1.8
                        and hacim_kat >= eski_hacim * 0.90
                        and degisim3 >= eski_degisim3 - 0.15
                        and btc_fark3 >= 0
                        and lider_skoru >= 4
                        and not satis_baskisi
                    )

                # Çoklu Güç Havuzu adayı:
                # Radar kategorisine girmese bile en az 2 dinamik teyidi olan
                # veya basamaklı trendi koruyan coin teknik motora alınır.
                guc_havuzu_adayi = (
                    not satis_baskisi
                    and radar_skoru >= 40
                    and kalite_skoru >= 5
                    and 0.5 <= degisim3 <= 10
                    and degisim1 > -0.5
                    and hacim_kat >= 1.8
                    and btc_fark3 >= -0.5
                    and (
                        (
                            dinamik_teyit_sayisi >= 2
                            and (hacim_hizlaniyor or momentum_hizlaniyor)
                        )
                        or basamakli_trend
                    )
                )

                # Mikro Ön Alarm V2:
                # Coin henüz klasik Radar / Güç Havuzu kapısına girmemiş olsa bile
                # ticker'da belirgin hızlanma gösteriyorsa yalnız o coin için 1-3-5-10 dk
                # mikro analiz açılır. Böylece bütün piyasaya 1 dk mum isteği atılmadan
                # LAYER tipi yeni başlayan patlamalar daha erken incelenebilir.
                mikro_on_alarm = (
                    not satis_baskisi
                    and degisim3 <= 10
                    and degisim1 <= 6
                    and (
                        # Ani tek-dakika hizlanma
                        (hizli_degisim >= 0.25 and hacim_kat >= 1.15 and btc_fark3 >= -1.0)
                        # TT tipi basamakli hareket: tek mum patlamasi olmadan 3-5 dk birikimli ivme
                        or (
                            (hizli_degisim3 >= 0.70 or hizli_degisim5 >= 1.05)
                            and hacim_kat >= 1.15
                            and degisim1 >= -0.25
                            and btc_fark3 >= -1.0
                        )
                        # Saatlik motor da yeni guclenmeye baslamissa
                        or (
                            0.70 <= degisim1 <= 4.5
                            and 0.40 <= degisim3 <= 7.0
                            and hacim_kat >= 1.50
                            and btc_fark3 >= -0.8
                        )
                    )
                )

                mikro_aday = False

                if erken_aday or guc_havuzu_adayi or mikro_on_alarm:
                    guc_izleme_havuzu[symbol] = time.time() + GUC_IZLEME_SURESI

                yildiz_adayi = (
                    radar_skoru >= 88
                    and lider_skoru >= 7
                    and btc_guc_skoru >= 7
                    and kalite_skoru >= 14
                    and hacim_kat >= 5
                    and degisim1 > 1
                    and degisim3 >= 4
                    and zirve_yakin
                )

                elit_adayi = (
                    radar_skoru >= 74
                    and lider_skoru >= 5
                    and btc_guc_skoru >= 5
                    and kalite_skoru >= 10
                    and hacim_kat >= 8
                    and degisim1 > 0
                    and degisim3 >= 3
                    and btcden_guclu
                )

                trader_adayi = (
                    radar_skoru >= 55
                    and hacim_kat >= 15
                    and btcden_guclu
                    and btc_guc_skoru >= 4
                    and degisim3 >= 6
                )

                roket_adayi = (
                    radar_skoru >= 62
                    and kalite_skoru >= 8
                    and hacim_kat >= 5
                    and degisim1 > 0
                    and degisim3 >= 1.5
                    and not (hacim_kat >= 10 and degisim3 < 4 and lider_skoru < 7)
                    and btcden_guclu
                    and btc_guc_skoru >= 4
                    and (haber_skoru > 0 or lider_skoru >= 5)
                )

                assistant_ana_aday = (
                    erken_aday
                    or guc_havuzu_adayi
                    or yildiz_adayi
                    or elit_adayi
                    or trader_adayi
                    or roket_adayi
                )

                # Klasik aday değilse bile Mikro Ön Alarm teknik ön havuza sokabilir.
                # Asıl adaylık biraz aşağıda gerçek 1-3-5-10 dk verisiyle doğrulanır.
                if not assistant_ana_aday and not mikro_on_alarm:
                    continue

                if yildiz_adayi:
                    radar_kategori = "⭐ Yıldız"
                elif elit_adayi:
                    radar_kategori = "🔥 Elit Roket"
                elif trader_adayi:
                    radar_kategori = "📊 Trader Hacim"
                elif roket_adayi:
                    radar_kategori = "🚀 Roket Adayı"
                elif erken_aday:
                    radar_kategori = "🌱 Erken Aday"
                else:
                    radar_kategori = "⚡ Güçleniyor"

                adaylar.append({
                    "symbol": symbol,
                    "fiyat": fiyat,
                    "radar_skoru": radar_skoru,
                    "radar_kategori": radar_kategori,
                    "orijinal_erken_aday": erken_aday,
                    "erken_aday": erken_aday,
                    "assistant_ana_aday": assistant_ana_aday,
                    "mikro_on_alarm": mikro_on_alarm,
                    "hizli_degisim1": round(hizli_degisim, 3),
                    "hizli_degisim3": round(hizli_degisim3, 3),
                    "hizli_degisim5": round(hizli_degisim5, 3),
                    "mikro_aday": mikro_aday,
                    "mikro": mikro,
                    "guc_havuzu_adayi": guc_havuzu_adayi,
                    "basamakli_trend": basamakli_trend,
                    "dinamik_teyit_sayisi": dinamik_teyit_sayisi,
                    "hacim_hizlaniyor": hacim_hizlaniyor,
                    "momentum_hizlaniyor": momentum_hizlaniyor,
                    "btc_farki_aciliyor": btc_farki_aciliyor,
                    "lider_gucleniyor": lider_gucleniyor,
                    "genel_skor": round(genel_skor, 2),
                    "kalite_skoru": round(kalite_skoru, 2),
                    "hacim": round(hacim_kat, 2),
                    "degisim1": round(degisim1, 2),
                    "degisim3": round(degisim3, 2),
                    "degisim24": round(degisim24, 2),
                    "btcden_guclu": btcden_guclu,
                    "btc_fark3": round(btc_fark3, 2),
                    "btc_guc_skoru": btc_guc_skoru,
                    "lider_skoru": round(lider_skoru, 2),
                    "haber_skoru": haber_skoru,
                    "zirve_yakin": zirve_yakin,
                    "yeni_zirve": yeni_zirve
                })

            except Exception as e:
                print(f"Coin hata ({coin.get('pair', '?')}):", e)

        # --------------------------------------------------
        # 60DK BAĞIMSIZ GÖRECELİ GÜÇ BONUSU
        # Öğrenme raporunda en güçlü eşikler:
        #   Coin - BTC 60dk > +0.98
        #   Coin - piyasa 60dk > +0.87
        # Bu bonus AL kapısını / AI skorunu DEĞİŞTİRMEZ. Yalnız bilgi ve eşit
        # Radar skorlarında öncelik amacıyla tutulur; gerçek sonucu AL öğrenmesi ölçer.
        # Hızlı taramada piyasa medyanı yalnız hareket eden coinlerden sapmasın diye
        # son TAM taramanın medyanı kullanılır.
        if tam_tarama and piyasa_degisim1leri:
            SON_PIYASA_MEDYAN_60 = statistics.median(piyasa_degisim1leri)
        piyasa_medyan60 = SON_PIYASA_MEDYAN_60
        btc60 = float(btc_d.get("1s", 0) or 0)

        for _a in adaylar:
            _coin60 = float(_a.get("degisim1", 0) or 0)
            _btc_rel60 = _coin60 - btc60
            _piy_rel60 = _coin60 - piyasa_medyan60
            _bonus = int(_btc_rel60 > 0.98) + int(_piy_rel60 > 0.87)
            _a["coin_btc_60"] = round(_btc_rel60, 2)
            _a["coin_piyasa_60"] = round(_piy_rel60, 2)
            _a["goreceli_guc_bonus"] = _bonus

        adaylar.sort(
            # Radar ana sıralama olarak kalır; bonus yalnız eşit Radar skorunda öncelik verir.
            key=lambda x: (x["radar_skoru"], x.get("goreceli_guc_bonus", 0), x["genel_skor"]),
            reverse=True
        )

        radar_top10 = adaylar[:10]

        # Radar Top10 dışında, hareket teyidi yüksek coinleri de teknik motora sok.
        guc_top10 = sorted(
            [a for a in adaylar if a.get("guc_havuzu_adayi")],
            key=lambda x: (
                x.get("dinamik_teyit_sayisi", 0),
                1 if x.get("basamakli_trend") else 0,
                x.get("genel_skor", 0),
                x.get("radar_skoru", 0),
            ),
            reverse=True
        )[:10]

        # Radar dışında Mikro Ön Alarm'a düşen en güçlü coinleri de ayrıca koru.
        # Böylece düşük Radar skoru nedeniyle Top10 dışında kalıp erken hareket kaçmaz.
        mikro_on_top = sorted(
            [a for a in adaylar if a.get("mikro_on_alarm")],
            key=lambda x: (
                x.get("hizli_degisim3", 0),
                x.get("hizli_degisim5", 0),
                x.get("hacim", 0),
                x.get("radar_skoru", 0),
            ),
            reverse=True
        )[:8]

        # Aynı coin listelerde varsa tek kez analiz edilir.
        top10 = []
        gorulenler = set()
        for aday in radar_top10 + guc_top10 + mikro_on_top:
            symbol = aday.get("symbol")
            if symbol in gorulenler:
                continue
            gorulenler.add(symbol)
            top10.append(aday)

        print(
            f"Teknik havuz: RadarTop10={len(radar_top10)} | "
            f"ÇokluGüç={len(guc_top10)} | MikroÖn={len(mikro_on_top)} | Benzersiz={len(top10)}"
        )

        # API optimizasyonu: pahalı 1 dk mum çağrısı yalnız gerçekten teknik motora kalan coinlerde yapılır.
        for a in top10:
            mikro = mikro_ivme_hesapla(a["symbol"])
            a["mikro"] = mikro
            mikro_skor = float(mikro.get("skor", 0) or 0)
            a["mikro_aday"] = bool(
                mikro
                and not mikro.get("sisti", False)
                and mikro_skor >= 55
                and float(mikro.get("d3", 0) or 0) >= 0.25
                and float(mikro.get("d5", 0) or 0) >= 0.35
                and (mikro.get("fiyat_ivme") or mikro.get("basamak"))
                and (mikro.get("hacim_ivmeleniyor") or float(mikro.get("hacim1x", 0) or 0) >= 1.30)
                and float(a.get("btc_fark3", 0) or 0) >= -0.8
            )

            # Normal Radar kapısından gelmeyen coin ancak gerçek mikro teyit aldıysa
            # teknik AL motoruna geçebilir. Mikro teyit yoksa burada elenir.
            if a.get("mikro_on_alarm") and not a.get("assistant_ana_aday"):
                if a["mikro_aday"]:
                    a["erken_aday"] = True
                    a["radar_kategori"] = "🌱 Mikro Erken"
                    a["assistant_ana_aday"] = True
                else:
                    a["mikro_on_alarm_reddedildi"] = True

        # Mikro ön alarmdan gelip teyit alamayanları teknik API çağrısından önce çıkar.
        top10 = [
            a for a in top10
            if a.get("assistant_ana_aday") and not a.get("mikro_on_alarm_reddedildi")
        ]

        # O anki piyasa rejimini tüm taranan coinlerin 3 saatlik medyanından çıkar.
        # V52 kalite katmanı güçlü rejimde Kalıcılık önerisini yalnız burada kullanır.
        piyasa_medyan3_anlik = statistics.median(piyasa_degisim3leri) if piyasa_degisim3leri else 0.0

        # H mantığı: Radar Top10 + Çoklu Güç + teyitli Mikro Erken üzerinde teknik analiz + karar motoru.
        for a in top10:
            teknik = teknik_analiz_hesapla(a["symbol"])
            a["teknik"] = teknik
            karar = h_karar_hesapla(a)
            a.update(karar)
            giris_k, devam_g = destek_skorlari(a)
            a["giris_kalitesi"] = giris_k
            a["devam_gucu"] = devam_g
            a["erken_puan"] = round(float((a.get("mikro") or {}).get("skor", 0) or 0), 1)
            kal_skor, kal_etiket, kal_nedenler = kalicilik_skoru_hesapla(a)
            a["kalicilik_skoru"] = kal_skor
            a["kalicilik_etiket"] = kal_etiket
            a["kalicilik_nedenler"] = kal_nedenler

            # V52: haftalık kod önerilerini S49 ölçeğinde birleşik kalite katmanına uygula.
            # Yeni AL üretmez; mevcut AL'ı daha seçici hale getirir.
            kod_onerisi_kalite_katmani(a, piyasa_medyan3_anlik)
            # Kod önerisi kalitesi mesaj puanı değildir; AL seçimi/sıralaması ve keşif raporunda kullanılır.
            # AL mesajı için 10 nedenden en az 3 ana neden (trend, momentum, hacim, BTC farkı, liderlik) şart.
            if a.get("karar") == "🟢 AL" and not neden_kontrolu(a):
                a["karar"] = "🟡 BEKLE"
                a.setdefault("nedenler", []).append(
                    f"Ana neden eşiği karşılanmadı ({a.get('neden_ana_sayi', 0)}/5; en az 3 gerekli)"
                )
                al_karar_izi(a.get("symbol", "?"), "neden", "VETO", ana_neden=a.get("neden_ana_sayi", 0))

            # Coin daha önce AL aldıysa, canlı teknik durumunu dinamik çıkış motoruna taşı.


            # --------------------------------------------------
            # AL DEBUG LOG
            # Telegram'a hiçbir şey göndermez.
            # Railway logunda coin neden AL / BEKLE olduğunu gösterir.
            # --------------------------------------------------
            if teknik:
                ema20 = teknik.get("ema20")
                ema50 = teknik.get("ema50")
                rsi = teknik.get("rsi")
                macd_hist = teknik.get("macd_hist")
                adx = teknik.get("adx")
                fiyat = a.get("fiyat", 0)
                kategori = a.get("radar_kategori", "")
                ai_skor = a.get("ai_skoru", 0)

                ema_ok = (
                    ema20 is not None
                    and ema50 is not None
                    and fiyat
                    and ema20 > ema50
                    and fiyat > ema20
                )
                macd_ok = macd_hist is not None and macd_hist > 0

                if a.get("erken_aday"):
                    rsi_ok = rsi is not None and 48 <= rsi <= 70
                    adx_ok = adx is not None and adx >= 30
                    skor_ok = ai_skor >= 80
                elif "Elit" in kategori:
                    rsi_ok = rsi is not None and 45 <= rsi <= 75
                    adx_ok = adx is not None and adx >= 28
                    skor_ok = ai_skor >= 85
                elif "Yıldız" in kategori:
                    # Yıldızlarda normal teknik kapıyı göster.
                    # H tipi istisnai devam varsa karar motoru ayrıca AL verebilir.
                    rsi_ok = rsi is not None and 48 <= rsi <= 70
                    adx_ok = adx is not None and adx >= 30
                    skor_ok = ai_skor >= 85
                else:
                    rsi_ok = rsi is not None and 48 <= rsi <= 75
                    adx_ok = adx is not None and adx >= 27
                    skor_ok = ai_skor >= 80

                def durum(ok):
                    return "✅" if ok else "❌"

                rsi_txt = "NA" if rsi is None else f"{rsi:.1f}"
                adx_txt = "NA" if adx is None else f"{adx:.1f}"
                macd_txt = "NA" if macd_hist is None else f"{macd_hist:.5f}"

                print(
                    f"[AL DEBUG] {a['symbol']} | {a.get('karar', '🟡 BEKLE')} | "
                    f"{kategori} | "
                    f"EMA {durum(ema_ok)} | "
                    f"RSI {rsi_txt} {durum(rsi_ok)} | "
                    f"MACD {macd_txt} {durum(macd_ok)} | "
                    f"ADX {adx_txt} {durum(adx_ok)} | "
                    f"AI {ai_skor}/100 {durum(skor_ok)} | "
                    f"Radar {a.get('radar_skoru', 0)} | "
                    f"KodKalite {a.get('kod_oneri_kalite', 0)}/100"
                )
            else:
                print(
                    f"[AL DEBUG] {a['symbol']} | 🟡 BEKLE | "
                    f"Teknik veri alınamadı"
                )

        # V57: Her teknik adayı karar anında kayda al. Bu sayede +%5 yapan ama alınmayan
        # coinlerde sorunun adaylık, AI kararı, risk, teyit, tekrar veya bütçe olup olmadığı görülür.
        for _iz in top10:
            _bp, _be, _bn = bes_plus_profil_yumusak(_iz)
            _mik = _iz.get("mikro") or {}
            al_karar_izi(
                _iz.get("symbol", "?"),
                "aday",
                _iz.get("karar", "BEKLE"),
                kategori=_iz.get("radar_kategori", ""),
                ai=float(_iz.get("ai_skoru", 0) or 0),
                radar=float(_iz.get("radar_skoru", 0) or 0),
                profil=float(_bp or 0),
                devam=float(_iz.get("devam_gucu", 0) or 0),
                kalicilik=float(_iz.get("kalicilik_skoru", 0) or 0),
                hacim=float(_iz.get("hacim", 0) or 0),
                risk=str(_iz.get("risk", "")),
                d1=float(_mik.get("d1", 0) or 0),
                d3=float(_mik.get("d3", 0) or 0),
                d5=float(_mik.get("d5", 0) or 0),
                d10=float(_mik.get("d10", 0) or 0),
            )

        # V51 3 günlük keşif: AL olup olmadığına bakmadan teknik havuzdaki güçlü adayları
        # gölge olarak 3 saat izler. Böylece bot sadece kendi AL'larından değil,
        # sonradan en çok güçlenen kaçırılmış coinlerden de kod önerisi çıkarabilir.
        for _kesif_aday in top10:
            kesif_gozlem_baslat(_kesif_aday, btc_d, piyasa_medyan3_anlik)

        # AL kalite koruması: Assistant AL bekletilmez.
        # Yalnızca çok düşük hacim + kısa vade aynı anda sönüyorsa bariz zayıflık veto edilir.
        for _a in top10:
            if _a.get("karar") == "🟢 AL":
                _m = _a.get("mikro") or {}
                if _m:
                    _gh = float(_a.get("hacim", 0) or 0)
                    _d1 = float(_m.get("d1", 0) or 0)
                    _d3 = float(_m.get("d3", 0) or 0)
                    _h1 = float(_m.get("hacim1x", 0) or 0)
                    _hi = float(_m.get("hacim_ivme", 0) or 0)

                    cok_zayif_hacim = _gh < 0.30 and _h1 < 0.80 and _hi < 1.00
                    mikro_sonuyor = _d1 < -0.15 and _d3 <= 0.10

                    if cok_zayif_hacim and mikro_sonuyor:
                        print(
                            f"[AL MIKRO VETO] {_a.get('symbol')} | "
                            f"Hacim={_gh:.2f}x | 1dkHacim={_h1:.2f}x | İvme={_hi:.2f}x | "
                            f"1dk={_d1:+.2f}% | 3dk={_d3:+.2f}%"
                        )
                        al_karar_izi(_a.get("symbol", "?"), "mikro", "VETO", neden="çok zayıf hacim + mikro sönüş", hacim=_gh, d1=_d1, d3=_d3)
                        _a["karar"] = "🟡 BEKLE"

        # İlk aday sıralamasını Radar yapar; H motorundan sonra en güçlü teknik fırsat üste çıkar.
        top10.sort(
            key=lambda x: (
                x.get("kod_oneri_kalite", 0),
                x.get("kod_oneri_momentum_blok", 0),
                x.get("ai_skoru", 0),
                x.get("radar_skoru", 0),
            ),
            reverse=True
        )

        if not top10:
            print("Şu an uygun aday yok.")
        else:
            gonderilecekler = []

            for a in top10:
                symbol = a["symbol"]
                karar = a.get("karar", "🟡 BEKLE")
                onceki_karar = son_ai_kararlar.get(symbol)
                son_ai_kararlar[symbol] = karar

                # Telegram yalnızca gerçek AL kararlarında konuşur.
                # BEKLE ve SAT/PAS arka planda/loglarda izlenmeye devam eder.
                if "🟢 AL" not in karar:
                    al_karar_izi(symbol, "telegram", "GELMEDİ", neden=f"karar={karar}")
                    continue

                # Aynı AL kararını tekrar gönderme.
                if onceki_karar == karar:
                    al_karar_izi(symbol, "telegram", "GELMEDİ", neden="aynı AL kararı tekrar")
                    continue

                al_karar_izi(symbol, "telegram", "GÖNDERİLECEK")
                gonderilecekler.append(a)

            if not gonderilecekler:
                print("Yeni AL kararı yok. Telegram sessiz.")
            else:
                mesaj = ""

                for a in gonderilecekler:
                    teknik = a.get("teknik")
                    if not teknik:
                        continue

                    mikro = a.get("mikro") or {}
                    neden_saglanan = a.get("neden_saglanan", [])
                    # Sayı tüm 10 ölçütü kapsar; metinde yalnızca en çok üç ana uygun neden gösterilir.
                    oncelik = [
                        "Trend çok güçlü", "Momentum hızlanıyor", "Hacim hızlanıyor",
                        "BTC farkı açılıyor", "Lider güçleniyor", "Basamaklı trend korunuyor",
                    ]
                    gorunen_nedenler = [n for n in oncelik if n in neden_saglanan][:3]
                    momentum_etiketi = (
                        "💪 ÇİFT MOMENTUM ✅"
                        if a.get("kod_oneri_d3_ok") and a.get("kod_oneri_d5_ok")
                        else "⚡ TEK MOMENTUM"
                    )
                    neden_satir = (
                        f"📌 Neden: {a.get('neden_sayi', 0)}/10 | "
                        f"Önemli neden: {a.get('neden_ana_sayi', 0)}/5 | {momentum_etiketi}"
                    )
                    gorunen_coin = a['symbol'][:-3] if a['symbol'].endswith("TRY") else a['symbol']
                    sinyal_sira, onceki_5 = _sinyal_sira_hazirla(a.get("symbol", ""))
                    sira_prefix = _sira_etiketi(sinyal_sira)
                    onceki_5_etiket = " | Önceki +%5 ✅" if onceki_5 else ""
                    d3 = float(mikro.get("d3", 0) or 0)
                    d5 = float(mikro.get("d5", 0) or 0)
                    mesaj += (
                        f"{sira_prefix} {gorunen_coin} | {a.get('radar_kategori', '')} + 🟢 AL{onceki_5_etiket}\n"
                        f"💰 Fiyat: {round(a['fiyat'], 4)}\n"
                        f"{neden_satir}\n"
                        + (" • ".join(gorunen_nedenler) + "\n" if gorunen_nedenler else "")
                        + f"Hacim: {a.get('hacim', 0)}x | 3dk: %{d3:+.2f} | 5dk: %{d5:+.2f}\n\n"
                    )
                print(mesaj)
                telegram_gonder(mesaj)
                for _g in gonderilecekler:
                    _g["_sinyal_event_id"] = _sinyal_sira_ekle(
                        _g.get("symbol", ""), _g.get("fiyat", 0)
                    )
                    al_karar_izi(_g.get("symbol", "?"), "telegram", "GÖNDERİLDİ")

                # Gönderilen AL sinyallerini yalnızca sonuç araştırması için kaydet; pozisyon açılmaz.
                piyasa_medyan3 = piyasa_medyan3_anlik
                btc_giris_fiyati = ticker_fiyat_haritasi.get("BTCTRY", 0)
                for _a in gonderilecekler:
                    al_ogrenme_baslat(_a, btc_d, piyasa_fiyatlari, piyasa_medyan3, btc_giris_fiyati)

        # Ana radar 60 saniyede bir çalışır. Henüz +%5 mesajı gitmemiş aktif AL varsa
        # aradaki fiyatı 15 saniyede bir kontrol ederek kısa süreli hedef temasını kaçırmaz.
        beklenen = 0
        while beklenen < TARAMA_SURESI:
            sure = min(KAR_TAKIP_SURESI, TARAMA_SURESI - beklenen)
            time.sleep(sure)
            beklenen += sure
            if beklenen >= TARAMA_SURESI:
                continue
            aktif_kar_takibi = any(
                not k.get("tamamlandi") and not k.get("kar_mesaji_gonderildi", True)
                for k in AL_OGRENME_KAYITLARI
            )
            if not aktif_kar_takibi:
                continue
            try:
                takip_response = requests.get(
                    "https://api.btcturk.com/api/v2/ticker", timeout=10
                )
                takip_response.raise_for_status()
                al_ogrenme_guncelle(takip_response.json().get("data", []))
            except Exception as e:
                print("+%5 hızlı takip hatası:", e)

    except Exception as e:
        print("Bot genel hata:", e)
        time.sleep(30)
