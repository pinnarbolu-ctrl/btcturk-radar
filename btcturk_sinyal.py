# ==========================================
# MAIN 30 | V56 - V51 TABAN + YUMUSAK 5+ PROFIL + %5 KARAR NOKTASI
# Amaç: +%5 yapanların ortak güç yapısını bilgi/puan olarak kullanmak; iyi adayları sert eşiklerle boğmamak.
# +%5'te tek karar mesajı: güç korunuyorsa KÂRI KORU / devam edebilir; güç kaybediyorsa %5 KÂR SAT.
# Bunun dışında normal SAT/KÂR AL Telegram mesajı yoktur. Zarar kes güvenlik mesajı korunur.
# Taban: main (21).py
# 21 sadeligi + 13 AL/SAT/Kar Koru + 1-3-5-10 dk erken yakalama
# Giris/Devam skorları sadece bilgi, AL için veto DEGIL
# Fast Scan V1: 60 sn hızlı ön tarama + 5 dk tam tarama
# AL Relax V1: normal AL için ADX 27 / AI 80
# Final Cleanup / Core Candidate Scanner
# Candidate thresholds synced with latest working Coin Radar
# ==========================================

import os
import time
import json
import requests
import feedparser
import statistics
import base64
import hmac
import hashlib
import uuid
from decimal import Decimal, ROUND_DOWN


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

CHAT_IDS = [2097448038]

TARAMA_SURESI = 60
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
# Her aday için RADAR'ın neden AL verdiğini, neden susturduğunu ve işlem katmanında
# neden pozisyon açılmadığını Railway loguna tek satır halinde yazar.
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

# Sade birleşik: açık AL takibi + dinamik kâr koruma
AL_TAKIP = {}
POZISYON_TAKIP_SURESI = 15
KAR_BILDIR_ESIK = 5.0
KAR_KORU_BASLANGIC = 7.0
# Dinamik çıkış motoru: sabit trailing yerine Devam + Yorgunluk + Zirve Dönüşü.
CIKIS_MIKRO_YENILEME = 60
CIKIS_KORU_SKORU = 55
CIKIS_SAT_SKORU = 75
# PAPER/LIVE gerçek pozisyon zarar kesme sınırı.
# Kâr kilidinden bağımsızdır; işlem girişinden %-1.5 düşüşte pozisyon kapatılır.
ZARAR_KES_YUZDE = -1.5

# DEVAM TEYIDI V1:
# Telegram AL sinyali aninda gorunur, fakat PAPER/LIVE emir 45 sn boyunca
# gucun korundugu dogrulanmadan acilmaz. Bu katman ek BTCTurk mum istegi yapmaz;
# 15 sn ticker fiyatlarini kullanir, dolayisiyla 429 yukunu artirmaz.
AL_ONAY_BEKLEME_SN = 45
AL_ONAY_MIN_DEVAM = 60.0
AL_ONAY_MAX_ANLIK_GERI = -0.60      # teyit penceresinde gorulen en kotu geri cekilme
AL_ONAY_MAX_KAPANIS_GERI = -0.35   # 45 sn sonunda sinyal fiyatina gore
AL_ONAY_MAX_SON_ADIM_GERI = -0.30  # son 15 sn adiminin kotulesme limiti
AL_ONAY_NEGATIF_MIKRO = -0.40      # ilk AL aninda 3dk+5dk birlikte bundan kotuyse veto

# AL Rejim / Seçicilik Öğrenmesi
# AL öğrenme verisini Railway Volume varsa kalıcı alanda tut.
# AL_OGRENME_DOSYA env ile özel yol verilmişse onu kullanır.
_RAILWAY_VOLUME = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
_AL_DEFAULT_DIR = _RAILWAY_VOLUME if _RAILWAY_VOLUME else "."
AL_OGRENME_DOSYA = os.getenv("AL_OGRENME_DOSYA", os.path.join(_AL_DEFAULT_DIR, "al_ogrenme_rejim.json"))
AL_OGRENME_SURESI = 3 * 60 * 60
REJIM_RAPOR_ARALIGI = 24 * 60 * 60
SON_REJIM_RAPOR_ZAMANI = time.time()

# 24 SAATLİK +%5 YAKALAMA BAŞARI RAPORU
# Bu sayaç deploy edildiği andan başlar; eski kayıtları yeni test sonucuna karıştırmaz.
YUZDE5_RAPOR_ARALIGI = 24 * 60 * 60
YUZDE5_RAPOR_ETIKETI = "BTCTÜRK SİNYAL 49"
_YUZDE5_META_DOSYA = os.path.join(_AL_DEFAULT_DIR, "yuzde5_basariraporu_sinyal49.json")


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


_YUZDE5_META = _yuzde5_meta_yukle()
if not _YUZDE5_META.get("baslangic"):
    _YUZDE5_META["baslangic"] = time.time()
    _YUZDE5_META["son_rapor"] = _YUZDE5_META["baslangic"]
    _yuzde5_meta_kaydet(_YUZDE5_META)


# =========================
# GERÇEK AL/SAT MODU
# Varsayılan PAPER. Railway'de TRADING_MODE=LIVE yapılmadan gerçek emir göndermez.
# API anahtarlarını KODA YAZMA; Railway Variables:
#   BTCTURK_API_KEY
#   BTCTURK_API_SECRET
# =========================
TRADING_MODE = os.getenv("TRADING_MODE", "PAPER").strip().upper()
LIVE_MODE = TRADING_MODE == "LIVE"
BTCTURK_API_KEY = os.getenv("BTCTURK_API_KEY", "").strip()
BTCTURK_API_SECRET = os.getenv("BTCTURK_API_SECRET", "").strip()

LIVE_TOPLAM_SERMAYE_TL = float(os.getenv("LIVE_TOPLAM_SERMAYE_TL", "4000") or 4000)
LIVE_ISLEM_TUTARI_TL = float(os.getenv("LIVE_ISLEM_TUTARI_TL", "1000") or 1000)
LIVE_MAX_AKTIF = int(os.getenv("LIVE_MAX_AKTIF", "4") or 4)
LIVE_MIN_TRY_TAMPON = float(os.getenv("LIVE_MIN_TRY_TAMPON", "5") or 5)

_LIVE_DEFAULT_DIR = _RAILWAY_VOLUME if _RAILWAY_VOLUME else "."
LIVE_DURUM_DOSYA = os.getenv(
    "LIVE_DURUM_DOSYA",
    os.path.join(_LIVE_DEFAULT_DIR, "live_pozisyonlari.json")
)
LIVE_POZISYONLAR = {}


def _btcturk_sayi(x, default=0.0):
    try:
        if isinstance(x, str):
            x = x.replace(",", ".")
        return float(x)
    except Exception:
        return default


def _btcturk_auth_headers():
    if not BTCTURK_API_KEY or not BTCTURK_API_SECRET:
        raise RuntimeError("BTCTURK_API_KEY / BTCTURK_API_SECRET eksik")
    stamp = str(int(time.time() * 1000))
    secret = base64.b64decode(BTCTURK_API_SECRET)
    payload = f"{BTCTURK_API_KEY}{stamp}".encode("utf-8")
    signature = base64.b64encode(
        hmac.new(secret, payload, hashlib.sha256).digest()
    ).decode("utf-8")
    return {
        "X-PCK": BTCTURK_API_KEY,
        "X-Stamp": stamp,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


def _btcturk_private_get(path, timeout=12):
    url = "https://api.btcturk.com" + path
    r = requests.get(url, headers=_btcturk_auth_headers(), timeout=timeout)
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "message": r.text[:300]}
    if r.status_code != 200 or not data.get("success", False):
        raise RuntimeError(
            f"BTCTurk GET hata {r.status_code}: "
            f"{data.get('message') or data.get('code') or 'bilinmeyen hata'}"
        )
    return data


def _btcturk_bakiyeler():
    return _btcturk_private_get("/api/v1/users/balances").get("data", []) or []


def _btcturk_bakiye(asset):
    asset = str(asset or "").upper()
    for b in _btcturk_bakiyeler():
        if str(b.get("asset", "")).upper() == asset:
            return {
                "free": _btcturk_sayi(b.get("free")),
                "balance": _btcturk_sayi(b.get("balance")),
                "locked": _btcturk_sayi(b.get("locked")),
                "precision": int(b.get("precision", 8) or 8),
            }
    return {"free": 0.0, "balance": 0.0, "locked": 0.0, "precision": 8}


def _btcturk_market_emir(symbol, taraf, quantity):
    symbol = str(symbol or "").upper()
    taraf = str(taraf or "").lower()
    if taraf not in ("buy", "sell"):
        raise ValueError("taraf buy/sell olmalı")
    q = float(quantity)
    if q <= 0:
        raise ValueError("quantity > 0 olmalı")

    payload = {
        "quantity": q,
        "price": 0,
        "stopPrice": 0,
        "newOrderClientId": str(uuid.uuid4()),
        "orderMethod": "market",
        "orderType": taraf,
        "pairSymbol": symbol,
    }
    r = requests.post(
        "https://api.btcturk.com/api/v1/order",
        headers=_btcturk_auth_headers(),
        json=payload,
        timeout=15,
    )
    try:
        data = r.json()
    except Exception:
        data = {"success": False, "message": r.text[:300]}
    if r.status_code != 200 or not data.get("success", False):
        raise RuntimeError(
            f"BTCTurk emir reddedildi {r.status_code}: "
            f"{data.get('message') or data.get('code') or 'bilinmeyen hata'}"
        )
    return data.get("data") or {}


def _live_yukle():
    global LIVE_POZISYONLAR
    try:
        if os.path.exists(LIVE_DURUM_DOSYA):
            with open(LIVE_DURUM_DOSYA, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    LIVE_POZISYONLAR = d
    except Exception as e:
        print("[LIVE] durum yükleme hatası:", e)


def _live_kaydet():
    try:
        klasor = os.path.dirname(LIVE_DURUM_DOSYA)
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        tmp = LIVE_DURUM_DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(LIVE_POZISYONLAR, f, ensure_ascii=False, indent=2)
        os.replace(tmp, LIVE_DURUM_DOSYA)
    except Exception as e:
        print("[LIVE] durum kaydetme hatası:", e)


def _live_aktifler():
    return [p for p in LIVE_POZISYONLAR.values() if p.get("aktif")]


def _coin_asset(symbol):
    symbol = str(symbol or "").upper()
    if symbol.endswith("TRY"):
        return symbol[:-3]
    return symbol


def _poll_balance_delta(asset, before, timeout=12):
    son = before
    bas = time.time()
    while time.time() - bas < timeout:
        try:
            son = _btcturk_bakiye(asset)["free"]
            if abs(son - before) > 1e-12:
                return son - before, son
        except Exception:
            pass
        time.sleep(1)
    return son - before, son


def _floor_precision(value, precision):
    q = Decimal("1").scaleb(-int(max(0, precision)))
    return float(Decimal(str(max(0.0, value))).quantize(q, rounding=ROUND_DOWN))


def live_al_ac(symbol, sinyal_fiyat):
    """Gerçek AL sinyalini 1000 TL market alış emrine çevirir."""
    if not LIVE_MODE:
        return None
    if not BTCTURK_API_KEY or not BTCTURK_API_SECRET:
        print("[LIVE AL] API anahtarı eksik; emir gönderilmedi.")
        telegram_gonder("⛔ LIVE AL durdu: BTCTURK_API_KEY / BTCTURK_API_SECRET eksik.")
        return None

    eski = LIVE_POZISYONLAR.get(symbol)
    if eski and eski.get("aktif"):
        print(f"[LIVE AL] {symbol} zaten açık; ikinci kez alınmadı.")
        return eski

    aktifler = _live_aktifler()
    kullanilan = sum(float(p.get("tl", 0) or 0) for p in aktifler)
    kalan_limit = LIVE_TOPLAM_SERMAYE_TL - kullanilan

    if len(aktifler) >= LIVE_MAX_AKTIF or kalan_limit + 1e-9 < LIVE_ISLEM_TUTARI_TL:
        print(
            f"[LIVE AL] Bütçe/pozisyon limiti dolu | "
            f"aktif={len(aktifler)}/{LIVE_MAX_AKTIF} | "
            f"kullanılan={kullanilan:.2f}/{LIVE_TOPLAM_SERMAYE_TL:.2f} TL"
        )
        return None

    try:
        try_bakiye = _btcturk_bakiye("TRY")["free"]
        if try_bakiye < LIVE_ISLEM_TUTARI_TL + LIVE_MIN_TRY_TAMPON:
            raise RuntimeError(
                f"Yetersiz serbest TRY: {try_bakiye:.2f} TL "
                f"(gerekli en az {LIVE_ISLEM_TUTARI_TL + LIVE_MIN_TRY_TAMPON:.2f})"
            )

        asset = _coin_asset(symbol)
        coin_before = _btcturk_bakiye(asset)["free"]

        emir = _btcturk_market_emir(symbol, "buy", round(LIVE_ISLEM_TUTARI_TL, 2))
        order_id = emir.get("id")
        delta, coin_after = _poll_balance_delta(asset, coin_before)
        alinmis = max(0.0, delta)

        # Bakiye gecikirse tahmini miktar kullanma: canlı SAT için gerçek miktar şart.
        if alinmis <= 0:
            raise RuntimeError(
                f"AL emri gönderildi (order={order_id}) fakat alınan {asset} miktarı "
                "bakiyeden doğrulanamadı. Otomatik SAT güvenlik nedeniyle açılmadı."
            )

        efektif_giris = LIVE_ISLEM_TUTARI_TL / alinmis if alinmis > 0 else float(sinyal_fiyat)
        poz = {
            "aktif": True,
            "symbol": symbol,
            "asset": asset,
            "giris_fiyat": efektif_giris,
            "sinyal_fiyat": float(sinyal_fiyat),
            "tl": LIVE_ISLEM_TUTARI_TL,
            "coin_miktar": alinmis,
            "order_id_al": order_id,
            "acilis_zamani": time.time(),
        }
        LIVE_POZISYONLAR[symbol] = poz
        _live_kaydet()

        yeni_kullanilan = kullanilan + LIVE_ISLEM_TUTARI_TL
        print(
            f"[LIVE AL] {symbol} | {LIVE_ISLEM_TUTARI_TL:.0f} TL | "
            f"miktar={alinmis:.12f} | efektif giriş≈{efektif_giris:.6f}"
        )
        telegram_gonder(
            f"🟢 GERÇEK AL - {symbol}\n"
            f"Tutar: {LIVE_ISLEM_TUTARI_TL:.0f} TL | Miktar: {alinmis:.8f}\n"
            f"Yaklaşık giriş: {efektif_giris:.6f}\n"
            f"Aktif sermaye: {yeni_kullanilan:.0f}/{LIVE_TOPLAM_SERMAYE_TL:.0f} TL\n"
            f"Order ID: {order_id}"
        )
        return poz

    except Exception as e:
        print(f"[LIVE AL HATA] {symbol}: {e}")
        telegram_gonder(f"⛔ GERÇEK AL HATASI - {symbol}\n{e}")
        return None


def live_sat_kapat(symbol, sinyal_fiyat, sebep="dinamik çıkış", bildirim=True):
    """Dinamik çıkış tetiklenince yalnız botun aldığı kayıtlı miktarı market satar."""
    if not LIVE_MODE:
        return False

    poz = LIVE_POZISYONLAR.get(symbol)
    if not poz or not poz.get("aktif"):
        print(f"[LIVE SAT] {symbol} için bot kayıtlı açık pozisyon bulamadı; SAT gönderilmedi.")
        return False

    try:
        asset = poz.get("asset") or _coin_asset(symbol)
        bakiye = _btcturk_bakiye(asset)
        kayitli = float(poz.get("coin_miktar", 0) or 0)
        satilabilir = min(kayitli, float(bakiye.get("free", 0) or 0))
        satilabilir = _floor_precision(satilabilir, int(bakiye.get("precision", 8) or 8))
        if satilabilir <= 0:
            raise RuntimeError(f"Satılabilir {asset} bakiyesi yok")

        try_before = _btcturk_bakiye("TRY")["free"]
        emir = _btcturk_market_emir(symbol, "sell", satilabilir)
        order_id = emir.get("id")
        try_delta, try_after = _poll_balance_delta("TRY", try_before)
        gelir = max(0.0, try_delta)

        giris_tl = float(poz.get("tl", LIVE_ISLEM_TUTARI_TL) or LIVE_ISLEM_TUTARI_TL)
        kar_tl = gelir - giris_tl if gelir > 0 else None
        getiri = (kar_tl / giris_tl * 100.0) if kar_tl is not None and giris_tl else None

        poz.update({
            "aktif": False,
            "kapanis_fiyat_sinyal": float(sinyal_fiyat),
            "kapanis_zamani": time.time(),
            "order_id_sat": order_id,
            "satilan_miktar": satilabilir,
            "gelir_tl": gelir,
            "kar_tl": kar_tl,
            "getiri_yuzde": getiri,
            "kapanis_sebebi": sebep,
        })
        _live_kaydet()

        sonuc = (
            f"%{getiri:+.2f} | {kar_tl:+.2f} TL"
            if getiri is not None else
            "TRY bakiye değişimi henüz doğrulanamadı"
        )
        print(f"[LIVE SAT] {symbol} | miktar={satilabilir:.12f} | {sonuc} | {sebep}")
        if bildirim:
            telegram_gonder(
                f"🔴 GERÇEK SAT - {symbol}\n"
                f"Miktar: {satilabilir:.8f} | Sinyal fiyatı: {float(sinyal_fiyat):.6f}\n"
                f"Sonuç: {sonuc}\n"
                f"Sebep: {sebep}\n"
                f"Order ID: {order_id}"
            )
        return True

    except Exception as e:
        print(f"[LIVE SAT HATA] {symbol}: {e}")
        telegram_gonder(f"⛔ GERÇEK SAT HATASI - {symbol}\n{e}")
        return False


def islem_al_ac(symbol, fiyat):
    if LIVE_MODE:
        return live_al_ac(symbol, fiyat)
    return paper_al_ac(symbol, fiyat)


def islem_sat_kapat(symbol, fiyat, sebep="dinamik çıkış", bildirim=True):
    if LIVE_MODE:
        return live_sat_kapat(symbol, fiyat, sebep, bildirim=bildirim)
    return paper_sat_kapat(symbol, fiyat, sebep, bildirim=bildirim)


def trading_startup_kontrol():
    """Başlangıçta mod ve private API erişimini güvenli biçimde doğrular."""
    if not LIVE_MODE:
        print("[TRADING] PAPER modu aktif. Gerçek emir gönderilmeyecek.")
        telegram_gonder(
            f"🧪 AL/SAT PAPER modu aktif | "
            f"{PAPER_ISLEM_TUTARI_TL:.0f} TL/işlem | max {PAPER_MAX_AKTIF}"
        )
        return True

    try:
        if not BTCTURK_API_KEY or not BTCTURK_API_SECRET:
            raise RuntimeError("BTCTURK_API_KEY / BTCTURK_API_SECRET eksik")
        try_free = _btcturk_bakiye("TRY")["free"]
        print(f"[TRADING] LIVE API OK | serbest TRY={try_free:.2f}")
        telegram_gonder(
            f"🔴 LIVE AL/SAT AKTİF\n"
            f"BtcTurk API bağlantısı OK | Serbest TRY: {try_free:.2f}\n"
            f"{LIVE_ISLEM_TUTARI_TL:.0f} TL/işlem | "
            f"toplam bot limiti {LIVE_TOPLAM_SERMAYE_TL:.0f} TL | max {LIVE_MAX_AKTIF}"
        )
        return True
    except Exception as e:
        print(f"[TRADING] LIVE BAŞLANGIÇ HATASI: {e}")
        telegram_gonder(f"⛔ LIVE AL/SAT başlatılamadı\n{e}")
        return False


_live_yukle()

# =========================
# PAPER İŞLEM / SERMAYE YÖNETİMİ
# Bu katman GERÇEK EMİR GÖNDERMEZ.
# Toplam sanal sermaye 4000 TL, işlem başı 1000 TL, en fazla 4 açık pozisyon.
# =========================
PAPER_TOPLAM_SERMAYE_TL = float(os.getenv("PAPER_TOPLAM_SERMAYE_TL", "4000") or 4000)
PAPER_ISLEM_TUTARI_TL = float(os.getenv("PAPER_ISLEM_TUTARI_TL", "1000") or 1000)
PAPER_MAX_AKTIF = int(os.getenv("PAPER_MAX_AKTIF", "4") or 4)
_PAPER_DEFAULT_DIR = _RAILWAY_VOLUME if _RAILWAY_VOLUME else "."
PAPER_DURUM_DOSYA = os.getenv("PAPER_DURUM_DOSYA", os.path.join(_PAPER_DEFAULT_DIR, "paper_pozisyonlari.json"))
PAPER_POZISYONLAR = {}


def _paper_yukle():
    global PAPER_POZISYONLAR
    try:
        if os.path.exists(PAPER_DURUM_DOSYA):
            with open(PAPER_DURUM_DOSYA, "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, dict):
                    PAPER_POZISYONLAR = d
    except Exception as e:
        print("[PAPER] durum yükleme hatası:", e)


def _paper_kaydet():
    try:
        klasor = os.path.dirname(PAPER_DURUM_DOSYA)
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        tmp = PAPER_DURUM_DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(PAPER_POZISYONLAR, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PAPER_DURUM_DOSYA)
    except Exception as e:
        print("[PAPER] durum kaydetme hatası:", e)


def _paper_aktifler():
    return [p for p in PAPER_POZISYONLAR.values() if p.get("aktif")]


def paper_al_ac(symbol, fiyat):
    """Main 30 gerçek AL mesajını 1000 TL'lik sanal işleme çevirir."""
    if not symbol or fiyat <= 0:
        return None
    eski = PAPER_POZISYONLAR.get(symbol)
    if eski and eski.get("aktif"):
        al_karar_izi(symbol, "işlem", "ALINMADI", neden="aynı coin zaten portföyde")
        return eski

    aktifler = _paper_aktifler()
    kullanilan = sum(float(p.get("tl", 0) or 0) for p in aktifler)
    kalan = max(0.0, PAPER_TOPLAM_SERMAYE_TL - kullanilan)
    if len(aktifler) >= PAPER_MAX_AKTIF or kalan + 1e-9 < PAPER_ISLEM_TUTARI_TL:
        print(f"[PAPER] Bütçe dolu | aktif={len(aktifler)}/{PAPER_MAX_AKTIF} | kullanılan={kullanilan:.2f}/{PAPER_TOPLAM_SERMAYE_TL:.2f} TL | {symbol} alınmadı")
        al_karar_izi(symbol, "işlem", "ALINMADI", neden="bütçe/max pozisyon dolu", aktif=f"{len(aktifler)}/{PAPER_MAX_AKTIF}", kullanilan_tl=round(kullanilan,2))
        return None

    miktar = PAPER_ISLEM_TUTARI_TL / fiyat
    poz = {
        "aktif": True,
        "symbol": symbol,
        "giris_fiyat": float(fiyat),
        "tl": PAPER_ISLEM_TUTARI_TL,
        "coin_miktar": miktar,
        "acilis_zamani": time.time(),
    }
    PAPER_POZISYONLAR[symbol] = poz
    _paper_kaydet()
    yeni_kullanilan = kullanilan + PAPER_ISLEM_TUTARI_TL
    print(f"[PAPER AL] {symbol} | {PAPER_ISLEM_TUTARI_TL:.0f} TL | giriş={fiyat:.6f} | bütçe={yeni_kullanilan:.0f}/{PAPER_TOPLAM_SERMAYE_TL:.0f} TL")
    al_karar_izi(symbol, "işlem", "ALINDI", giris=float(fiyat), kullanilan_tl=round(yeni_kullanilan,2))
    try:
        telegram_gonder(
            f"🧪 PAPER AL - {symbol}\n"
            f"Tutar: {PAPER_ISLEM_TUTARI_TL:.0f} TL | Giriş: {fiyat:.6f}\n"
            f"Aktif sermaye: {yeni_kullanilan:.0f}/{PAPER_TOPLAM_SERMAYE_TL:.0f} TL"
        )
    except Exception:
        pass
    return poz


def paper_sat_kapat(symbol, fiyat, sebep="dinamik çıkış", bildirim=True):
    """Dinamik SAT/KÂR AL tetiklenince sanal pozisyonu kapatır."""
    poz = PAPER_POZISYONLAR.get(symbol)
    if not poz or not poz.get("aktif"):
        return False
    giris = float(poz.get("giris_fiyat", fiyat) or fiyat)
    getiri = ((float(fiyat) / giris) - 1.0) * 100 if giris else 0.0
    kar_tl = float(poz.get("tl", 0) or 0) * getiri / 100.0
    poz.update({
        "aktif": False,
        "kapanis_fiyat": float(fiyat),
        "kapanis_zamani": time.time(),
        "getiri_yuzde": getiri,
        "kar_tl": kar_tl,
        "kapanis_sebebi": sebep,
    })
    _paper_kaydet()
    kullanilan = sum(float(p.get("tl", 0) or 0) for p in _paper_aktifler())
    print(f"[PAPER SAT] {symbol} | çıkış={fiyat:.6f} | getiri=%{getiri:+.2f} | P/L={kar_tl:+.2f} TL | {sebep}")
    if bildirim:
        try:
            telegram_gonder(
                f"🧪 PAPER SAT - {symbol}\n"
                f"Giriş: {giris:.6f} | Çıkış: {fiyat:.6f}\n"
                f"Sonuç: %{getiri:+.2f} | {kar_tl:+.2f} TL\n"
                f"Sebep: {sebep}\n"
                f"Açık sermaye: {kullanilan:.0f}/{PAPER_TOPLAM_SERMAYE_TL:.0f} TL"
            )
        except Exception:
            pass
    return True


_paper_yukle()





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

def al_takip_baslat(aday):
    """
    Gercek AL mesaji gonderilen coini takibe alir.

    V51 DEVAM TEYIDI:
    Telegram AL mesaji aninda gorunur; PAPER/LIVE pozisyon hemen acilmaz.
    Once 45 saniye ticker fiyatiyla gucun geriye kacip kacmadigi dogrulanir.
    """
    symbol = aday.get("symbol")
    fiyat = float(aday.get("fiyat", 0) or 0)
    if not symbol or fiyat <= 0:
        return

    mevcut = AL_TAKIP.get(symbol)
    if mevcut and mevcut.get("aktif"):
        al_karar_izi(symbol, "takip", "ALINMADI", neden="aktif takip zaten var")
        return

    teknik = aday.get("teknik") or {}
    mikro = aday.get("mikro") or {}
    devam0 = float(aday.get("devam_gucu", 0) or 0)
    bp_skor, bp_etiket, bp_neden = bes_plus_profil_yumusak(aday)
    aday["bes_plus_profil"] = bp_skor
    aday["bes_plus_etiket"] = bp_etiket
    aday["bes_plus_neden"] = bp_neden
    AL_TAKIP[symbol] = {
        "aktif": True,
        "giris": fiyat,
        "tepe": fiyat,
        "max_getiri": 0.0,
        "kar_bildirildi": False,
        "kar_koru_bildirildi": False,
        "sat_bildirildi": False,
        "son_mikro_zamani": 0.0,
        "son_mikro": mikro,
        "devam_gucu": devam0,
        "kalicilik": float(aday.get("kalicilik_skoru", 0) or 0),
        "ai_skoru": float(aday.get("ai_skoru", 0) or 0),
        "adx": teknik.get("adx"),
        "rsi": teknik.get("rsi"),
        "macd_hist": teknik.get("macd_hist"),
        "max_devam": devam0,
        "risk": str(aday.get("risk", "Bilinmiyor") or "Bilinmiyor"),
        "bes_plus_profil": bp_skor,
        "bes_plus_etiket": bp_etiket,
        "bes_plus_neden": bp_neden,
        "portfoyde": False,
        # Devam teyidi hafizasi
        "onay_bekliyor": True,
        "onay_baslangic": time.time(),
        "onay_sinyal_fiyat": fiyat,
        "onay_fiyatlari": [fiyat],
        "onay_min_fiyat": fiyat,
        "onay_devam_ilk": devam0,
        "onay_mikro_ilk": dict(mikro),
        "onay_sonucu": "BEKLIYOR",
    }

    # Risk Yuksek aday sinyal olarak gosterilebilir/follow edilebilir,
    # fakat PAPER veya LIVE portfoye gercek pozisyon olarak ALINMAZ.
    risk_etiketi = str(aday.get("risk", "Bilinmiyor") or "Bilinmiyor")
    if "Yüksek" in risk_etiketi:
        AL_TAKIP[symbol]["onay_bekliyor"] = False
        AL_TAKIP[symbol]["onay_sonucu"] = "RISK_VETO"
        print(f"[İŞLEM VETO] {symbol} | Risk Yüksek -> PAPER/LIVE AL açılmadı.")
        al_karar_izi(symbol, "risk", "VETO", neden="Risk Yüksek", profil=bp_skor, devam=devam0)
        return

    print(
        f"[DEVAM TEYİDİ] {symbol} | AL sinyali görüldü, emir {AL_ONAY_BEKLEME_SN} sn beklemede | "
        f"fiyat={fiyat:.8f} | Devam={devam0:.1f}"
    )
    al_karar_izi(symbol, "teyit", "BEKLİYOR", sinyal_fiyat=fiyat, devam=devam0, profil=bp_skor, risk=risk_etiketi)


def _devam_teyidi_degerlendir(symbol, p, fiyat):
    """45 sn ticker tabanli teyit. (ok, neden, metrikler) dondurur."""
    sinyal = float(p.get("onay_sinyal_fiyat", p.get("giris", fiyat)) or fiyat)
    fiyatlar = list(p.get("onay_fiyatlari") or [])
    if not fiyatlar or fiyatlar[-1] != fiyat:
        fiyatlar.append(float(fiyat))
    # 15 sn takipte 45 sn icin en fazla son 5 nokta yeterli.
    fiyatlar = fiyatlar[-5:]
    p["onay_fiyatlari"] = fiyatlar
    p["onay_min_fiyat"] = min(float(p.get("onay_min_fiyat", sinyal) or sinyal), float(fiyat))

    anlik = _pct(float(fiyat), sinyal) if sinyal > 0 else 0.0
    min_geri = _pct(float(p["onay_min_fiyat"]), sinyal) if sinyal > 0 else 0.0
    son_adim = _pct(fiyatlar[-1], fiyatlar[-2]) if len(fiyatlar) >= 2 and fiyatlar[-2] > 0 else 0.0
    yukselen_adim = sum(1 for i in range(1, len(fiyatlar)) if fiyatlar[i] >= fiyatlar[i-1])

    devam0 = float(p.get("onay_devam_ilk", p.get("devam_gucu", 0)) or 0)
    m0 = p.get("onay_mikro_ilk") or {}
    d3 = float(m0.get("d3", 0) or 0)
    d5 = float(m0.get("d5", 0) or 0)

    nedenler = []
    if devam0 < AL_ONAY_MIN_DEVAM:
        nedenler.append(f"Devam düşük ({devam0:.1f} < {AL_ONAY_MIN_DEVAM:.0f})")
    if min_geri <= AL_ONAY_MAX_ANLIK_GERI:
        nedenler.append(f"45sn içinde fazla geri çekildi (%{min_geri:+.2f})")
    if anlik <= AL_ONAY_MAX_KAPANIS_GERI:
        nedenler.append(f"teyit sonunda sinyal altı (%{anlik:+.2f})")
    if son_adim <= AL_ONAY_MAX_SON_ADIM_GERI:
        nedenler.append(f"son 15sn momentum negatif (%{son_adim:+.2f})")
    if d3 <= AL_ONAY_NEGATIF_MIKRO and d5 <= AL_ONAY_NEGATIF_MIKRO:
        nedenler.append(f"ilk mikro 3dk/5dk birlikte negatif ({d3:+.2f}/{d5:+.2f})")

    # Fiyat sadece yatay kaldiysa veto etme; ama tamamen dusen seri de guc teyidi sayilmaz.
    if len(fiyatlar) >= 4 and yukselen_adim == 0 and anlik < 0:
        nedenler.append("45sn boyunca yükselen adım yok")

    metrik = {
        "anlik": round(anlik, 3),
        "min_geri": round(min_geri, 3),
        "son_adim": round(son_adim, 3),
        "yukselen_adim": yukselen_adim,
        "devam0": round(devam0, 1),
        "d3": round(d3, 3),
        "d5": round(d5, 3),
    }
    return (len(nedenler) == 0), nedenler, metrik

def al_takip_teknik_guncelle(aday):
    """Aktif AL yeniden teknik taramaya girerse çıkış motoruna canlı teknik durumu taşır."""
    symbol = aday.get("symbol")
    p = AL_TAKIP.get(symbol)
    if not p or not p.get("aktif"):
        return
    teknik = aday.get("teknik") or {}
    p["devam_gucu"] = float(aday.get("devam_gucu", p.get("devam_gucu", 0)) or 0)
    p["kalicilik"] = float(aday.get("kalicilik_skoru", p.get("kalicilik", 0)) or 0)
    p["ai_skoru"] = float(aday.get("ai_skoru", p.get("ai_skoru", 0)) or 0)
    p["adx"] = teknik.get("adx", p.get("adx"))
    p["rsi"] = teknik.get("rsi", p.get("rsi"))
    p["macd_hist"] = teknik.get("macd_hist", p.get("macd_hist"))
    p["son_mikro"] = aday.get("mikro") or p.get("son_mikro") or {}
    bp_skor, bp_etiket, bp_neden = bes_plus_profil_yumusak(aday)
    p["bes_plus_profil"] = bp_skor
    p["bes_plus_etiket"] = bp_etiket
    p["bes_plus_neden"] = bp_neden
    p["max_devam"] = max(float(p.get("max_devam", 0) or 0), p["devam_gucu"] )


def _dinamik_cikis_skorlari(p, max_getiri, tepe_geri):
    """0-100 Devam, Yorgunluk ve Zirve Dönüşü skorlarını üretir."""
    m = p.get("son_mikro") or {}
    d1 = float(m.get("d1", 0) or 0)
    d3 = float(m.get("d3", 0) or 0)
    d5 = float(m.get("d5", 0) or 0)
    d10 = float(m.get("d10", 0) or 0)
    h1 = float(m.get("hacim1x", 0) or 0)
    hi = float(m.get("hacim_ivme", 0) or 0)
    devam_eski = float(p.get("devam_gucu", 0) or 0)
    kal = float(p.get("kalicilik", 0) or 0)
    adx = p.get("adx")
    rsi = p.get("rsi")
    macd = p.get("macd_hist")

    devam = 35.0
    devam += min(20.0, max(0.0, devam_eski - 55.0) * 0.45)
    devam += min(12.0, max(0.0, kal - 55.0) * 0.30)
    if d1 > 0: devam += 7
    if d3 > 0: devam += 8
    if d5 > 0: devam += 6
    if d10 > 0: devam += 4
    if m.get("fiyat_ivme"): devam += 6
    if m.get("basamak"): devam += 6
    if h1 >= 1.10: devam += 4
    if hi >= 1.10: devam += 5
    if adx is not None and adx >= 28: devam += 5
    if macd is not None and macd > 0: devam += 5
    if d1 < -0.35: devam -= 8
    if d3 < -0.50: devam -= 10
    devam = max(0.0, min(100.0, devam))

    yorgun = 10.0
    if d1 < 0: yorgun += 12
    if d3 < 0: yorgun += 14
    if d1 < -0.45 and d3 < 0: yorgun += 15
    if d3 > 0 and d1 < (d3 / 3.0) * 0.35: yorgun += 8
    if d5 > 0 and d3 < (d5 / 5.0) * 1.2: yorgun += 7
    if h1 < 0.80: yorgun += 7
    if hi < 0.85: yorgun += 8
    if rsi is not None and rsi >= 80: yorgun += 8
    if macd is not None and macd < 0: yorgun += 12
    if kal and kal < 55: yorgun += 10
    max_devam = float(p.get("max_devam", devam_eski) or devam_eski)
    if max_devam - devam_eski >= 15: yorgun += 10
    yorgun = max(0.0, min(100.0, yorgun))

    donus = 0.0
    # Tepe geri çekilmesi tek başına SAT değildir; mikro bozulmayla birlikte ağırlık kazanır.
    if tepe_geri >= 1.0: donus += 12
    if tepe_geri >= 2.0: donus += 15
    if tepe_geri >= 3.0: donus += 18
    if tepe_geri >= 5.0: donus += 20
    if d1 < 0: donus += 8
    if d3 < 0: donus += 12
    if d1 < -0.60 and d3 < -0.30: donus += 15
    # Büyük kârda aynı geri çekilme daha anlamlıdır.
    if max_getiri >= 10 and tepe_geri >= 2.0: donus += 5
    if max_getiri >= 20 and tepe_geri >= 2.5: donus += 8
    donus = max(0.0, min(100.0, donus))

    # Devam güçlüyse çıkış riskini aşağı çeker; yorgunluk + dönüş riski yukarı taşır.
    cikis = (yorgun * 0.42) + (donus * 0.48) + ((100.0 - devam) * 0.10)
    cikis = max(0.0, min(100.0, cikis))
    return round(devam, 1), round(yorgun, 1), round(donus, 1), round(cikis, 1)


def al_takip_guncelle(ticker):
    """
    Otomatik emir vermez. Açık AL'larda tepeyi ve canlı mikro yapıyı izler.
    Çıkışı sabit yüzdeyle değil Devam Gücü + Yorgunluk + Zirve Dönüşü ile değerlendirir.
    """
    if not AL_TAKIP:
        return

    fiyatlar = {}
    for coin in ticker:
        try:
            sym = coin.get("pair", "")
            f = float(coin.get("last", 0) or 0)
            if sym and f > 0:
                fiyatlar[sym] = f
        except Exception:
            pass

    simdi = time.time()
    for symbol, p in AL_TAKIP.items():
        if not p.get("aktif"):
            continue

        fiyat = fiyatlar.get(symbol)
        if not fiyat:
            continue

        # DEVAM TEYIDI: Telegram AL geldi ama PAPER/LIVE henuz acilmadiysa
        # 15 sn ticker noktalarini biriktir; 45 sn sonunda guc korunduysa emir ac.
        if p.get("onay_bekliyor") and not p.get("portfoyde"):
            _of = p.setdefault("onay_fiyatlari", [])
            if not _of or abs(float(_of[-1]) - float(fiyat)) > 1e-12:
                _of.append(float(fiyat))
                if len(_of) > 5:
                    del _of[:-5]
            p["onay_min_fiyat"] = min(float(p.get("onay_min_fiyat", fiyat) or fiyat), float(fiyat))

            gecen = simdi - float(p.get("onay_baslangic", simdi) or simdi)
            if gecen < AL_ONAY_BEKLEME_SN:
                continue

            onay_ok, onay_nedenler, onay_m = _devam_teyidi_degerlendir(symbol, p, fiyat)
            p["onay_bekliyor"] = False
            if not onay_ok:
                p["onay_sonucu"] = "VETO"
                p["aktif"] = False
                print(
                    f"[DEVAM VETO] {symbol} | " + "; ".join(onay_nedenler) +
                    f" | sinyal->45sn %{onay_m['anlik']:+.2f} | min %{onay_m['min_geri']:+.2f} | "
                    f"son15 %{onay_m['son_adim']:+.2f}"
                )
                al_karar_izi(symbol, "teyit", "VETO", neden="; ".join(onay_nedenler), anlik=onay_m['anlik'], min_geri=onay_m['min_geri'], son15=onay_m['son_adim'])
                continue

            paper_poz = islem_al_ac(symbol, float(fiyat))
            if paper_poz:
                p["portfoyde"] = True
                p["onay_sonucu"] = "ONAY"
                p["islem_giris"] = float(paper_poz.get("giris_fiyat", fiyat) or fiyat)
                p["islem_tl"] = float(paper_poz.get("tl", LIVE_ISLEM_TUTARI_TL if LIVE_MODE else PAPER_ISLEM_TUTARI_TL) or (LIVE_ISLEM_TUTARI_TL if LIVE_MODE else PAPER_ISLEM_TUTARI_TL))
                # Cikis motoru gercek islem girisini baz alsin; sinyal fiyati Telegram referansi olarak p['giris']te kalir.
                print(
                    f"[DEVAM ONAY] {symbol} | %{onay_m['anlik']:+.2f} / 45sn | "
                    f"min %{onay_m['min_geri']:+.2f} | son15 %{onay_m['son_adim']:+.2f} -> PAPER/LIVE AL açıldı"
                )
                al_karar_izi(symbol, "teyit", "ONAY", anlik=onay_m['anlik'], min_geri=onay_m['min_geri'], son15=onay_m['son_adim'], islem_giris=p.get('islem_giris'))
            else:
                p["onay_sonucu"] = "EMIR_ACILMADI"
                # Butce dolu vb. durumda yalniz sinyal takibi sursun, portfoy stopu calismasin.
                print(f"[DEVAM ONAY] {symbol} teyit geçti fakat işlem katmanı pozisyon açmadı.")
                al_karar_izi(symbol, "teyit", "ALINMADI", neden="teyit geçti ama işlem katmanı açmadı", anlik=onay_m['anlik'])

        # Sadece açık AL coinlerinde dakikalık yapıyı yaklaşık dakikada bir yenile.
        if simdi - float(p.get("son_mikro_zamani", 0) or 0) >= CIKIS_MIKRO_YENILEME:
            yeni_mikro = mikro_ivme_hesapla(symbol)
            if yeni_mikro:
                p["son_mikro"] = yeni_mikro
            p["son_mikro_zamani"] = simdi

        giris = float(p.get("giris", fiyat))
        tepe = float(p.get("tepe", giris))
        if fiyat > tepe:
            tepe = fiyat
            p["tepe"] = fiyat

        getiri = _pct(fiyat, giris)
        max_getiri = max(float(p.get("max_getiri", 0.0)), _pct(tepe, giris))
        p["max_getiri"] = max_getiri
        tepe_geri = max(0.0, -_pct(fiyat, tepe)) if tepe > 0 else 0.0

        devam, yorgun, donus, cikis = _dinamik_cikis_skorlari(p, max_getiri, tepe_geri)
        p["cikis_devam"] = devam
        p["cikis_yorgunluk"] = yorgun
        p["cikis_donus"] = donus
        p["cikis_skoru"] = cikis

        # ZARAR KES:
        # Yalnız PAPER/LIVE portföyüne gerçekten alınmış pozisyonlarda çalışır.
        # Sinyal fiyatını değil, işlem katmanında kaydedilen gerçek/PAPER girişini baz alır.
        islem_giris = float(p.get("islem_giris", giris) or giris)
        islem_getiri = _pct(fiyat, islem_giris) if islem_giris > 0 else getiri
        zarar_kes = p.get("portfoyde") and islem_getiri <= ZARAR_KES_YUZDE

        if zarar_kes and not p.get("sat_bildirildi"):
            sat_sebebi = (
                f"zarar kes: işlem getirisi %{islem_getiri:+.2f} "
                f"<= %{ZARAR_KES_YUZDE:.2f}"
            )
            kapandi = islem_sat_kapat(symbol, fiyat, sebep=sat_sebebi, bildirim=False)

            # PAPER'da veya LIVE emri başarıyla gönderildiyse takibi kapat.
            # LIVE SAT başarısız olursa sonraki turda yeniden denenebilmesi için açık bırak.
            if kapandi:
                p["sat_bildirildi"] = True
                p["aktif"] = False
                mesaj = (
                    f"🛑 ZARAR KES - {symbol}\n"
                    f"İşlem girişi: {islem_giris:.4f} | Güncel: {fiyat:.4f}\n"
                    f"Sonuç: %{islem_getiri:+.2f} | Stop: %{ZARAR_KES_YUZDE:.2f}\n"
                    f"Neden: -%1.5 zarar kes sınırı aşıldı.\n"
                    f"Not: {'GERÇEK pozisyon otomatik kapatma emri gönderildi.' if LIVE_MODE else 'PAPER pozisyon otomatik kapatıldı.'}"
                )
                print(mesaj)
                telegram_gonder(mesaj)
                continue
            else:
                print(f"[STOP RETRY] {symbol} | SAT başarısız; pozisyon takibi açık tutuluyor.")

        # +%5 KARAR NOKTASI:
        # Gerçek/PAPER pozisyon +%5'e ulaştığında yalnız BİR kez karar verilir.
        # Güç korunuyorsa SAT yok, kâr korunarak devam izlenir. Güç kaybediyorsa +%5 KÂR SAT yapılır.
        guclu_devam = devam >= 72 and yorgun < 45 and donus < 55 and cikis < CIKIS_KORU_SKORU
        islem_max_getiri = _pct(tepe, islem_giris) if islem_giris > 0 else max_getiri
        karar_getiri = islem_getiri if p.get("portfoyde") else getiri

        if p.get("portfoyde") and karar_getiri >= KAR_BILDIR_ESIK and not p.get("kar_bildirildi"):
            p["kar_bildirildi"] = True
            profil = float(p.get("bes_plus_profil", 0) or 0)
            profil_etiket = str(p.get("bes_plus_etiket", "") or "")
            profil_neden = list(p.get("bes_plus_neden", []) or [])
            ortak = " • ".join(profil_neden[:4]) if profil_neden else "çoklu güç yapısı izleniyor"

            if guclu_devam:
                mesaj = (
                    f"🟢 +%5 KÂRI KORU - {symbol}\n"
                    f"İşlem girişi: {islem_giris:.4f} | Güncel: {fiyat:.4f}\n"
                    f"Getiri: %{karar_getiri:+.2f} | Görülen tepe: %{islem_max_getiri:+.2f}\n"
                    f"5+ Profil {profil:.0f}/100 | {profil_etiket}\n"
                    f"Devam {devam:.0f} | Yorgunluk {yorgun:.0f} | Dönüş {donus:.0f} | Çıkış {cikis:.0f}\n"
                    f"Güç durumu: KORUNUYOR → devam edebilir.\n"
                    f"Ortak güç: {ortak}\n"
                    f"Karar: SAT YOK; kâr korunarak takip devam."
                )
                print(mesaj)
                telegram_gonder(mesaj)
            else:
                sat_sebebi = (
                    f"+%5 karar noktası: güç kaybediyor | "
                    f"Devam {devam:.0f}, Yorgunluk {yorgun:.0f}, Dönüş {donus:.0f}, Çıkış {cikis:.0f}"
                )
                kapandi = islem_sat_kapat(symbol, fiyat, sebep=sat_sebebi, bildirim=False)
                if kapandi:
                    p["sat_bildirildi"] = True
                    p["aktif"] = False
                mesaj = (
                    f"💰 +%5 KÂR SAT - {symbol}\n"
                    f"İşlem girişi: {islem_giris:.4f} | Güncel: {fiyat:.4f}\n"
                    f"Getiri: %{karar_getiri:+.2f} | Görülen tepe: %{islem_max_getiri:+.2f}\n"
                    f"5+ Profil {profil:.0f}/100 | {profil_etiket}\n"
                    f"Devam {devam:.0f} | Yorgunluk {yorgun:.0f} | Dönüş {donus:.0f} | Çıkış {cikis:.0f}\n"
                    f"Güç durumu: KAYBEDİYOR → devam etmeyebilir.\n"
                    f"Ortak güç: {ortak}\n"
                    f"Karar: {'SAT yapıldı.' if kapandi else 'SAT emri açılamadı; takip sürüyor.'}"
                )
                print(mesaj)
                telegram_gonder(mesaj)
                if kapandi:
                    continue

        # KÂR KİLİDİ:
        # Tepe +%7'yi geçtiğinde RED örneğindeki gibi +%9.9'dan +%2'ye kadar
        # kârın geri verilmesini engellemek için tepe bazlı trailing sınırı sıkılaşır.
        kar_kilidi_limit = None
        if max_getiri >= 20.0:
            kar_kilidi_limit = 2.25
        elif max_getiri >= 15.0:
            kar_kilidi_limit = 2.50
        elif max_getiri >= 10.0:
            kar_kilidi_limit = 2.75
        elif max_getiri >= 7.0:
            kar_kilidi_limit = 3.00

        # Devam hâlâ çok güçlüyse yalnız 0.50 puan ek nefes payı ver.
        efektif_kilit = (
            kar_kilidi_limit + (0.50 if guclu_devam else 0.0)
            if kar_kilidi_limit is not None else None
        )
        kar_kilidi_sat = (
            efektif_kilit is not None
            and tepe_geri >= efektif_kilit
        )

        # SAT: kâr kilidi VEYA belirgin teknik yorgunluk/dönüş.
        sat_kosulu = (
            kar_kilidi_sat
            or (
                max_getiri >= 8.0
                and not guclu_devam
                and (
                    cikis >= CIKIS_SAT_SKORU
                    or (max_getiri >= 15.0 and tepe_geri >= 4.0 and donus >= 55)
                    or (max_getiri >= 20.0 and tepe_geri >= 3.5 and yorgun >= 55)
                )
            )
        )
        if sat_kosulu and not p.get("sat_bildirildi"):
            p["sat_bildirildi"] = True

            if kar_kilidi_sat:
                sat_sebebi = (
                    f"kâr kilidi: tepe geri %{tepe_geri:.2f} "
                    f">= %{efektif_kilit:.2f}"
                )
            else:
                sat_sebebi = f"dinamik çıkış skoru {cikis:.0f}"

            if p.get("portfoyde"):
                islem_sat_kapat(symbol, fiyat, sebep=sat_sebebi, bildirim=False)

            p["aktif"] = False
            emir_notu = (
                "GERÇEK pozisyon otomatik kapatma emri gönderildi."
                if LIVE_MODE and p.get("portfoyde")
                else "PAPER pozisyon otomatik kapatıldı."
                if p.get("portfoyde")
                else "Bu sinyal portföye alınmamıştı; emir gönderilmedi."
            )
            neden_sat = (
                f"tepe sonrası kâr kilidi çalıştı (%{efektif_kilit:.2f} trailing)."
                if kar_kilidi_sat
                else "devam zayıfladı ve dönüş/yorgunluk birlikte yükseldi."
            )

            # Kullanıcı tercihi: +%5 karar mesajı dışında normal SAT/KÂR AL Telegram mesajı gönderme.
            print(
                f"[SESSİZ DİNAMİK ÇIKIŞ] {symbol} | max=%{max_getiri:+.2f} | şimdi=%{getiri:+.2f} | "
                f"geri=%{tepe_geri:.2f} | Devam={devam:.0f} Yorgunluk={yorgun:.0f} Dönüş={donus:.0f} | {neden_sat}"
            )
            continue

        # KÂRI KORU: erken uyarı. Devam hâlâ çok güçlüyse nefeslenmeye izin verir.
        koru_kosulu = (
            max_getiri >= KAR_KORU_BASLANGIC
            and not guclu_devam
            and (
                cikis >= CIKIS_KORU_SKORU
                or (tepe_geri >= 2.0 and yorgun >= 50)
                or (tepe_geri >= 2.5 and donus >= 45)
            )
        )
        if koru_kosulu and not p.get("kar_koru_bildirildi"):
            p["kar_koru_bildirildi"] = True
            print(
                f"[SESSİZ KÂR KORU] {symbol} | max=%{max_getiri:+.2f} | şimdi=%{getiri:+.2f} | "
                f"Devam={devam:.0f} Yorgunluk={yorgun:.0f} Dönüş={donus:.0f} Çıkış={cikis:.0f}"
            )

    # Aynı ticker akışı AL öğrenmesini de günceller; ekstra piyasa API isteği oluşturmaz.
    al_ogrenme_guncelle(ticker)
    rejim_raporu_gerekirse_gonder()


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
    """Her 24 saatte, test başlangıcından sonraki sinyallerin +%5 yakalama oranını gönderir."""
    global _YUZDE5_META

    simdi = time.time()
    son_rapor = float(
        _YUZDE5_META.get("son_rapor", _YUZDE5_META.get("baslangic", simdi)) or simdi
    )
    if simdi - son_rapor < YUZDE5_RAPOR_ARALIGI:
        return

    pencere_bas = son_rapor
    pencere_son = simdi

    # Yalnız bu 24 saatlik test penceresinde açılan AL kayıtları.
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
        f"📊 24 SAATLİK +%5 YAKALAMA RAPORU — {YUZDE5_RAPOR_ETIKETI}\n\n"
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

    _YUZDE5_META["son_rapor"] = simdi
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


# Railway deploy / restart kontrolu: Telegram baglantisini aninda dogrula.
telegram_gonder("✅ BTCTÜRK RADAR AL/SAT başladı ve aktif. Tarama başlıyor.")
trading_startup_kontrol()



def restart_sonrasi_pozisyon_takibini_geri_kur():
    """Railway restart/deploy sonrasi persist edilmis acik PAPER/LIVE pozisyonlari cikis motoruna geri baglar."""
    restored = 0
    pozisyonlar = LIVE_POZISYONLAR if LIVE_MODE else PAPER_POZISYONLAR
    mod = "LIVE" if LIVE_MODE else "PAPER"

    for symbol, pos in list(pozisyonlar.items()):
        if not isinstance(pos, dict) or not pos.get("aktif"):
            continue
        try:
            giris = float(
                pos.get("giris_fiyat")
                or pos.get("entry_price")
                or pos.get("giris")
                or pos.get("price")
                or 0
            )
        except Exception:
            giris = 0.0
        if giris <= 0:
            print(f"[RESTART TAKIP] {symbol} atlandı: giriş fiyatı bulunamadı.")
            continue

        # Restart sonrasi acik pozisyon zaten gercek/PAPER isleme alinmistir;
        # 45 sn Devam Teyidi tekrar uygulanmaz ve ikinci AL emri gonderilmez.
        AL_TAKIP[symbol] = {
            "aktif": True,
            "giris": giris,
            "tepe": float(pos.get("max_fiyat") or pos.get("peak_price") or giris),
            "max_getiri": float(pos.get("max_getiri") or pos.get("peak_return") or 0.0),
            "kar_bildirildi": False,
            "kar_koru_bildirildi": False,
            "sat_bildirildi": False,
            "son_mikro_zamani": 0.0,
            "son_mikro": {},
            "devam_gucu": 0.0,
            "kalicilik": 0.0,
            "ai_skoru": 0.0,
            "adx": None,
            "rsi": None,
            "macd_hist": None,
            "max_devam": 0.0,
            "risk": "RESTORE",
            "portfoyde": True,
            "islem_giris": giris,
            "islem_tl": float(pos.get("tl", LIVE_ISLEM_TUTARI_TL if LIVE_MODE else PAPER_ISLEM_TUTARI_TL) or (LIVE_ISLEM_TUTARI_TL if LIVE_MODE else PAPER_ISLEM_TUTARI_TL)),
            "onay_bekliyor": False,
            "onay_sonucu": "RESTORE",
        }
        restored += 1
        print(f"[RESTART TAKIP] {mod} {symbol} geri bağlandı | giriş={giris:.8f}")

    if restored:
        print(f"[RESTART TAKIP] {restored} açık pozisyon için AL_TAKIP yeniden oluşturuldu.")
    return restored



restart_sonrasi_pozisyon_takibini_geri_kur()

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
        rejim_raporu_gerekirse_gonder()
        yuzde5_basariraporu_gerekirse_gonder()

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
            # Coin daha önce AL aldıysa, canlı teknik durumunu dinamik çıkış motoruna taşı.
            al_takip_teknik_guncelle(a)


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
                    f"Radar {a.get('radar_skoru', 0)}"
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
            key=lambda x: (x.get("ai_skoru", 0), x.get("radar_skoru", 0)),
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

                    ema_yon = "Yukarı" if teknik["ema20"] > teknik["ema50"] else "Aşağı"
                    macd_yon = "Pozitif" if teknik["macd_hist"] is not None and teknik["macd_hist"] > 0 else "Negatif"
                    nedenler = list(a.get("nedenler", []))
                    hizlar = []

                    if a.get("hacim_hizlaniyor"):
                        hizlar.append("hacim hızlanıyor")
                    if a.get("momentum_hizlaniyor"):
                        hizlar.append("momentum hızlanıyor")
                    if a.get("btc_farki_aciliyor"):
                        hizlar.append("BTC farkı açılıyor")
                    if a.get("lider_gucleniyor"):
                        hizlar.append("lider güçleniyor")
                    if a.get("basamakli_trend"):
                        hizlar.append("basamaklı trend korunuyor")

                    if hizlar:
                        baslik = "Erken yakalama" if a.get("orijinal_erken_aday") else "Hareket teyidi"
                        nedenler.insert(0, baslik + ": " + ", ".join(hizlar))

                    rel_bonus = int(a.get("goreceli_guc_bonus", 0) or 0)
                    if rel_bonus:
                        nedenler.insert(0,
                            f"60dk göreceli güç +{rel_bonus} "
                            f"(BTC {a.get('coin_btc_60', 0):+.2f} / piyasa {a.get('coin_piyasa_60', 0):+.2f})"
                        )

                    # 6+ gerçek olumlu neden varsa yalnızca Neden başına alarm koy.
                    # AL kararı veya filtrelerde hiçbir etkisi yok.
                    toplam_neden_sayisi = len(a.get("nedenler", [])) + len(hizlar)
                    neden_alarm = "🚨 🚨 " if toplam_neden_sayisi >= 6 else ""
                    neden = " • ".join(nedenler[:5])

                    mikro = a.get("mikro") or {}
                    mikro_satir = ""
                    if mikro:
                        mikro_satir = (
                            f"⏱ 1dk %{mikro.get('d1', 0)} | 3dk %{mikro.get('d3', 0)} | "
                            f"5dk %{mikro.get('d5', 0)} | 10dk %{mikro.get('d10', 0)}\n"
                        )

                    gorunen_coin = a['symbol'][:-3] if a['symbol'].endswith("TRY") else a['symbol']
                    risk = a.get('risk', 'Bilinmiyor')
                    risk = risk.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "")

                    mesaj += (
                        f"{gorunen_coin} | {a.get('radar_kategori', '')} + 🟢 AL\n\n"
                        f"AI {a.get('ai_skoru', 0)} | Risk {risk} | Erken {a.get('erken_puan', 0)} | "
                        f"Giriş {a.get('giris_kalitesi', 0)} | Devam {a.get('devam_gucu', 0)} | "
                        f"Kalıcılık {a.get('kalicilik_skoru', 0)} | "
                        f"5+Profil {bes_plus_profil_yumusak(a)[0]}\n\n"
                        f"Fiyat {round(a['fiyat'], 4)} | Hacim {a['hacim']}x | Radar {a['radar_skoru']}/100 | BTC 3s %{round(btc, 2)}\n"
                        f"{mikro_satir}"
                        f"EMA {ema_yon} | RSI {teknik['rsi']} | ADX {teknik['adx']} | MACD {macd_yon}\n\n"
                        f"📌 Takip: +%5 karar noktası | güçlü=KÂRI KORU / zayıf=%5 KÂR SAT\n"
                        f"{neden_alarm}Neden: {neden}\n\n"
                    )

                print(mesaj)
                telegram_gonder(mesaj)
                for _g in gonderilecekler:
                    al_karar_izi(_g.get("symbol", "?"), "telegram", "GÖNDERİLDİ")

                # Yalnızca gerçekten gönderilen AL'ları +%5 kâr bildirimi ve 3 saatlik rejim öğrenmesi için takip et.
                piyasa_medyan3 = statistics.median(piyasa_degisim3leri) if piyasa_degisim3leri else 0.0
                btc_giris_fiyati = ticker_fiyat_haritasi.get("BTCTRY", 0)
                for _a in gonderilecekler:
                    al_takip_baslat(_a)
                    al_ogrenme_baslat(_a, btc_d, piyasa_fiyatlari, piyasa_medyan3, btc_giris_fiyati)

        # Ana tarama 60 sn; kâr bildirimi için açık AL'lar 15 sn'de bir kontrol edilir.
        beklenen = 0
        while beklenen < TARAMA_SURESI:
            sure = min(POZISYON_TAKIP_SURESI, TARAMA_SURESI - beklenen)
            time.sleep(sure)
            beklenen += sure

            if AL_TAKIP:
                try:
                    r = requests.get("https://api.btcturk.com/api/v2/ticker", timeout=10)
                    r.raise_for_status()
                    al_takip_guncelle(r.json().get("data", []))
                except Exception as e:
                    print("Kâr bildirim takip hatası:", e)

    except Exception as e:
                    print("Hızlı AL takip hatası:", e)

    except Exception as e:
        print("Bot genel hata:", e)
        time.sleep(30)
