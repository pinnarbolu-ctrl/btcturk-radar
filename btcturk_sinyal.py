import os
import time
import requests
import feedparser
import json


BOT_TOKEN = os.getenv("BOT_TOKEN")

CHAT_IDS = [
    2097448038,
    1877715122
]

TEKRAR_SURESI = 3 * 60 * 60
TARAMA_SURESI = 5 * 60
HIZLI_ON_TARAMA_SURESI = 60
HIZLI_FIYAT_ESIK = 0.40  # 60 sn fiyat ivmesi (%)
HIZLI_HACIM_ESIK = 0.35  # ticker hacmindeki 60 sn pozitif artış (%)
HIZLI_MAX_ADAY = 15       # API yükünü sınırlamak için dakikada en fazla tam analiz
HIZLI_IZLEME_SURESI = 3 * 60    # Ön taramanın yakaladığı coin 3 dk sessiz takipte kalır

# V5.5.1 MAIN13 KALİTELİ ROKET ADAYI + ROKET + ELİT:
# 3 katmanlı yapı korunur: Roket Adayı erken hazırlık, Roket doğrulanmış hareket, Elit en güçlü grup.
# V5.5.1: Roket Adayı, main_13_coklu_guc_havuzu.py içindeki gerçek AL teknik kapısıyla süzülür; Devam Gücü en az 60 kalır.
# Erken yakalama korunur; yalnızca yüksek hacim görmek üst kategori için artık yeterli değildir.
MIKRO_BASAMAK_MIN_SKOR = 60
MIKRO_BASAMAK_MIN_HACIM = 1.35
MIKRO_BASAMAK_MAX_DEGISIM1 = 3.20
MIKRO_BASAMAK_MAX_DEGISIM3 = 5.50
ERKEN_LIDER_MAX_RANK = 10          # 60 sn hızlananlar içinde ilk 10
ERKEN_LIDER_MIN_SKOR = 5           # normal lider skorunda güçlü teyit
ERKEN_LIDER_MIN_BTC_FARK3 = 1.0    # BTC'den 3s bazda en az +%1 ayrışma
ERKEN_LIDER_MIN_MIKRO_IVME = 1.20  # alternatif teyitte hacim basamak ivmesi
hizli_izleme_havuzu = {}        # symbol -> son tetiklenme zamanı

# V5.5.0 - AL Assistant Çoklu Güç Havuzu uyarlaması.
# Bir coin ilk güçlenme işaretinde doğrudan Telegram'a düşmez. Önce havuza alınır,
# sonraki derin analizde güçlenmeyi koruyup artırırsa Roket Adayı olabilir.
al_assistant_guc_havuzu = {}
AL_GUC_HAVUZU_SURESI = 8 * 60
AL_GUC_HAVUZU_MIN_BEKLEME = 45
STOP_RAPOR_SURESI = 2 * 60 * 60
HAFTALIK_RAPOR_SURESI = 7 * 24 * 60 * 60

gonderilenler = {}
son_durumlar = {}
aktif_sinyaller = {}
ilk_tespitler = {}
onceki_veriler = {}
stop_raporlari = []
son_stop_raporu = time.time()

haftalik_kayitlar = []
h1_kayitlari = []
h2_kayitlari = []
kategori_istatistikleri = {}
V5_RAPOR_STATE_DOSYA = "v5_report_state.json"

def _v5_rapor_state_yukle():
    try:
        with open(V5_RAPOR_STATE_DOSYA, "r", encoding="utf-8") as f:
            veri = json.load(f)
        ts = float(veri.get("son_haftalik_rapor", 0) or 0)
        if ts > 0:
            return ts
    except Exception:
        pass

    # Deploy / restart anında haftalık rapor gönderme.
    # State dosyası yoksa bu açılış anını yeni başlangıç kabul et.
    simdi = time.time()
    try:
        _v5_rapor_state_kaydet(simdi)
    except Exception:
        pass
    print("📅 Haftalık rapor state bulunamadı; sayaç bu açılıştan itibaren başlatıldı.")
    return simdi

def _v5_rapor_state_kaydet(zaman_degeri):
    try:
        gecici = V5_RAPOR_STATE_DOSYA + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump({"son_haftalik_rapor": float(zaman_degeri)}, f, ensure_ascii=False, indent=2)
        os.replace(gecici, V5_RAPOR_STATE_DOSYA)
        return True
    except Exception as e:
        print("❌ Haftalık rapor zamanı kaydedilemedi:", e)
        return False

def _v5_zaman_yazi(ts):
    if not ts:
        return "henüz gönderilmedi"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except Exception:
        return str(ts)

son_haftalik_rapor = _v5_rapor_state_yukle()
_son_rapor_kontrol_logu = 0.0

STABLE_COINLER = [
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "USDP"
]


DURUM_SEVIYESI = {
    "📈 İzleme": 1,
    "⚡ GÜÇLÜ HACİM": 2,
    "📊 TRADER HACİM": 3,
    "📈 GÜÇLENİYOR": 4,
    "🚀 Roket Adayı": 5,
    "🚀 Roket": 6,
    "🔥 Elit Roket": 7,
    "⭐ Yıldız": 8
}

# V4.25: Telegram sadeleşti. Bu kategoriler dışındakiler sadece arka planda izlenir.
TELEGRAM_KATEGORILERI = {
    "📊 TRADER HACİM",
    "🚀 Roket Adayı",
    "🚀 Roket",
    "🔥 Elit Roket",
    "⭐ Yıldız"
}


# === V5.1 DECISION ENGINE PATCH ===
# Bu blok Telegram mesajını artırmadan karar kalitesini yükseltir.
# Yıldız Adayı Telegram kategorisi değildir; sadece arka planda izlenir.
V5_1_SURUM = "V5.1 decision engine"
V5_1_YILDIZ_ADAY_DB = "v5_yildiz_adaylari.json"
V5_1_ZAYIF_TRADER_MIN_MOMENTUM = 4.0
V5_1_YILDIZ_ADAY_MIN_MOMENTUM = 2.0
V5_1_YILDIZ_ADAY_MAX_MOMENTUM = 4.5
V5_1_GUCLENME_SKOR_BONUS = 4
V5_1_ZAYIF_TRADER_CEZA = 8

try:
    DURUM_SEVIYESI.setdefault("⭐ Yıldız Adayı", 5.5)
except Exception:
    pass


def v5_1_json_yukle(dosya, varsayilan):
    try:
        with open(dosya, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def v5_1_json_kaydet(dosya, veri):
    try:
        with open(dosya, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("V5.1 json kaydedilemedi:", dosya, e)


v5_1_yildiz_adaylari = v5_1_json_yukle(V5_1_YILDIZ_ADAY_DB, {})


def v5_1_guclenme_bayraklari(a):
    """Hacim/momentum güçlenmesini mesaj süsü olmaktan çıkarıp karar motoruna verir."""
    notlar = a.get("guclenme_notlari", []) or []
    hacim_gucleniyor = any("hacim güçleniyor" in str(n).lower() for n in notlar)
    momentum_gucleniyor = any("momentum güçleniyor" in str(n).lower() for n in notlar)

    onceki = a.get("onceki_veri") or {}
    try:
        eski_hacim = float(onceki.get("hacim", a.get("hacim", 0)) or 0)
        yeni_hacim = float(a.get("hacim", 0) or 0)
        if eski_hacim > 0 and yeni_hacim >= eski_hacim * 1.20:
            hacim_gucleniyor = True
    except Exception:
        pass

    try:
        eski_momentum = float(onceki.get("degisim3", a.get("degisim3", 0)) or 0)
        yeni_momentum = float(a.get("degisim3", 0) or 0)
        if yeni_momentum - eski_momentum >= 0.5:
            momentum_gucleniyor = True
    except Exception:
        pass

    return bool(hacim_gucleniyor), bool(momentum_gucleniyor)


def v5_1_zayif_trader_hacim_mi(a):
    """10x+ hacim ama 3s momentum < 4 ise Telegram spam/risk sayılır."""
    try:
        return (
            float(a.get("hacim", 0) or 0) >= 10
            and float(a.get("degisim3", 0) or 0) < V5_1_ZAYIF_TRADER_MIN_MOMENTUM
            and not bool(a.get("momentum_gucleniyor", False))
        )
    except Exception:
        return False


def v5_1_yildiz_adayi_mi(a):
    """Erken yakalama için Telegram'a düşmeyen arka plan yıldız adayı."""
    try:
        degisim3 = float(a.get("degisim3", 0) or 0)
        return (
            bool(a.get("btcden_guclu", False))
            and float(a.get("lider_skoru", 0) or 0) >= 6
            and float(a.get("hacim", 0) or 0) >= 5
            and bool(a.get("hacim_gucleniyor", False))
            and V5_1_YILDIZ_ADAY_MIN_MOMENTUM <= degisim3 <= V5_1_YILDIZ_ADAY_MAX_MOMENTUM
            and bool(a.get("zirve_yakin", False) or a.get("yeni_zirve", False))
        )
    except Exception:
        return False


def v5_1_yildiz_adayi_kaydet(symbol, a):
    try:
        v5_1_yildiz_adaylari[symbol] = {
            "zaman": time.time(),
            "fiyat": a.get("fiyat"),
            "skor": a.get("skor"),
            "guc_skoru": a.get("guc_skoru"),
            "hacim": a.get("hacim"),
            "degisim3": a.get("degisim3"),
            "btc_fark": a.get("btc_fark"),
            "lider_skoru": a.get("lider_skoru"),
            "durum": "⭐ Yıldız Adayı",
        }
        # 7 günden eski adayları temizle.
        simdi = time.time()
        eski = [s for s, k in v5_1_yildiz_adaylari.items() if simdi - float(k.get("zaman", simdi)) > 7 * 24 * 3600]
        for s in eski:
            v5_1_yildiz_adaylari.pop(s, None)
        v5_1_json_kaydet(V5_1_YILDIZ_ADAY_DB, v5_1_yildiz_adaylari)
    except Exception as e:
        print("V5.1 yıldız adayı kaydedilemedi:", symbol, e)


def v5_1_yildiz_adayindan_guclendi_mi(symbol, a):
    onceki = v5_1_yildiz_adaylari.get(symbol)
    if not onceki:
        return False
    try:
        return (
            float(a.get("degisim3", 0) or 0) >= 4
            and float(a.get("hacim", 0) or 0) >= float(onceki.get("hacim", 0) or 0) * 0.90
            and float(a.get("guc_skoru", 0) or 0) >= float(onceki.get("guc_skoru", 0) or 0)
        )
    except Exception:
        return False


def v5_1_sinyal_sonuc_kalite_raporu(kayitlar):
    """H1 var/H2 yok ayrımını rapora ekler; kar al mı bekle mi sorusuna veri üretir."""
    try:
        if not kayitlar:
            return "\n🎯 V5.1 H1/H2 KALİTE ANALİZİ\nYeterli kayıt yok.\n"
        h1_h2_yok = [k for k in kayitlar if k.get("h1") and not k.get("h2")]
        h2ler = [k for k in kayitlar if k.get("h2")]
        stoplar = [k for k in kayitlar if k.get("stop") and not k.get("h1") and not k.get("h2")]
        aktif = [k for k in kayitlar if k.get("sonuc") == "aktif"]
        toplam = max(len(kayitlar), 1)
        msg = "\n🎯 V5.1 H1/H2 KALİTE ANALİZİ\n"
        msg += f"H1 oldu H2 olmadı: {len(h1_h2_yok)} (%{round(len(h1_h2_yok)*100/toplam,1)})\n"
        msg += f"H2 tamamladı: {len(h2ler)} (%{round(len(h2ler)*100/toplam,1)})\n"
        msg += f"Stop oldu: {len(stoplar)} (%{round(len(stoplar)*100/toplam,1)})\n"
        msg += f"Aktif takip: {len(aktif)}\n"
        if len(h1_h2_yok) > len(h2ler) and len(h1_h2_yok) >= 3:
            msg += "Yorum: H1 sonrası kar alma daha verimli görünüyor; H2 için ek teyit gerekebilir.\n"
        elif len(h2ler) >= len(h1_h2_yok) and len(h2ler) >= 3:
            msg += "Yorum: H2 tutma mantığı çalışıyor; güçlü kombinasyonlarda beklemek mantıklı.\n"
        return msg
    except Exception as e:
        return f"\n🎯 V5.1 H1/H2 KALİTE ANALİZİ\nRapor hatası: {e}\n"


def v5_1_adaptif_strateji_raporu(kayitlar):
    """30 günlük raporda strateji önerisi üretir; 7 günlük raporda kısa kalır."""
    try:
        if len(kayitlar) < 5:
            return "\n🤖 V5.1 ADAPTİF STRATEJİ\nDaha net öneri için en az 5 sonuç kaydı gerekli.\n"
        toplam = len(kayitlar)
        h2 = sum(1 for k in kayitlar if k.get("h2"))
        stop = sum(1 for k in kayitlar if k.get("stop") and not k.get("h1") and not k.get("h2"))
        zayif_trader = [k for k in kayitlar if float(k.get("hacim", 0) or 0) >= 10 and float(k.get("degisim3", 0) or 0) < 4]
        guclenen = [k for k in kayitlar if k.get("hacim_gucleniyor") and k.get("momentum_gucleniyor")]
        msg = "\n🤖 V5.1 ADAPTİF STRATEJİ\n"
        msg += f"Genel H2: %{round(h2*100/max(toplam,1),1)} | Stop: %{round(stop*100/max(toplam,1),1)}\n"
        if zayif_trader:
            z_stop = sum(1 for k in zayif_trader if k.get("stop") and not k.get("h1") and not k.get("h2"))
            msg += f"Zayıf Trader Hacim: {len(zayif_trader)} kayıt | Stop %{round(z_stop*100/max(len(zayif_trader),1),1)}\n"
            msg += "Öneri: 10x+ hacimde 3s momentum <4 ise Telegram'a alma, DNA'da izle.\n"
        if guclenen:
            g_h2 = sum(1 for k in guclenen if k.get("h2"))
            msg += f"Hacim+Momentum güçlenen: {len(guclenen)} kayıt | H2 %{round(g_h2*100/max(len(guclenen),1),1)}\n"
            msg += "Öneri: Bu kombinasyon kategori yükseltmede öncelikli kalsın.\n"
        return msg
    except Exception as e:
        return f"\n🤖 V5.1 ADAPTİF STRATEJİ\nRapor hatası: {e}\n"

# === /V5.1 DECISION ENGINE PATCH ===

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


BASARI_DB_DOSYA = "basari_veritabani.json"

PIYASA_DB_DOSYA = "piyasa_veritabani.json"
PIYASA_RAPOR_GUN = 3
PIYASA_KAZANAN_ESIK = 10
SINYALE_GORE_TAKIP_SAATI = 72


def piyasa_db_yukle():
    try:
        with open(PIYASA_DB_DOSYA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def piyasa_db_kaydet(veriler):
    """Tüm coin piyasa özetini saklar. Sadece sinyal alanları değil, kaçanları da analiz eder."""
    try:
        simdi = time.time()
        # Dosya şişmesin: 7 günlük kayıt yeterli.
        temiz = [k for k in veriler if simdi - float(k.get("zaman", simdi)) <= 7 * 24 * 60 * 60]
        with open(PIYASA_DB_DOSYA, "w", encoding="utf-8") as f:
            json.dump(temiz[-5000:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Piyasa veritabanı kaydedilemedi:", e)


piyasa_kayitlari = piyasa_db_yukle()


def piyasa_kaydi_ekle(symbol, veri):
    """Her taramada tüm coinleri kaydeder; sinyal gelmeyen ama sonradan gidenleri yakalamak için."""
    try:
        kayit = {
            "zaman": time.time(),
            "symbol": symbol,
            "fiyat": round(float(veri.get("fiyat", 0)), 8),
            "degisim1": round(float(veri.get("degisim1", 0)), 4),
            "degisim3": round(float(veri.get("degisim3", 0)), 4),
            "degisim24": round(float(veri.get("degisim24", 0)), 4),
            "hacim": round(float(veri.get("hacim", 0)), 4),
            "btc_guclu": bool(veri.get("btc_guclu", False)),
            "btc_fark": round(float(veri.get("btc_fark", 0)), 4),
            "lider_mi": bool(veri.get("lider_mi", False)),
            "lider_skoru": round(float(veri.get("lider_skoru", 0)), 4),
            "zirve_teyidi": bool(veri.get("zirve_teyidi", False)),
            "zirve_yakin": bool(veri.get("zirve_yakin", False)),
            "yeni_zirve": bool(veri.get("yeni_zirve", False)),
            "haber_var": bool(veri.get("haber_var", False)),
            "sinyal_var": bool(veri.get("sinyal_var", False)),
            "durum": veri.get("durum"),
            "guc_skoru": round(float(veri.get("guc_skoru", 0)), 4),
            "gec_pump_puan": int(veri.get("gec_pump_puan", 0)),
            "mikro_basamak": bool(veri.get("mikro_basamak", False)),
            "mikro_basamak_skor": round(float(veri.get("mikro_basamak_skor", 0)), 4),
            "mikro_mum_sayisi": int(veri.get("mikro_mum_sayisi", 0) or 0),
            "mikro_hacim_ivmesi": round(float(veri.get("mikro_hacim_ivmesi", 1.0) or 1.0), 4),
            "hizli_lider_rank": int(veri.get("hizli_lider_rank", 0) or 0),
            "hizli_fiyat_ivme": round(float(veri.get("hizli_fiyat_ivme", 0) or 0), 4),
            "hizli_hacim_ivme": round(float(veri.get("hizli_hacim_ivme", 0) or 0), 4),
            "erken_lider_onayi": bool(veri.get("erken_lider_onayi", False)),
        }
        piyasa_kayitlari.append(kayit)

        # Her kayıtta dosyaya yazmak güvenli ama pahalı olabilir; yine de Railway yeniden başlarsa veri kaybolmasın.
        if len(piyasa_kayitlari) % 20 == 0:
            piyasa_db_kaydet(piyasa_kayitlari)
    except Exception as e:
        print("Piyasa kaydı eklenemedi:", symbol, e)


def piyasa_kacirilan_raporu_olustur(gun=PIYASA_RAPOR_GUN, esik=PIYASA_KAZANAN_ESIK):
    """Son X günde %10+ yapan tüm coinleri ve botun kaçırdıklarını özetler."""
    simdi = time.time()
    baslangic = simdi - gun * 24 * 60 * 60
    kayitlar = [k for k in piyasa_kayitlari if float(k.get("zaman", 0)) >= baslangic]

    if not kayitlar:
        return "\n🎯 PİYASA ANALİZİ (3 Gün)\nYeterli piyasa kaydı yok.\n"

    # Her coin için son 3 günün en yüksek 24s performanslı kaydını al.
    coin_ozet = {}
    for k in kayitlar:
        s = k.get("symbol")
        if not s:
            continue
        if s not in coin_ozet or float(k.get("degisim24", 0)) > float(coin_ozet[s].get("degisim24", 0)):
            coin_ozet[s] = k

    kazananlar = [k for k in coin_ozet.values() if float(k.get("degisim24", 0)) >= esik]
    kazananlar = sorted(kazananlar, key=lambda x: float(x.get("degisim24", 0)), reverse=True)

    if not kazananlar:
        return f"\n🎯 PİYASA ANALİZİ ({gun} Gün)\n%{esik}+ yapan coin bulunamadı.\n"

    # Aynı dönemde botun ÖNCEDEN sinyal verdiği coinler.
    # Not: Sinyal, büyük hareket kaydından sonra geldiyse yakalanmış sayılmaz.
    # Böylece geç gelen sinyaller yakalama oranını yapay yükseltmez.
    sinyal_haritasi = {}
    for b in basari_kayitlari:
        s = b.get("symbol")
        if not s:
            continue

        sinyal_zaman = float(b.get("zaman", 0) or 0)
        if sinyal_zaman < baslangic:
            continue

        mevcut = sinyal_haritasi.get(s)
        if mevcut is None or sinyal_zaman < mevcut.get("zaman", 0):
            sinyal_haritasi[s] = {
                "zaman": sinyal_zaman,
                "kategori": b.get("kategori", "Bilinmiyor"),
                "giris": b.get("giris"),
            }

    yakalananlar = []
    kacirilanlar = []
    for k in kazananlar:
        s = k.get("symbol")
        sinyal = sinyal_haritasi.get(s)
        buyuk_hareket_zaman = float(k.get("zaman", 0) or 0)

        if sinyal and sinyal.get("zaman", 0) <= buyuk_hareket_zaman:
            k["yakalanan_kategori"] = sinyal.get("kategori", "Bilinmiyor")
            try:
                k["sinyalden_sonra_saat"] = round((buyuk_hareket_zaman - sinyal.get("zaman", buyuk_hareket_zaman)) / 3600, 2)
            except Exception:
                k["sinyalden_sonra_saat"] = 0
            yakalananlar.append(k)
        else:
            kacirilanlar.append(k)

    def oran(liste, alan):
        if not liste:
            return 0
        return round(sum(1 for k in liste if k.get(alan)) * 100 / len(liste), 1)

    def ort(liste, alan):
        if not liste:
            return 0
        return round(sum(float(k.get(alan, 0)) for k in liste) / len(liste), 2)

    yakalama_orani = round(len(yakalananlar) * 100 / max(len(kazananlar), 1), 1)

    mesaj = f"\n🎯 PİYASA ANALİZİ ({gun} Gün)\n"
    mesaj += f"%{esik}+ yapan coin: {len(kazananlar)}\n"
    mesaj += f"Bot yakaladı: {len(yakalananlar)}\n"
    mesaj += f"Bot kaçırdı: {len(kacirilanlar)}\n"
    mesaj += f"Yakalama Oranı: %{yakalama_orani}\n"

    if kacirilanlar:
        mesaj += "\n🚀 EN BÜYÜK KAÇIRILANLAR\n"
        for k in kacirilanlar[:5]:
            mesaj += f"{k.get('symbol')} | 24s: %{round(float(k.get('degisim24', 0)), 2)} | Hacim: {round(float(k.get('hacim', 0)), 2)}x\n"

        mesaj += "\n🔍 KAÇIRILANLARIN ORTAK ÖZELLİĞİ\n"
        mesaj += f"BTC Güçlü: %{oran(kacirilanlar, 'btc_guclu')}\n"
        mesaj += f"Lider: %{oran(kacirilanlar, 'lider_mi')}\n"
        mesaj += f"Zirve: %{oran(kacirilanlar, 'zirve_teyidi')}\n"
        mesaj += f"Haber: %{oran(kacirilanlar, 'haber_var')}\n"
        mesaj += f"Hacim >10x: %{round(sum(1 for k in kacirilanlar if float(k.get('hacim', 0)) >= 10) * 100 / max(len(kacirilanlar), 1), 1)}\n"
        mesaj += f"Ort. Hacim: {ort(kacirilanlar, 'hacim')}x | Ort. BTC Fark: %{ort(kacirilanlar, 'btc_fark')}\n"
        mesaj += f"Ort. 1s: %{ort(kacirilanlar, 'degisim1')} | Ort. 3s: %{ort(kacirilanlar, 'degisim3')} | Ort. 24s: %{ort(kacirilanlar, 'degisim24')}\n"

        sebepler = []
        if oran(kacirilanlar, 'btc_guclu') >= 70:
            sebepler.append("BTC güçlüydü ama kriterlerden kaçtı")
        if oran(kacirilanlar, 'lider_mi') < 40:
            sebepler.append("Lider oranı düşük")
        if sum(1 for k in kacirilanlar if float(k.get('hacim', 0)) >= 5) * 100 / max(len(kacirilanlar), 1) < 50:
            sebepler.append("Hacim eşiği altında kaldılar")
        if oran(kacirilanlar, 'zirve_teyidi') < 40:
            sebepler.append("Zirve teyidi zayıf")

        if sebepler:
            mesaj += "En Sık Sebep: " + " • ".join(sebepler[:2]) + "\n"

    if yakalananlar:
        mesaj += "\n✅ YAKALANAN %10+ COINLER\n"
        for k in yakalananlar[:5]:
            mesaj += (
                f"{k.get('symbol')} | {k.get('yakalanan_kategori', 'Bilinmiyor')} | "
                f"24s: %{round(float(k.get('degisim24', 0)), 2)} | "
                f"Sinyalden sonra: {k.get('sinyalden_sonra_saat', 0)}s\n"
            )

        kategori_sayilari = {}
        for k in yakalananlar:
            kat = k.get("yakalanan_kategori", "Bilinmiyor")
            kategori_sayilari[kat] = kategori_sayilari.get(kat, 0) + 1

        mesaj += "\n📌 YAKALAYAN KATEGORİLER\n"
        for kat, adet in sorted(kategori_sayilari.items(), key=lambda x: x[1], reverse=True):
            mesaj += f"{kat}: {adet}\n"

        mesaj += (
            "Yakalanan ort.: "
            f"1s %{ort(yakalananlar, 'degisim1')} | "
            f"3s %{ort(yakalananlar, 'degisim3')} | "
            f"24s %{ort(yakalananlar, 'degisim24')} | "
            f"Hacim {ort(yakalananlar, 'hacim')}x\n"
        )

    return mesaj


def basari_db_yukle():
    try:
        with open(BASARI_DB_DOSYA, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def legacy_basari_db_kaydet_v4(veriler):
    try:
        with open(BASARI_DB_DOSYA, "w", encoding="utf-8") as f:
            json.dump(veriler[-500:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Başarı veritabanı kaydedilemedi:", e)


basari_kayitlari = basari_db_yukle()


def legacy_basari_kaydi_olustur_v4(symbol, a, simdi):
    guclenme_notlari = a.get("guclenme_notlari", []) or []
    hacim_gucleniyor = any("hacim güçleniyor" in str(n).lower() for n in guclenme_notlari)
    momentum_gucleniyor = any("momentum güçleniyor" in str(n).lower() for n in guclenme_notlari)

    # Güçlenme notu boşsa, gönderim anındaki son tarama verisinden de bayrak üret.
    onceki = a.get("onceki_veri") or {}
    if onceki:
        eski_hacim = float(onceki.get("hacim", a.get("hacim", 0)) or 0)
        yeni_hacim = float(a.get("hacim", 0) or 0)
        if eski_hacim > 0 and yeni_hacim >= eski_hacim * 1.20:
            hacim_gucleniyor = True

        eski_momentum = float(onceki.get("degisim3", a.get("degisim3", 0)) or 0)
        yeni_momentum = float(a.get("degisim3", 0) or 0)
        if yeni_momentum - eski_momentum >= 0.5:
            momentum_gucleniyor = True

    return {
        "symbol": symbol,
        "kategori": a["durum"],
        "zaman": simdi,
        "giris": a["fiyat"],
        "skor": round(a["skor"], 4),
        "kalite": round(a["kalite_skoru"], 4),
        "hacim": round(a["hacim"], 4),
        "haber": a["haber_skoru"],
        "btc_guclu": bool(a["btcden_guclu"]),
        "btc_fark": round(a.get("btc_fark", 0), 4),
        "degisim1": round(a["degisim1"], 4),
        "degisim3": round(a["degisim3"], 4),
        "degisim24": round(a["degisim24"], 4),
        "yakalama_tipi": ("erken" if a.get("degisim1", 0) <= 2 else ("normal" if a.get("degisim1", 0) <= 6 else "gec")),
        "guclenme_bonus": a.get("guclenme_bonus", 0),
        "hacim_gucleniyor": bool(hacim_gucleniyor),
        "momentum_gucleniyor": bool(momentum_gucleniyor),

        # V4.25.1 DNA alanları: Telegram'da kalabalık yapmadan raporda analiz edilir.
        "haber_var": bool(a.get("haber_skoru", 0) > 0),
        "lider_mi": bool(a.get("lider_skoru", 0) >= 5),
        "lider_guclu": bool(a.get("lider_skoru", 0) >= 7),
        "zirve_yakin": bool(a.get("zirve_yakin", False)),
        "yeni_zirve": bool(a.get("yeni_zirve", False)),
        "zirve_teyidi": bool(a.get("zirve_yakin", False) or a.get("yeni_zirve", False)),
        "hacim_10x": bool(a.get("hacim", 0) >= 10),
        "hacim_15x": bool(a.get("hacim", 0) >= 15),
        "btc_bonus": int(a.get("btc_fark_bonus", 0)),
        "lider_bonus": int(a.get("lider_bonus", 0)),
        "zirve_bonus": int(a.get("zirve_bonus", 0)),
        "hacim_bonus": int(a.get("hacim_bonus", 0)),
        "gec_pump_puan": int(a.get("gec_pump_puan", 0)),

        "h1": False,
        "h2": False,
        "stop": False,
        "max_kazanc": 0.0,
        "sonuc": "aktif"
    }

def basari_kaydi_guncelle(symbol, fiyat, durum=None, h1=False, h2=False, stop=False):
    """Başarı kaydını günceller.

    V4.28 düzeltmesi:
    - H1 sonrası kayıt kapanmaz; H2 gelirse aynı kayıt H2 olarak güncellenir.
    - H1/H2/Stop süreleri saklanır.
    - Stop, H1/H2 gelmeden olursa başarısız sayılır; H1 sonrası stop sadece risk notu olarak kalır.
    """
    simdi = time.time()

    for k in reversed(basari_kayitlari):
        if k.get("symbol") != symbol:
            continue

        if k.get("sonuc") in ("h2", "stop"):
            continue

        giris = k.get("giris", fiyat)

        if giris:
            kazanc = ((fiyat - giris) / giris) * 100
            k["max_kazanc"] = round(max(float(k.get("max_kazanc", 0) or 0), kazanc), 4)
            k["son_kazanc"] = round(kazanc, 4)

        if durum:
            k["kategori_son"] = durum

        if h1 and not k.get("h1"):
            k["h1"] = True
            k["h1_zaman"] = simdi
            k["h1_sure_saat"] = round((simdi - float(k.get("zaman", simdi))) / 3600, 2)
            k["sonuc"] = "h1"

        if h2 and not k.get("h2"):
            k["h2"] = True
            k["h2_zaman"] = simdi
            k["h2_sure_saat"] = round((simdi - float(k.get("zaman", simdi))) / 3600, 2)
            k["sonuc"] = "h2"

        if stop and not k.get("stop"):
            k["stop"] = True
            k["stop_zaman"] = simdi
            k["stop_sure_saat"] = round((simdi - float(k.get("zaman", simdi))) / 3600, 2)
            if not k.get("h1") and not k.get("h2"):
                k["sonuc"] = "stop"

        basari_db_kaydet(basari_kayitlari)
        return

def telegram_gonder(mesaj):
    """Telegram mesajını parçalara ayırarak gönderir ve gerçek başarı durumunu döndürür."""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN bulunamadı. Railway Variables kontrol et.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    parcalar = []
    kalan = str(mesaj)
    while len(kalan) > 3900:
        bol = kalan.rfind("\n", 0, 3900)
        if bol == -1:
            bol = 3900
        parcalar.append(kalan[:bol])
        kalan = kalan[bol:].lstrip()
    if kalan:
        parcalar.append(kalan)

    tumu_basarili = True
    for chat_id in CHAT_IDS:
        for sira, parca in enumerate(parcalar, 1):
            try:
                r = requests.get(url, params={"chat_id": chat_id, "text": parca}, timeout=15)
                try:
                    cevap = r.json()
                    telegram_ok = bool(cevap.get("ok"))
                except Exception:
                    cevap = {"raw": r.text[:500]}
                    telegram_ok = False
                if not (r.ok and telegram_ok):
                    tumu_basarili = False
                    print(f"❌ Telegram gönderim hatası | chat={chat_id} parça={sira}/{len(parcalar)} status={r.status_code} cevap={cevap}")
                else:
                    print(f"✅ Telegram gönderildi | chat={chat_id} parça={sira}/{len(parcalar)}")
            except Exception as e:
                tumu_basarili = False
                print(f"❌ Telegram bağlantı hatası | chat={chat_id}: {e}")
    return tumu_basarili


def veri_getir(symbol, saat=24):
    simdi = int(time.time())
    url = (
        f"https://graph-api.btcturk.com/v1/klines/history?"
        f"symbol={symbol}&resolution=60&from={simdi - (saat * 3600)}&to={simdi}"
    )
    return requests.get(url, timeout=10).json()


def anlik_fiyat(symbol):
    try:
        d = veri_getir(symbol, 1)
        c = d["c"]
        if len(c) == 0:
            return None
        return c[-1]
    except:
        return None



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



def gec_pump_puani_hesapla(degisim1, degisim3, degisim24, hacim_kat, btcden_guclu, lider_skoru):
    """
    V4.25.4 Geç Pump puanı.
    Tek başına 24s yükselişiyle iyi trendleri elemez; geç kalma riskini çoklu teyitle ölçer.
    AIOZ gibi BTC'den güçlü ve lider hareketleri yanlışlıkla kaçırmamak için BTC/lider/hacim koruması verir.
    """
    puan = 0

    if degisim24 > 8:
        puan += 1
    if degisim24 > 12:
        puan += 1
    if degisim24 > 15:
        puan += 1

    if degisim3 > 5:
        puan += 1
    if degisim1 > 3:
        puan += 1

    # Güçlü devam sinyalleri varsa direkt geç pump sayma.
    if btcden_guclu:
        puan -= 1
    if lider_skoru >= 5:
        puan -= 1
    if hacim_kat > 15:
        puan -= 1

    return max(puan, 0)


def gec_pump_mi(degisim1, degisim3, degisim24, hacim_kat, btcden_guclu, lider_skoru):
    return gec_pump_puani_hesapla(
        degisim1, degisim3, degisim24, hacim_kat, btcden_guclu, lider_skoru
    ) >= 3

def guc_skoru_hesapla(
    hacim_kat,
    degisim3,
    btc_guc_skoru,
    lider_skoru,
    haber_skoru,
    satis_baskisi,
    gec_pump,
    btc_fark3=0,
    zirve_yakin=False,
    yeni_zirve=False
):
    """
    V4.25 Güç Skoru: 100 üzerinden tek karar skoru.
    V4.25 commit ince ayarı:
    - 10x / 15x / 20x hacim daha net ödüllendirilir.
    - BTC farkı belirginse ekstra puan alır.
    - Liderlik ve zirve teyidi trader mantığında skora yansır.
    """
    # V5 momentum/hacim ayarı:
    # Raporlarda 6%+ momentum en güçlü grup, 10x+ hacim ise tek başına zayıf çıktı.
    # Bu yüzden güç skorunda momentum ağırlığı artırıldı, hacim etkisi azaltıldı.
    hacim_puan = min(hacim_kat / 10, 1) * 18
    momentum_puan = min(max(degisim3, 0) / 6, 1) * 34
    btc_puan = (btc_guc_skoru / 10) * 20
    lider_puan = (lider_skoru / 10) * 15
    haber_puan = (min(haber_skoru, 20) / 20) * 10

    toplam = hacim_puan + momentum_puan + btc_puan + lider_puan + haber_puan

    # Momentum teyidi: 6%+ 3s momentum raporda en başarılı bant olduğu için ekstra ödüllenir.
    if degisim3 >= 6:
        toplam += 6
    elif degisim3 >= 4:
        toplam += 3
    elif degisim3 >= 2:
        toplam += 1

    # Yüksek hacim tek başına artık güçlü sinyal sayılmaz.
    # 10x+ hacim, momentum/liderlik zayıfsa geç kalmış hareket olarak puan kırar.
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

    # Geç Pump artık skor/bonus kesmez; sadece DNA raporunda risk verisi olarak tutulur.
    if zirve_yakin or yeni_zirve:
        toplam += 1

    if satis_baskisi:
        toplam -= 12

    return round(max(min(toplam, 100), 0), 2)


def neden_secildi_olustur(a):
    """
    V4.25 mesaj açıklaması. Ham skor yerine sinyalin mantığını kısa şekilde anlatır.
    """
    notlar = []

    if a.get("btc_fark3", 0) >= 1:
        notlar.append(f"BTC'den 3s bazda %{round(a.get('btc_fark3', 0), 2)} güçlü")

    if a.get("btc_fark24", 0) >= 2:
        notlar.append(f"BTC'den 24s bazda %{round(a.get('btc_fark24', 0), 2)} güçlü")

    if a.get("hacim", 0) >= 15:
        notlar.append(f"Trader hacim: {round(a.get('hacim', 0), 2)}x")
    elif a.get("hacim", 0) >= 8:
        notlar.append(f"Güçlü hacim: {round(a.get('hacim', 0), 2)}x")

    if a.get("lider_skoru", 0) >= 7:
        notlar.append("Lider grubunda")
    elif a.get("lider_skoru", 0) >= 5:
        notlar.append("Lider takibe yakın")

    if a.get("yeni_zirve"):
        notlar.append("Yeni zirve denemesi var")
    elif a.get("zirve_yakin"):
        notlar.append("Zirveye yakın")

    if a.get("haber_skoru", 0) > 0:
        notlar.append("Haber desteği var")

    if a.get("guclenme_bonus", 0) > 0:
        notlar.append("Önceki tespite göre güçleniyor")

    if not notlar:
        notlar.append("Hacim, momentum ve BTC gücü birlikte yeterli")

    return notlar[:5]

def haber_var_mi(a):
    return a.get("haber_skoru", 0) > 0


def lider_mi(a):
    return a.get("lider_skoru", 0) >= 5


def zirve_teyidi_var_mi(a):
    return bool(a.get("zirve_yakin") or a.get("yeni_zirve"))


def ortak_sinyal_ozeti_olustur(a):
    """
    V4.25.8 Telegram kısa özet.
    Tek satırda sadece karar için en hızlı okunan sinyalleri gösterir.
    Hacim ayrı satırda yazıldığı için burada tekrar edilmez.
    """
    btc_fark = round(a.get("btc_fark", 0), 2)
    if a.get("btcden_guclu"):
        btc_text = f"BTC'den %{btc_fark} güçlü"
    else:
        btc_text = "BTC gücü zayıf"

    lider_text = "Lider ✅" if lider_mi(a) else "Lider ❌"
    zirve_text = "Zirve ✅" if zirve_teyidi_var_mi(a) else "Zirve ❌"

    return f"{btc_text} • {lider_text} • {zirve_text}"


def guclenme_mesaji_olustur(a):
    """
    Mesajda sadece karar için anlamlı güçlenme notları kalsın:
    - Hacim güçleniyor
    - Momentum güçleniyor

    Not: Bazı coinlerde guclenme_notlari boş gelebiliyor.
    Bu yüzden gönderim anında onceki_veri üzerinden de kontrol yapıyoruz.
    """
    satirlar = []

    for not_text in a.get("guclenme_notlari", []) or []:
        if "Hacim güçleniyor" in not_text:
            satirlar.append("📈 " + not_text)
        elif "momentum güçleniyor" in not_text.lower():
            temiz = not_text.replace("3s momentum güçleniyor", "Momentum güçleniyor")
            temiz = temiz.replace("3S momentum güçleniyor", "Momentum güçleniyor")
            satirlar.append("⚡ " + temiz)

    # Güçlenme notları boşsa veya eksikse, son tarama verisine göre tekrar üret.
    onceki = a.get("onceki_veri")
    if onceki:
        eski_hacim = onceki.get("hacim", a.get("hacim", 0))
        yeni_hacim = a.get("hacim", 0)

        if (
            eski_hacim
            and yeni_hacim >= eski_hacim * 1.20
            and not any("Hacim güçleniyor" in s for s in satirlar)
        ):
            satirlar.append(
                f"📈 Hacim güçleniyor: {round(eski_hacim, 2)}x → {round(yeni_hacim, 2)}x"
            )

        eski_momentum = onceki.get("degisim3", a.get("degisim3", 0))
        yeni_momentum = a.get("degisim3", 0)

        if (
            yeni_momentum - eski_momentum >= 0.5
            and not any("Momentum güçleniyor" in s for s in satirlar)
        ):
            satirlar.append(
                f"⚡ Momentum güçleniyor: %{round(eski_momentum, 2)} → %{round(yeni_momentum, 2)}"
            )

    return "\n".join(satirlar)


def lider_notu_olustur(a):
    lider = a.get("lider_skoru", 0)
    if lider >= 7:
        return "Lider grubunda"
    if lider >= 5:
        return "Lider takibe yakın"
    return "Henüz lider değil / takipçi olabilir"

def sure_yaz(saniye):
    dakika = int(saniye // 60)
    saat = dakika // 60
    kalan = dakika % 60

    if saat > 0:
        return f"{saat} saat {kalan} dk"
    return f"{dakika} dk"


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


def guclenme_bonusu_hesapla(symbol, genel_skor, hacim_kat, degisim3):
    """
    V4.25.8 Final.
    Mesajda görünmesini istediğimiz canlı güçlenme satırlarını üretir:
    - Hacim güçleniyor
    - Momentum güçleniyor

    Önce son taramadaki veriye bakar. Yoksa ilk tespite döner.
    Böylece sadece ilk tespitten değil, son taramadan bu yana güçlenen coinler de mesajda görünür.
    """
    referans = onceki_veriler.get(symbol) or ilk_tespitler.get(symbol)

    if referans is None:
        return 0, []

    bonus = 0
    notlar = []

    eski_skor = referans.get("skor", genel_skor)
    eski_hacim = referans.get("hacim", hacim_kat)
    eski_degisim3 = referans.get("degisim3", degisim3)

    # Skor bonusu arka planda kalsın; Telegram mesajında gösterilmeyecek.
    if genel_skor - eski_skor >= 2:
        bonus += 2
        notlar.append(f"Skor güçleniyor: {round(eski_skor, 2)} → {round(genel_skor, 2)}")

    # Telegram'da gösterilecek.
    if eski_hacim > 0 and hacim_kat >= eski_hacim * 1.20:
        bonus += 2
        notlar.append(f"Hacim güçleniyor: {round(eski_hacim, 2)}x → {round(hacim_kat, 2)}x")

    # Telegram'da gösterilecek.
    if degisim3 - eski_degisim3 >= 0.5:
        bonus += 2
        notlar.append(f"3s momentum güçleniyor: %{round(eski_degisim3, 2)} → %{round(degisim3, 2)}")

    return bonus, notlar

def stop_raporu_gonder():
    global stop_raporlari
    global son_stop_raporu

    simdi = time.time()

    if simdi - son_stop_raporu < STOP_RAPOR_SURESI:
        return

    if len(stop_raporlari) == 0:
        son_stop_raporu = simdi
        return

    mesaj = "📊 STOP RAPORU\n\n"

    for s in stop_raporlari:
        mesaj += (
            f"{s['durum']}\n"
            f"{s['symbol']} | %{round(s['sonuc'], 2)}\n"
            f"Süre: {s['sure']}\n\n"
        )

    # V4.30: STOP RAPORU Telegram'a gönderilmez.
    # Stop bilgileri basari_kayitlari içinde arka planda raporlar için tutulur.
    print("STOP raporu arka planda kaydedildi, Telegram'a gönderilmedi.")

    stop_raporlari = []
    son_stop_raporu = simdi


def haftalik_kayit_ekle(symbol, durum, skor, kalite_skoru, haber_skoru, hacim, degisim3):
    kategori_istatistikleri.setdefault(durum, {"toplam":0,"h1":0,"h2":0,"stop":0})
    kategori_istatistikleri[durum]["toplam"] += 1

    haftalik_kayitlar.append({
        "zaman": time.time(),
        "symbol": symbol,
        "durum": durum,
        "skor": skor,
        "kalite_skoru": kalite_skoru,
        "haber_skoru": haber_skoru,
        "hacim": hacim,
        "degisim3": degisim3
    })



def kategori_performans_raporu_olustur(kayitlar, gun=7):
    """Kategori bazlı H1/H2/Stop ve ortalama kazanç raporu üretir.

    Not:
    - Başarı DB'deki ilk sinyal kategorisini baz alır.
    - Son 7 gün varsayılan kullanılır; kayıt yoksa son 100 kayıtla devam eder.
    - H1/H2 sonrası stop görse bile başarı korunur; stop oranı ayrıca gösterilir.
    """
    if not kayitlar:
        return ""

    simdi = time.time()
    baslangic = simdi - gun * 24 * 60 * 60
    secilenler = [k for k in kayitlar if float(k.get("zaman", 0)) >= baslangic]

    # Bot yeni başladıysa veya DB'de zaman alanı eskiyse rapor boş kalmasın.
    if not secilenler:
        secilenler = kayitlar[-100:]

    kategoriler = {}

    for k in secilenler:
        kat = k.get("kategori") or k.get("durum") or "Bilinmeyen"
        if kat not in kategoriler:
            kategoriler[kat] = {
                "toplam": 0,
                "h1": 0,
                "h2": 0,
                "stop": 0,
                "aktif": 0,
                "kazanc_toplam": 0.0,
                "skor_toplam": 0.0,
                "kalite_toplam": 0.0,
                "hacim_toplam": 0.0,
                "son_kazanc_toplam": 0.0,
            }

        v = kategoriler[kat]
        v["toplam"] += 1

        if k.get("h1"):
            v["h1"] += 1
        if k.get("h2"):
            v["h2"] += 1
        if k.get("stop") and not k.get("h1") and not k.get("h2"):
            v["stop"] += 1
        if k.get("sonuc") == "aktif":
            v["aktif"] += 1

        v["kazanc_toplam"] += float(k.get("max_kazanc", 0) or 0)
        v["skor_toplam"] += float(k.get("skor", 0) or 0)
        v["kalite_toplam"] += float(k.get("kalite", 0) or 0)
        v["hacim_toplam"] += float(k.get("hacim", 0) or 0)
        v["son_kazanc_toplam"] += float(k.get("son_kazanc", k.get("max_kazanc", 0)) or 0)

    def yuzde(adet, toplam):
        return round(adet * 100 / max(toplam, 1), 1)

    sirali = sorted(
        kategoriler.items(),
        key=lambda item: (
            yuzde(item[1]["h2"], item[1]["toplam"]),
            yuzde(item[1]["h1"], item[1]["toplam"]),
            item[1]["toplam"],
        ),
        reverse=True,
    )

    mesaj = f"\n🎯 KATEGORİ PERFORMANS RAPORU ({gun} Gün)\n"

    for kat, v in sirali:
        toplam = max(v["toplam"], 1)
        mesaj += f"\n{kat}\n"
        mesaj += (
            f"Toplam: {v['toplam']} | "
            f"H1: {v['h1']} (%{yuzde(v['h1'], toplam)}) | "
            f"H2: {v['h2']} (%{yuzde(v['h2'], toplam)}) | "
            f"Stop: {v['stop']} (%{yuzde(v['stop'], toplam)})\n"
        )
        mesaj += (
            f"Ort. Max Kazanç: %{round(v['kazanc_toplam'] / toplam, 2)} | "
            f"Ort. Son Kazanç: %{round(v['son_kazanc_toplam'] / toplam, 2)} | "
            f"Ort. Skor: {round(v['skor_toplam'] / toplam, 2)} | "
            f"Ort. Kalite: {round(v['kalite_toplam'] / toplam, 2)} | "
            f"Ort. Hacim: {round(v['hacim_toplam'] / toplam, 2)}x\n"
        )

    return mesaj



def yildiz_oncesi_analiz_raporu_olustur(kayitlar, gun=7, yildiz_esik=30):
    """%30+ gidenleri (Yıldız profili) ve gitmeyenlerle farklarını analiz eder.
    Amaç: Yıldız olanı sonradan görmek değil, yıldız olmadan önceki ortak özellikleri bulmak.
    """
    if not kayitlar:
        return ""

    simdi = time.time()
    pencere = gun * 24 * 60 * 60

    # Zamanı olmayan eski kayıtlarda rapor boş kalmasın diye son 150 kayda düş.
    gunluk = [k for k in kayitlar if not k.get("zaman") or simdi - float(k.get("zaman", simdi)) <= pencere]
    if not gunluk:
        gunluk = kayitlar[-150:]

    yildizlar = [k for k in gunluk if float(k.get("max_kazanc", 0)) >= yildiz_esik]
    yildiz_olmayanlar = [
        k for k in gunluk
        if float(k.get("max_kazanc", 0)) < yildiz_esik and (k.get("h1") or k.get("h2") or k.get("stop") or float(k.get("max_kazanc", 0)) >= 3)
    ]

    def ort(liste, alan):
        if not liste:
            return 0
        return round(sum(float(k.get(alan, 0) or 0) for k in liste) / len(liste), 2)

    def oran(liste, alan):
        if not liste:
            return 0
        return round(sum(1 for k in liste if k.get(alan)) * 100 / len(liste), 1)

    def oran_hacim(liste, esik):
        if not liste:
            return 0
        return round(sum(1 for k in liste if float(k.get("hacim", 0) or 0) >= esik) * 100 / len(liste), 1)

    def oran_guclenme(liste):
        if not liste:
            return 0
        return round(sum(1 for k in liste if float(k.get("guclenme_bonus", 0) or 0) > 0) * 100 / len(liste), 1)

    def yakalama_dagilimi(liste):
        if not liste:
            return "Erken %0 | Normal %0 | Geç %0"
        erken = sum(1 for k in liste if k.get("yakalama_tipi") == "erken")
        normal = sum(1 for k in liste if k.get("yakalama_tipi") == "normal")
        gec = sum(1 for k in liste if k.get("yakalama_tipi") == "gec")
        toplam = max(len(liste), 1)
        return f"Erken %{round(erken*100/toplam,1)} | Normal %{round(normal*100/toplam,1)} | Geç %{round(gec*100/toplam,1)}"

    mesaj = f"\n⭐ YILDIZ ÖNCESİ ANALİZ ({gun} Gün)\n"
    mesaj += f"%{yildiz_esik}+ giden: {len(yildizlar)} | Karşılaştırma: {len(yildiz_olmayanlar)}\n"

    if not yildizlar:
        mesaj += "Henüz %30+ yıldız örneği yok. Veri biriktikçe analiz netleşecek.\n"
        return mesaj

    mesaj += "\nYıldızların ortak özellikleri:\n"
    mesaj += f"BTC Güçlü: %{oran(yildizlar, 'btc_guclu')}\n"
    mesaj += f"Lider: %{oran(yildizlar, 'lider_mi')}\n"
    mesaj += f"Zirve: %{oran(yildizlar, 'zirve_teyidi')}\n"
    mesaj += f"Haber: %{oran(yildizlar, 'haber_var')}\n"
    mesaj += f"Hacim >10x: %{oran_hacim(yildizlar, 10)} | Hacim >15x: %{oran_hacim(yildizlar, 15)}\n"
    mesaj += f"Güçlenme Bonusu Var: %{oran_guclenme(yildizlar)}\n"
    mesaj += f"İlk Sinyal Ort.: 1s %{ort(yildizlar,'degisim1')} | 3s %{ort(yildizlar,'degisim3')} | 24s %{ort(yildizlar,'degisim24')} | Hacim {ort(yildizlar,'hacim')}x\n"
    mesaj += f"Yakalama Tipi: {yakalama_dagilimi(yildizlar)}\n"

    if yildiz_olmayanlar:
        mesaj += "\nYıldız olmayanlarda aynı göstergeler:\n"
        mesaj += f"BTC Güçlü: %{oran(yildiz_olmayanlar, 'btc_guclu')} | Lider: %{oran(yildiz_olmayanlar, 'lider_mi')} | Zirve: %{oran(yildiz_olmayanlar, 'zirve_teyidi')}\n"
        mesaj += f"Hacim >10x: %{oran_hacim(yildiz_olmayanlar, 10)} | Güçlenme: %{oran_guclenme(yildiz_olmayanlar)}\n"
        mesaj += f"İlk Sinyal Ort.: 1s %{ort(yildiz_olmayanlar,'degisim1')} | 3s %{ort(yildiz_olmayanlar,'degisim3')} | 24s %{ort(yildiz_olmayanlar,'degisim24')} | Hacim {ort(yildiz_olmayanlar,'hacim')}x\n"

    # En güçlü yıldız kombinasyonunu sade şekilde çıkar.
    def komb(k):
        parca = []
        parca.append("BTC Güçlü" if k.get("btc_guclu") else "BTC Zayıf")
        parca.append("Lider" if k.get("lider_mi") else "Lider Yok")
        parca.append("Zirve" if k.get("zirve_teyidi") else "Zirve Yok")
        parca.append("Hacim>10x" if float(k.get("hacim", 0) or 0) >= 10 else "Hacim<10x")
        parca.append("Güçleniyor" if float(k.get("guclenme_bonus", 0) or 0) > 0 else "Güçlenme Yok")
        return " + ".join(parca)

    kombinasyonlar = {}
    for k in gunluk:
        ad = komb(k)
        if ad not in kombinasyonlar:
            kombinasyonlar[ad] = {"toplam": 0, "yildiz": 0}
        kombinasyonlar[ad]["toplam"] += 1
        if float(k.get("max_kazanc", 0) or 0) >= yildiz_esik:
            kombinasyonlar[ad]["yildiz"] += 1

    anlamli = [(ad, v) for ad, v in kombinasyonlar.items() if v["toplam"] >= 3]
    if anlamli:
        en_iyi_ad, en_iyi_v = max(anlamli, key=lambda item: (item[1]["yildiz"] / max(item[1]["toplam"], 1), item[1]["yildiz"]))
        oran_y = round(en_iyi_v["yildiz"] * 100 / max(en_iyi_v["toplam"], 1), 1)
        mesaj += "\n🏆 Yıldız Kombinasyonu\n"
        mesaj += f"{en_iyi_ad}\n"
        mesaj += f"Yıldız Oranı: %{oran_y} | Örnek: {en_iyi_v['toplam']}\n"

    en_buyuk = sorted(yildizlar, key=lambda k: float(k.get("max_kazanc", 0) or 0), reverse=True)[:5]
    if en_buyuk:
        mesaj += "\nEn büyük yıldızlar:\n"
        for k in en_buyuk:
            mesaj += f"{k.get('symbol')} +%{round(float(k.get('max_kazanc',0) or 0), 1)} | İlk 24s %{k.get('degisim24', 0)} | Hacim {k.get('hacim', 0)}x\n"

    return mesaj

def legacy_haftalik_rapor_gonder_v4():
    global son_haftalik_rapor
    global haftalik_kayitlar

    simdi = time.time()

    if simdi - son_haftalik_rapor < HAFTALIK_RAPOR_SURESI:
        return

    if len(haftalik_kayitlar) == 0:
        son_haftalik_rapor = simdi
        return

    kategori_sayilari = {}
    en_yuksek_skor = {}
    en_yuksek_hacim = None

    for k in haftalik_kayitlar:
        kategori_sayilari[k["durum"]] = kategori_sayilari.get(k["durum"], 0) + 1

        s = k["symbol"]
        if s not in en_yuksek_skor or k["skor"] > en_yuksek_skor[s]["skor"]:
            en_yuksek_skor[s] = k

        if en_yuksek_hacim is None or k["hacim"] > en_yuksek_hacim["hacim"]:
            en_yuksek_hacim = k

    en_iyi = sorted(en_yuksek_skor.values(), key=lambda x: x["skor"], reverse=True)[:5]

    mesaj = "🧬 COIN RADAR DNA RAPORU V4.28\n\n"
    mesaj += f"Toplam kayıt: {len(haftalik_kayitlar)}\n\n"

    mesaj += "Kategori Dağılımı:\n"
    for durum, adet in sorted(kategori_sayilari.items(), key=lambda x: x[1], reverse=True):
        mesaj += f"{durum}: {adet}\n"

    mesaj += "\n🏆 En Yüksek Skorlar:\n"
    for i, k in enumerate(en_iyi, start=1):
        mesaj += (
            f"{i}. {k['symbol']} | {k['durum']}\n"
            f"Skor: {round(k['skor'], 2)} | Kalite: {round(k['kalite_skoru'], 2)} | Haber: {k['haber_skoru']}\n"
        )

    if en_yuksek_hacim is not None:
        mesaj += (
            f"\n🚨 En Büyük Hacim:\n"
            f"{en_yuksek_hacim['symbol']} | {round(en_yuksek_hacim['hacim'], 2)}x\n"
        )

    
    if basari_kayitlari:
        son_kayitlar = basari_kayitlari[-100:]
        basarililar = [k for k in son_kayitlar if k.get("h1") or k.get("h2") or k.get("max_kazanc", 0) >= 3]
        basarisizlar = [k for k in son_kayitlar if k.get("stop") and not k.get("h1") and not k.get("h2")]

        def ortalama(liste, alan):
            if not liste:
                return 0
            return round(sum(float(k.get(alan, 0)) for k in liste) / len(liste), 2)

        mesaj += "\n🧠 ORTAK SİNYAL ANALİZİ\n"
        mesaj += f"Başarılı örnek: {len(basarililar)} | Başarısız örnek: {len(basarisizlar)}\n"

        if basarililar:
            mesaj += (
                "\nBaşarılı Ortalama:\n"
                f"Skor: {ortalama(basarililar, 'skor')} | "
                f"Kalite: {ortalama(basarililar, 'kalite')} | "
                f"Hacim: {ortalama(basarililar, 'hacim')}x | "
                f"Güçlenme: {ortalama(basarililar, 'guclenme_bonus')} | "
                f"BTC Fark: %{ortalama(basarililar, 'btc_fark')}\n"
            )

        if basarisizlar:
            mesaj += (
                "\nBaşarısız Ortalama:\n"
                f"Skor: {ortalama(basarisizlar, 'skor')} | "
                f"Kalite: {ortalama(basarisizlar, 'kalite')} | "
                f"Hacim: {ortalama(basarisizlar, 'hacim')}x | "
                f"Güçlenme: {ortalama(basarisizlar, 'guclenme_bonus')} | "
                f"BTC Fark: %{ortalama(basarisizlar, 'btc_fark')}\n"
            )

        def oran(liste, alan):
            if not liste:
                return 0
            return round(sum(1 for k in liste if k.get(alan)) * 100 / len(liste), 1)

        def kombinasyon_adi(k):
            parcaciklar = []
            if k.get("btc_guclu"):
                parcaciklar.append("BTC Güçlü")
            else:
                parcaciklar.append("BTC Zayıf")
            parcaciklar.append("Lider" if k.get("lider_mi") else "Lider Yok")
            parcaciklar.append("Hacim >10x" if k.get("hacim_10x") else "Hacim <10x")
            parcaciklar.append("Zirve Yakın" if k.get("zirve_teyidi") else "Zirve Zayıf")
            parcaciklar.append("Haber Var" if k.get("haber_var") else "Haber Yok")
            return " + ".join(parcaciklar)

        def basarili_mi(k):
            return bool(k.get("h1") or k.get("h2") or k.get("max_kazanc", 0) >= 3)

        h2_yapanlar = [k for k in son_kayitlar if k.get("h2")]
        if h2_yapanlar:
            mesaj += "\n🥇 H2 YAPANLARIN ORTAK ÖZELLİKLERİ\n"
            mesaj += f"BTC Güçlü: %{oran(h2_yapanlar, 'btc_guclu')}\n"
            mesaj += f"Lider: %{oran(h2_yapanlar, 'lider_mi')}\n"
            mesaj += f"Hacim >10x: %{oran(h2_yapanlar, 'hacim_10x')}\n"
            mesaj += f"Zirveye Yakın: %{oran(h2_yapanlar, 'zirve_teyidi')}\n"
            mesaj += f"Haber Desteği: %{oran(h2_yapanlar, 'haber_var')}\n"
            mesaj += f"Ort. Geç Pump Puanı: {ortalama(h2_yapanlar, 'gec_pump_puan')}\n"

        stop_olanlar = [k for k in son_kayitlar if k.get("stop") and not k.get("h1") and not k.get("h2")]
        if stop_olanlar:
            mesaj += "\n🚫 STOP OLANLARIN ORTAK ÖZELLİKLERİ\n"
            mesaj += f"BTC Güçlü: %{oran(stop_olanlar, 'btc_guclu')}\n"
            mesaj += f"Lider: %{oran(stop_olanlar, 'lider_mi')}\n"
            mesaj += f"Hacim >10x: %{oran(stop_olanlar, 'hacim_10x')}\n"
            mesaj += f"Zirveye Yakın: %{oran(stop_olanlar, 'zirve_teyidi')}\n"
            mesaj += f"Haber Desteği: %{oran(stop_olanlar, 'haber_var')}\n"
            mesaj += f"Ort. Geç Pump Puanı: {ortalama(stop_olanlar, 'gec_pump_puan')}\n"

        # V4.26.1 - İlk yakalama analizi: Bot coinleri erken mi, geç mi yakalıyor?
        # Bu bölüm ATM/FIDA gibi örneklerde, ilk mesaj anındaki 1s/3s/24s oranlarını karşılaştırır.
        if h2_yapanlar or stop_olanlar:
            mesaj += "\n⏱️ İLK YAKALAMA ANALİZİ\n"
            if h2_yapanlar:
                mesaj += (
                    "H2 ilk sinyal ort.: "
                    f"1s %{ortalama(h2_yapanlar, 'degisim1')} | "
                    f"3s %{ortalama(h2_yapanlar, 'degisim3')} | "
                    f"24s %{ortalama(h2_yapanlar, 'degisim24')} | "
                    f"Hacim {ortalama(h2_yapanlar, 'hacim')}x\n"
                )
            if stop_olanlar:
                mesaj += (
                    "STOP ilk sinyal ort.: "
                    f"1s %{ortalama(stop_olanlar, 'degisim1')} | "
                    f"3s %{ortalama(stop_olanlar, 'degisim3')} | "
                    f"24s %{ortalama(stop_olanlar, 'degisim24')} | "
                    f"Hacim {ortalama(stop_olanlar, 'hacim')}x\n"
                )
            mesaj += "Amaç: H2 yapanlar erken mi yakalandı, stop olanlar geç mi geldi görmek.\n"

        # V4.31 - Özellik / Hacim / Momentum başarı analizleri:
        # Amaç: Hangi özellik, hacim bandı ve momentum aralığı H2 başarısına daha çok katkı veriyor?
        def ozellik_basari_hesapla(ad, filtre_fn):
            ilgili = [k for k in son_kayitlar if filtre_fn(k)]
            if not ilgili:
                return {
                    "ad": ad,
                    "toplam": 0,
                    "basari": 0,
                    "h2": 0,
                    "basari_orani": 0,
                    "h2_orani": 0,
                    "veri_yok": True,
                }
            basarili = [k for k in ilgili if basarili_mi(k)]
            h2_ler = [k for k in ilgili if k.get("h2")]
            return {
                "ad": ad,
                "toplam": len(ilgili),
                "basari": len(basarili),
                "h2": len(h2_ler),
                "basari_orani": round(len(basarili) * 100 / max(len(ilgili), 1), 1),
                "h2_orani": round(len(h2_ler) * 100 / max(len(ilgili), 1), 1),
                "veri_yok": False,
            }

        def basari_satiri(sonuc):
            if sonuc.get("veri_yok"):
                return f"{sonuc['ad']}: veri yok\n"
            return (
                f"{sonuc['ad']}: Başarı %{sonuc['basari_orani']} | "
                f"H2 %{sonuc['h2_orani']} | Örnek {sonuc['toplam']}\n"
            )

        def aralik_basari_hesapla(ad, filtre_fn):
            return ozellik_basari_hesapla(ad, filtre_fn)

        if son_kayitlar:
            ozellik_sonuclari = [
                ozellik_basari_hesapla("BTC Güçlü", lambda k: bool(k.get("btc_guclu"))),
                ozellik_basari_hesapla("Lider", lambda k: bool(k.get("lider_mi"))),
                ozellik_basari_hesapla("Zirve", lambda k: bool(k.get("zirve_teyidi"))),
                ozellik_basari_hesapla("Hacim >10x", lambda k: bool(k.get("hacim_10x"))),
                ozellik_basari_hesapla("Hacim Güçleniyor", lambda k: bool(k.get("hacim_gucleniyor"))),
                ozellik_basari_hesapla("Momentum Güçleniyor", lambda k: bool(k.get("momentum_gucleniyor"))),
                ozellik_basari_hesapla("Haber Desteği", lambda k: bool(k.get("haber_var"))),
            ]

            mesaj += "\n🏆 ÖZELLİK BAŞARI TABLOSU\n"
            for sonuc in ozellik_sonuclari:
                mesaj += basari_satiri(sonuc)

            # En başarılı özellikler: ikinci raporda hızlı yorum için H2 oranına göre sıralı özet.
            anlamli_ozellikler = [s for s in ozellik_sonuclari if not s.get("veri_yok") and s.get("toplam", 0) >= 3]
            if anlamli_ozellikler:
                sirali_ozellikler = sorted(
                    anlamli_ozellikler,
                    key=lambda s: (s["h2_orani"], s["basari_orani"], s["toplam"]),
                    reverse=True,
                )
                mesaj += "\n🥇 EN BAŞARILI ÖZELLİKLER\n"
                for i, s in enumerate(sirali_ozellikler[:5], 1):
                    mesaj += (
                        f"{i}. {s['ad']} | H2 %{s['h2_orani']} | "
                        f"Başarı %{s['basari_orani']} | Örnek {s['toplam']}\n"
                    )

            # Hacim bandı analizi: Roket/Elit eşiklerini veriyle ayarlamak için.
            hacim_bantlari = [
                ("0-2x", lambda k: 0 <= float(k.get("hacim", 0) or 0) < 2),
                ("2-5x", lambda k: 2 <= float(k.get("hacim", 0) or 0) < 5),
                ("5-10x", lambda k: 5 <= float(k.get("hacim", 0) or 0) < 10),
                ("10x+", lambda k: float(k.get("hacim", 0) or 0) >= 10),
            ]
            mesaj += "\n📊 HACİM BAŞARI ANALİZİ\n"
            for ad, fn in hacim_bantlari:
                mesaj += basari_satiri(aralik_basari_hesapla(ad, fn))

            # Momentum bandı analizi: 3s momentumun hangi aralıkta daha çok H2 ürettiğini görür.
            momentum_bantlari = [
                ("0-2%", lambda k: 0 <= float(k.get("degisim3", 0) or 0) < 2),
                ("2-4%", lambda k: 2 <= float(k.get("degisim3", 0) or 0) < 4),
                ("4-6%", lambda k: 4 <= float(k.get("degisim3", 0) or 0) < 6),
                ("6%+", lambda k: float(k.get("degisim3", 0) or 0) >= 6),
            ]
            mesaj += "\n⚡ MOMENTUM BAŞARI ANALİZİ\n"
            for ad, fn in momentum_bantlari:
                mesaj += basari_satiri(aralik_basari_hesapla(ad, fn))

        kombinasyonlar = {}
        for k in son_kayitlar:
            ad = kombinasyon_adi(k)
            if ad not in kombinasyonlar:
                kombinasyonlar[ad] = {"toplam": 0, "basarili": 0, "h2": 0}
            kombinasyonlar[ad]["toplam"] += 1
            if basarili_mi(k):
                kombinasyonlar[ad]["basarili"] += 1
            if k.get("h2"):
                kombinasyonlar[ad]["h2"] += 1

        anlamli_kombinasyonlar = [
            (ad, v) for ad, v in kombinasyonlar.items()
            if v["toplam"] >= 3
        ]
        if anlamli_kombinasyonlar:
            en_iyi_ad, en_iyi_v = max(
                anlamli_kombinasyonlar,
                key=lambda item: (item[1]["basarili"] / max(item[1]["toplam"], 1), item[1]["h2"], item[1]["toplam"])
            )
            basari_orani = round(en_iyi_v["basarili"] * 100 / max(en_iyi_v["toplam"], 1), 1)
            h2_orani = round(en_iyi_v["h2"] * 100 / max(en_iyi_v["toplam"], 1), 1)
            mesaj += "\n🏆 EN BAŞARILI KOMBİNASYON\n"
            mesaj += f"{en_iyi_ad}\n"
            mesaj += f"Başarı Oranı: %{basari_orani} | H2: %{h2_orani}\n"
            mesaj += f"Örnek Sayısı: {en_iyi_v['toplam']}\n"

            en_kotu_ad, en_kotu_v = min(
                anlamli_kombinasyonlar,
                key=lambda item: (item[1]["basarili"] / max(item[1]["toplam"], 1), -item[1]["toplam"])
            )
            kotu_oran = round(en_kotu_v["basarili"] * 100 / max(en_kotu_v["toplam"], 1), 1)
            mesaj += "\n⚠️ EN ZAYIF KOMBİNASYON\n"
            mesaj += f"{en_kotu_ad}\n"
            mesaj += f"Başarı Oranı: %{kotu_oran} | Örnek: {en_kotu_v['toplam']}\n"


    if h1_kayitlari:
        mesaj += "\n🏆 EN HIZLI H1\n"
        for i,k in enumerate(sorted(h1_kayitlari,key=lambda x:x["sure"])[:5],1):
            mesaj += f"{i}. {k['symbol']} | {sure_yaz(k['sure'])}\n"

    mesaj += yildiz_oncesi_analiz_raporu_olustur(basari_kayitlari, gun=7, yildiz_esik=30)

    mesaj += kategori_performans_raporu_olustur(basari_kayitlari, gun=7)

    if h2_kayitlari:
        mesaj += "\n🏆 EN HIZLI H2\n"
        for i,k in enumerate(sorted(h2_kayitlari,key=lambda x:x["sure"])[:5],1):
            mesaj += f"{i}. {k['symbol']} | {sure_yaz(k['sure'])}\n"

    mesaj += piyasa_kacirilan_raporu_olustur()

    telegram_gonder(mesaj)
    print(mesaj)

    # Piyasa verilerini rapordan sonra da sakla; son 7 gün korunur.
    piyasa_db_kaydet(piyasa_kayitlari)

    haftalik_kayitlar = []
    h1_kayitlari.clear()
    h2_kayitlari.clear()
    kategori_istatistikleri.clear()
    son_haftalik_rapor = simdi


def hedef_stop_kontrol():
    kapanacaklar = []

    for symbol, s in list(aktif_sinyaller.items()):
        fiyat = anlik_fiyat(symbol)

        if fiyat is None:
            continue

        giris = s["giris"]
        kazanc = ((fiyat - giris) / giris) * 100
        gecen_sure = sure_yaz(time.time() - s["zaman"])

        # V4.22: Başarı veritabanı için maksimum kazanç sürekli güncellenir.
        basari_kaydi_guncelle(symbol, fiyat, durum=s.get("durum"))

        if not s["stop_bildi"] and fiyat <= s["stop"]:
            stop_raporlari.append({
                "symbol": symbol,
                "durum": s["durum"],
                "sonuc": kazanc,
                "sure": gecen_sure
            })

            print(f"STOP RAPORA EKLENDİ: {symbol} {round(kazanc, 2)}%")

            kategori_istatistikleri.setdefault(s["durum"], {"toplam":0,"h1":0,"h2":0,"stop":0})
            kategori_istatistikleri[s["durum"]]["stop"] = kategori_istatistikleri[s["durum"]].get("stop", 0) + 1

            basari_kaydi_guncelle(symbol, fiyat, stop=True)

            s["stop_bildi"] = True
            kapanacaklar.append(symbol)
            continue

        # V4.15: Sinyal oluştuğu andan itibaren zirve takibi.
        # H1 beklemez. Fiyat yükseldikçe zirve güncellenir.
        onceki_zirve = s.get("zirve_fiyat") or giris

        if fiyat > onceki_zirve:
            s["zirve_fiyat"] = fiyat
            onceki_zirve = fiyat

        geri_cekilme = ((fiyat - onceki_zirve) / onceki_zirve) * 100 if onceki_zirve else 0

        if not s.get("guc_kaybi_bildi", False) and fiyat <= onceki_zirve * 0.985:
            mesaj = (
                f"⚠️ GÜÇ KAYBEDİYOR\n\n"
                f"Coin: {symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Zirve: {round(onceki_zirve, 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Zirveden geri çekilme: %{round(abs(geri_cekilme), 2)}\n"
                f"Süre: {gecen_sure}\n\n"
                f"Not: Sinyal sonrası güç zayıflıyor olabilir."
            )
            # sessiz kayit
            s["guc_kaybi_bildi"] = True

        if not s.get("momentum_cokusu_bildi", False) and fiyat <= onceki_zirve * 0.97:
            mesaj = (
                f"🚨 MOMENTUM ÇÖKÜYOR\n\n"
                f"Coin: {symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Zirve: {round(onceki_zirve, 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Zirveden geri çekilme: %{round(abs(geri_cekilme), 2)}\n"
                f"Süre: {gecen_sure}\n\n"
                f"Not: Sinyal sonrası güç kaybı derinleşti."
            )
            # sessiz kayit
            s["momentum_cokusu_bildi"] = True

        if not s["hedef1_bildi"] and fiyat >= s["hedef1"]:
            s["hedef1_bildi"] = True

            mesaj = (
                f"✅ HEDEF 1 GELDİ\n\n"
                f"Coin: {symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Hedef 1: {round(s['hedef1'], 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Kazanç: %{round(kazanc, 2)}\n"
                f"Süre: {gecen_sure}"
            )
            telegram_gonder(mesaj)
            print(mesaj)

            kategori_istatistikleri.setdefault(s["durum"], {"toplam":0,"h1":0,"h2":0,"stop":0})
            kategori_istatistikleri[s["durum"]]["h1"] += 1

            h1_kayitlari.append({
                "symbol": symbol,
                "sure": time.time() - s["zaman"]
            })

            basari_kaydi_guncelle(symbol, fiyat, h1=True)


        if not s["hedef2_bildi"] and fiyat >= s["hedef2"]:
            mesaj = (
                f"🚀 HEDEF 2 GELDİ\n\n"
                f"Coin: {symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Hedef 2: {round(s['hedef2'], 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Kazanç: %{round(kazanc, 2)}\n"
                f"Süre: {gecen_sure}"
            )
            telegram_gonder(mesaj)
            print(mesaj)

            kategori_istatistikleri.setdefault(s["durum"], {"toplam":0,"h1":0,"h2":0,"stop":0})
            kategori_istatistikleri[s["durum"]]["h2"] += 1

            h2_kayitlari.append({
                "symbol": symbol,
                "sure": time.time() - s["zaman"]
            })

            basari_kaydi_guncelle(symbol, fiyat, h2=True)

            s["hedef2_bildi"] = True
            kapanacaklar.append(symbol)

        # V4.28: 72 saat sonunda hâlâ hedef/stop yoksa açık sinyali arka planda kapat.
        if time.time() - s["zaman"] > SINYALE_GORE_TAKIP_SAATI * 3600:
            mesaj = (
                f"⏳ SİNYAL TAKİP KAPANDI\n\n"
                f"Coin: {symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Sonuç: %{round(kazanc, 2)}\n"
                f"Süre: {gecen_sure}\n\n"
                f"Not: 72 saat içinde H1/H2/Stop netleşmedi. Rapor için max kazanç kaydedildi."
            )
            print(mesaj)
            kapanacaklar.append(symbol)
            continue

    for symbol in kapanacaklar:
        aktif_sinyaller.pop(symbol, None)


def mikro_basamak_hesapla(o, h, l, c, v):
    """V5.4.2 erken roket formasyonu.

    Son saatlik mumlarda 2-3 kısa mumun basamak şeklinde yukarı taşınmasını ölçer.
    Büyük patlama mumunu beklemek yerine, patlama öncesi sıkışma + yukarı taşıma +
    hacim ivmesini puanlar. Yalnızca mevcut/geçmiş mum kullanır.
    """
    try:
        n = min(len(o), len(h), len(l), len(c), len(v))
        if n < 10:
            return 0, False, {"mum_sayisi": 0, "hacim_ivmesi": 1.0, "neden": "yetersiz veri"}

        oo = [float(x) for x in o[-12:]]
        hh = [float(x) for x in h[-12:]]
        ll = [float(x) for x in l[-12:]]
        cc = [float(x) for x in c[-12:]]
        vv = [float(x) for x in v[-12:]]
        m = len(cc)

        # Son 8 mumun tipik gövdesi: "kısa mum" için coine göre adaptif referans.
        body_pct = []
        for i in range(max(0, m - 9), m - 1):
            base = abs(oo[i]) if oo[i] else abs(cc[i])
            if base > 0:
                body_pct.append(abs(cc[i] - oo[i]) / base * 100.0)
        body_ref = sorted(body_pct)[len(body_pct)//2] if body_pct else 0.6
        kisa_esik = max(0.22, min(1.35, body_ref * 1.35))

        best = {"skor": 0, "mum_sayisi": 0, "hacim_ivmesi": 1.0, "kisa_esik": kisa_esik}

        # 2 veya 3 mumluk diziyi, son 4 mum içinde ara. Böylece mevcut saatlik mum
        # henüz tamamlanmadan da basamak yapısı görülebilir.
        for adet in (3, 2):
            for end in range(m - 1, max(adet - 2, m - 5), -1):
                start = end - adet + 1
                if start < 0:
                    continue
                idx = list(range(start, end + 1))

                govdeler = []
                kisa = True
                for i in idx:
                    base = abs(oo[i]) if oo[i] else abs(cc[i])
                    bp = abs(cc[i] - oo[i]) / base * 100.0 if base > 0 else 99
                    govdeler.append(bp)
                    if bp > kisa_esik:
                        kisa = False
                        break
                if not kisa:
                    continue

                # "Birbirini geçme": kapanışlar ve tepeler basamak şeklinde yukarı.
                kapanis_yukari = all(cc[b] > cc[a] for a, b in zip(idx, idx[1:]))
                tepe_yukari = all(hh[b] >= hh[a] for a, b in zip(idx, idx[1:]))
                dip_korunuyor = all(ll[b] >= ll[a] * 0.997 for a, b in zip(idx, idx[1:]))
                if not (kapanis_yukari and tepe_yukari and dip_korunuyor):
                    continue

                # Seri toplamda pozitif olmalı ama henüz patlama kadar uzamış olmamalı.
                ilk = cc[idx[0]-1] if idx[0] > 0 else oo[idx[0]]
                seri_getiri = ((cc[idx[-1]] / ilk) - 1.0) * 100.0 if ilk > 0 else 0.0
                if seri_getiri <= 0 or seri_getiri > 4.5:
                    continue

                # Hacim: 5x şartı değil, seri içinde kademeli artış / son mumun öncekiye göre açılması.
                vol_seq = [max(vv[i], 0.0) for i in idx]
                hacim_artiyor = sum(1 for a, b in zip(vol_seq, vol_seq[1:]) if b >= a * 0.92)
                first_v = max(vol_seq[0], 1e-12)
                hacim_ivmesi = vol_seq[-1] / first_v

                puan = 0
                puan += 38 if adet == 3 else 28
                puan += 18 if kapanis_yukari else 0
                puan += 12 if tepe_yukari else 0
                puan += 8 if dip_korunuyor else 0
                if hacim_artiyor >= adet - 1:
                    puan += 12
                elif hacim_ivmesi >= 1.15:
                    puan += 8
                if 0.20 <= seri_getiri <= 2.80:
                    puan += 10
                elif seri_getiri <= 4.0:
                    puan += 5

                puan = int(max(0, min(100, puan)))
                if puan > best["skor"]:
                    best = {
                        "skor": puan,
                        "mum_sayisi": adet,
                        "hacim_ivmesi": round(hacim_ivmesi, 3),
                        "seri_getiri": round(seri_getiri, 3),
                        "ort_govde": round(sum(govdeler)/len(govdeler), 3),
                        "kisa_esik": round(kisa_esik, 3),
                        "son_index": end,
                    }

        uygun = best.get("skor", 0) >= MIKRO_BASAMAK_MIN_SKOR
        return best.get("skor", 0), bool(uygun), best
    except Exception as e:
        print("Mikro basamak hesap hatası:", e)
        return 0, False, {"mum_sayisi": 0, "hacim_ivmesi": 1.0, "neden": str(e)}




def al_assistant_guclenen_aday_hesapla(
    symbol, hacim_kat, degisim1, degisim3, btcden_guclu, lider_skoru,
    mikro_basamak=False, hacim_gucleniyor=False, momentum_gucleniyor=False
):
    """
    V5.5.0 - Son AL Assistant'taki Çoklu Güç Havuzu yaklaşımının Radar uyarlaması.

    Fark: İlk güçlü görüntüde mesaj yok. Coin önce güç havuzuna alınır.
    En az bir sonraki taramada hacim/momentum/BTC/liderlik tarafında gücünü
    koruyup artırırsa GÜÇLENEN ADAY onayı alır. Böylece anlık 20-25 aday yağmuru
    yerine gerçekten devam eden hazırlıklar Roket Adayı olur.
    """
    simdi = time.time()

    # Süresi dolan kayıtları hafifçe temizle.
    for _sym, _st in list(al_assistant_guc_havuzu.items()):
        if simdi - float(_st.get("son_zaman", simdi)) > AL_GUC_HAVUZU_SURESI:
            al_assistant_guc_havuzu.pop(_sym, None)

    positive_momentum = (degisim1 >= 0.20) or (degisim3 >= 0.60)
    hacim_canli = hacim_kat >= 1.50
    liderlik = lider_skoru >= 4

    # İlk havuz kapısı: gevşek ama mesaj üretmez. AL Assistant'taki gibi izleme amacı taşır.
    ilk_teyit = sum([
        bool(positive_momentum),
        bool(hacim_canli or hacim_gucleniyor),
        bool(btcden_guclu),
        bool(liderlik),
        bool(momentum_gucleniyor),
        bool(mikro_basamak),
    ])
    havuza_girebilir = (
        positive_momentum
        and degisim3 >= 0.50
        and hacim_kat >= 1.35
        and degisim1 > -0.20
        and ilk_teyit >= 3
    )

    state = al_assistant_guc_havuzu.get(symbol)
    if state is None:
        if havuza_girebilir:
            al_assistant_guc_havuzu[symbol] = {
                "ilk_zaman": simdi, "son_zaman": simdi,
                "hacim": hacim_kat, "degisim1": degisim1, "degisim3": degisim3,
                "lider": lider_skoru, "btc_guclu": bool(btcden_guclu),
                "gorulme": 1,
            }
        return False, 0.0, ilk_teyit, "HAVUZA_ALINDI" if havuza_girebilir else "IZLEME"

    yas = simdi - float(state.get("ilk_zaman", simdi))
    onceki_hacim = float(state.get("hacim", hacim_kat) or hacim_kat)
    onceki_m3 = float(state.get("degisim3", degisim3) or degisim3)
    onceki_lider = float(state.get("lider", lider_skoru) or lider_skoru)

    # AL Assistant'ın taramalar arası güçlenme fikri: sadece mevcut seviye değil yön önemli.
    havuz_hacim_guclu = hacim_gucleniyor or (onceki_hacim > 0 and hacim_kat >= onceki_hacim * 1.10)
    havuz_momentum_guclu = momentum_gucleniyor or (degisim3 >= onceki_m3 + 0.20)
    havuz_lider_guclu = lider_skoru >= max(4, onceki_lider)
    momentum_korundu = degisim3 >= max(0.60, onceki_m3 - 0.15) and degisim1 > -0.10

    # Assistant benzeri kalite skoru: momentum ve devam yönü hacimden daha ağır.
    score = 0.0
    if degisim1 >= 0.80: score += 12
    elif degisim1 >= 0.25: score += 8
    if degisim3 >= 2.00: score += 20
    elif degisim3 >= 1.00: score += 15
    elif degisim3 >= 0.60: score += 10
    if havuz_momentum_guclu: score += 16
    if 1.5 <= hacim_kat < 3: score += 8
    elif 3 <= hacim_kat < 8: score += 12
    elif hacim_kat >= 8: score += 8
    if havuz_hacim_guclu: score += 12
    if btcden_guclu: score += 10
    if lider_skoru >= 7: score += 10
    elif lider_skoru >= 5: score += 7
    elif lider_skoru >= 4: score += 4
    if mikro_basamak: score += 4
    if not momentum_korundu: score -= 20
    if hacim_kat >= 8 and degisim3 < 0.70: score -= 20
    score = round(max(0.0, min(100.0, score)), 1)

    confirmation_count = sum([
        bool(momentum_korundu),
        bool(hacim_kat >= 1.50),
        bool(havuz_hacim_guclu),
        bool(havuz_momentum_guclu),
        bool(btcden_guclu),
        bool(lider_skoru >= 4),
        bool(mikro_basamak),
    ])

    # Kritik kalite farkı: 60+ devam gücü kategori_belirle'de ayrıca zorunlu.
    # Burada ise mutlaka en az bir GERÇEK güçlenme ve 2. gözlem istenir.
    guclenme_yonu = havuz_hacim_guclu or havuz_momentum_guclu
    guclenen_aday = (
        yas >= AL_GUC_HAVUZU_MIN_BEKLEME
        and int(state.get("gorulme", 1)) >= 1
        and momentum_korundu
        and btcden_guclu
        and lider_skoru >= 4
        and hacim_kat >= 1.50
        and guclenme_yonu
        and score >= 72
        and confirmation_count >= 5
        and not (hacim_kat >= 8 and degisim3 < 0.70)
    )

    # Havuzu güncelle; güç kaybında kayıt kısa sürede doğal olarak söner.
    if havuza_girebilir or guclenen_aday:
        state.update({
            "son_zaman": simdi, "hacim": hacim_kat, "degisim1": degisim1,
            "degisim3": degisim3, "lider": lider_skoru,
            "btc_guclu": bool(btcden_guclu), "gorulme": int(state.get("gorulme", 1)) + 1,
        })
        al_assistant_guc_havuzu[symbol] = state
    elif not momentum_korundu or degisim3 < 0.30:
        al_assistant_guc_havuzu.pop(symbol, None)

    return guclenen_aday, score, confirmation_count, "GUCLENEN_ADAY" if guclenen_aday else "HAVUZDA"


# -----------------------------------------------------------------------------
# V5.5.1 - main_13_coklu_guc_havuzu.py kalite kapısı
# Roket Adayı, güç havuzundan çıkmakla yetinmez. main_13'te Telegram'a yalnızca
# gerçek AL teknik teyidi geçen coinler düştüğü için aynı kalite kapısı burada da
# Roket Adayı seviyesine uygulanır: EMA trendi + RSI + MACD + ADX + AI skoru.
# -----------------------------------------------------------------------------
MAIN13_ADAY_AI_MIN = 80.0
MAIN13_ADAY_ADX_MIN = 30.0
MAIN13_ADAY_RSI_MIN = 48.0
MAIN13_ADAY_RSI_MAX = 70.0
main13_teknik_cache = {}
MAIN13_TEKNIK_CACHE_SURESI = 55


def _main13_ema(veriler, periyot):
    if len(veriler) < periyot:
        return None
    ema = sum(veriler[:periyot]) / periyot
    k = 2 / (periyot + 1)
    for fiyat in veriler[periyot:]:
        ema = fiyat * k + ema * (1 - k)
    return ema


def _main13_ema_serisi(veriler, periyot):
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


def _main13_rsi(kapanislar, periyot=14):
    if len(kapanislar) < periyot + 1:
        return None
    farklar = [kapanislar[i] - kapanislar[i - 1] for i in range(1, len(kapanislar))]
    kazanclar = [max(x, 0) for x in farklar]
    kayiplar = [max(-x, 0) for x in farklar]
    ort_kazanc = sum(kazanclar[:periyot]) / periyot
    ort_kayip = sum(kayiplar[:periyot]) / periyot
    for i in range(periyot, len(farklar)):
        ort_kazanc = ((ort_kazanc * (periyot - 1)) + kazanclar[i]) / periyot
        ort_kayip = ((ort_kayip * (periyot - 1)) + kayiplar[i] / 1) / periyot
    if ort_kayip == 0:
        return 100.0
    rs = ort_kazanc / ort_kayip
    return 100 - (100 / (1 + rs))


def _main13_macd(kapanislar):
    ema12 = _main13_ema_serisi(kapanislar, 12)
    ema26 = _main13_ema_serisi(kapanislar, 26)
    if not ema12 or not ema26:
        return None, None, None
    macd_seri = []
    for i in range(len(kapanislar)):
        if i < len(ema12) and i < len(ema26) and ema12[i] is not None and ema26[i] is not None:
            macd_seri.append(ema12[i] - ema26[i])
    if len(macd_seri) < 9:
        return None, None, None
    sinyal = _main13_ema(macd_seri, 9)
    macd = macd_seri[-1]
    histogram = macd - sinyal if sinyal is not None else None
    return macd, sinyal, histogram


def _main13_atr_adx(yuksekler, dusukler, kapanislar, periyot=14):
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


def _main13_teknik_getir(symbol):
    simdi = time.time()
    cache = main13_teknik_cache.get(symbol)
    if cache and simdi - cache.get("zaman", 0) <= MAIN13_TEKNIK_CACHE_SURESI:
        return cache.get("veri")
    try:
        d = veri_getir(symbol, 120)
        c = [float(x) for x in d.get("c", [])]
        h = [float(x) for x in d.get("h", [])]
        l = [float(x) for x in (d.get("l") or [])]
        if len(c) < 55 or len(h) != len(c) or len(l) != len(c):
            return None
        ema20 = _main13_ema(c, 20)
        ema50 = _main13_ema(c, 50)
        rsi = _main13_rsi(c, 14)
        _, _, macd_hist = _main13_macd(c)
        atr, adx = _main13_atr_adx(h, l, c, 14)
        atr_yuzde = (atr / c[-1] * 100) if atr is not None and c[-1] else None
        veri = {
            "fiyat": c[-1], "ema20": ema20, "ema50": ema50, "rsi": rsi,
            "macd_hist": macd_hist, "adx": adx, "atr_yuzde": atr_yuzde,
        }
        main13_teknik_cache[symbol] = {"zaman": simdi, "veri": veri}
        return veri
    except Exception as e:
        print(f"MAIN13 teknik hata {symbol}: {e}")
        return None


def main13_roket_adayi_teknik_onayi(symbol, radar_skoru, lider_skoru, btcden_guclu, degisim1, degisim3, degisim24):
    """main_13 AI karar motorunun erken/kaliteli AL kapısını Roket Adayı için uygular."""
    teknik = _main13_teknik_getir(symbol)
    if not teknik:
        return False, 0.0, {"neden": "teknik veri yetersiz"}

    fiyat = teknik.get("fiyat") or 0
    ema20 = teknik.get("ema20")
    ema50 = teknik.get("ema50")
    rsi = teknik.get("rsi")
    macd_hist = teknik.get("macd_hist")
    adx = teknik.get("adx")
    atr_yuzde = teknik.get("atr_yuzde")

    skor = 20.0
    skor += max(0, min((radar_skoru - 55) * 0.50, 20))

    ema_yukari = bool(ema20 is not None and ema50 is not None and ema20 > ema50 and fiyat > ema20)
    if ema20 is not None and ema50 is not None:
        skor += 12 if ema20 > ema50 else -8
        if fiyat and ema20:
            skor += 4 if fiyat > ema20 else -5

    if rsi is not None:
        if 50 <= rsi <= 65: skor += 12
        elif 45 <= rsi < 50: skor += 5
        elif 65 < rsi <= 72: skor += 6
        elif 72 < rsi <= 78: skor += 1
        elif 78 < rsi <= 85: skor -= 7
        elif rsi > 85: skor -= 12
        elif rsi < 40: skor -= 10

    macd_pozitif = macd_hist is not None and macd_hist > 0
    if macd_hist is not None:
        skor += 12 if macd_pozitif else -14

    if adx is not None:
        if adx >= 40: skor += 18
        elif adx >= 30: skor += 14
        elif adx >= 25: skor += 9
        elif adx >= 20: skor += 3
        else: skor -= 8

    if atr_yuzde is not None:
        if 1 <= atr_yuzde <= 4.5: skor += 5
        elif atr_yuzde > 7: skor -= 10
        elif atr_yuzde > 5: skor -= 5

    if btcden_guclu: skor += 4
    if lider_skoru >= 7: skor += 5
    elif lider_skoru >= 5: skor += 2

    if 1 <= degisim1 <= 4: skor += 5
    elif 4 < degisim1 <= 8: skor += 2
    elif degisim1 > 8: skor -= 4

    if 3 <= degisim3 <= 8: skor += 7
    elif 8 < degisim3 <= 15: skor += 4
    elif degisim3 > 15: skor += 1
    if degisim24 > 30: skor -= 5

    if adx is not None:
        if adx < 20: skor = min(skor, 74)
        elif adx < 25: skor = min(skor, 82)
        elif adx < 30: skor = min(skor, 90)

    skor = round(max(0, min(skor, 100)), 1)

    # main_13'te erken aday için kullanılan en seçici teknik kapı.
    onay = (
        ema_yukari
        and rsi is not None and MAIN13_ADAY_RSI_MIN <= rsi <= MAIN13_ADAY_RSI_MAX
        and macd_pozitif
        and adx is not None and adx >= MAIN13_ADAY_ADX_MIN
        and skor >= MAIN13_ADAY_AI_MIN
    )
    return onay, skor, {
        "ema_ok": ema_yukari,
        "rsi": None if rsi is None else round(rsi, 1),
        "macd_ok": macd_pozitif,
        "adx": None if adx is None else round(adx, 1),
        "ai_skor": skor,
    }


def kategori_belirle(symbol, genel_skor, kalite_skoru, hacim_kat, haber_skoru, btcden_guclu, btc_fark, degisim1, degisim3, degisim24, zirve_yakin, guclenme_bonus=0, btc_guc_skoru=0, lider_skoru=0, guc_skoru=0, yeni_zirve=False, mikro_basamak=False, mikro_basamak_skor=0, mikro_hacim_ivmesi=1.0, hizli_lider_rank=0, hizli_fiyat_ivme=0.0, hizli_hacim_ivme=0.0, hacim_gucleniyor=False, momentum_gucleniyor=False, devam_gucu=0):
    """
    V4.25 kategori mantığı.

    Telegram sadeleşti:
    - 📊 TRADER HACİM
    - 🚀 Roket Adayı (erken hazırlık)
    - 🚀 Roket (hacim + momentum doğrulandı)
    - 🔥 Elit Roket (en güçlü hacim + liderlik)
    - ⭐ Yıldız

    İzleme ve Güçlü Hacim arka planda kalır; Telegram'a gönderilmez.
    Geç Pump kategori değildir; yalnızca DNA raporunda risk puanı olarak tutulur.
    """

    # V5.4.6 DEVAM TEYİDİ
    # Üst kategorilerde yalnızca anlık yüksek hacim değil, hareketin devam edip etmediği de aranır.
    # Roket: en az bir güçlenme bayrağı + yeterli devam gücü.
    # Elit: iki güçlenme birlikte veya çok güçlü devam + çok güçlü liderlik.
    roket_devam_onayi = (
        devam_gucu >= 60
        and (hacim_gucleniyor or momentum_gucleniyor)
    )
    elit_devam_onayi = (
        devam_gucu >= 70
        and (
            (hacim_gucleniyor and momentum_gucleniyor)
            or (devam_gucu >= 78 and lider_skoru >= 7)
        )
    )

    # 1) ⭐ YILDIZ - en seçici seviye
    if (
        guc_skoru >= 88
        and lider_skoru >= 7
        and btc_guc_skoru >= 7
        and kalite_skoru >= 14
        and hacim_kat >= 5
        and degisim1 > 1
        and degisim3 >= 4
        and zirve_yakin
    ):
        return "⭐ Yıldız", "En güçlü lider aday"

    # 2) 🔥 ELİT ROKET - Roket Adayı'ndan daha güçlü hacim teyidi ister
    if (
        guc_skoru >= 74
        and lider_skoru >= 5
        and btc_guc_skoru >= 5
        and kalite_skoru >= 10
        and hacim_kat >= 8
        and degisim1 > 0
        and degisim3 >= 3
        and btcden_guclu
        and elit_devam_onayi
    ):
        return "🔥 Elit Roket", "Hacim + momentum + liderlik + devam gücü"

    # 3) 📊 TRADER HACİM - 15x+ hacim özel sinyali
    # Not: Roket Adayı'ndan önce kontrol edilir; yoksa 15x+ hacimli adaylar
    # çoğu zaman Roket Adayı olarak etiketlenip Trader Hacim hiç görünmez.
    if (
        guc_skoru >= 55
        and hacim_kat >= 15
        and btcden_guclu
        and btc_guc_skoru >= 4
        and degisim3 >= 6
    ):
        if zirve_yakin or yeni_zirve:
            return "📊 TRADER HACİM", "15x+ hacim + BTC gücü + zirve teyidi"
        return "📊 TRADER HACİM", "15x+ hacim + BTC gücü"

    # 4) 🚀 ROKET ADAYI - main_13 Çoklu Güç Havuzu + gerçek AL teknik kapısı.
    # Artık mikro-basamak tek başına kapı değildir ve zorunlu da değildir.
    # İlk görüntü mesaj üretmez; güç havuzu onayından sonra EMA+RSI+MACD+ADX+AI>=80 teknik kapısı da gerekir.
    # Radar teyitleri: hacim/hacim güçlenmesi, BTC üstünlüğü, liderlik,
    # momentum güçlenmesi ve mikro basamak. Devam Gücü >=60 ayrıca korunur.
    guclenen_aday, assistant_aday_skoru, assistant_teyit, assistant_havuz_durumu = al_assistant_guclenen_aday_hesapla(
        symbol=symbol,
        hacim_kat=hacim_kat,
        degisim1=degisim1,
        degisim3=degisim3,
        btcden_guclu=btcden_guclu,
        lider_skoru=lider_skoru,
        mikro_basamak=mikro_basamak,
        hacim_gucleniyor=hacim_gucleniyor,
        momentum_gucleniyor=momentum_gucleniyor,
    )

    main13_teknik_onay = False
    main13_ai_skoru = 0.0
    main13_detay = {}
    if (
        guclenen_aday
        and devam_gucu >= 60
        and degisim1 <= MIKRO_BASAMAK_MAX_DEGISIM1
        and degisim3 <= MIKRO_BASAMAK_MAX_DEGISIM3
    ):
        main13_teknik_onay, main13_ai_skoru, main13_detay = main13_roket_adayi_teknik_onayi(
            symbol, guc_skoru, lider_skoru, btcden_guclu, degisim1, degisim3, degisim24
        )
        if not main13_teknik_onay:
            print(
                f"MAIN13 aday filtresi: {symbol} PAS | "
                f"AI {main13_ai_skoru}/100 | RSI {main13_detay.get('rsi')} | "
                f"ADX {main13_detay.get('adx')} | EMA {main13_detay.get('ema_ok')} | "
                f"MACD {main13_detay.get('macd_ok')}"
            )

    if (
        guclenen_aday
        and devam_gucu >= 60
        and degisim1 <= MIKRO_BASAMAK_MAX_DEGISIM1
        and degisim3 <= MIKRO_BASAMAK_MAX_DEGISIM3
        and main13_teknik_onay
    ):
        return "🚀 Roket Adayı", f"MAIN13 güçlü aday • AI {main13_ai_skoru}/100 • {assistant_teyit} teyit"

    # 5) 🚀 ROKET - artık "aday" değil; hareket hacim + momentum ile doğrulanmış olmalı.
    # Erken Roket Adayı %1-2 civarında hazırlığı haber verir. Hacim 5x+ açılıp
    # güç/kalite/BTC/liderlik teyidi gelince aynı coin Roket seviyesine yükselir.
    if (
        guc_skoru >= 62
        and kalite_skoru >= 8
        and hacim_kat >= 5
        and degisim1 > 0
        and degisim3 >= 1.5
        and not (hacim_kat >= 10 and degisim3 < 4 and lider_skoru < 7)
        and btcden_guclu
        and btc_guc_skoru >= 4
        and (haber_skoru > 0 or lider_skoru >= 5)
        and roket_devam_onayi
    ):
        if hacim_gucleniyor and momentum_gucleniyor:
            return "🚀 Roket", "Hacim + momentum birlikte güçleniyor"
        if haber_skoru > 0:
            return "🚀 Roket", "Devam gücü + haber teyidi"
        return "🚀 Roket", "Devam gücü + liderlik teyidi"

    # Arka plan güçlü hacim
    if hacim_kat >= 12 and btcden_guclu and degisim3 >= 4 and not (degisim1 < 0 and degisim3 < 0):
        return "⚡ GÜÇLÜ HACİM", "Arka plan güçlü hacim + momentum teyidi"

    # Arka plan izleme
    if genel_skor >= 8.5 and 5 <= hacim_kat < 12 and degisim3 > 1 and btcden_guclu:
        return "📈 İzleme", "Arka plan izleme"

    return None, None


# ============================================================
# COIN RADAR V5.1 - GERCEK DNA / OGRENME / OPTIMIZASYON MOTORU
# Bu blok son calisan V4/V25 dosyasina dokunmadan, while True'dan once
# fonksiyon override ederek profesyonel V5 analiz katmanini aktif eder.
# ============================================================

import math
import statistics
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

V5_SURUM = "V5.3 RAPOR DOGRULUK + DEVAM GUCU + OGRENME"
V5_DNA_JSON = "coin_dna_veritabani_v5.json"
V5_ANALIZ_JSON = "v5_analiz_ozeti.json"
V5_SQLITE_DB = "coin_radar_v5.sqlite"
V5_PARAMETRE_JSON = "v5_parametre_onerileri.json"
V5_DASHBOARD_JSON = "v5_dashboard.json"
V5_DASHBOARD_HTML = "v5_dashboard.html"
V5_API_PORT = int(os.getenv("V5_API_PORT", "8787"))

# V5 DNA: sinyal anindaki profil + sonuc metrikleri. 90+ alan hedeflenir.
V5_DNA_ALANLARI = [
    "id", "symbol", "base", "sector", "kategori", "kategori_son", "sonuc",
    "zaman", "tarih", "hafta", "gun_adi", "gun_no", "saat", "saat_blok", "ay",
    "giris", "son_fiyat", "max_fiyat", "min_fiyat", "max_kazanc", "min_kazanc", "son_kazanc",
    "h1", "h2", "stop", "h1_zaman", "h2_zaman", "stop_zaman", "h1_sure_saat", "h2_sure_saat", "stop_sure_saat",
    "skor", "kalite", "guc_skoru", "ai_skor", "ai_olasilik", "yildiz_olasilik",
    "risk_puani", "firsat_puani", "momentum_puani", "akilli_para_puani", "balina_puani",
    "hacim", "hacim_log", "hacim_2x", "hacim_5x", "hacim_7x", "hacim_8x", "hacim_10x", "hacim_12x", "hacim_15x", "hacim_20x", "hacim_50x",
    "hacim_gucleniyor", "hacim_onceki", "hacim_artis_orani", "hacim_bonus",
    "degisim1", "degisim3", "degisim24", "momentum_gucleniyor", "momentum_onceki", "momentum_farki",
    "yakalama_tipi", "erken_yakalandi", "normal_yakalandi", "gec_yakalandi", "gec_pump_puan",
    "btc_guclu", "btc_fark", "btc_fark1", "btc_fark3", "btc_fark24", "btc_guc_skoru", "btc_bonus",
    "piyasa_modu", "btc_trend_puani", "btc_risk_puani", "btc_dususte_mi",
    "lider_mi", "lider_guclu", "lider_skoru", "lider_bonus", "lider_rank",
    "zirve_yakin", "yeni_zirve", "zirve_teyidi", "zirve_bonus", "zirve_mesafe",
    "haber", "haber_var", "haber_pozitif", "haber_negatif", "haber_bonus", "haber_risk",
    "rsi", "macd", "macd_signal", "macd_hist", "ema20", "ema50", "ema200", "ema_durum", "trend_durum",
    "giris_kalitesi", "giris_uygun", "tepe_riski", "giris_riskleri", "runup6", "ust_fitil_orani", "kapanis_pozisyonu", "yesil_seri", "range_genisleme",
    "fear_greed", "btc_dominans", "dominans_durum",
    "ortak_sinyal", "filtre_imzasi", "pattern_key", "dna_alan_sayisi", "created_at"
]

V5_BOOL_FILTTRELER = [
    ("BTC guclu", "btc_guclu"), ("Lider", "lider_mi"), ("Lider guclu", "lider_guclu"),
    ("Zirve teyidi", "zirve_teyidi"), ("Haber var", "haber_var"), ("Hacim gucleniyor", "hacim_gucleniyor"),
    ("Momentum gucleniyor", "momentum_gucleniyor"), ("Hacim 8x+", "hacim_8x"),
    ("Hacim 10x+", "hacim_10x"), ("Erken", "erken_yakalandi"), ("Gec degil", "gec_degildir")
]

V5_SEKTOR_HARITASI = {
    "FET": "AI", "AGIX": "AI", "OCEAN": "AI", "NMR": "AI", "ARKM": "AI", "AIOZ": "AI",
    "SOL": "Layer1", "AVAX": "Layer1", "ADA": "Layer1", "DOT": "Layer1", "NEAR": "Layer1", "ATOM": "Layer1",
    "ARB": "Layer2", "OP": "Layer2", "MATIC": "Layer2", "STRK": "Layer2",
    "UNI": "DeFi", "AAVE": "DeFi", "MKR": "DeFi", "COMP": "DeFi", "SNX": "DeFi", "LDO": "DeFi",
    "DOGE": "Meme", "SHIB": "Meme", "PEPE": "Meme", "FLOKI": "Meme", "BONK": "Meme",
    "CHZ": "Fan", "CITY": "Fan", "PSG": "Fan", "BAR": "Fan", "JUV": "Fan", "FB": "Fan",
    "SAND": "Game", "MANA": "Game", "AXS": "Game", "GALA": "Game", "ENJ": "Game",
}


def v5_safe_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def v5_safe_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default


def v5_round(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return 0


def v5_load_json(path, default=None):
    if default is None:
        default = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def v5_save_json(path, data, limit=None):
    try:
        if isinstance(data, list) and limit:
            data = data[-limit:]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("V5 JSON kayit hatasi:", path, e)


def v5_coin_base(symbol):
    s = str(symbol or "").upper().replace("TRY", "")
    return s


def v5_sector(symbol):
    return V5_SEKTOR_HARITASI.get(v5_coin_base(symbol), "Genel")


def v5_now_parts(ts=None):
    ts = ts or time.time()
    lt = time.localtime(ts)
    gunler = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma", "Cumartesi", "Pazar"]
    saat = int(time.strftime("%H", lt))
    if 0 <= saat < 6:
        blok = "gece"
    elif 6 <= saat < 12:
        blok = "sabah"
    elif 12 <= saat < 18:
        blok = "oglen"
    else:
        blok = "aksam"
    return {
        "tarih": time.strftime("%Y-%m-%d", lt),
        "hafta": time.strftime("%Y-W%W", lt),
        "gun_adi": gunler[lt.tm_wday],
        "gun_no": lt.tm_wday,
        "saat": saat,
        "saat_blok": blok,
        "ay": lt.tm_mon,
    }


def v5_mean(values):
    vals = [v5_safe_float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else 0


def v5_pct(part, total):
    return round(part * 100 / total, 1) if total else 0


def v5_success(k):
    return bool(k.get("h1") or k.get("h2") or v5_safe_float(k.get("max_kazanc")) >= 3)


def v5_big_success(k):
    return bool(k.get("h2") or v5_safe_float(k.get("max_kazanc")) >= 6)


def v5_fail(k):
    return bool((k.get("stop") and not k.get("h1") and not k.get("h2")) or v5_safe_float(k.get("max_kazanc")) < -2)


def v5_yakalama_tipi(d1, d3, d24):
    d1, d3, d24 = v5_safe_float(d1), v5_safe_float(d3), v5_safe_float(d24)
    if d1 <= 2 and d3 <= 5 and d24 <= 12:
        return "erken"
    if d1 <= 6 and d3 <= 10 and d24 <= 25:
        return "normal"
    return "gec"


def v5_piyasa_modu(a=None):
    a = a or {}
    btc1 = v5_safe_float(a.get("btc_fark1", a.get("btc_fark", 0)))
    btc3 = v5_safe_float(a.get("btc_fark3", a.get("btc_fark", 0)))
    btc24 = v5_safe_float(a.get("btc_fark24", 0))
    # Elimizde tam BTC fiyat serisi yoksa sinyalin BTC'ye gore gucunu piyasa modu vekili olarak kullaniyoruz.
    skor = btc1 * 0.2 + btc3 * 0.5 + btc24 * 0.3
    if skor >= 3:
        return "boga"
    if skor <= -3:
        return "ayi"
    return "yatay"


def v5_rsi_from_a(a):
    # Orijinal bot RSI hesaplamiyorsa bos gecmez; momentumdan yaklasik risk vekili uretir.
    if "rsi" in a:
        return v5_round(a.get("rsi"), 2)
    d1 = v5_safe_float(a.get("degisim1")); d3 = v5_safe_float(a.get("degisim3")); d24 = v5_safe_float(a.get("degisim24"))
    return int(max(1, min(99, 50 + d1 * 2.0 + d3 * 0.9 + d24 * 0.18)))


def v5_ema_durum_from_a(a):
    if a.get("ema_durum"):
        return a.get("ema_durum")
    d3 = v5_safe_float(a.get("degisim3")); d24 = v5_safe_float(a.get("degisim24"))
    if d3 > 0 and d24 > 0:
        return "pozitif"
    if d3 < 0 and d24 < 0:
        return "negatif"
    return "karisik"


def v5_momentum_puani(k):
    puan = 0
    puan += min(max(v5_safe_float(k.get("degisim1")), 0) * 5, 20)
    d3 = v5_safe_float(k.get("degisim3"))
    puan += min(max(d3, 0) * 4, 35)
    if d3 >= 6:
        puan += 10
    elif d3 >= 4:
        puan += 5
    puan += min(max(v5_safe_float(k.get("degisim24")), 0) * 0.7, 20)
    if k.get("momentum_gucleniyor"):
        puan += 15
    if k.get("yakalama_tipi") == "erken":
        puan += 10
    if k.get("yakalama_tipi") == "gec":
        puan -= 15
    return int(max(0, min(100, round(puan))))


def v5_akilli_para_puani(k):
    puan = 0
    hacim = v5_safe_float(k.get("hacim"))
    d3 = v5_safe_float(k.get("degisim3"))
    # Hacim tek başına değil, momentumla birlikte anlamlı kabul edilir.
    puan += min(hacim * 1.8, 22)
    if hacim >= 10 and d3 < 4:
        puan -= 8
    elif hacim >= 10 and d3 >= 6:
        puan += 6
    if k.get("hacim_gucleniyor"):
        puan += 15
    if k.get("lider_mi"):
        puan += 15
    if k.get("btc_guclu"):
        puan += 15
    if k.get("zirve_teyidi"):
        puan += 10
    if k.get("gec_yakalandi"):
        puan -= 15
    return int(max(0, min(100, round(puan))))


def v5_risk_puani(k):
    risk = 0
    if not k.get("btc_guclu"):
        risk += 16
    if not k.get("lider_mi"):
        risk += 10
    if not k.get("zirve_teyidi"):
        risk += 8
    if v5_safe_float(k.get("hacim")) < 5:
        risk += 12
    if k.get("yakalama_tipi") == "gec":
        risk += 20
    if v5_safe_float(k.get("degisim24")) > 35:
        risk += 12
    risk += min(v5_safe_float(k.get("gec_pump_puan")) * 5, 25)
    if str(k.get("piyasa_modu")) == "ayi":
        risk += 10
    return int(max(0, min(100, round(risk))))


def v5_firsat_puani(k):
    puan = 0
    puan += min(v5_safe_float(k.get("skor")) * 2, 20)
    puan += min(v5_safe_float(k.get("kalite")) * 2, 20)
    hacim = v5_safe_float(k.get("hacim"))
    d3 = v5_safe_float(k.get("degisim3"))
    puan += min(hacim * 0.9, 12)
    puan += min(max(d3, 0) * 2.2, 18)
    if d3 >= 6:
        puan += 8
    if hacim >= 10 and d3 < 4:
        puan -= 6
    puan += 10 if k.get("btc_guclu") else 0
    puan += 10 if k.get("lider_mi") else 0
    puan += 10 if k.get("zirve_teyidi") else 0
    puan += 5 if k.get("haber_var") else 0
    puan += 5 if k.get("hacim_gucleniyor") else 0
    puan += 5 if k.get("momentum_gucleniyor") else 0
    puan -= v5_risk_puani(k) * 0.25
    return int(max(0, min(100, round(puan))))


def v5_filter_value(k, key):
    if key == "gec_degildir":
        return k.get("yakalama_tipi") != "gec"
    return bool(k.get(key))


def v5_pattern_key(k):
    parts = []
    if k.get("btc_guclu"): parts.append("BTC")
    if k.get("lider_mi"): parts.append("Lider")
    if k.get("zirve_teyidi"): parts.append("Zirve")
    if k.get("haber_var"): parts.append("Haber")
    if v5_safe_float(k.get("hacim")) >= 10: parts.append("10x+")
    elif v5_safe_float(k.get("hacim")) >= 8: parts.append("8x+")
    if k.get("hacim_gucleniyor"): parts.append("Hacim↑")
    if k.get("momentum_gucleniyor"): parts.append("Mom↑")
    if k.get("yakalama_tipi") == "erken": parts.append("Erken")
    if not parts:
        parts.append("Zayif-Ortak")
    return "+".join(parts)


def v5_learn_weights(kayitlar=None):
    kayitlar = kayitlar or basari_kayitlari
    kayitlar = [k for k in kayitlar if k.get("sonuc") != "aktif"] or kayitlar[-500:]
    if len(kayitlar) < 12:
        return {"base": 42, "skor": 1.2, "kalite": 1.1, "hacim": 0.45, "btc_guclu": 7, "lider_mi": 7, "zirve_teyidi": 6, "haber_var": 4, "hacim_gucleniyor": 3, "momentum_gucleniyor": 8, "gec": -10, "risk": -0.25}
    weights = {"base": 35, "skor": 1.0, "kalite": 1.0, "hacim": 0.45, "risk": -0.25}
    for label, key in V5_BOOL_FILTTRELER:
        yes = [k for k in kayitlar if v5_filter_value(k, key)]
        no = [k for k in kayitlar if not v5_filter_value(k, key)]
        if len(yes) >= 3 and len(no) >= 3:
            yes_rate = v5_pct(sum(v5_success(k) for k in yes), len(yes))
            no_rate = v5_pct(sum(v5_success(k) for k in no), len(no))
            weights[key] = round(max(-18, min(18, (yes_rate - no_rate) / 3)), 2)
    # Sayisal alan katsayilari: basarili ortalama ile basarisiz ortalama farkina gore hafif ayar.
    ok = [k for k in kayitlar if v5_success(k)]
    bad = [k for k in kayitlar if not v5_success(k)]
    for alan, cap, div in [("skor", 2.0, 8), ("kalite", 2.0, 8), ("hacim", 1.5, 10), ("guc_skoru", 0.8, 20)]:
        if ok and bad:
            diff = v5_mean([k.get(alan) for k in ok]) - v5_mean([k.get(alan) for k in bad])
            weights[alan] = round(max(0.1, min(cap, 1 + diff / div)), 2)
    return weights


def v5_ai_score(k, weights=None):
    weights = weights or v5_learn_weights()
    puan = v5_safe_float(weights.get("base", 40))
    puan += v5_safe_float(k.get("skor")) * v5_safe_float(weights.get("skor", 1.0))
    puan += v5_safe_float(k.get("kalite")) * v5_safe_float(weights.get("kalite", 1.0))
    puan += min(v5_safe_float(k.get("hacim")), 30) * v5_safe_float(weights.get("hacim", 0.8))
    puan += v5_safe_float(k.get("guc_skoru")) * v5_safe_float(weights.get("guc_skoru", 0.3))
    for _, key in V5_BOOL_FILTTRELER:
        if v5_filter_value(k, key):
            puan += v5_safe_float(weights.get(key, 0))
    if k.get("yakalama_tipi") == "gec":
        puan += v5_safe_float(weights.get("gec", -10))
    puan += v5_risk_puani(k) * v5_safe_float(weights.get("risk", -0.25))
    return int(max(1, min(99, round(puan))))


def v5_yildiz_probability(k, weights=None):
    score = v5_ai_score(k, weights)
    # Logistic sekle yakin; AI skorunu olasiliga cevirir.
    prob = 100 / (1 + math.exp(-(score - 55) / 12))
    if k.get("kategori") == "⭐ Yıldız" or k.get("kategori_son") == "⭐ Yıldız":
        prob = max(prob, 86)
    if k.get("yakalama_tipi") == "gec":
        prob -= 8
    return int(max(1, min(97, round(prob))))


def v5_make_dna(symbol, a, simdi):
    onceki = a.get("onceki_veri") or {}
    notes = a.get("guclenme_notlari", []) or []
    hacim = v5_safe_float(a.get("hacim")); d1 = v5_safe_float(a.get("degisim1")); d3 = v5_safe_float(a.get("degisim3")); d24 = v5_safe_float(a.get("degisim24"))
    onceki_hacim = v5_safe_float(onceki.get("hacim"), hacim)
    onceki_mom = v5_safe_float(onceki.get("degisim3"), d3)
    hacim_gucleniyor = any("hacim" in str(n).lower() and "güç" in str(n).lower() for n in notes) or (onceki_hacim > 0 and hacim >= onceki_hacim * 1.2)
    momentum_gucleniyor = any("momentum" in str(n).lower() and "güç" in str(n).lower() for n in notes) or (d3 - onceki_mom >= 0.5)
    yak = v5_yakalama_tipi(d1, d3, d24)
    haber = v5_safe_float(a.get("haber_skoru"))
    lider_skoru = v5_safe_float(a.get("lider_skoru"))
    btc_fark = v5_safe_float(a.get("btc_fark"))
    zirve_teyidi = bool(a.get("zirve_yakin") or a.get("yeni_zirve"))
    parts = v5_now_parts(simdi)
    dna = {
        "id": f"{int(simdi)}_{symbol}", "symbol": symbol, "base": v5_coin_base(symbol), "sector": v5_sector(symbol),
        "kategori": a.get("durum"), "kategori_son": a.get("durum"), "sonuc": "aktif", "zaman": simdi,
        **parts,
        "giris": v5_round(a.get("fiyat"), 8), "son_fiyat": v5_round(a.get("fiyat"), 8), "max_fiyat": v5_round(a.get("fiyat"), 8), "min_fiyat": v5_round(a.get("fiyat"), 8),
        "max_kazanc": 0.0, "min_kazanc": 0.0, "son_kazanc": 0.0, "h1": False, "h2": False, "stop": False,
        "h1_zaman": None, "h2_zaman": None, "stop_zaman": None, "h1_sure_saat": None, "h2_sure_saat": None, "stop_sure_saat": None,
        "skor": v5_round(a.get("skor")), "kalite": v5_round(a.get("kalite_skoru")), "guc_skoru": v5_round(a.get("guc_skoru")),
        "giris_kalitesi": v5_safe_int(a.get("giris_kalitesi")), "giris_uygun": bool(a.get("giris_uygun")),
        "tepe_riski": bool(a.get("tepe_riski")), "giris_riskleri": list(a.get("giris_riskleri", []) or []),
        "runup6": v5_round(a.get("runup6")), "ust_fitil_orani": v5_round(a.get("ust_fitil_orani")),
        "kapanis_pozisyonu": v5_round(a.get("kapanis_pozisyonu")), "yesil_seri": v5_safe_int(a.get("yesil_seri")),
        "range_genisleme": v5_round(a.get("range_genisleme")),
        "hacim": v5_round(hacim), "hacim_log": v5_round(math.log1p(max(hacim, 0))),
        "hacim_2x": hacim >= 2, "hacim_5x": hacim >= 5, "hacim_7x": hacim >= 7, "hacim_8x": hacim >= 8, "hacim_10x": hacim >= 10, "hacim_12x": hacim >= 12, "hacim_15x": hacim >= 15, "hacim_20x": hacim >= 20, "hacim_50x": hacim >= 50,
        "hacim_gucleniyor": bool(hacim_gucleniyor), "hacim_onceki": v5_round(onceki_hacim), "hacim_artis_orani": v5_round(((hacim - onceki_hacim) / onceki_hacim * 100) if onceki_hacim else 0), "hacim_bonus": v5_safe_int(a.get("hacim_bonus")),
        "degisim1": v5_round(d1), "degisim3": v5_round(d3), "degisim24": v5_round(d24), "momentum_gucleniyor": bool(momentum_gucleniyor), "momentum_onceki": v5_round(onceki_mom), "momentum_farki": v5_round(d3 - onceki_mom),
        "yakalama_tipi": yak, "erken_yakalandi": yak == "erken", "normal_yakalandi": yak == "normal", "gec_yakalandi": yak == "gec", "gec_pump_puan": v5_safe_int(a.get("gec_pump_puan")),
        "btc_guclu": bool(a.get("btcden_guclu") or a.get("btc_guclu")), "btc_fark": v5_round(btc_fark), "btc_fark1": v5_round(a.get("btc_fark1", btc_fark)), "btc_fark3": v5_round(a.get("btc_fark3", btc_fark)), "btc_fark24": v5_round(a.get("btc_fark24", 0)), "btc_guc_skoru": v5_round(a.get("btc_guc_skoru")), "btc_bonus": v5_safe_int(a.get("btc_fark_bonus", a.get("btc_bonus", 0))),
        "piyasa_modu": v5_piyasa_modu(a), "btc_trend_puani": int(max(0, min(100, 50 + btc_fark * 4))), "btc_risk_puani": int(max(0, min(100, 50 - btc_fark * 4))), "btc_dususte_mi": btc_fark < -1,
        "lider_mi": lider_skoru >= 5, "lider_guclu": lider_skoru >= 7, "lider_skoru": v5_round(lider_skoru), "lider_bonus": v5_safe_int(a.get("lider_bonus")), "lider_rank": v5_safe_int(a.get("lider_rank"), 0),
        "zirve_yakin": bool(a.get("zirve_yakin")), "yeni_zirve": bool(a.get("yeni_zirve")), "zirve_teyidi": zirve_teyidi, "zirve_bonus": v5_safe_int(a.get("zirve_bonus")), "zirve_mesafe": v5_round(a.get("zirve_mesafe")),
        "haber": v5_round(haber), "haber_var": haber > 0, "haber_pozitif": haber > 0, "haber_negatif": haber < 0, "haber_bonus": max(0, int(haber)), "haber_risk": abs(min(0, int(haber))),
        "rsi": v5_rsi_from_a(a), "macd": v5_round(a.get("macd")), "macd_signal": v5_round(a.get("macd_signal")), "macd_hist": v5_round(a.get("macd_hist")), "ema20": v5_round(a.get("ema20")), "ema50": v5_round(a.get("ema50")), "ema200": v5_round(a.get("ema200")), "ema_durum": v5_ema_durum_from_a(a), "trend_durum": v5_ema_durum_from_a(a),
        "fear_greed": v5_safe_int(os.getenv("FEAR_GREED", "0")), "btc_dominans": v5_safe_float(os.getenv("BTC_DOMINANCE", "0")), "dominans_durum": "bilinmiyor",
        "ortak_sinyal": "", "filtre_imzasi": "", "pattern_key": "", "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(simdi)),
    }
    dna["momentum_puani"] = v5_momentum_puani(dna)
    dna["akilli_para_puani"] = v5_akilli_para_puani(dna)
    dna["balina_puani"] = int(max(0, min(100, min(hacim * 4, 70) + (15 if hacim_gucleniyor else 0) + (15 if lider_skoru >= 7 else 0))))
    dna["risk_puani"] = v5_risk_puani(dna)
    dna["firsat_puani"] = v5_firsat_puani(dna)
    dna["ai_skor"] = v5_ai_score(dna)
    dna["ai_olasilik"] = dna["ai_skor"]
    dna["yildiz_olasilik"] = v5_yildiz_probability(dna)
    dna["pattern_key"] = v5_pattern_key(dna)
    dna["filtre_imzasi"] = dna["pattern_key"]
    dna["ortak_sinyal"] = dna["pattern_key"].replace("+", " • ")
    dna["dna_alan_sayisi"] = sum(1 for x in V5_DNA_ALANLARI if x in dna)
    return dna


def v5_sql_init():
    try:
        con = sqlite3.connect(V5_SQLITE_DB)
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, symbol TEXT, zaman REAL, kategori TEXT, sonuc TEXT, data TEXT)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_zaman ON signals(zaman)")
        cur.execute("CREATE TABLE IF NOT EXISTS analysis (zaman REAL, type TEXT, data TEXT)")
        con.commit(); con.close()
    except Exception as e:
        print("V5 SQLite init hatasi:", e)


def v5_sql_upsert(k):
    try:
        v5_sql_init()
        con = sqlite3.connect(V5_SQLITE_DB)
        cur = con.cursor()
        cur.execute("INSERT OR REPLACE INTO signals(id, symbol, zaman, kategori, sonuc, data) VALUES (?, ?, ?, ?, ?, ?)", (str(k.get("id") or f"{k.get('zaman')}_{k.get('symbol')}"), k.get("symbol"), v5_safe_float(k.get("zaman")), k.get("kategori"), k.get("sonuc"), json.dumps(k, ensure_ascii=False)))
        con.commit(); con.close()
    except Exception as e:
        print("V5 SQLite upsert hatasi:", e)


def v5_sql_save_analysis(t, data):
    try:
        v5_sql_init()
        con = sqlite3.connect(V5_SQLITE_DB)
        cur = con.cursor()
        cur.execute("INSERT INTO analysis(zaman, type, data) VALUES (?, ?, ?)", (time.time(), t, json.dumps(data, ensure_ascii=False)))
        con.commit(); con.close()
    except Exception as e:
        print("V5 SQLite analysis hatasi:", e)


def v5_sync_all_to_sqlite():
    try:
        for k in basari_kayitlari[-3000:]:
            if "id" not in k:
                k["id"] = f"{int(v5_safe_float(k.get('zaman'), time.time()))}_{k.get('symbol')}"
            v5_sql_upsert(k)
    except Exception as e:
        print("V5 sqlite sync hatasi:", e)


# Override: her sinyal kaydini 90+ alanli DNA olarak olusturur.
def basari_kaydi_olustur(symbol, a, simdi):
    return v5_make_dna(symbol, a, simdi)


# Override: JSON + SQLite birlikte kaydeder. Eski dosya adini korur.
def basari_db_kaydet(veriler):
    try:
        with open(BASARI_DB_DOSYA, "w", encoding="utf-8") as f:
            json.dump(veriler[-3000:], f, ensure_ascii=False, indent=2)
        v5_save_json(V5_DNA_JSON, veriler[-3000:], limit=3000)
        for k in veriler[-10:]:
            v5_sql_upsert(k)
    except Exception as e:
        print("V5 basari veritabani kaydedilemedi:", e)


def v5_filter_contribution(kayitlar):
    out = []
    total = len(kayitlar)
    genel = v5_pct(sum(v5_success(k) for k in kayitlar), total)
    for ad, key in V5_BOOL_FILTTRELER:
        yes = [k for k in kayitlar if v5_filter_value(k, key)]
        no = [k for k in kayitlar if not v5_filter_value(k, key)]
        if len(yes) < 2:
            continue
        yr = v5_pct(sum(v5_success(k) for k in yes), len(yes))
        nr = v5_pct(sum(v5_success(k) for k in no), len(no)) if no else genel
        out.append({"filtre": ad, "ornek": len(yes), "basari": yr, "genel": genel, "katki": round(yr - nr, 1)})
    return sorted(out, key=lambda x: x["katki"], reverse=True)


def v5_pattern_discovery(kayitlar, top=8):
    groups = {}
    for k in kayitlar:
        key = k.get("pattern_key") or v5_pattern_key(k)
        groups.setdefault(key, []).append(k)
    rows = []
    for key, arr in groups.items():
        if len(arr) < 2:
            continue
        rows.append({
            "pattern": key, "adet": len(arr),
            "basari": v5_pct(sum(v5_success(k) for k in arr), len(arr)),
            "h2": v5_pct(sum(v5_big_success(k) for k in arr), len(arr)),
            "ort_kazanc": v5_mean([k.get("max_kazanc") for k in arr]),
            "risk": v5_mean([k.get("risk_puani") for k in arr]),
        })
    return sorted(rows, key=lambda x: (x["basari"], x["ort_kazanc"], x["adet"]), reverse=True)[:top]


def v5_category_league(kayitlar):
    cats = {}
    for k in kayitlar:
        cats.setdefault(k.get("kategori", "Bilinmiyor"), []).append(k)
    rows = []
    for c, arr in cats.items():
        rows.append({"kategori": c, "adet": len(arr), "basari": v5_pct(sum(v5_success(k) for k in arr), len(arr)), "h2": v5_pct(sum(v5_big_success(k) for k in arr), len(arr)), "ort_kazanc": v5_mean([k.get("max_kazanc") for k in arr]), "stop": v5_pct(sum(bool(k.get("stop")) for k in arr), len(arr))})
    return sorted(rows, key=lambda x: (x["basari"], x["h2"], x["ort_kazanc"]), reverse=True)


def v5_failure_analysis(kayitlar):
    fails = [k for k in kayitlar if v5_fail(k) or (not v5_success(k) and k.get("sonuc") != "aktif")]
    if not fails:
        return {"adet": 0, "sebepler": []}
    causes = []
    checks = [
        ("BTC zayif", lambda k: not k.get("btc_guclu")), ("Lider yok", lambda k: not k.get("lider_mi")),
        ("Zirve teyidi yok", lambda k: not k.get("zirve_teyidi")), ("Gec yakalama", lambda k: k.get("yakalama_tipi") == "gec"),
        ("Hacim 8x altinda", lambda k: v5_safe_float(k.get("hacim")) < 8), ("Haber destegi yok", lambda k: not k.get("haber_var")),
        ("24s hareket sisik", lambda k: v5_safe_float(k.get("degisim24")) > 30), ("Risk puani yuksek", lambda k: v5_safe_float(k.get("risk_puani")) >= 55),
    ]
    for ad, fn in checks:
        cnt = sum(1 for k in fails if fn(k))
        if cnt:
            causes.append({"sebep": ad, "adet": cnt, "oran": v5_pct(cnt, len(fails))})
    return {"adet": len(fails), "sebepler": sorted(causes, key=lambda x: x["oran"], reverse=True)}


def v5_market_catch_rate(gun=30, esik=10):
    try:
        now = time.time(); start = now - gun * 86400
        market = [k for k in piyasa_kayitlari if v5_safe_float(k.get("zaman")) >= start]
        by_symbol = {}
        for k in market:
            s = k.get("symbol")
            if not s:
                continue
            if s not in by_symbol or v5_safe_float(k.get("degisim24")) > v5_safe_float(by_symbol[s].get("degisim24")):
                by_symbol[s] = k
        winners = [k for k in by_symbol.values() if v5_safe_float(k.get("degisim24")) >= esik]
        signals = {}
        for b in basari_kayitlari:
            if v5_safe_float(b.get("zaman")) >= start:
                s = b.get("symbol")
                if s and (s not in signals or v5_safe_float(b.get("zaman")) < signals[s]):
                    signals[s] = v5_safe_float(b.get("zaman"))
        caught, missed = [], []
        for w in winners:
            s = w.get("symbol"); wz = v5_safe_float(w.get("zaman"))
            if s in signals and signals[s] <= wz:
                caught.append(w)
            else:
                missed.append(w)
        return {"gun": gun, "esik": esik, "kazanan": len(winners), "yakalanan": len(caught), "kacirilan": len(missed), "yakalama_orani": v5_pct(len(caught), len(winners)), "en_buyuk_kacan": sorted(missed, key=lambda x: v5_safe_float(x.get("degisim24")), reverse=True)[:10]}
    except Exception as e:
        return {"hata": str(e), "kazanan": 0, "yakalanan": 0, "kacirilan": 0, "yakalama_orani": 0, "en_buyuk_kacan": []}


def v5_parameter_optimization(kayitlar):
    suggestions = []
    tests = [
        ("hacim_esigi", "hacim", [5, 6, 7, 8, 10, 12, 15]),
        ("skor_esigi", "skor", [8, 10, 12, 14, 16, 18, 20]),
        ("kalite_esigi", "kalite", [5, 6, 7, 8, 9, 10, 12]),
        ("rsi_ust_limit", "rsi", [62, 65, 68, 70, 72, 75, 80]),
        ("risk_ust_limit", "risk_puani", [40, 45, 50, 55, 60, 65, 70]),
    ]
    for name, field, values in tests:
        best = None
        for v in values:
            if name.endswith("ust_limit"):
                arr = [k for k in kayitlar if v5_safe_float(k.get(field)) <= v]
            else:
                arr = [k for k in kayitlar if v5_safe_float(k.get(field)) >= v]
            if len(arr) < 3:
                continue
            rate = v5_pct(sum(v5_success(k) for k in arr), len(arr))
            h2 = v5_pct(sum(v5_big_success(k) for k in arr), len(arr))
            score = rate + h2 * 0.35 + min(len(arr), 50) * 0.1
            row = {"parametre": name, "onerilen": v, "ornek": len(arr), "basari": rate, "h2": h2, "skor": round(score, 2)}
            if best is None or row["skor"] > best["skor"]:
                best = row
        if best:
            suggestions.append(best)
    # Kural bazli yorumlar
    catch = v5_market_catch_rate(30, 10)
    if catch.get("kazanan", 0) >= 3 and catch.get("yakalama_orani", 0) < 50:
        suggestions.append({"parametre": "catch_rate", "onerilen": "erken filtreleri gevset", "ornek": catch.get("kazanan"), "basari": catch.get("yakalama_orani"), "h2": 0, "skor": 0})
    v5_save_json(V5_PARAMETRE_JSON, suggestions)
    return sorted(suggestions, key=lambda x: x.get("skor", 0), reverse=True)


def v5_backtest_simulation(kayitlar, gun=180):
    start = time.time() - gun * 86400
    arr = [k for k in kayitlar if v5_safe_float(k.get("zaman")) >= start]
    if len(arr) < 5:
        return {"gun": gun, "ornek": len(arr), "not": "Yeterli gecmis sonuc yok. Veri biriktikce 6 aylik simulasyon otomatik dolacak."}
    strategies = {
        "mevcut": lambda k: True,
        "sadece_ai_60": lambda k: v5_ai_score(k) >= 60,
        "btc_lider_hacim8": lambda k: k.get("btc_guclu") and k.get("lider_mi") and v5_safe_float(k.get("hacim")) >= 8,
        "erken_normal_risk55": lambda k: k.get("yakalama_tipi") != "gec" and v5_safe_float(k.get("risk_puani")) <= 55,
        "haberli_guclu": lambda k: k.get("haber_var") and k.get("btc_guclu") and v5_safe_float(k.get("hacim")) >= 5,
    }
    out = []
    for name, fn in strategies.items():
        sel = [k for k in arr if fn(k)]
        if not sel:
            continue
        out.append({"strateji": name, "adet": len(sel), "basari": v5_pct(sum(v5_success(k) for k in sel), len(sel)), "h2": v5_pct(sum(v5_big_success(k) for k in sel), len(sel)), "ort_kazanc": v5_mean([k.get("max_kazanc") for k in sel]), "stop": v5_pct(sum(bool(k.get("stop")) for k in sel), len(sel))})
    return {"gun": gun, "ornek": len(arr), "sonuclar": sorted(out, key=lambda x: (x["basari"], x["ort_kazanc"]), reverse=True)}


def v5_hall_of_fame(kayitlar):
    by = {}
    for k in kayitlar:
        by.setdefault(k.get("symbol"), []).append(k)
    rows = []
    for s, arr in by.items():
        if not s:
            continue
        rows.append({"symbol": s, "adet": len(arr), "basari": v5_pct(sum(v5_success(k) for k in arr), len(arr)), "h2": v5_pct(sum(v5_big_success(k) for k in arr), len(arr)), "en_iyi": max([v5_safe_float(k.get("max_kazanc")) for k in arr] or [0]), "ort": v5_mean([k.get("max_kazanc") for k in arr])})
    return sorted(rows, key=lambda x: (x["basari"], x["en_iyi"], x["adet"]), reverse=True)[:10]


def v5_time_analysis(kayitlar):
    def group(field):
        d = {}
        for k in kayitlar:
            key = k.get(field, "?")
            d.setdefault(key, []).append(k)
        rows = []
        for key, arr in d.items():
            if len(arr) >= 2:
                rows.append({"ad": key, "adet": len(arr), "basari": v5_pct(sum(v5_success(k) for k in arr), len(arr)), "ort": v5_mean([k.get("max_kazanc") for k in arr])})
        return sorted(rows, key=lambda x: (x["basari"], x["ort"]), reverse=True)[:5]
    return {"saat": group("saat"), "gun": group("gun_adi"), "saat_blok": group("saat_blok")}


def v5_sector_analysis(kayitlar):
    d = {}
    for k in kayitlar:
        d.setdefault(k.get("sector") or v5_sector(k.get("symbol")), []).append(k)
    rows = []
    for sec, arr in d.items():
        rows.append({"sektor": sec, "adet": len(arr), "basari": v5_pct(sum(v5_success(k) for k in arr), len(arr)), "ort": v5_mean([k.get("max_kazanc") for k in arr])})
    return sorted(rows, key=lambda x: (x["basari"], x["ort"]), reverse=True)


def v5_target_stop_drawdown(kayitlar):
    return {
        "h1_isabet": v5_pct(sum(bool(k.get("h1")) for k in kayitlar), len(kayitlar)),
        "h2_isabet": v5_pct(sum(bool(k.get("h2")) for k in kayitlar), len(kayitlar)),
        "stop_orani": v5_pct(sum(bool(k.get("stop")) for k in kayitlar), len(kayitlar)),
        "ort_max_kazanc": v5_mean([k.get("max_kazanc") for k in kayitlar]),
        "ort_min_kazanc": v5_mean([k.get("min_kazanc") for k in kayitlar]),
        "en_kotu_drawdown": min([v5_safe_float(k.get("min_kazanc")) for k in kayitlar] or [0]),
    }


def v5_news_btc_effect(kayitlar):
    def rate(arr): return v5_pct(sum(v5_success(k) for k in arr), len(arr))
    haberli = [k for k in kayitlar if k.get("haber_var")]
    habersiz = [k for k in kayitlar if not k.get("haber_var")]
    btc_ok = [k for k in kayitlar if k.get("btc_guclu")]
    btc_no = [k for k in kayitlar if not k.get("btc_guclu")]
    modes = {}
    for k in kayitlar:
        modes.setdefault(k.get("piyasa_modu", "bilinmiyor"), []).append(k)
    return {
        "haberli": {"adet": len(haberli), "basari": rate(haberli)}, "habersiz": {"adet": len(habersiz), "basari": rate(habersiz)},
        "btc_guclu": {"adet": len(btc_ok), "basari": rate(btc_ok)}, "btc_zayif": {"adet": len(btc_no), "basari": rate(btc_no)},
        "piyasa_modu": {m: {"adet": len(a), "basari": rate(a)} for m, a in modes.items()}
    }


def v5_build_analysis(gun=30):
    now = time.time(); start = now - gun * 86400
    kayitlar = [k for k in basari_kayitlari if v5_safe_float(k.get("zaman")) >= start]
    # Eski kayitlari V5 alanlariyla zenginlestir.
    for k in kayitlar:
        if "pattern_key" not in k: k["pattern_key"] = v5_pattern_key(k)
        if "risk_puani" not in k: k["risk_puani"] = v5_risk_puani(k)
        if "ai_skor" not in k: k["ai_skor"] = v5_ai_score(k)
        if "yildiz_olasilik" not in k: k["yildiz_olasilik"] = v5_yildiz_probability(k)
        if "sector" not in k: k["sector"] = v5_sector(k.get("symbol"))
    total = len(kayitlar)
    weights = v5_learn_weights(kayitlar)
    analysis = {
        "surum": V5_SURUM, "zaman": now, "gun": gun, "toplam_sinyal": total,
        "basari_orani": v5_pct(sum(v5_success(k) for k in kayitlar), total),
        "h2_orani": v5_pct(sum(v5_big_success(k) for k in kayitlar), total),
        "aktif": sum(1 for k in kayitlar if k.get("sonuc") == "aktif"),
        "weights": weights,
        "kategori_ligi": v5_category_league(kayitlar),
        "pattern_discovery": v5_pattern_discovery(kayitlar),
        "filtre_katki": v5_filter_contribution(kayitlar),
        "failure": v5_failure_analysis(kayitlar),
        "catch_rate": v5_market_catch_rate(gun, 10),
        "parametre_onerileri": v5_parameter_optimization(kayitlar),
        "backtest": v5_backtest_simulation(kayitlar, min(180, gun)),
        "hall_of_fame": v5_hall_of_fame(kayitlar),
        "time_analysis": v5_time_analysis(kayitlar),
        "sector_analysis": v5_sector_analysis(kayitlar),
        "target_stop_drawdown": v5_target_stop_drawdown(kayitlar),
        "news_btc_effect": v5_news_btc_effect(kayitlar),
    }
    v5_save_json(V5_ANALIZ_JSON, analysis)
    v5_save_json(V5_DASHBOARD_JSON, analysis)
    v5_sql_save_analysis("weekly", analysis)
    return analysis


def v5_dashboard_html(analysis):
    try:
        html = """<!doctype html><html><head><meta charset='utf-8'><title>Coin Radar V5</title><style>body{font-family:Arial;margin:24px;background:#111;color:#eee}.card{background:#1d1d1d;padding:16px;margin:12px 0;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #333;padding:8px;text-align:left}</style></head><body>"""
        html += f"<h1>Coin Radar {analysis.get('surum')}</h1><div class='card'>Toplam: {analysis.get('toplam_sinyal')} | Başarı: %{analysis.get('basari_orani')} | H2: %{analysis.get('h2_orani')}</div>"
        def table(title, rows, cols):
            nonlocal html
            html += f"<div class='card'><h2>{title}</h2><table><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
            for r in rows[:10]:
                html += "<tr>" + "".join(f"<td>{r.get(c,'')}</td>" for c in cols) + "</tr>"
            html += "</table></div>"
        table("Kategori Ligi", analysis.get("kategori_ligi", []), ["kategori", "adet", "basari", "h2", "ort_kazanc"])
        table("Pattern Discovery", analysis.get("pattern_discovery", []), ["pattern", "adet", "basari", "h2", "ort_kazanc"])
        table("Filtre Katkı", analysis.get("filtre_katki", []), ["filtre", "ornek", "basari", "katki"])
        html += "</body></html>"
        with open(V5_DASHBOARD_HTML, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print("V5 dashboard html hatasi:", e)


def v5_professional_report_text(gun=30):
    a = v5_build_analysis(gun)
    try:
        now_v5_1 = time.time()
        kayitlar = [k for k in basari_kayitlari if v5_safe_float(k.get("zaman")) >= now_v5_1 - gun * 86400]
    except Exception:
        kayitlar = []
    v5_dashboard_html(a)
    msg = f"🧠 COIN RADAR {V5_SURUM}\n"
    msg += f"Dönem: Son {gun} gün | DNA alanı: {len(V5_DNA_ALANLARI)} | Sinyal: {a['toplam_sinyal']}\n"
    msg += f"Başarı: %{a['basari_orani']} | H2: %{a['h2_orani']} | Aktif: {a['aktif']}\n\n"
    if not a["toplam_sinyal"]:
        return msg + "Henüz rapor için yeterli V5 sinyal sonucu yok. Sinyaller geldikçe DNA ve öğrenme motoru dolacak.\n"

    # İlk bakışta okunacak kısa karar özeti.
    cr7 = a.get("catch_rate") or {}
    try:
        cr30 = v5_market_catch_rate(30, 10)
    except Exception:
        cr30 = {}
    kategori_ligi = a.get("kategori_ligi") or []
    en_iyi_kategori = kategori_ligi[0] if kategori_ligi else {}
    failure_rows = (a.get("failure") or {}).get("sebepler") or []
    en_buyuk_problem = failure_rows[0].get("sebep") if failure_rows else "Belirgin tek sorun yok"
    if a.get("basari_orani", 0) >= 30 and cr7.get("yakalama_orani", 0) >= 65:
        ai_kisa = "Sistem dengeli görünüyor; eşikleri şimdilik koru."
    elif cr7.get("yakalama_orani", 0) < 55:
        ai_kisa = "Yakalama oranı düşük; kaçırılan coin nedenlerini izle."
    else:
        ai_kisa = "Başarı düşük; yeni eşik yerine öğrenme verisini büyüt."

    msg += "📌 KARAR ÖZETİ\n"
    msg += f"Başarı %{a.get('basari_orani',0)} | H2 %{a.get('h2_orani',0)}\n"
    msg += f"Catch Rate 7G %{cr7.get('yakalama_orani',0)} | 30G %{cr30.get('yakalama_orani',0)}\n"
    if en_iyi_kategori:
        msg += f"En iyi kategori: {en_iyi_kategori.get('kategori')} (%{en_iyi_kategori.get('basari',0)} başarı, {en_iyi_kategori.get('adet',0)} örnek)\n"
    msg += f"En büyük gözlem: {en_buyuk_problem}\n"
    msg += f"AI kısa yorum: {ai_kisa}\n\n"
    msg += "🧠 ÖĞRENME\n"
    msg += "🏆 KATEGORİ LİGİ\n"
    for r in a["kategori_ligi"][:6]:
        msg += f"{r['kategori']}: {r['adet']} sinyal | Başarı %{r['basari']} | H2 %{r['h2']} | Ort %{r['ort_kazanc']}\n"
    msg += "\n🧬 PATTERN DISCOVERY\n"
    pattern_rows = [r for r in a["pattern_discovery"] if r.get("adet",0) >= 10 and r.get("basari",0) >= 30][:6]
    if pattern_rows:
        for r in pattern_rows:
            msg += f"{r['pattern']}: {r['adet']} | Başarı %{r['basari']} | Ort %{r['ort_kazanc']}\n"
    else:
        msg += "Henüz 10+ örnek ve %30+ başarı sağlayan güvenilir desen yok.\n"
    msg += "\n📊 FİLTRE KATKI ANALİZİ\n"
    for r in a["filtre_katki"][:7]:
        msg += f"{r['filtre']}: katkı %{r['katki']} | başarı %{r['basari']} | örnek {r['ornek']}\n"
    nb = a["news_btc_effect"]
    msg += "\n📰 HABER / BTC ETKİSİ\n"
    msg += f"Haberli başarı %{nb['haberli']['basari']} ({nb['haberli']['adet']}) | Habersiz %{nb['habersiz']['basari']} ({nb['habersiz']['adet']})\n"
    msg += f"BTC güçlü başarı %{nb['btc_guclu']['basari']} ({nb['btc_guclu']['adet']}) | BTC zayıf %{nb['btc_zayif']['basari']} ({nb['btc_zayif']['adet']})\n"
    cr = a["catch_rate"]
    msg += "\n🎯 GERÇEK CATCH RATE\n"
    msg += f"%{cr.get('esik',10)}+ piyasa kazananı: {cr.get('kazanan',0)} | Yakalanan: {cr.get('yakalanan',0)} | Kaçan: {cr.get('kacirilan',0)} | Oran %{cr.get('yakalama_orani',0)}\n"
    if cr.get("en_buyuk_kacan"):
        msg += "En büyük kaçanlar: " + ", ".join([f"{x.get('symbol')}(%{v5_round(x.get('degisim24'),1)})" for x in cr["en_buyuk_kacan"][:5]]) + "\n"
    fail = a["failure"]
    msg += "\n📉 BAŞARISIZLIK SEBEBİ\n"
    if fail["adet"]:
        for s in fail["sebepler"][:5]:
            msg += f"{s['sebep']}: %{s['oran']}\n"
    else:
        msg += "Belirgin başarısızlık kümesi yok.\n"
    msg += "\n🤖 AI / PARAMETRE ÖNERİLERİ\n"
    ai_rows = [r for r in a["parametre_onerileri"] if r.get("ornek",0) >= 30 and r.get("fark",0) >= 5][:6]
    if ai_rows:
        for r in ai_rows:
            msg += f"{r['parametre']}: {r['onerilen']} | başarı %{r.get('basari',0)} | fark +%{r.get('fark',0)} | örnek {r.get('ornek',0)}\n"
    else:
        msg += "30+ örnek ve en az +%5 iyileşme sağlayan güvenilir öneri yok.\n"
    bt = a["backtest"]
    msg += "\n🔁 GEÇMİŞTEN SİMÜLASYON\n"
    if bt.get("sonuclar"):
        for r in bt["sonuclar"][:5]:
            msg += f"{r['strateji']}: {r['adet']} | başarı %{r['basari']} | ort %{r['ort_kazanc']}\n"
    else:
        msg += bt.get("not", "Yeterli veri yok.") + "\n"
    ts = a["target_stop_drawdown"]
    msg += "\n🎯 HEDEF / STOP / DRAWDOWN\n"
    msg += f"H1 %{ts['h1_isabet']} | H2 %{ts['h2_isabet']} | Stop %{ts['stop_orani']} | Ort Max %{ts['ort_max_kazanc']} | En kötü DD %{ts['en_kotu_drawdown']}\n"
    msg += "\n📊 DETAY\n"
    msg += "🏅 HALL OF FAME\n"
    hof_rows = [r for r in a["hall_of_fame"] if r.get("adet",0) >= 3][:5]
    if hof_rows:
        for r in hof_rows:
            msg += f"{r['symbol']}: başarı %{r['basari']} | en iyi %{v5_round(r['en_iyi'],1)} | adet {r['adet']}\n"
    else:
        msg += "En az 3 sinyalli yeterli coin yok.\n"
    msg += "\n⏱️ EN İYİ ZAMANLAR\n"
    best_hours = a["time_analysis"].get("saat", [])[:3]
    if best_hours:
        msg += "Saat: " + ", ".join([f"{r['ad']}:%{r['basari']}" for r in best_hours]) + "\n"
    best_days = a["time_analysis"].get("gun", [])[:3]
    if best_days:
        msg += "Gün: " + ", ".join([f"{r['ad']}:%{r['basari']}" for r in best_days]) + "\n"
    msg += "\n📊 SEKTÖR ANALİZİ\n"
    for r in a["sector_analysis"][:5]:
        msg += f"{r['sektor']}: {r['adet']} | başarı %{r['basari']} | ort %{r['ort']}\n"

    try:
        if gun >= 30:
            msg += v5_1_sinyal_sonuc_kalite_raporu(kayitlar)
            msg += v5_1_adaptif_strateji_raporu(kayitlar)
        else:
            msg += "\n📌 V5.1 Haftalık Karar Notu\nBu rapor kısa tutuldu. Strateji/eşik önerileri için /ay komutunu kullan.\n"
    except Exception as e:
        msg += f"\nV5.1 rapor eki hatası: {e}\n"
    msg += "\n📚 V5 çıktı dosyaları: coin_dna_veritabani_v5.json, coin_radar_v5.sqlite, v5_dashboard.html, v5_dashboard.json\n"
    return msg


# Legacy: V5 30 gunluk rapor gonderici pasif hale getirildi.
def legacy_haftalik_rapor_gonder_v5_30gun():
    try:
        v5_sync_all_to_sqlite()
        rapor = v5_report_text(30)
        telegram_gonder(rapor)
    except Exception as e:
        telegram_gonder(f"V5 rapor motoru hata verdi: {e}")
        print("V5 haftalik rapor hatasi:", e)


class V5APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path.startswith("/api/analysis"):
                data = v5_build_analysis(30)
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/api/signals"):
                body = json.dumps(basari_kayitlari[-200:], ensure_ascii=False).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/dashboard"):
                a = v5_build_analysis(30); v5_dashboard_html(a)
                with open(V5_DASHBOARD_HTML, "rb") as f: body = f.read()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
            self.send_response(200); self.send_header("Content-Type", "text/plain; charset=utf-8"); self.end_headers(); self.wfile.write(b"Coin Radar V5 API: /api/analysis /api/signals /dashboard")
        except Exception as e:
            self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode("utf-8"))

    def log_message(self, format, *args):
        return


def v5_start_api_if_enabled():
    if os.getenv("V5_API", "0") != "1":
        return
    try:
        def run():
            server = HTTPServer(("0.0.0.0", V5_API_PORT), V5APIHandler)
            print(f"Coin Radar V5 API aktif: port {V5_API_PORT}")
            server.serve_forever()
        threading.Thread(target=run, daemon=True).start()
    except Exception as e:
        print("V5 API baslatilamadi:", e)


# Bot acilista DB ve opsiyonel API hazir olur. V5_API=1 yapilmazsa web server acilmaz.
v5_sql_init()
v5_start_api_if_enabled()
print(f"{V5_SURUM} aktif. DNA alanı: {len(V5_DNA_ALANLARI)}")


# ============================================================
# COIN RADAR V5.2 FINAL - EKSIK KALAN PROFESYONEL KATMAN
# ============================================================
# Bu blok V5.1'in uzerine kalan eksikleri ekler:
# - Opsiyonel gercek ML modeli (sklearn varsa LogisticRegression)
# - Harici piyasa verisi: Fear&Greed, BTC dominance, global market snapshot
# - BTCTurk gecmis mum indirerek basit backtest/simulasyon
# - Telegram komut paneli: /v5 /bugun /hafta /ay /dna /oneriler /dashboard /backtest
# - Gelismis HTML dashboard
# - Runtime parametre uygulama dosyasi
# - Daha net basarisizlik sebebi ve filtre katkisi raporu
# Sistem guvenligi: hicbiri ana sinyal uretimini bozmaz; hepsi try/except ve env flag ile korunur.

V5_FINAL_SURUM = "V5.2 FINAL PRO + ML + KOMUT + BACKTEST + DIS VERI"


# --- V5 startup compatibility helpers ---
# Bazı V5.2 açılış fonksiyonları bu yardımcı isimleri çağırıyor.
# Ana rapor motorundaki mevcut fonksiyonlara güvenli alias olarak eklenmiştir.
def v5_load_records(gun=None):
    """Başarı kayıtlarını güvenli şekilde döndürür. gun verilirse son X günle sınırlar."""
    try:
        records = list(basari_kayitlari or [])
        if gun:
            start = time.time() - float(gun) * 24 * 60 * 60
            records = [k for k in records if v5_safe_float(k.get("zaman")) >= start]
        return records
    except Exception:
        return []


def v5_star_probability(k, weights=None):
    """Eski V5.2 çağrıları için yıldız olasılığı alias'ı."""
    try:
        return v5_yildiz_probability(k, weights)
    except Exception:
        return 0


def v5_parameter_suggestions(kayitlar=None):
    """Eski V5.2 çağrıları için parametre önerisi alias'ı."""
    try:
        return v5_parameter_optimization(kayitlar or v5_load_records())
    except Exception:
        return []
# --- /V5 startup compatibility helpers ---

V5_ML_MODEL_JSON = "v5_ml_model.json"
V5_EXTERNAL_JSON = "v5_external_market.json"
V5_RUNTIME_PARAMS_JSON = "v5_runtime_params.json"
V5_BACKTEST_JSON = "v5_backtest_ozeti.json"
V5_COMMAND_STATE_JSON = "v5_telegram_command_state.json"
V5_ADVANCED_DASHBOARD_HTML = "v5_advanced_dashboard.html"


def v5_http_json(url, timeout=12, headers=None):
    try:
        r = requests.get(url, timeout=timeout, headers=headers or {"User-Agent": "CoinRadarV5/1.0"})
        if r.status_code >= 400:
            return None
        return r.json()
    except Exception:
        return None


def v5_external_market_snapshot(force=False):
    """Fear&Greed, BTC dominance ve global piyasa verisi. Harici kaynak calismazsa bot bozulmaz."""
    try:
        if (not force) and os.path.exists(V5_EXTERNAL_JSON):
            old = v5_load_json(V5_EXTERNAL_JSON, {})
            if time.time() - v5_safe_float(old.get("updated_at"), 0) < 6 * 3600:
                return old
        out = {"updated_at": time.time(), "fear_greed": None, "btc_dominance": None, "market_change_24h": None, "source_status": {}}
        fg = v5_http_json("https://api.alternative.me/fng/?limit=1&format=json")
        if fg and fg.get("data"):
            one = fg["data"][0]
            out["fear_greed"] = {"value": v5_safe_float(one.get("value")), "label": one.get("value_classification")}
            out["source_status"]["fear_greed"] = "ok"
        else:
            out["source_status"]["fear_greed"] = "unavailable"
        cg = v5_http_json("https://api.coingecko.com/api/v3/global")
        data = (cg or {}).get("data") or {}
        if data:
            out["btc_dominance"] = v5_safe_float((data.get("market_cap_percentage") or {}).get("btc"))
            out["market_change_24h"] = v5_safe_float(data.get("market_cap_change_percentage_24h_usd"))
            out["source_status"]["coingecko_global"] = "ok"
        else:
            out["source_status"]["coingecko_global"] = "unavailable"
        v5_save_json(V5_EXTERNAL_JSON, out)
        return out
    except Exception as e:
        return {"updated_at": time.time(), "error": str(e), "fear_greed": None, "btc_dominance": None, "market_change_24h": None}


V5_ML_FEATURES = [
    "genel_skor", "kalite_skoru", "hacim", "degisim1", "degisim3", "degisim24",
    "haber_skoru", "btc_fark", "btc_fark1", "btc_fark3", "btc_fark24",
    "btc_guc_skoru", "lider_skoru", "guc_skoru", "momentum_score",
    "risk_score", "smart_money_score", "whale_score", "capture_score",
    "hour", "weekday", "entry_pump_pct", "market_btc_3h", "market_btc_24h"
]


def v5_feature_vector(k):
    return [v5_safe_float(k.get(f)) for f in V5_ML_FEATURES]


def v5_train_ml_model(records=None):
    """sklearn varsa gercek LogisticRegression egitir; yoksa agirlikli fallback model uretir."""
    try:
        records = records or v5_load_records()
        rows = [k for k in records if k.get("sonuc") or k.get("h1") or k.get("h2") or k.get("stop")]
        rows = rows[-2000:]
        if len(rows) < 20:
            model = {"type": "fallback", "trained": False, "reason": "en az 20 sonuc kaydi gerekli", "features": V5_ML_FEATURES, "weights": {}, "bias": 0}
            v5_save_json(V5_ML_MODEL_JSON, model)
            return model
        y = [1 if v5_success(k) else 0 for k in rows]
        if len(set(y)) < 2:
            model = {"type": "fallback", "trained": False, "reason": "basarili ve basarisiz ornek birlikte gerekli", "features": V5_ML_FEATURES, "weights": {}, "bias": 0}
            v5_save_json(V5_ML_MODEL_JSON, model)
            return model
        X = [v5_feature_vector(k) for k in rows]
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            scaler = StandardScaler()
            Xs = scaler.fit_transform(X)
            clf = LogisticRegression(max_iter=1000, class_weight="balanced")
            clf.fit(Xs, y)
            model = {
                "type": "sklearn_logistic_regression",
                "trained": True,
                "sample_count": len(rows),
                "positive_count": sum(y),
                "features": V5_ML_FEATURES,
                "coef": [float(x) for x in clf.coef_[0]],
                "intercept": float(clf.intercept_[0]),
                "mean": [float(x) for x in scaler.mean_],
                "scale": [float(x) if float(x) != 0 else 1.0 for x in scaler.scale_],
                "updated_at": time.time()
            }
            v5_save_json(V5_ML_MODEL_JSON, model)
            return model
        except Exception as e:
            # Fallback: basarili ortalama - basarisiz ortalama farkindan agirlik uretir.
            pos = [v5_feature_vector(k) for k in rows if v5_success(k)]
            neg = [v5_feature_vector(k) for k in rows if not v5_success(k)]
            weights = {}
            for i, f in enumerate(V5_ML_FEATURES):
                pm = v5_mean([p[i] for p in pos]); nm = v5_mean([n[i] for n in neg])
                weights[f] = max(-3, min(3, (pm - nm) / (abs(nm) + 1)))
            model = {"type": "fallback_weight_model", "trained": True, "sample_count": len(rows), "positive_count": sum(y), "features": V5_ML_FEATURES, "weights": weights, "bias": 0, "sklearn_error": str(e), "updated_at": time.time()}
            v5_save_json(V5_ML_MODEL_JSON, model)
            return model
    except Exception as e:
        return {"type": "error", "trained": False, "error": str(e), "features": V5_ML_FEATURES}


def v5_ml_probability(k, model=None):
    try:
        model = model or v5_load_json(V5_ML_MODEL_JSON, {}) or v5_train_ml_model()
        if model.get("type") == "sklearn_logistic_regression" and model.get("trained"):
            vals = v5_feature_vector(k)
            mean = model.get("mean") or [0] * len(vals)
            scale = model.get("scale") or [1] * len(vals)
            coef = model.get("coef") or [0] * len(vals)
            z = model.get("intercept", 0)
            for val, m, s, c in zip(vals, mean, scale, coef):
                z += ((val - m) / (s or 1)) * c
            return round(100 / (1 + pow(2.718281828, -z)), 1)
        if model.get("type") == "fallback_weight_model" and model.get("trained"):
            z = 0.0
            weights = model.get("weights") or {}
            for f in V5_ML_FEATURES:
                z += v5_safe_float(k.get(f)) * v5_safe_float(weights.get(f)) / 10
            return round(max(1, min(99, 50 + z)), 1)
        # Model egitilmemisse kural tabanli AI skorunu olasilik gibi kullan.
        return v5_round(k.get("ai_decision_score", v5_star_probability(k)), 1)
    except Exception:
        return v5_round(k.get("ai_decision_score", 50), 1)


def v5_fetch_history(symbol, hours=24*180, resolution=60):
    """BTCTurk graph-api'den parca parca mum indirir. Varsayilan 6 ay/1s."""
    try:
        now = int(time.time())
        step = 24 * 30 * 3600
        start = now - int(hours * 3600)
        all_o, all_h, all_l, all_c, all_v, all_t = [], [], [], [], [], []
        t = start
        while t < now:
            to = min(now, t + step)
            url = f"https://graph-api.btcturk.com/v1/klines/history?symbol={symbol}&resolution={resolution}&from={t}&to={to}"
            d = v5_http_json(url, timeout=15) or {}
            all_o += d.get("o", []) or []
            all_h += d.get("h", []) or []
            all_l += d.get("l", []) or []
            all_c += d.get("c", []) or []
            all_v += d.get("v", []) or []
            all_t += d.get("t", []) or []
            t = to + 1
            time.sleep(0.08)
        return {"o": all_o, "h": all_h, "l": all_l, "c": all_c, "v": all_v, "t": all_t}
    except Exception as e:
        return {"error": str(e), "o": [], "h": [], "l": [], "c": [], "v": [], "t": []}


def v5_backtest_symbol(symbol, hours=24*180):
    """Mevcut mantiga yakin basit gecmis simulasyon. Ana bot karar fonksiyonunu bozmaz."""
    try:
        d = v5_fetch_history(symbol, hours=hours)
        c, h, v, ts = d.get("c", []), d.get("h", []), d.get("v", []), d.get("t", [])
        if len(c) < 60:
            return {"symbol": symbol, "error": "yetersiz veri", "bars": len(c)}
        signals = []
        for i in range(24, len(c)-24):
            try:
                deg1 = ((c[i] - c[i-1]) / c[i-1]) * 100
                deg3 = ((c[i] - c[i-3]) / c[i-3]) * 100
                deg24 = ((c[i] - c[i-24]) / c[i-24]) * 100
                avg_v = sum(v[i-6:i-1]) / 5 if i >= 6 else 0
                hacim = (v[i] / avg_v) if avg_v else 0
                zirve = c[i] >= max(h[max(0, i-12):i] or [c[i]]) * 0.995
                # Basit V5 sinyal profili: hacim+momentum+zirve. Haber/BTC yoksa nötr.
                if hacim >= 8 and deg3 >= 2 and deg24 < 18:
                    future = c[i+1:min(len(c), i+25)]
                    max_gain = max([((x - c[i]) / c[i]) * 100 for x in future] or [0])
                    min_gain = min([((x - c[i]) / c[i]) * 100 for x in future] or [0])
                    signals.append({"t": ts[i] if i < len(ts) else i, "price": c[i], "hacim": round(hacim, 2), "deg3": round(deg3, 2), "deg24": round(deg24, 2), "zirve": zirve, "max_24h": round(max_gain, 2), "min_24h": round(min_gain, 2), "success": max_gain >= 5})
            except Exception:
                continue
        return {"symbol": symbol, "bars": len(c), "signals": len(signals), "success_rate": v5_pct(sum(1 for s in signals if s["success"]), len(signals)), "avg_max_24h": v5_mean([s["max_24h"] for s in signals]), "best": max([s["max_24h"] for s in signals] or [0]), "worst": min([s["min_24h"] for s in signals] or [0]), "sample": signals[-10:]}
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def v5_run_backtest(symbols=None, hours=24*180):
    try:
        symbols = symbols or ["BTCTRY", "ETHTRY", "SOLTRY", "AVAXTRY", "XRPTRY", "FETTRY", "HOTTRY", "AIOZTRY"]
        symbols = [s for s in symbols if s != "BTCTRY"]
        results = [v5_backtest_symbol(s, hours=hours) for s in symbols[:25]]
        ok = [r for r in results if not r.get("error")]
        out = {"updated_at": time.time(), "hours": hours, "symbols": len(results), "avg_success_rate": v5_mean([r.get("success_rate") for r in ok]), "avg_gain": v5_mean([r.get("avg_max_24h") for r in ok]), "results": results}
        v5_save_json(V5_BACKTEST_JSON, out)
        return out
    except Exception as e:
        return {"error": str(e), "results": []}


def v5_apply_runtime_params(suggestions=None):
    """Kodu otomatik degistirmez; guvenli runtime parametre dosyasi yazar. Istenirse ileride ana esikler buradan okunur."""
    try:
        suggestions = suggestions or v5_parameter_suggestions(v5_load_records())
        params = v5_load_json(V5_RUNTIME_PARAMS_JSON, {}) or {}
        params.setdefault("created_at", time.time())
        params["updated_at"] = time.time()
        params["mode"] = os.getenv("V5_AUTO_PARAMETRE", "0")
        params["suggestions"] = suggestions
        if os.getenv("V5_AUTO_PARAMETRE", "0") == "1":
            # Yalnizca makul sinirlar icinde oneriyi aktif ayar olarak yazar.
            active = {}
            for s in suggestions:
                txt = str(s.get("onerilen_ayar", ""))
                if "hacim" in txt.lower() and any(x in txt for x in ["7", "8", "9", "10"]):
                    active["volume_threshold_hint"] = txt
            params["active_hints"] = active
        v5_save_json(V5_RUNTIME_PARAMS_JSON, params)
        return params
    except Exception as e:
        return {"error": str(e)}


def v5_failure_reasons(records=None):
    try:
        records = records or v5_load_records()
        failed = [k for k in records if (k.get("sonuc") or k.get("stop")) and not v5_success(k)]
        if not failed:
            return []
        rules = [
            ("BTC zayıf / coin BTC'den güçlü değil", lambda k: not k.get("btcden_guclu") or v5_safe_float(k.get("btc_fark")) < 0),
            ("Hacim yetersiz veya sürdürülebilir değil", lambda k: v5_safe_float(k.get("hacim")) < 8 or not k.get("volume_strengthening")),
            ("Geç yakalama / ilk mumda fazla gitmiş", lambda k: v5_safe_float(k.get("entry_pump_pct") or k.get("degisim24")) > 12),
            ("Lider onayı yok", lambda k: not k.get("leader")),
            ("Zirve onayı yok", lambda k: not k.get("near_high")),
            ("Haber desteği yok veya negatif", lambda k: v5_safe_float(k.get("haber_skoru")) <= 0),
            ("Risk puanı yüksek", lambda k: v5_safe_float(k.get("risk_score")) >= 65),
        ]
        out = []
        for name, fn in rules:
            cnt = sum(1 for k in failed if fn(k))
            out.append({"sebep": name, "adet": cnt, "oran": v5_pct(cnt, len(failed))})
        return sorted(out, key=lambda x: x["adet"], reverse=True)
    except Exception:
        return []


def v5_advanced_dashboard_html(analysis=None):
    try:
        analysis = analysis or v5_build_analysis(30)
        ext = v5_external_market_snapshot()
        model = v5_train_ml_model(v5_load_records())
        failures = v5_failure_reasons(v5_load_records())
        params = v5_apply_runtime_params(analysis.get("parametre_onerileri") or [])
        html = """<!doctype html><html><head><meta charset='utf-8'><title>Coin Radar V5 Final</title>
<style>body{font-family:Arial;margin:0;background:#0d1117;color:#e6edf3}.wrap{max-width:1200px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}.card{background:#161b22;border:1px solid #30363d;padding:16px;border-radius:14px}.big{font-size:30px;font-weight:bold}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #30363d;padding:8px;text-align:left}.ok{color:#7ee787}.warn{color:#f2cc60}.bad{color:#ff7b72}small{color:#8b949e}</style></head><body><div class='wrap'>"""
        html += f"<h1>Coin Radar {V5_FINAL_SURUM}</h1><small>Güncelleme: {time.strftime('%Y-%m-%d %H:%M:%S')}</small>"
        html += "<div class='grid'>"
        html += f"<div class='card'><div>Toplam Sinyal</div><div class='big'>{analysis.get('toplam_sinyal',0)}</div></div>"
        html += f"<div class='card'><div>Başarı</div><div class='big ok'>%{analysis.get('basari_orani',0)}</div></div>"
        html += f"<div class='card'><div>Catch Rate</div><div class='big warn'>%{(analysis.get('catch_rate') or {}).get('catch_rate',0)}</div></div>"
        html += f"<div class='card'><div>ML Model</div><div class='big'>{model.get('type','-')}</div><small>Örnek: {model.get('sample_count',0)}</small></div>"
        fg = ext.get('fear_greed') or {}
        html += f"<div class='card'><div>Fear & Greed</div><div class='big'>{fg.get('value','-')}</div><small>{fg.get('label','')}</small></div>"
        html += f"<div class='card'><div>BTC Dominance</div><div class='big'>%{v5_round(ext.get('btc_dominance'),1)}</div></div>"
        html += "</div>"
        def table(title, rows, cols):
            nonlocal html
            html += f"<div class='card'><h2>{title}</h2><table><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
            for r in rows[:20]:
                html += "<tr>" + "".join(f"<td>{r.get(c,'')}</td>" for c in cols) + "</tr>"
            html += "</table></div>"
        table("Kategori Ligi", analysis.get("kategori_ligi") or [], ["kategori","adet","basari","h2","ort_getiri"])
        table("En Karlı Coinler", analysis.get("coin_hall_of_fame") or [], ["symbol","adet","basari","h2","en_iyi","ort"])
        table("Başarısızlık Sebepleri", failures, ["sebep","adet","oran"])
        table("Parametre Önerileri", params.get("suggestions") or [], ["konu","mevcut","onerilen_ayar","neden"])
        html += "</div></body></html>"
        with open(V5_ADVANCED_DASHBOARD_HTML, "w", encoding="utf-8") as f:
            f.write(html)
        return V5_ADVANCED_DASHBOARD_HTML
    except Exception as e:
        print("V5 advanced dashboard hatasi:", e)
        return None


# V5.2: Var olan API handler'i gelismis endpointlerle genislet.
try:
    _V5OldAPIHandler = V5APIHandler
    class V5APIHandler(_V5OldAPIHandler):
        def do_GET(self):
            try:
                if self.path.startswith("/api/external"):
                    body = json.dumps(v5_external_market_snapshot(force=True), ensure_ascii=False).encode("utf-8")
                    self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
                if self.path.startswith("/api/ml"):
                    body = json.dumps(v5_train_ml_model(v5_load_records()), ensure_ascii=False).encode("utf-8")
                    self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
                if self.path.startswith("/api/backtest"):
                    body = json.dumps(v5_run_backtest(hours=24*30), ensure_ascii=False).encode("utf-8")
                    self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
                if self.path.startswith("/dashboard/advanced"):
                    v5_advanced_dashboard_html(v5_build_analysis(30))
                    with open(V5_ADVANCED_DASHBOARD_HTML, "rb") as f: body = f.read()
                    self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
                return super().do_GET()
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode("utf-8"))
except Exception as e:
    print("V5 API override hatasi:", e)


def v5_report_text(gun=7):
    a = v5_build_analysis(gun)
    ext = v5_external_market_snapshot()
    model = v5_train_ml_model(v5_load_records())
    v5_advanced_dashboard_html(a)
    msg = v5_professional_report_text(gun)
    msg += "\n🧠 V5.3 ÖĞRENME MOTORU EKLER\n"
    msg += f"ML model: {model.get('type')} | Eğitim: {'✅' if model.get('trained') else '❌'} | Örnek: {model.get('sample_count',0)}\n"
    fg = ext.get('fear_greed') or {}
    msg += f"Fear&Greed: {fg.get('value','-')} {fg.get('label','')} | BTC Dominance: %{v5_round(ext.get('btc_dominance'),1)}\n"
    failures = v5_failure_reasons(v5_load_records())[:3]
    if failures:
        msg += "Başarısızlık ana sebepleri: " + ", ".join([f"{x['sebep']} %{x['oran']}" for x in failures]) + "\n"
    msg += "Komutlar: /v5 /bugun /hafta /ay /dna /oneriler /dashboard /backtest\n"
    msg += "Dosyalar: v5_advanced_dashboard.html, v5_ml_model.json, v5_external_market.json, v5_backtest_ozeti.json\n"
    return msg


# Override: haftalik rapor V5.2 final rapor metnini gonderir.
def haftalik_rapor_gonder():
    """Haftalık raporu kalıcı zaman takibi ve görünür hata loglarıyla gönderir."""
    global son_haftalik_rapor, _son_rapor_kontrol_logu
    simdi = time.time()
    gecen = simdi - float(son_haftalik_rapor or 0)
    kalan = max(0, HAFTALIK_RAPOR_SURESI - gecen)

    # Her taramada log yağdırmamak için kontrol durumunu saatte bir yaz.
    if simdi - _son_rapor_kontrol_logu >= 3600:
        print("📊 Haftalık rapor kontrolü")
        print("📅 Son rapor:", _v5_zaman_yazi(son_haftalik_rapor))
        if kalan > 0:
            print(f"⏳ Kalan süre: {int(kalan // 86400)} gün {int((kalan % 86400) // 3600)} saat {int((kalan % 3600) // 60)} dk")
        else:
            print("⏳ Rapor zamanı geldi.")
        _son_rapor_kontrol_logu = simdi

    if kalan > 0:
        return False

    # Otomatik haftalık rapor boş veriyle gönderilmesin. /hafta komutu yine her zaman çalışır.
    try:
        son7 = [k for k in v5_load_records() if v5_ts(k) >= simdi - HAFTALIK_RAPOR_SURESI]
    except Exception:
        son7 = []
    if not son7:
        print("📊 Haftalık rapor zamanı geldi ama son 7 günde V5 sinyali yok; otomatik rapor gönderilmedi.")
        son_haftalik_rapor = simdi
        _v5_rapor_state_kaydet(simdi)
        return False

    try:
        print("🧠 Haftalık V5 raporu hazırlanıyor...")
        rapor_metni = v5_report_text(7)
        print(f"✅ V5 raporu hazır. Uzunluk: {len(rapor_metni)} karakter")
        gonderildi = telegram_gonder(rapor_metni)
        if not gonderildi:
            print("❌ Haftalık rapor gönderilemedi; zaman damgası güncellenmedi.")
            return False
        son_haftalik_rapor = simdi
        _v5_rapor_state_kaydet(simdi)
        print("✅ Haftalık rapor başarıyla gönderildi ve zamanı kalıcı kaydedildi.")
        return True
    except Exception as e:
        print("❌ V5.3 haftalık rapor hatası:", repr(e))
        # Hata mesajını Telegram'a göndermeye çalış, fakat ana döngüyü durdurma.
        try:
            telegram_gonder(f"V5.3 rapor motoru hata verdi: {e}")
        except Exception as bildirim_hatasi:
            print("❌ Rapor hata bildirimi de gönderilemedi:", bildirim_hatasi)
        return False


def v5_telegram_send_to(chat_id, text):
    try:
        if not BOT_TOKEN:
            return False
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        chunks, kalan = [], str(text)
        while len(kalan) > 3900:
            cut = kalan.rfind("\n", 0, 3900)
            if cut == -1: cut = 3900
            chunks.append(kalan[:cut]); kalan = kalan[cut:].lstrip()
        chunks.append(kalan)
        for ch in chunks:
            requests.post(url, json={"chat_id": chat_id, "text": ch}, timeout=15)
        return True
    except Exception as e:
        print("V5 command send hatasi:", e)
        return False


def v5_handle_command(text):
    t = (text or "").strip().lower()
    if t in ["/v5", "/start", "/help"]:
        return "🧠 Coin Radar V5 Komutları\n/bugun - günlük özet\n/hafta - 7 gün\n/ay - 30 gün\n/dna - DNA özeti\n/oneriler - parametre önerileri\n/dashboard - panel dosyaları\n/backtest - 30 günlük hızlı simülasyon"
    if t == "/bugun": return v5_report_text(1)
    if t == "/hafta": return v5_report_text(7)
    if t == "/ay": return v5_report_text(30)
    if t == "/dna":
        a = v5_build_analysis(30)
        return "🧬 DNA Özeti\n" + json.dumps({"toplam": a.get("toplam_sinyal"), "pattern": a.get("pattern_discovery", [])[:5], "hall_of_fame": a.get("coin_hall_of_fame", [])[:5]}, ensure_ascii=False, indent=2)
    if t == "/oneriler":
        a = v5_build_analysis(30); params = v5_apply_runtime_params(a.get("parametre_onerileri") or [])
        rows = params.get("suggestions") or []
        if not rows: return "Şu an yeterli veriyle parametre önerisi yok."
        return "🤖 Parametre Önerileri\n" + "\n".join([f"- {x.get('konu')}: {x.get('onerilen_ayar')} ({x.get('neden')})" for x in rows[:10]])
    if t == "/dashboard":
        v5_advanced_dashboard_html(v5_build_analysis(30))
        return "📊 Dashboard üretildi: v5_advanced_dashboard.html\nAPI açıksa: /dashboard/advanced"
    if t == "/backtest":
        bt = v5_run_backtest(hours=24*30)
        return f"📈 30 Gün Backtest\nSembol: {bt.get('symbols')} | Ortalama başarı: %{v5_round(bt.get('avg_success_rate'),1)} | Ortalama max getiri: %{v5_round(bt.get('avg_gain'),1)}\nDetay: v5_backtest_ozeti.json"
    return None


def v5_start_telegram_commands_if_enabled():
    if os.getenv("V5_TELEGRAM_COMMANDS", "0") != "1":
        return
    if not BOT_TOKEN:
        return
    try:
        state = v5_load_json(V5_COMMAND_STATE_JSON, {}) or {}
        offset = int(state.get("offset", 0) or 0)
        def loop():
            nonlocal offset
            while True:
                try:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
                    data = requests.get(url, params={"timeout": 25, "offset": offset + 1}, timeout=35).json()
                    for upd in data.get("result", []) or []:
                        offset = max(offset, int(upd.get("update_id", 0)))
                        msg = upd.get("message") or upd.get("edited_message") or {}
                        chat = msg.get("chat") or {}
                        chat_id = chat.get("id")
                        text = msg.get("text") or ""
                        answer = v5_handle_command(text)
                        if answer and chat_id:
                            v5_telegram_send_to(chat_id, answer)
                    v5_save_json(V5_COMMAND_STATE_JSON, {"offset": offset, "updated_at": time.time()})
                except Exception as e:
                    print("V5 telegram command loop hatasi:", e)
                    time.sleep(10)
        threading.Thread(target=loop, daemon=True).start()
        print("V5 Telegram komut paneli aktif.")
    except Exception as e:
        print("V5 Telegram komut paneli baslatilamadi:", e)


# Acilista dis veri, ML ve dashboard hazirlanir; dis kaynak hatasi botu durdurmaz.
try:
    v5_external_market_snapshot()
    v5_train_ml_model(v5_load_records())
    v5_apply_runtime_params(v5_parameter_suggestions(v5_load_records()))
    v5_advanced_dashboard_html(v5_build_analysis(30))
    v5_start_telegram_commands_if_enabled()
    print(f"{V5_FINAL_SURUM} aktif.")
except Exception as e:
    print("V5.2 final acilis hazirligi hatasi:", e)


# ================================================================
# COIN RADAR V5.3 - RAPOR DOGRULUK + DEVAM GUCU + OGRENME MOTORU
# Sinyal esikleri degistirilmez. Bu katman olcum ve raporlama icindir.
# ================================================================
V5_OGRENME_MIN_ORNEK = int(os.getenv("V5_OGRENME_MIN_ORNEK", "20"))
V5_PATTERN_MIN_ORNEK = int(os.getenv("V5_PATTERN_MIN_ORNEK", "10"))


def v5_bool(k, *keys):
    for key in keys:
        if key in k and k.get(key) is not None:
            return bool(k.get(key))
    return False


def v5_field(k, *keys, default=0.0):
    for key in keys:
        if key in k and k.get(key) is not None:
            return v5_safe_float(k.get(key), default)
    return default


def v5_nihai_sonuc(k):
    """Her sinyali tek bir nihai sinifa ayirir."""
    if v5_bool(k, "h2") or str(k.get("sonuc", "")).lower() == "h2":
        return "h2"
    if v5_bool(k, "h1") or str(k.get("sonuc", "")).lower() == "h1":
        return "h1"
    if v5_bool(k, "stop") or str(k.get("sonuc", "")).lower() == "stop":
        return "stop"
    if str(k.get("sonuc", "")).lower() in ("kapandi", "suresi_doldu", "expired"):
        return "suresi_doldu"
    return "aktif"


def v5_devam_gucu_hesapla(k):
    """0-100 devam gucu. Sinyali filtrelemez; sadece olcer."""
    d1 = v5_field(k, "degisim1")
    d3 = v5_field(k, "degisim3")
    d24 = v5_field(k, "degisim24")
    hacim = v5_field(k, "hacim")
    btc_fark = v5_field(k, "btc_fark", "btc_fark3")
    lider = v5_field(k, "lider_skoru")
    gec_pump = v5_field(k, "gec_pump_puan")

    puan = 35.0
    puan += min(max(d3, 0), 8) * 2.0
    puan += 10 if v5_bool(k, "momentum_gucleniyor") else 0
    puan += 10 if v5_bool(k, "hacim_gucleniyor", "volume_strengthening") else 0
    puan += 8 if v5_bool(k, "btc_guclu", "btcden_guclu") else -10
    puan += min(max(btc_fark, -3), 5) * 2
    puan += 8 if (v5_bool(k, "lider_guclu") or lider >= 7) else (4 if (v5_bool(k, "lider_mi", "leader") or lider >= 5) else -5)
    puan += 6 if v5_bool(k, "zirve_teyidi", "near_high") else 0
    if 5 <= hacim <= 15:
        puan += 8
    elif 15 < hacim <= 30:
        puan += 4
    elif hacim > 50:
        puan -= 5
    elif hacim < 2:
        puan -= 8
    if d1 > 6:
        puan -= min(12, (d1 - 6) * 2)
    if d24 > 20:
        puan -= min(15, (d24 - 20) * 0.6)
    if gec_pump > 0:
        puan -= min(15, gec_pump * 2)
    if hacim >= 10 and d3 < 1:
        puan -= 8
    return int(max(0, min(100, round(puan))))


def v5_devam_gucu_seviye(puan):
    if puan >= 80: return "Cok Guclu"
    if puan >= 65: return "Guclu"
    if puan >= 50: return "Orta"
    return "Riskli"


# Yeni DNA kaydina devam gucu ekle.
_v5_make_dna_v52 = v5_make_dna
def v5_make_dna(symbol, a, simdi):
    dna = _v5_make_dna_v52(symbol, a, simdi)
    puan = v5_devam_gucu_hesapla(dna)
    dna["devam_gucu"] = puan
    dna["devam_gucu_seviye"] = v5_devam_gucu_seviye(puan)
    dna["nihai_sonuc"] = v5_nihai_sonuc(dna)
    return dna


def basari_kaydi_guncelle(symbol, fiyat, durum=None, h1=False, h2=False, stop=False):
    """Max/min performansi ve tek nihai sonucu guvenilir bicimde gunceller."""
    simdi = time.time()
    for k in reversed(basari_kayitlari):
        if k.get("symbol") != symbol:
            continue
        # H2 kesin terminaldir. H1 sonrasi stop nihai sonucu bozamaz.
        if v5_nihai_sonuc(k) == "h2":
            return
        giris = v5_safe_float(k.get("giris"), fiyat)
        if giris:
            kazanc = ((fiyat - giris) / giris) * 100
            k["son_fiyat"] = fiyat
            k["son_kazanc"] = round(kazanc, 4)
            k["max_kazanc"] = round(max(v5_safe_float(k.get("max_kazanc")), kazanc), 4)
            # Ilk kayitlarda min 0 olabilir; negatif hareketleri mutlaka sakla.
            onceki_min = v5_safe_float(k.get("min_kazanc"), 0.0)
            k["min_kazanc"] = round(min(onceki_min, kazanc), 4)
            k["max_fiyat"] = max(v5_safe_float(k.get("max_fiyat"), giris), fiyat)
            onceki_min_fiyat = v5_safe_float(k.get("min_fiyat"), giris) or giris
            k["min_fiyat"] = min(onceki_min_fiyat, fiyat)
        if durum:
            k["kategori_son"] = durum
        if h1 and not k.get("h1"):
            k["h1"] = True
            k["h1_zaman"] = simdi
            k["h1_sure_saat"] = round((simdi - v5_safe_float(k.get("zaman"), simdi)) / 3600, 2)
            k["sonuc"] = "h1"
        if h2 and not k.get("h2"):
            k["h2"] = True
            k["h2_zaman"] = simdi
            k["h2_sure_saat"] = round((simdi - v5_safe_float(k.get("zaman"), simdi)) / 3600, 2)
            k["sonuc"] = "h2"
            k["stop"] = False
        if stop:
            k["stop_zaman"] = simdi
            k["stop_sure_saat"] = round((simdi - v5_safe_float(k.get("zaman"), simdi)) / 3600, 2)
            if k.get("h1") or k.get("h2"):
                k["hedef_sonrasi_stop"] = True
                k["hedef_sonrasi_stop_kazanc"] = k.get("son_kazanc", 0)
                k["stop"] = False
                k["sonuc"] = "h2" if k.get("h2") else "h1"
            else:
                k["stop"] = True
                k["sonuc"] = "stop"
        k["nihai_sonuc"] = v5_nihai_sonuc(k)
        if "devam_gucu" not in k:
            k["devam_gucu"] = v5_devam_gucu_hesapla(k)
            k["devam_gucu_seviye"] = v5_devam_gucu_seviye(k["devam_gucu"])
        basari_db_kaydet(basari_kayitlari)
        return


def v5_pattern_discovery(kayitlar, top=8):
    groups = {}
    for k in kayitlar:
        key = k.get("pattern_key") or v5_pattern_key(k)
        groups.setdefault(key, []).append(k)
    rows = []
    for key, arr in groups.items():
        if len(arr) < V5_PATTERN_MIN_ORNEK:
            continue
        rows.append({
            "pattern": key, "adet": len(arr),
            "basari": v5_pct(sum(v5_success(k) for k in arr), len(arr)),
            "h2": v5_pct(sum(v5_big_success(k) for k in arr), len(arr)),
            "ort_kazanc": v5_mean([k.get("max_kazanc") for k in arr]),
            "risk": v5_mean([k.get("risk_puani") for k in arr]),
        })
    return sorted(rows, key=lambda x: (x["basari"], x["h2"], x["adet"]), reverse=True)[:top]


def v5_parameter_optimization(kayitlar):
    """Az ornekle esik onermez; mevcut basariya anlamli fark arar."""
    suggestions = []
    baseline = v5_pct(sum(v5_success(k) for k in kayitlar), len(kayitlar))
    tests = [
        ("hacim_esigi", "hacim", [5, 6, 7, 8, 10, 12, 15]),
        ("skor_esigi", "skor", [8, 10, 12, 14, 16, 18, 20]),
        ("kalite_esigi", "kalite", [5, 6, 7, 8, 9, 10, 12]),
        ("rsi_ust_limit", "rsi", [62, 65, 68, 70, 72, 75, 80]),
        ("risk_ust_limit", "risk_puani", [40, 45, 50, 55, 60, 65, 70]),
    ]
    for name, field, values in tests:
        best = None
        for v in values:
            arr = ([k for k in kayitlar if v5_safe_float(k.get(field)) <= v]
                   if name.endswith("ust_limit") else
                   [k for k in kayitlar if v5_safe_float(k.get(field)) >= v])
            if len(arr) < V5_OGRENME_MIN_ORNEK:
                continue
            rate = v5_pct(sum(v5_success(k) for k in arr), len(arr))
            h2r = v5_pct(sum(v5_big_success(k) for k in arr), len(arr))
            fark = round(rate - baseline, 1)
            if fark < 3.0:
                continue
            score = fark + h2r * 0.25 + min(len(arr), 100) * 0.03
            row = {"parametre": name, "onerilen": v, "ornek": len(arr), "basari": rate, "h2": h2r, "fark": fark, "skor": round(score, 2), "guven": "orta" if len(arr) < 50 else "guclu"}
            if best is None or row["skor"] > best["skor"]:
                best = row
        if best:
            suggestions.append(best)
    v5_save_json(V5_PARAMETRE_JSON, suggestions)
    return sorted(suggestions, key=lambda x: x.get("skor", 0), reverse=True)


def v5_failure_analysis(kayitlar):
    fails = [k for k in kayitlar if v5_nihai_sonuc(k) in ("stop", "suresi_doldu")]
    if not fails:
        return {"adet": 0, "sebepler": []}
    checks = [
        ("Başarısızlarda BTC gücü yok", lambda k: not v5_bool(k, "btc_guclu", "btcden_guclu")),
        ("Başarısızlarda lider onayı yok", lambda k: not (v5_bool(k, "lider_mi", "leader") or v5_field(k, "lider_skoru") >= 5)),
        ("Başarısızlarda zirve teyidi yok", lambda k: not v5_bool(k, "zirve_teyidi", "near_high")),
        ("Başarısızlarda geç yakalama", lambda k: k.get("yakalama_tipi") == "gec"),
        ("Başarısızlarda hacim 8x altında", lambda k: v5_field(k, "hacim") < 8),
        ("Başarısızlarda haber desteği yok", lambda k: not v5_bool(k, "haber_var") and v5_field(k, "haber", "haber_skoru") <= 0),
        ("Başarısızlarda risk puanı yüksek", lambda k: v5_field(k, "risk_puani", "risk_score") >= 55),
    ]
    causes=[]
    for ad, fn in checks:
        cnt=sum(1 for k in fails if fn(k))
        if cnt:
            causes.append({"sebep":ad,"adet":cnt,"oran":v5_pct(cnt,len(fails))})
    return {"adet":len(fails),"sebepler":sorted(causes,key=lambda x:x["oran"],reverse=True)}


def v5_failure_reasons(records=None):
    records = records or v5_load_records()
    result = v5_failure_analysis(records)
    return result.get("sebepler", [])


def v5_target_stop_drawdown(kayitlar):
    final = [v5_nihai_sonuc(k) for k in kayitlar]
    mins = [v5_safe_float(k.get("min_kazanc")) for k in kayitlar if k.get("min_kazanc") is not None]
    return {
        "h1_isabet": v5_pct(sum(x in ("h1", "h2") for x in final), len(kayitlar)),
        "h2_isabet": v5_pct(sum(x == "h2" for x in final), len(kayitlar)),
        "stop_orani": v5_pct(sum(x == "stop" for x in final), len(kayitlar)),
        "aktif_orani": v5_pct(sum(x == "aktif" for x in final), len(kayitlar)),
        "ort_max_kazanc": v5_mean([k.get("max_kazanc") for k in kayitlar]),
        "ort_min_kazanc": v5_mean(mins),
        "en_kotu_drawdown": min(mins or [0]),
    }


def v5_devam_gucu_analizi(kayitlar):
    bands=[(80,101,"80-100"),(65,80,"65-79"),(50,65,"50-64"),(0,50,"0-49")]
    rows=[]
    for lo,hi,label in bands:
        arr=[k for k in kayitlar if lo <= v5_safe_float(k.get("devam_gucu", v5_devam_gucu_hesapla(k))) < hi]
        if arr:
            rows.append({"band":label,"adet":len(arr),"basari":v5_pct(sum(v5_success(k) for k in arr),len(arr)),"h2":v5_pct(sum(v5_big_success(k) for k in arr),len(arr)),"ort":v5_mean([k.get("max_kazanc") for k in arr])})
    return rows


def v5_kazanan_dna(kayitlar):
    wins=[k for k in kayitlar if v5_nihai_sonuc(k) in ("h1","h2")]
    if not wins: return {"adet":0}
    def oran(*keys): return v5_pct(sum(v5_bool(k,*keys) for k in wins),len(wins))
    cats={}
    for k in wins: cats[k.get("kategori","Bilinmiyor")]=cats.get(k.get("kategori","Bilinmiyor"),0)+1
    return {
        "adet":len(wins), "btc":oran("btc_guclu","btcden_guclu"), "lider":oran("lider_mi","leader"),
        "zirve":oran("zirve_teyidi","near_high"), "mom_up":oran("momentum_gucleniyor"), "vol_up":oran("hacim_gucleniyor","volume_strengthening"),
        "ort_devam":v5_mean([k.get("devam_gucu",v5_devam_gucu_hesapla(k)) for k in wins]), "ort_skor":v5_mean([k.get("skor") for k in wins]),
        "ort_hacim":v5_mean([k.get("hacim") for k in wins]), "ort_max":v5_mean([k.get("max_kazanc") for k in wins]),
        "en_iyi_kategori":max(cats,key=cats.get) if cats else "-"
    }


def v5_skor_basari_analizi(kayitlar):
    bands=[(0,15,"0-14.9"),(15,20,"15-19.9"),(20,25,"20-24.9"),(25,30,"25-29.9"),(30,10**9,"30+")]
    rows=[]
    for lo,hi,label in bands:
        arr=[k for k in kayitlar if lo <= v5_field(k,"skor") < hi]
        if arr:
            finals=[v5_nihai_sonuc(k) for k in arr]
            rows.append({"band":label,"adet":len(arr),"basari":v5_pct(sum(x in ("h1","h2") for x in finals),len(arr)),"h2":v5_pct(sum(x=="h2" for x in finals),len(arr)),"stop":v5_pct(sum(x=="stop" for x in finals),len(arr)),"ort":v5_mean([k.get("max_kazanc") for k in arr])})
    return rows


def v5_haftalik_degerlendirme(analysis):
    notes=[]
    cats=[x for x in analysis.get("kategori_ligi",[]) if x.get("adet",0)>=V5_PATTERN_MIN_ORNEK]
    if cats:
        best=max(cats,key=lambda x:(x.get("h2",0),x.get("basari",0)))
        notes.append(f"En güçlü kategori {best['kategori']} (başarı %{best['basari']}, H2 %{best['h2']}, {best['adet']} örnek).")
    dg=[x for x in analysis.get("devam_gucu_analizi",[]) if x.get("adet",0)>=V5_PATTERN_MIN_ORNEK]
    if dg:
        best=max(dg,key=lambda x:(x.get("h2",0),x.get("basari",0)))
        notes.append(f"En verimli Devam Gücü bandı {best['band']} (başarı %{best['basari']}, H2 %{best['h2']}).")
    cr=analysis.get("catch_rate",{})
    notes.append(f"Piyasa yakalama oranı %{cr.get('yakalama_orani',0)}; kaçan coin sayısı {cr.get('kacirilan',0)}.")
    if not analysis.get("parametre_onerileri"):
        notes.append(f"Eşik değişikliği önerilmedi: en az {V5_OGRENME_MIN_ORNEK} örnek ve +%3 başarı farkı şartı sağlanmadı.")
    return notes


_v5_build_analysis_v52 = v5_build_analysis
def v5_build_analysis(gun=30):
    a = _v5_build_analysis_v52(gun)
    start=time.time()-gun*86400
    kayitlar=[k for k in basari_kayitlari if v5_safe_float(k.get("zaman"))>=start]
    for k in kayitlar:
        k["nihai_sonuc"]=v5_nihai_sonuc(k)
        if "devam_gucu" not in k:
            k["devam_gucu"]=v5_devam_gucu_hesapla(k)
            k["devam_gucu_seviye"]=v5_devam_gucu_seviye(k["devam_gucu"])
    a["devam_gucu_analizi"]=v5_devam_gucu_analizi(kayitlar)
    a["kazanan_dna"]=v5_kazanan_dna(kayitlar)
    a["skor_basari"]=v5_skor_basari_analizi(kayitlar)
    a["haftalik_degerlendirme"]=v5_haftalik_degerlendirme(a)
    a["target_stop_drawdown"]=v5_target_stop_drawdown(kayitlar)
    a["failure"]=v5_failure_analysis(kayitlar)
    a["pattern_discovery"]=v5_pattern_discovery(kayitlar)
    a["parametre_onerileri"]=v5_parameter_optimization(kayitlar)
    v5_save_json(V5_ANALIZ_JSON,a)
    v5_save_json(V5_DASHBOARD_JSON,a)
    return a


_v5_professional_report_text_v52 = v5_professional_report_text
def v5_professional_report_text(gun=30):
    msg=_v5_professional_report_text_v52(gun)
    a=v5_build_analysis(gun)
    rows=a.get("devam_gucu_analizi",[])
    msg += "\n🚀 DEVAM GÜCÜ ANALİZİ\n"
    if rows:
        for r in rows: msg += f"{r['band']}: {r['adet']} | Başarı %{r['basari']} | H2 %{r['h2']} | Ort %{r['ort']}\n"
    else: msg += "Henüz yeterli veri yok.\n"
    d=a.get("kazanan_dna",{})
    msg += "\n🧬 7 GÜNÜN KAZANANLARININ DNA'SI\n"
    if d.get("adet"):
        msg += f"Kazanan: {d['adet']} | BTC güçlü %{d['btc']} | Lider %{d['lider']} | Zirve %{d['zirve']}\n"
        msg += f"Mom↑ %{d['mom_up']} | Hacim↑ %{d['vol_up']} | Ort Devam {d['ort_devam']} | Ort Skor {d['ort_skor']} | Ort Hacim {d['ort_hacim']}x\n"
        msg += f"En sık kategori: {d['en_iyi_kategori']} | Ort Max %{d['ort_max']}\n"
    else: msg += "Henüz kazanan kaydı yok.\n"
    msg += "\n📈 SKOR BAŞARI ANALİZİ\n"
    for r in a.get("skor_basari",[]):
        msg += f"{r['band']}: {r['adet']} | Başarı %{r['basari']} | H2 %{r['h2']} | Stop %{r['stop']} | Ort %{r['ort']}\n"
    msg += "\n📅 HAFTALIK DEĞERLENDİRME\n"
    for note in a.get("haftalik_degerlendirme",[]): msg += f"• {note}\n"
    return msg




# === V5.4 COMMIT 2: KACIRILAN COIN + FLASH CRASH + ILK DAKIKA OGRENME MOTORU ===
V5_COMMIT2_MIN_PATTERN_ORNEK = 10
V5_COMMIT2_MIN_HALL_ORNEK = 3
V5_COMMIT2_MIN_AI_ORNEK = 30
V5_COMMIT2_MIN_AI_FARK = 5.0
V5_FLASH_CRASH_ESIK = -5.0
V5_FLASH_TOPARLANMA_ESIK = 3.0
V5_PERFORMANS_DAKIKALARI = (5, 15, 30, 60)


def _v5c2_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _v5c2_bool(k, *keys):
    for key in keys:
        if key in k and k.get(key) is not None:
            return bool(k.get(key))
    return False


def _v5c2_market_by_symbol(gun=7):
    baslangic = time.time() - gun * 86400
    gruplar = {}
    for k in piyasa_kayitlari:
        if _v5c2_float(k.get('zaman')) < baslangic:
            continue
        s = k.get('symbol')
        if not s:
            continue
        gruplar.setdefault(s, []).append(k)
    for s in gruplar:
        gruplar[s].sort(key=lambda x: _v5c2_float(x.get('zaman')))
    return gruplar


def _v5c2_kacma_sebepleri(k):
    sebepler = []
    hacim = _v5c2_float(k.get('hacim'))
    momentum = _v5c2_float(k.get('degisim3'))
    lider = _v5c2_bool(k, 'lider_mi') or _v5c2_float(k.get('lider_skoru')) >= 5
    btc_ok = _v5c2_bool(k, 'btc_guclu', 'btcden_guclu')
    zirve = _v5c2_bool(k, 'zirve_teyidi', 'zirve_yakin', 'yeni_zirve')
    gec = int(_v5c2_float(k.get('gec_pump_puan'))) >= 3

    if not btc_ok:
        sebepler.append('BTC filtresi')
    if not lider:
        sebepler.append('Lider filtresi')
    if hacim < 5:
        sebepler.append('Hacim filtresi')
    elif hacim < 8:
        sebepler.append('Hacim/kalite eşiği')
    if momentum < 2:
        sebepler.append('Momentum yetersiz')
    if not zirve:
        sebepler.append('Zirve teyidi yok')
    if gec:
        sebepler.append('Geç hareket riski')
    if not sebepler:
        sebepler.append('Birleşik skor/kategori eşiği')
    return sebepler


def v5_kacirilan_coin_motoru(gun=7, esik=10):
    """Kazanan fakat zamanında sinyal almayan coinleri ve olası eleme nedenlerini açıklar."""
    try:
        baslangic = time.time() - gun * 86400
        market = [k for k in piyasa_kayitlari if _v5c2_float(k.get('zaman')) >= baslangic]
        coin_ozet = {}
        for k in market:
            s = k.get('symbol')
            if not s:
                continue
            if s not in coin_ozet or _v5c2_float(k.get('degisim24')) > _v5c2_float(coin_ozet[s].get('degisim24')):
                coin_ozet[s] = k

        kazananlar = [k for k in coin_ozet.values() if _v5c2_float(k.get('degisim24')) >= esik]
        sinyaller = {}
        for b in basari_kayitlari:
            z = _v5c2_float(b.get('zaman'))
            if z < baslangic:
                continue
            s = b.get('symbol')
            if s and (s not in sinyaller or z < sinyaller[s]):
                sinyaller[s] = z

        kacirilan = []
        neden_sayilari = {}
        for k in kazananlar:
            s = k.get('symbol')
            hareket_zamani = _v5c2_float(k.get('zaman'))
            if s in sinyaller and sinyaller[s] <= hareket_zamani:
                continue
            sebepler = _v5c2_kacma_sebepleri(k)
            for sebep in sebepler:
                neden_sayilari[sebep] = neden_sayilari.get(sebep, 0) + 1
            kacirilan.append({
                'symbol': s,
                'degisim24': round(_v5c2_float(k.get('degisim24')), 2),
                'hacim': round(_v5c2_float(k.get('hacim')), 2),
                'momentum': round(_v5c2_float(k.get('degisim3')), 2),
                'btc_guclu': _v5c2_bool(k, 'btc_guclu', 'btcden_guclu'),
                'lider': _v5c2_bool(k, 'lider_mi') or _v5c2_float(k.get('lider_skoru')) >= 5,
                'zirve': _v5c2_bool(k, 'zirve_teyidi', 'zirve_yakin', 'yeni_zirve'),
                'sebepler': sebepler,
            })
        kacirilan.sort(key=lambda x: x['degisim24'], reverse=True)
        nedenler = sorted(({'sebep': k, 'adet': v} for k, v in neden_sayilari.items()), key=lambda x: x['adet'], reverse=True)
        return {'gun': gun, 'esik': esik, 'adet': len(kacirilan), 'coinler': kacirilan, 'nedenler': nedenler}
    except Exception as e:
        return {'gun': gun, 'esik': esik, 'adet': 0, 'coinler': [], 'nedenler': [], 'hata': str(e)}


def v5_flash_crash_likidite_avi(gun=7):
    """Piyasa snapshot'larından sert düşüş ve sonrasındaki toparlanmayı ölçer."""
    olaylar = []
    for symbol, arr in _v5c2_market_by_symbol(gun).items():
        if len(arr) < 3:
            continue
        peak_price = None
        peak_time = None
        best = None
        for i, k in enumerate(arr):
            fiyat = _v5c2_float(k.get('fiyat'))
            if fiyat <= 0:
                continue
            if peak_price is None or fiyat > peak_price:
                peak_price = fiyat
                peak_time = _v5c2_float(k.get('zaman'))
                continue
            dusus = ((fiyat - peak_price) / peak_price) * 100
            if dusus > V5_FLASH_CRASH_ESIK:
                continue
            low_price = fiyat
            low_time = _v5c2_float(k.get('zaman'))
            future = arr[i+1:]
            if future:
                max_after = max(_v5c2_float(x.get('fiyat')) for x in future)
                toparlanma = ((max_after - low_price) / low_price) * 100 if low_price else 0
            else:
                toparlanma = 0
            skor = max(0, min(100, abs(dusus) * 7 + max(toparlanma, 0) * 3))
            aday = {
                'symbol': symbol,
                'dusus': round(dusus, 2),
                'toparlanma': round(toparlanma, 2),
                'dakika': round((low_time - peak_time) / 60, 1) if peak_time else 0,
                'likidite_avi_skoru': int(round(skor)),
                'toparladi': toparlanma >= V5_FLASH_TOPARLANMA_ESIK,
            }
            if best is None or abs(aday['dusus']) > abs(best['dusus']):
                best = aday
        if best:
            olaylar.append(best)
    olaylar.sort(key=lambda x: (x['toparladi'], x['likidite_avi_skoru']), reverse=True)
    toparlayan = [x for x in olaylar if x['toparladi']]
    return {
        'gun': gun,
        'adet': len(olaylar),
        'toparlayan': len(toparlayan),
        'basari': round(len(toparlayan) * 100 / max(len(olaylar), 1), 1),
        'ort_dusus': round(sum(x['dusus'] for x in olaylar) / max(len(olaylar), 1), 2),
        'ort_toparlanma': round(sum(x['toparlanma'] for x in toparlayan) / max(len(toparlayan), 1), 2),
        'olaylar': olaylar[:10],
    }


# Aktif sinyaller her 5 dakikada güncellendiği için performans checkpoint'lerini burada sakla.
_v5c2_basari_kaydi_guncelle = basari_kaydi_guncelle
def basari_kaydi_guncelle(symbol, fiyat, durum=None, h1=False, h2=False, stop=False):
    _v5c2_basari_kaydi_guncelle(symbol, fiyat, durum=durum, h1=h1, h2=h2, stop=stop)
    simdi = time.time()
    degisti = False
    for k in reversed(basari_kayitlari):
        if k.get('symbol') != symbol:
            continue
        giris = _v5c2_float(k.get('giris'), fiyat)
        zaman = _v5c2_float(k.get('zaman'), simdi)
        if giris <= 0:
            return
        kazanc = ((fiyat - giris) / giris) * 100
        gecen_dk = (simdi - zaman) / 60
        for dk in V5_PERFORMANS_DAKIKALARI:
            key = f'performans_{dk}dk'
            if gecen_dk >= dk and key not in k:
                k[key] = round(kazanc, 4)
                k[f'fiyat_{dk}dk'] = round(float(fiyat), 8)
                k[f'zaman_{dk}dk'] = simdi
                degisti = True
        if degisti:
            basari_db_kaydet(basari_kayitlari)
        return


def v5_ilk_dakika_analizi(kayitlar):
    rows = []
    for dk in V5_PERFORMANS_DAKIKALARI:
        key = f'performans_{dk}dk'
        arr = [k for k in kayitlar if k.get(key) is not None]
        if not arr:
            continue
        degerler = [_v5c2_float(k.get(key)) for k in arr]
        rows.append({
            'dakika': dk,
            'adet': len(arr),
            'ort': round(sum(degerler) / len(degerler), 2),
            'pozitif': round(sum(1 for x in degerler if x > 0) * 100 / len(degerler), 1),
            'eksi2': round(sum(1 for x in degerler if x <= -2) * 100 / len(degerler), 1),
            'arti3': round(sum(1 for x in degerler if x >= 3) * 100 / len(degerler), 1),
        })
    return rows


# Hall of Fame: tek seferlik sans yerine en az 3 sinyal.
def v5_hall_of_fame(kayitlar):
    by = {}
    for k in kayitlar:
        s = k.get('symbol')
        if s:
            by.setdefault(s, []).append(k)
    rows = []
    for s, arr in by.items():
        if len(arr) < V5_COMMIT2_MIN_HALL_ORNEK:
            continue
        rows.append({
            'symbol': s,
            'adet': len(arr),
            'basari': v5_pct(sum(v5_success(k) for k in arr), len(arr)),
            'h2': v5_pct(sum(v5_big_success(k) for k in arr), len(arr)),
            'en_iyi': max([v5_safe_float(k.get('max_kazanc')) for k in arr] or [0]),
            'ort': v5_mean([k.get('max_kazanc') for k in arr]),
        })
    return sorted(rows, key=lambda x: (x['basari'], x['h2'], x['adet']), reverse=True)[:10]


# AI önerisi: en az 30 örnek ve mevcut başarıya göre +%5 fark.
def v5_parameter_optimization(kayitlar):
    suggestions = []
    baseline = v5_pct(sum(v5_success(k) for k in kayitlar), len(kayitlar))
    tests = [
        ('hacim_esigi', 'hacim', [5, 6, 7, 8, 10, 12, 15]),
        ('skor_esigi', 'skor', [8, 10, 12, 14, 16, 18, 20]),
        ('kalite_esigi', 'kalite', [5, 6, 7, 8, 9, 10, 12]),
        ('rsi_ust_limit', 'rsi', [62, 65, 68, 70, 72, 75, 80]),
        ('risk_ust_limit', 'risk_puani', [40, 45, 50, 55, 60, 65, 70]),
    ]
    for name, field, values in tests:
        best = None
        for v in values:
            arr = ([k for k in kayitlar if v5_safe_float(k.get(field)) <= v]
                   if name.endswith('ust_limit') else
                   [k for k in kayitlar if v5_safe_float(k.get(field)) >= v])
            if len(arr) < V5_COMMIT2_MIN_AI_ORNEK:
                continue
            rate = v5_pct(sum(v5_success(k) for k in arr), len(arr))
            h2r = v5_pct(sum(v5_big_success(k) for k in arr), len(arr))
            fark = round(rate - baseline, 1)
            if fark < V5_COMMIT2_MIN_AI_FARK:
                continue
            score = fark + h2r * 0.25 + min(len(arr), 100) * 0.03
            row = {'parametre': name, 'onerilen': v, 'ornek': len(arr), 'basari': rate, 'h2': h2r, 'fark': fark, 'skor': round(score, 2)}
            if best is None or row['skor'] > best['skor']:
                best = row
        if best:
            suggestions.append(best)
    v5_save_json(V5_PARAMETRE_JSON, suggestions)
    return sorted(suggestions, key=lambda x: x.get('skor', 0), reverse=True)


_v5c2_build_analysis = v5_build_analysis
def v5_build_analysis(gun=30):
    a = _v5c2_build_analysis(gun)
    baslangic = time.time() - gun * 86400
    kayitlar = [k for k in basari_kayitlari if _v5c2_float(k.get('zaman')) >= baslangic]
    a['kacirilan_coin_motoru'] = v5_kacirilan_coin_motoru(gun, 10)
    a['flash_crash'] = v5_flash_crash_likidite_avi(gun)
    a['ilk_dakika_analizi'] = v5_ilk_dakika_analizi(kayitlar)
    a['hall_of_fame'] = v5_hall_of_fame(kayitlar)
    a['parametre_onerileri'] = v5_parameter_optimization(kayitlar)
    v5_save_json(V5_ANALIZ_JSON, a)
    v5_save_json(V5_DASHBOARD_JSON, a)
    return a


_v5c2_professional_report = v5_professional_report_text
def v5_professional_report_text(gun=30):
    msg = _v5c2_professional_report(gun)
    a = v5_build_analysis(gun)

    km = a.get('kacirilan_coin_motoru') or {}
    msg += '\n🎯 KAÇIRILAN COIN MOTORU\n'
    if km.get('adet'):
        for c in km.get('coinler', [])[:5]:
            msg += f"{c['symbol']} +%{c['degisim24']} | Hacim {c['hacim']}x | Mom %{c['momentum']}\n"
            msg += 'Neden: ' + ' • '.join(c.get('sebepler', [])[:3]) + '\n'
        msg += 'Kaçma sebepleri: ' + ', '.join(f"{x['sebep']} {x['adet']}" for x in km.get('nedenler', [])[:5]) + '\n'
    else:
        msg += 'Bu dönemde açıklanacak kaçırılan kazanan coin yok.\n'

    fc = a.get('flash_crash') or {}
    msg += '\n🌊 FLASH CRASH & LİKİDİTE AVI\n'
    msg += f"Olay: {fc.get('adet',0)} | Toparlayan: {fc.get('toparlayan',0)} | Başarı %{fc.get('basari',0)}\n"
    if fc.get('adet'):
        msg += f"Ort. düşüş %{fc.get('ort_dusus',0)} | Ort. toparlanma %{fc.get('ort_toparlanma',0)}\n"
        for x in fc.get('olaylar', [])[:5]:
            msg += f"{x['symbol']}: düşüş %{x['dusus']} → toparlanma %{x['toparlanma']} | Likidite skoru {x['likidite_avi_skoru']}\n"

    msg += '\n⏱️ İLK 5/15/30/60 DK ANALİZİ\n'
    rows = a.get('ilk_dakika_analizi') or []
    if rows:
        for r in rows:
            msg += f"{r['dakika']} dk: {r['adet']} | Ort %{r['ort']} | Pozitif %{r['pozitif']} | +%3 %{r['arti3']} | -%2 ve altı %{r['eksi2']}\n"
    else:
        msg += 'Yeni checkpoint verileri biriktikçe bu bölüm dolacak.\n'
    return msg

# === /V5.4 COMMIT 2 ===


# === V5.4 COMMIT 3: AKILLI ANALIZ MOTORU ===
V5_COMMIT3_TREND_DOSYA = "v5_haftalik_trend.json"
V5_COMMIT3_MIN_KATEGORI_ORNEK = 5
V5_COMMIT3_MIN_ZAMAN_ORNEK = 3
V5_COMMIT3_MIN_SEKTOR_ORNEK = 3


def _v5c3_float(v, default=0.0):
    try:
        return float(v if v is not None else default)
    except Exception:
        return float(default)


def _v5c3_mean(values):
    nums = [_v5c3_float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 3) if nums else 0.0


def _v5c3_pct(n, d):
    return round(100.0 * n / max(d, 1), 1)


def _v5c3_field(k, *names, default=0.0):
    for name in names:
        if name in k and k.get(name) is not None:
            return k.get(name)
    return default


def _v5c3_success(k):
    try:
        return v5_nihai_sonuc(k) in ("h1", "h2")
    except Exception:
        return bool(k.get("h1") or k.get("h2") or _v5c3_float(k.get("max_kazanc")) >= 3)


def _v5c3_h2(k):
    try:
        return v5_nihai_sonuc(k) == "h2"
    except Exception:
        return bool(k.get("h2"))


def _v5c3_stop(k):
    try:
        return v5_nihai_sonuc(k) == "stop"
    except Exception:
        return bool(k.get("stop") and not k.get("h1") and not k.get("h2"))


def _v5c3_oran(records, *fields):
    if not records:
        return 0.0
    adet = 0
    for k in records:
        if any(bool(k.get(f)) for f in fields):
            adet += 1
    return _v5c3_pct(adet, len(records))


def _v5c3_mode(records, field, default="-"):
    counts = {}
    for k in records:
        value = k.get(field)
        if value in (None, ""):
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return max(counts, key=counts.get) if counts else default


def v5_kazanan_dna_2(kayitlar):
    wins = [k for k in kayitlar if _v5c3_success(k)]
    if not wins:
        return {"adet": 0}
    return {
        "adet": len(wins),
        "btc_guclu": _v5c3_oran(wins, "btc_guclu", "btcden_guclu"),
        "lider": _v5c3_oran(wins, "lider_mi", "lider_guclu"),
        "zirve": _v5c3_oran(wins, "zirve_teyidi", "zirve_yakin", "yeni_zirve"),
        "haber": _v5c3_oran(wins, "haber_var"),
        "momentum_gucleniyor": _v5c3_oran(wins, "momentum_gucleniyor"),
        "hacim_gucleniyor": _v5c3_oran(wins, "hacim_gucleniyor", "volume_strengthening"),
        "ort_devam": _v5c3_mean([_v5c3_field(k, "devam_gucu", default=v5_devam_gucu_hesapla(k)) for k in wins]),
        "ort_rsi": _v5c3_mean([_v5c3_field(k, "rsi") for k in wins]),
        "ort_risk": _v5c3_mean([_v5c3_field(k, "risk_puani", "risk_score") for k in wins]),
        "ort_skor": _v5c3_mean([_v5c3_field(k, "skor", "genel_skor") for k in wins]),
        "ort_kalite": _v5c3_mean([_v5c3_field(k, "kalite", "kalite_skoru") for k in wins]),
        "ort_hacim": _v5c3_mean([_v5c3_field(k, "hacim") for k in wins]),
        "ort_momentum": _v5c3_mean([_v5c3_field(k, "degisim3") for k in wins]),
        "ort_btc_fark": _v5c3_mean([_v5c3_field(k, "btc_fark", "btc_fark3") for k in wins]),
        "ort_haber": _v5c3_mean([_v5c3_field(k, "haber", "haber_skoru") for k in wins]),
        "ort_max": _v5c3_mean([_v5c3_field(k, "max_kazanc") for k in wins]),
        "en_sik_kategori": _v5c3_mode(wins, "kategori", "Bilinmiyor"),
    }


def v5_kaybeden_dna(kayitlar):
    losses = [k for k in kayitlar if _v5c3_stop(k)]
    if not losses:
        return {"adet": 0}
    nedenler = v5_failure_analysis(losses).get("sebepler", []) if losses else []
    return {
        "adet": len(losses),
        "btc_guclu": _v5c3_oran(losses, "btc_guclu", "btcden_guclu"),
        "lider": _v5c3_oran(losses, "lider_mi", "lider_guclu"),
        "zirve": _v5c3_oran(losses, "zirve_teyidi", "zirve_yakin", "yeni_zirve"),
        "haber": _v5c3_oran(losses, "haber_var"),
        "momentum_gucleniyor": _v5c3_oran(losses, "momentum_gucleniyor"),
        "hacim_gucleniyor": _v5c3_oran(losses, "hacim_gucleniyor", "volume_strengthening"),
        "ort_devam": _v5c3_mean([_v5c3_field(k, "devam_gucu", default=v5_devam_gucu_hesapla(k)) for k in losses]),
        "ort_rsi": _v5c3_mean([_v5c3_field(k, "rsi") for k in losses]),
        "ort_risk": _v5c3_mean([_v5c3_field(k, "risk_puani", "risk_score") for k in losses]),
        "ort_skor": _v5c3_mean([_v5c3_field(k, "skor", "genel_skor") for k in losses]),
        "ort_kalite": _v5c3_mean([_v5c3_field(k, "kalite", "kalite_skoru") for k in losses]),
        "ort_hacim": _v5c3_mean([_v5c3_field(k, "hacim") for k in losses]),
        "ort_momentum": _v5c3_mean([_v5c3_field(k, "degisim3") for k in losses]),
        "ort_btc_fark": _v5c3_mean([_v5c3_field(k, "btc_fark", "btc_fark3") for k in losses]),
        "ort_min": _v5c3_mean([_v5c3_field(k, "min_kazanc", "drawdown") for k in losses]),
        "en_sik_kategori": _v5c3_mode(losses, "kategori", "Bilinmiyor"),
        "ana_neden": nedenler[0].get("sebep") if nedenler else "Belirgin tek neden yok",
    }


def v5_kategori_dna(kayitlar):
    groups = {}
    for k in kayitlar:
        cat = k.get("kategori") or k.get("durum") or "Bilinmiyor"
        groups.setdefault(cat, []).append(k)
    rows = []
    for cat, arr in groups.items():
        if len(arr) < V5_COMMIT3_MIN_KATEGORI_ORNEK:
            continue
        h2_times = [_v5c3_field(k, "h2_sure_saat") for k in arr if k.get("h2") and k.get("h2_sure_saat") is not None]
        rows.append({
            "kategori": cat,
            "adet": len(arr),
            "basari": _v5c3_pct(sum(_v5c3_success(k) for k in arr), len(arr)),
            "h2": _v5c3_pct(sum(_v5c3_h2(k) for k in arr), len(arr)),
            "stop": _v5c3_pct(sum(_v5c3_stop(k) for k in arr), len(arr)),
            "ort_devam": _v5c3_mean([_v5c3_field(k, "devam_gucu", default=v5_devam_gucu_hesapla(k)) for k in arr]),
            "ort_hacim": _v5c3_mean([_v5c3_field(k, "hacim") for k in arr]),
            "ort_momentum": _v5c3_mean([_v5c3_field(k, "degisim3") for k in arr]),
            "ort_risk": _v5c3_mean([_v5c3_field(k, "risk_puani", "risk_score") for k in arr]),
            "ort_max": _v5c3_mean([_v5c3_field(k, "max_kazanc") for k in arr]),
            "ort_h2_saat": _v5c3_mean(h2_times),
            "en_iyi_saat": _v5c3_en_iyi_zaman(arr, "saat"),
            "en_iyi_gun": _v5c3_en_iyi_zaman(arr, "gun"),
            "en_iyi_sektor": _v5c3_en_iyi_zaman(arr, "sector"),
        })
    return sorted(rows, key=lambda r: (r["h2"], r["basari"], r["adet"]), reverse=True)


def _v5c3_time_values(k):
    try:
        tm = time.localtime(_v5c3_float(k.get("zaman")))
        return tm.tm_hour, tm.tm_wday
    except Exception:
        return 0, 0


def _v5c3_en_iyi_zaman(records, kind):
    labels = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    groups = {}
    for k in records:
        hour, weekday = _v5c3_time_values(k)
        if kind == "saat":
            key = str(hour)
        elif kind == "gun":
            key = labels[weekday]
        else:
            key = str(k.get("sector") or k.get("sektor") or "Genel")
        groups.setdefault(key, []).append(k)
    valid = [(key, arr) for key, arr in groups.items() if len(arr) >= 2]
    if not valid:
        return "-"
    key, arr = max(valid, key=lambda item: (_v5c3_pct(sum(_v5c3_success(k) for k in item[1]), len(item[1])), len(item[1])))
    return key


def v5_zaman_gun_analizi_2(kayitlar):
    day_names = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    hour_groups, day_groups = {}, {}
    for k in kayitlar:
        h, d = _v5c3_time_values(k)
        hour_groups.setdefault(h, []).append(k)
        day_groups.setdefault(day_names[d], []).append(k)

    def make_rows(groups, label):
        rows = []
        for key, arr in groups.items():
            if len(arr) < V5_COMMIT3_MIN_ZAMAN_ORNEK:
                continue
            h2_times = [_v5c3_field(k, "h2_sure_saat") for k in arr if k.get("h2") and k.get("h2_sure_saat") is not None]
            rows.append({
                label: key,
                "adet": len(arr),
                "basari": _v5c3_pct(sum(_v5c3_success(k) for k in arr), len(arr)),
                "h2": _v5c3_pct(sum(_v5c3_h2(k) for k in arr), len(arr)),
                "stop": _v5c3_pct(sum(_v5c3_stop(k) for k in arr), len(arr)),
                "ort_kazanc": _v5c3_mean([_v5c3_field(k, "max_kazanc") for k in arr]),
                "ort_h2_saat": _v5c3_mean(h2_times),
            })
        return sorted(rows, key=lambda r: (r["h2"], r["basari"], r["adet"]), reverse=True)
    return {"saatler": make_rows(hour_groups, "saat"), "gunler": make_rows(day_groups, "gun")}


def v5_sektor_analizi_2(kayitlar):
    groups = {}
    for k in kayitlar:
        sec = k.get("sector") or k.get("sektor") or "Genel"
        groups.setdefault(str(sec), []).append(k)
    rows = []
    for sec, arr in groups.items():
        if len(arr) < V5_COMMIT3_MIN_SEKTOR_ORNEK:
            continue
        rows.append({
            "sektor": sec,
            "adet": len(arr),
            "basari": _v5c3_pct(sum(_v5c3_success(k) for k in arr), len(arr)),
            "h2": _v5c3_pct(sum(_v5c3_h2(k) for k in arr), len(arr)),
            "stop": _v5c3_pct(sum(_v5c3_stop(k) for k in arr), len(arr)),
            "ort_kazanc": _v5c3_mean([_v5c3_field(k, "max_kazanc") for k in arr]),
            "ort_devam": _v5c3_mean([_v5c3_field(k, "devam_gucu", default=v5_devam_gucu_hesapla(k)) for k in arr]),
        })
    return sorted(rows, key=lambda r: (r["h2"], r["basari"], r["adet"]), reverse=True)


def v5_kacirilan_simulasyon_2(kacirilan_motoru):
    coins = (kacirilan_motoru or {}).get("coinler", [])
    rows = []
    for c in coins[:10]:
        hacim = _v5c3_float(c.get("hacim"))
        mom = _v5c3_float(c.get("momentum"))
        reasons = c.get("sebepler", []) or []
        tests = []
        if hacim < 5:
            tests.append(f"Hacim eşiği {max(round(hacim,1),1)}x olsaydı yeniden değerlendirilirdi")
        elif hacim < 8:
            tests.append("Hacim eşiği 5x olsaydı geçebilirdi")
        if mom < 2:
            tests.append("Momentum alt sınırı 2 puan gevşetilseydi geçebilirdi")
        if any("Lider" in str(x) for x in reasons):
            tests.append("Lider şartı kaldırılırsa yakalanabilirdi")
        if any("Zirve" in str(x) for x in reasons):
            tests.append("Zirve teyidi opsiyonel olsaydı yakalanabilirdi")
        if any("BTC" in str(x) for x in reasons):
            tests.append("BTC filtresi gevşetilirse yakalanabilirdi")
        if not tests:
            tests.append("Mevcut kayıtlarla tek bir eşik nedeni kesinleştirilemedi")
        rows.append({"symbol": c.get("symbol"), "degisim24": c.get("degisim24"), "simulasyon": tests[:2]})
    return rows


def _v5c3_trend_yukle():
    try:
        with open(V5_COMMIT3_TREND_DOSYA, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _v5c3_trend_kaydet(history):
    try:
        tmp = V5_COMMIT3_TREND_DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history[-20:], f, ensure_ascii=False, indent=2)
        os.replace(tmp, V5_COMMIT3_TREND_DOSYA)
    except Exception as e:
        print("V5.4 trend kaydı hatası:", e)


def v5_trend_analizi_2(analysis):
    history = _v5c3_trend_yukle()
    current = {
        "zaman": time.time(),
        "gun": analysis.get("gun", 7),
        "basari": _v5c3_float(analysis.get("basari_orani")),
        "h2": _v5c3_float(analysis.get("h2_orani")),
        "catch_rate": _v5c3_float((analysis.get("catch_rate") or {}).get("yakalama_orani")),
        "en_iyi_kategori": ((analysis.get("kategori_ligi") or [{}])[0]).get("kategori", "-") if analysis.get("kategori_ligi") else "-",
    }
    previous = None
    for row in reversed(history):
        if int(row.get("gun", 0)) == int(current["gun"]):
            previous = row
            break
    result = {"mevcut": current, "onceki": previous}
    if previous:
        result["basari_fark"] = round(current["basari"] - _v5c3_float(previous.get("basari")), 1)
        result["h2_fark"] = round(current["h2"] - _v5c3_float(previous.get("h2")), 1)
        result["catch_fark"] = round(current["catch_rate"] - _v5c3_float(previous.get("catch_rate")), 1)
        result["kategori_degisti"] = current["en_iyi_kategori"] != previous.get("en_iyi_kategori")
    if int(current["gun"]) == 7:
        history.append(current)
        _v5c3_trend_kaydet(history)
    return result


def v5_haftalik_ai_yorumu_2(analysis):
    notes = []
    cats = analysis.get("kategori_dna_2", []) or []
    if cats:
        best = cats[0]
        worst = min(cats, key=lambda x: (x.get("basari", 0), x.get("h2", 0)))
        notes.append(f"En güçlü kategori {best['kategori']} (%{best['basari']} başarı, %{best['h2']} H2, {best['adet']} örnek).")
        if worst["kategori"] != best["kategori"]:
            notes.append(f"En zayıf kategori {worst['kategori']} (%{worst['basari']} başarı).")
    kd = analysis.get("kazanan_dna_2", {}) or {}
    ld = analysis.get("kaybeden_dna", {}) or {}
    if kd.get("adet") and ld.get("adet"):
        devam_fark = round(_v5c3_float(kd.get("ort_devam")) - _v5c3_float(ld.get("ort_devam")), 1)
        hacim_fark = round(_v5c3_float(kd.get("ort_hacim")) - _v5c3_float(ld.get("ort_hacim")), 1)
        if abs(devam_fark) >= 5:
            notes.append(f"Kazananların Devam Gücü kaybedenlerden {devam_fark:+} puan farklı.")
        else:
            notes.append("Devam Gücü ile başarı arasında henüz belirgin ayrışma yok.")
        if abs(hacim_fark) >= 2:
            notes.append(f"Kazanan-kaybeden ortalama hacim farkı {hacim_fark:+}x.")
    trend = analysis.get("trend_analizi_2", {}) or {}
    if trend.get("onceki"):
        notes.append(f"Geçen rapora göre başarı {trend.get('basari_fark',0):+} puan, H2 {trend.get('h2_fark',0):+} puan, Catch Rate {trend.get('catch_fark',0):+} puan değişti.")
    suggestions = analysis.get("parametre_onerileri", []) or []
    if suggestions:
        notes.append("Güvenilir örnek şartını geçen öneri var; otomatik uygulanmadı, yalnızca raporlandı.")
    else:
        notes.append("Algoritma değişikliği önerilmiyor; güvenilir örnek ve başarı farkı şartı oluşmadı.")
    return notes[:7]


_v5c3_build_analysis = v5_build_analysis
def v5_build_analysis(gun=30):
    a = _v5c3_build_analysis(gun)
    baslangic = time.time() - gun * 86400
    kayitlar = [k for k in basari_kayitlari if _v5c3_float(k.get("zaman")) >= baslangic]
    a["kazanan_dna_2"] = v5_kazanan_dna_2(kayitlar)
    a["kaybeden_dna"] = v5_kaybeden_dna(kayitlar)
    a["kategori_dna_2"] = v5_kategori_dna(kayitlar)
    a["zaman_gun_analizi_2"] = v5_zaman_gun_analizi_2(kayitlar)
    a["sektor_analizi_2"] = v5_sektor_analizi_2(kayitlar)
    a["kacirilan_simulasyon_2"] = v5_kacirilan_simulasyon_2(a.get("kacirilan_coin_motoru"))
    a["trend_analizi_2"] = v5_trend_analizi_2(a)
    a["haftalik_ai_yorumu_2"] = v5_haftalik_ai_yorumu_2(a)
    v5_save_json(V5_ANALIZ_JSON, a)
    v5_save_json(V5_DASHBOARD_JSON, a)
    return a


_v5c3_professional_report = v5_professional_report_text
def v5_professional_report_text(gun=30):
    msg = _v5c3_professional_report(gun)
    a = v5_build_analysis(gun)

    kd = a.get("kazanan_dna_2", {}) or {}
    msg += "\n🧬 KAZANAN DNA 2.0\n"
    if kd.get("adet"):
        msg += f"Kazanan {kd['adet']} | BTC güçlü %{kd['btc_guclu']} | Lider %{kd['lider']} | Zirve %{kd['zirve']} | Haber %{kd['haber']}\n"
        msg += f"Ort Devam {kd['ort_devam']} | RSI {kd['ort_rsi']} | Risk {kd['ort_risk']} | Skor {kd['ort_skor']} | Kalite {kd['ort_kalite']}\n"
        msg += f"Ort Hacim {kd['ort_hacim']}x | Mom %{kd['ort_momentum']} | BTC fark %{kd['ort_btc_fark']} | Ort Max %{kd['ort_max']}\n"
        msg += f"Tipik profil: {kd['en_sik_kategori']} • Mom↑ %{kd['momentum_gucleniyor']} • Hacim↑ %{kd['hacim_gucleniyor']}\n"
    else:
        msg += "Henüz kazanan kaydı yok.\n"

    ld = a.get("kaybeden_dna", {}) or {}
    msg += "\n📉 KAYBEDEN DNA\n"
    if ld.get("adet"):
        msg += f"Kaybeden {ld['adet']} | BTC güçlü %{ld['btc_guclu']} | Lider %{ld['lider']} | Zirve %{ld['zirve']} | Haber %{ld['haber']}\n"
        msg += f"Ort Devam {ld['ort_devam']} | RSI {ld['ort_rsi']} | Risk {ld['ort_risk']} | Skor {ld['ort_skor']} | Kalite {ld['ort_kalite']}\n"
        msg += f"Ort Hacim {ld['ort_hacim']}x | Mom %{ld['ort_momentum']} | Ort DD %{ld['ort_min']}\n"
        msg += f"Tipik profil: {ld['en_sik_kategori']} | Ana gözlem: {ld['ana_neden']}\n"
    else:
        msg += "Henüz nihai stop kaydı yok.\n"

    msg += "\n🎯 KATEGORİ DNA\n"
    rows = a.get("kategori_dna_2", []) or []
    if rows:
        for r in rows[:5]:
            msg += f"{r['kategori']}: {r['adet']} | Başarı %{r['basari']} | H2 %{r['h2']} | Stop %{r['stop']} | Devam {r['ort_devam']}\n"
            msg += f"Hacim {r['ort_hacim']}x | Mom %{r['ort_momentum']} | Risk {r['ort_risk']} | Ort Max %{r['ort_max']} | H2 süre {r['ort_h2_saat']}s\n"
    else:
        msg += "Kategori başına en az 5 örnek birikmesi bekleniyor.\n"

    zg = a.get("zaman_gun_analizi_2", {}) or {}
    msg += "\n⏰ SAAT / GÜN ANALİZİ 2.0\n"
    for r in (zg.get("saatler") or [])[:3]:
        msg += f"Saat {r['saat']}: {r['adet']} | Başarı %{r['basari']} | H2 %{r['h2']} | Stop %{r['stop']} | Ort %{r['ort_kazanc']}\n"
    for r in (zg.get("gunler") or [])[:3]:
        msg += f"{r['gun']}: {r['adet']} | Başarı %{r['basari']} | H2 %{r['h2']} | Stop %{r['stop']} | Ort %{r['ort_kazanc']}\n"

    msg += "\n📊 SEKTÖR ANALİZİ 2.0\n"
    sectors = a.get("sektor_analizi_2", []) or []
    if sectors:
        for r in sectors[:6]:
            msg += f"{r['sektor']}: {r['adet']} | Başarı %{r['basari']} | H2 %{r['h2']} | Stop %{r['stop']} | Ort %{r['ort_kazanc']} | Devam {r['ort_devam']}\n"
    else:
        msg += "Sektör başına en az 3 örnek birikmesi bekleniyor.\n"

    msg += "\n🧪 KAÇIRILAN COIN EŞİK SİMÜLASYONU\n"
    sims = a.get("kacirilan_simulasyon_2", []) or []
    if sims:
        for r in sims[:5]:
            msg += f"{r['symbol']} +%{r['degisim24']}: " + " • ".join(r['simulasyon']) + "\n"
    else:
        msg += "Simüle edilecek kaçırılan coin yok.\n"

    trend = a.get("trend_analizi_2", {}) or {}
    msg += "\n📈 HAFTALIK TREND\n"
    if trend.get("onceki"):
        arrow = lambda x: "↑" if x > 0 else ("↓" if x < 0 else "→")
        msg += f"Başarı {trend.get('basari_fark',0):+} puan {arrow(trend.get('basari_fark',0))} | H2 {trend.get('h2_fark',0):+} {arrow(trend.get('h2_fark',0))} | Catch {trend.get('catch_fark',0):+} {arrow(trend.get('catch_fark',0))}\n"
        msg += f"En iyi kategori: {trend['mevcut'].get('en_iyi_kategori')}" + (" (değişti)\n" if trend.get("kategori_degisti") else " (aynı)\n")
    else:
        msg += "İlk trend referansı kaydedildi; sonraki aynı dönem raporunda karşılaştırma başlayacak.\n"

    msg += "\n🤖 HAFTALIK AI YORUMU\n"
    for note in a.get("haftalik_ai_yorumu_2", []) or []:
        msg += f"• {note}\n"
    return msg

# === /V5.4 COMMIT 3 ===

# === V5.4 GIRIS ODAKLI SINYAL ENTEGRASYONU ===
# Ayrı bir sinyal motoru değildir. Mevcut Roket/Elit/Yıldız kararlarının
# Telegram'a çıkabilmesi için giriş kalitesini zorunlu bir koşul yapar.
GIRIS_KALITESI_MIN = 68


def giris_kalitesi_hesapla(o, h, l, c, v, degisim1, degisim3, degisim24,
                            hacim_kat, zirve_yakin=False, yeni_zirve=False,
                            satis_baskisi=False, gec_pump_puan=0):
    """0-100 giriş kalitesi üretir ve tepeden/uzamış hareketleri baskılar.

    Amaç coin gücünü tekrar puanlamak değil; güçlü coinin *şu anda* girişe uygun
    olup olmadığını ölçmektir. Yalnızca mevcut ve geçmiş mumlar kullanılır.
    """
    riskler = []
    hard_block = False
    skor = 70.0

    try:
        if not c or len(c) < 6:
            return 50, False, ["yetersiz mum verisi"], {}

        # API low alanı yoksa open/close minimumlarından güvenli vekil üret.
        if not l or len(l) != len(c):
            l = [min(float(oo), float(cc)) for oo, cc in zip(o, c)]

        fiyat = float(c[-1])
        prev_close = float(c[-2]) if float(c[-2]) else fiyat
        cur_open = float(o[-1])
        cur_high = float(h[-1])
        cur_low = float(l[-1])
        cur_range = max(cur_high - cur_low, 1e-12)

        # Mum içi kapanış ve üst fitil reddi.
        kapanis_pozisyonu = max(0.0, min(1.0, (fiyat - cur_low) / cur_range))
        ust_fitil = max(0.0, cur_high - max(cur_open, fiyat))
        ust_fitil_orani = max(0.0, min(1.0, ust_fitil / cur_range))

        # Son 6 saatlik hareket ne kadar uzadı? Lokal tepe kovalamayı yakalar.
        son6_low = min(float(x) for x in l[-6:])
        runup6 = ((fiyat / son6_low) - 1.0) * 100 if son6_low > 0 else 0.0

        # Son 3 tamamlanmış mumda üst üste yeşil sayısı.
        yesil_seri = 0
        for i in range(len(c) - 1, max(-1, len(c) - 5), -1):
            if float(c[i]) > float(o[i]):
                yesil_seri += 1
            else:
                break

        # Mevcut mum genişlemesi: son 5 mumun tipik range'ine göre.
        onceki_range_pct = []
        for i in range(max(1, len(c) - 6), len(c) - 1):
            pc = float(c[i-1]) if float(c[i-1]) else 0.0
            if pc > 0:
                onceki_range_pct.append((float(h[i]) - float(l[i])) / pc * 100)
        ort_range_pct = sum(onceki_range_pct) / len(onceki_range_pct) if onceki_range_pct else 0.0
        anlik_range_pct = cur_range / prev_close * 100 if prev_close > 0 else 0.0
        range_genisleme = (anlik_range_pct / ort_range_pct) if ort_range_pct > 0 else 1.0

        # Sağlıklı başlangıç / devam bölgesi ödülleri.
        if 0.25 <= degisim1 <= 2.8:
            skor += 10
        elif 2.8 < degisim1 <= 4.0:
            skor += 2
        elif degisim1 < -0.8:
            skor -= 10
            riskler.append("son 1s zayıf")

        if 1.5 <= degisim3 <= 5.0:
            skor += 10
        elif 5.0 < degisim3 <= 7.0:
            skor += 2
        elif degisim3 < 1.0:
            skor -= 6
            riskler.append("3s ivme yetersiz")

        if -2 <= degisim24 <= 8:
            skor += 5
        elif degisim24 > 12:
            skor -= 10
            riskler.append("24s hareket uzamış")
        if degisim24 > 18:
            skor -= 10

        if 5 <= hacim_kat <= 12:
            skor += 5
        elif hacim_kat >= 18:
            skor -= 6
            riskler.append("hacim climax riski")

        # Kapanış kalitesi / rejection.
        if kapanis_pozisyonu >= 0.60 and ust_fitil_orani <= 0.25:
            skor += 5
        if kapanis_pozisyonu <= 0.35:
            skor -= 10
            riskler.append("mum kapanışı zayıf")
        if ust_fitil_orani >= 0.40:
            skor -= 15
            riskler.append("üst fitil / satış reddi")

        # Lokal uzama: TURBO benzeri tepeden yakalamayı baskılar.
        if runup6 <= 4.5:
            skor += 8
        elif runup6 <= 6.0:
            skor += 2
        elif runup6 <= 8.5:
            skor -= 10
            riskler.append("6s yükseliş uzamış")
        else:
            skor -= 18
            riskler.append("6s aşırı uzama")

        # Üst üste yeşil mumlardan sonra kovalamayı azalt.
        if yesil_seri >= 3 and degisim3 >= 4:
            skor -= 10
            riskler.append("uzun yeşil mum serisi")

        # Zirve tek başına olumlu sayılmaz: uzama ile birleşirse giriş riski.
        if (zirve_yakin or yeni_zirve) and degisim1 >= 2.0 and runup6 >= 5.5:
            skor -= 8
            riskler.append("lokal zirvede giriş")
        # TURBO tipi: coin güçlü olsa da son 6 saatte zaten belirgin uzayıp
        # tepe bölgesindeyse giriş kalitesi ciddi düşer.
        if (zirve_yakin or yeni_zirve) and degisim1 >= 1.8 and runup6 >= 7.0:
            skor -= 15
            riskler.append("tepe kovalamaca riski")

        # Hacim patlaması hareketin sonunda geliyorsa ATM tipi risk.
        if hacim_kat >= 12 and degisim1 >= 3.0:
            skor -= 10
            riskler.append("hacim patlaması sonrası kovalamaca")
        if hacim_kat >= 15 and degisim3 >= 6.0:
            skor -= 8

        if range_genisleme >= 2.2 and degisim1 >= 2.5:
            skor -= 10
            riskler.append("genişleme mumu")

        if satis_baskisi:
            skor -= 25
            hard_block = True
            riskler.append("satış baskısı")

        if gec_pump_puan:
            skor -= min(float(gec_pump_puan) * 7, 21)
            if gec_pump_puan >= 2:
                riskler.append("geç hareket riski")

        # Not: mikro basamak puanı ana döngüde ayrıca eklenir; giriş kalitesi burada
        # sadece uzama/tepe riskini korumaya devam eder.

        # Sert güvenlik blokları: güçlü olsa bile Telegram'a gönderme.
        if degisim1 >= 6.0:
            hard_block = True
            riskler.append("1s aşırı yükseliş")
        if degisim3 >= 10.0 and degisim1 >= 4.0:
            hard_block = True
            riskler.append("3s aşırı momentum")
        if runup6 >= 10.5 and (zirve_yakin or yeni_zirve):
            hard_block = True
            riskler.append("tepeye aşırı uzamış")
        if ust_fitil_orani >= 0.58 and hacim_kat >= 5:
            hard_block = True
            riskler.append("yüksek hacimli rejection")

        skor = int(max(0, min(100, round(skor))))
        uygun = bool(skor >= GIRIS_KALITESI_MIN and not hard_block)
        metrikler = {
            "runup6": round(runup6, 3),
            "ust_fitil_orani": round(ust_fitil_orani, 3),
            "kapanis_pozisyonu": round(kapanis_pozisyonu, 3),
            "yesil_seri": int(yesil_seri),
            "range_genisleme": round(range_genisleme, 3),
            "hard_block": bool(hard_block),
        }
        return skor, uygun, riskler[:6], metrikler
    except Exception as e:
        print("Giriş kalitesi hesap hatası:", e)
        return 50, False, ["giriş kalitesi hesaplanamadı"], {}


# === V5.4.1 60 SN SESSIZ HIZLI ON TARAMA + 3 DK IZLEME HAVUZU ===
# Yeni kategori/sinyal üretmez. Yalnızca hızlı fiyat veya hacim ivmesi görülen
# coinleri 5 dakikalık genel taramayı beklemeden mevcut Radar analizine sokar.
son_tam_tarama = 0.0
on_tarama_onceki_ticker = {}

def _ticker_float(veri, *alanlar):
    for alan in alanlar:
        try:
            deger = veri.get(alan)
            if deger is not None and deger != "":
                return float(deger)
        except Exception:
            pass
    return 0.0

def hizli_on_tarama_adaylari(ticker, onceki):
    adaylar = []
    yeni_snapshot = {}
    for coin in ticker:
        try:
            symbol = coin.get("pair", "")
            if not symbol.endswith("TRY") or symbol == "BTCTRY" or stable_coin_mi(symbol) or len(symbol) > 15:
                continue
            fiyat = _ticker_float(coin, "last", "lastPrice", "price")
            hacim = _ticker_float(coin, "volume", "volume24h", "quoteVolume")
            if fiyat <= 0:
                continue
            yeni_snapshot[symbol] = {"fiyat": fiyat, "hacim": hacim}
            eski = onceki.get(symbol)
            if not eski:
                continue
            eski_fiyat = float(eski.get("fiyat", 0) or 0)
            eski_hacim = float(eski.get("hacim", 0) or 0)
            fiyat_ivme = ((fiyat / eski_fiyat) - 1.0) * 100 if eski_fiyat > 0 else 0.0
            hacim_ivme = ((hacim / eski_hacim) - 1.0) * 100 if eski_hacim > 0 and hacim > eski_hacim else 0.0
            if fiyat_ivme >= HIZLI_FIYAT_ESIK or hacim_ivme >= HIZLI_HACIM_ESIK:
                guc = max(fiyat_ivme / max(HIZLI_FIYAT_ESIK, 0.01), hacim_ivme / max(HIZLI_HACIM_ESIK, 0.01))
                adaylar.append((guc, symbol, fiyat_ivme, hacim_ivme))
        except Exception:
            continue
    adaylar.sort(reverse=True)
    return adaylar[:HIZLI_MAX_ADAY], yeni_snapshot
# === /V5.4.1 60 SN SESSIZ HIZLI ON TARAMA + 3 DK IZLEME HAVUZU ===

while True:
    try:
        print()
        print("COIN RADAR V5.5.1 MAIN13 KALITELI ROKET ADAYI")
        print("--------------------------------")

        hedef_stop_kontrol()
        #stop_raporu_gonder()
        haftalik_rapor_gonder()

        btc_d = btc_degisimleri()
        btc = btc_d.get("3s", 0)

        ticker = requests.get(
            "https://api.btcturk.com/api/v2/ticker",
            timeout=10
        ).json()["data"]

        simdi_tarama = time.time()
        tam_tarama = (simdi_tarama - son_tam_tarama) >= TARAMA_SURESI
        hizli_hedefler = set()

        hizli_adaylar, yeni_ticker_snapshot = hizli_on_tarama_adaylari(ticker, on_tarama_onceki_ticker)
        on_tarama_onceki_ticker = yeni_ticker_snapshot

        # V5.4.5: anlık piyasa liderliği. 60 sn hızlanan coinleri güç sırasına koy.
        # Bu sıralama Telegram'a yazılmaz; erken Roket Adayı seçiciliğinde kullanılır.
        hizli_lider_haritasi = {
            sym: {"rank": i + 1, "guc": guc, "fiyat_ivme": fp, "hacim_ivme": vp}
            for i, (guc, sym, fp, vp) in enumerate(hizli_adaylar)
        }

        # V5.4.1 SESSİZ HIZLI İZLEME HAVUZU
        # Ön taramada hızlanan coin ilk analizde Roket/Elit/Yıldız olmasa bile
        # hemen unutulmaz. 3 dakika boyunca her 60 saniyede yeniden mevcut
        # Radar kriterleriyle analiz edilir. Yeni Telegram kategorisi üretmez.
        for _, sym, _, _ in hizli_adaylar:
            hizli_izleme_havuzu[sym] = simdi_tarama

        hizli_izleme_havuzu = {
            sym: ts for sym, ts in hizli_izleme_havuzu.items()
            if simdi_tarama - ts <= HIZLI_IZLEME_SURESI
        }

        if tam_tarama:
            son_tam_tarama = simdi_tarama
            print("🔎 Tam piyasa taraması (5 dk)")
        else:
            anlik_hizli_hedefler = {x[1] for x in hizli_adaylar}

            # V5.5.0: AL Assistant güç havuzuna alınan coinleri de her 60 sn derin analiz et.
            # Böylece ilk güçlenme işaretinden sonra 5 dakikalık tam taramayı beklemiyoruz.
            al_assistant_guc_havuzu = {
                sym: st for sym, st in al_assistant_guc_havuzu.items()
                if simdi_tarama - float(st.get("son_zaman", simdi_tarama)) <= AL_GUC_HAVUZU_SURESI
            }
            hizli_hedefler = (
                anlik_hizli_hedefler
                | set(hizli_izleme_havuzu.keys())
                | set(al_assistant_guc_havuzu.keys())
            )
            if hizli_adaylar:
                ozet = ", ".join(
                    f"{sym}(fiyat %{fp:+.2f}, hacim %{vp:+.2f})"
                    for _, sym, fp, vp in hizli_adaylar[:8]
                )
                print(f"⚡ 60 sn ön tarama tetikledi: {ozet}")
            else:
                print("⚡ 60 sn ön tarama: hızlanan coin yok")

            if hizli_izleme_havuzu:
                print(
                    "👀 Sessiz hızlı izleme: "
                    + ", ".join(sorted(hizli_izleme_havuzu.keys()))
                )
            if al_assistant_guc_havuzu:
                print(
                    "🧠 AL güç havuzu: "
                    + ", ".join(sorted(al_assistant_guc_havuzu.keys()))
                )

        adaylar = []

        for coin in ticker:
            try:
                symbol = coin["pair"]
                _hl = hizli_lider_haritasi.get(symbol, {})
                hizli_lider_rank = int(_hl.get("rank", 0) or 0)
                hizli_fiyat_ivme = float(_hl.get("fiyat_ivme", 0) or 0)
                hizli_hacim_ivme = float(_hl.get("hacim_ivme", 0) or 0)

                if not symbol.endswith("TRY"):
                    continue

                if symbol == "BTCTRY":
                    continue

                if stable_coin_mi(symbol):
                    continue

                if len(symbol) > 15:
                    continue

                # 5 dk ana taramada tüm piyasa; ara dakikalarda sadece hızlanan coinler.
                if not tam_tarama and symbol not in hizli_hedefler:
                    continue

                d = veri_getir(symbol, 24)

                o = d["o"]
                h = d["h"]
                l = d.get("l") or [min(float(oo), float(cc)) for oo, cc in zip(o, d["c"])]
                c = d["c"]
                v = d["v"]

                if len(c) < 24:
                    continue

                fiyat = c[-1]

                degisim1 = ((c[-1] - c[-2]) / c[-2]) * 100
                degisim3 = ((c[-1] - c[-4]) / c[-4]) * 100
                degisim24 = ((c[-1] - c[-24]) / c[-24]) * 100

                son_hacim = v[-1]
                ort_hacim = sum(v[-6:-1]) / 5

                if ort_hacim == 0:
                    continue

                hacim_kat = son_hacim / ort_hacim

                # V5.4.2: Patlama mumundan önce görülen 2-3 kısa "basamak" mumu.
                mikro_basamak_skor, mikro_basamak, mikro_metrikler = mikro_basamak_hesapla(o, h, l, c, v)
                mikro_hacim_ivmesi = float(mikro_metrikler.get("hacim_ivmesi", 1.0) or 1.0)
                mikro_mum_sayisi = int(mikro_metrikler.get("mum_sayisi", 0) or 0)

                btc_guc_skoru, btc_fark1, btc_fark3, btc_fark24 = btc_gucu_v2_hesapla(
                    degisim1,
                    degisim3,
                    degisim24,
                    btc_d
                )
                btc_fark = btc_fark3

                btcden_guclu = btc_guc_skoru >= 4 and btc_fark3 >= 0.5
                son_mum_yesil = c[-1] > o[-1]
                zirve_yakin = fiyat > max(h[-12:-1]) * 0.995
                yeni_zirve = fiyat >= max(h[-24:-1])
                satis_baskisi = son_hacim > ort_hacim * 5 and degisim1 < 0

                haber_skoru = haber_puani(symbol)

                # V5 momentum/hacim ayarı:
                # Momentum 6%+ raporda en güçlü grup çıktı; hacim 10x+ tek başına zayıf kaldı.
                hacim_skoru = min(hacim_kat * 1.5, 8)
                momentum_skoru = min(max(0, degisim3 * 3), 24)
                btc_skoru = btc_guc_skoru
                mum_skoru = 1 if son_mum_yesil else 0
                zirve_skoru = 1 if zirve_yakin else 0

                genel_skor = (
                    hacim_skoru * 0.30
                    + momentum_skoru * 0.35
                    + btc_skoru * 0.15
                    + haber_skoru * 0.20
                    + mum_skoru
                    + zirve_skoru
                )

                kalite_skoru = (
                    hacim_skoru * 0.35
                    + momentum_skoru * 0.40
                    + btc_skoru * 0.15
                    + mum_skoru
                    + zirve_skoru
                )

                # Hacim artık ancak momentum teyidi varsa ek puan alır.
                if hacim_kat >= 5 and degisim3 >= 2:
                    genel_skor += 2

                if hacim_kat >= 8 and degisim3 >= 4:
                    genel_skor += 2

                hacim_bonus = 0
                if hacim_kat >= 20 and degisim3 >= 6:
                    hacim_bonus = 2
                elif hacim_kat >= 15 and degisim3 >= 6:
                    hacim_bonus = 1
                elif hacim_kat >= 10 and degisim3 >= 4:
                    hacim_bonus = 1
                genel_skor += hacim_bonus

                # Momentum bonusu: rapora göre 6%+ 3s momentum H2 başarısında öne çıktı.
                if degisim3 >= 6:
                    genel_skor += 6
                elif degisim3 >= 4:
                    genel_skor += 3
                elif degisim3 >= 2:
                    genel_skor += 1

                if haber_skoru >= 15:
                    genel_skor += 4

                if haber_skoru > 0 and hacim_kat > 3:
                    genel_skor += 5

                if degisim24 > 10:
                    genel_skor -= 4

                # Sadece aşırı şişmiş ve son saatte çok hızlanmış hareketlerde küçük geç kalma cezası.
                if degisim3 > 9 and degisim24 > 18 and degisim1 > 5:
                    genel_skor -= 2

                if degisim1 > 4:
                    genel_skor -= 4

                if degisim24 > 0 and degisim3 > degisim24 * 0.85:
                    genel_skor -= 2

                if degisim3 > 0 and degisim1 > degisim3 * 0.65:
                    genel_skor -= 2

                # 10x+ hacim güçlü momentum olmadan geliyorsa artık fazla ödüllendirilmez.
                if hacim_kat >= 10 and degisim3 < 4:
                    genel_skor -= 3

                if satis_baskisi:
                    genel_skor -= 5

                # V5.4.2 erken yapı bonusu: 5x hacim gelmeden skoru hazırlamaya başlar.
                # Büyük tek mum değil, küçük basamaklar ödüllendirilir.
                mikro_bonus = 0
                if mikro_basamak:
                    mikro_bonus = 4 if mikro_mum_sayisi >= 3 else 3
                    if mikro_hacim_ivmesi >= 1.15:
                        mikro_bonus += 2
                    if 0 < degisim1 <= 2.5 and 0.7 <= degisim3 <= 4.5:
                        mikro_bonus += 2
                    genel_skor += mikro_bonus
                    kalite_skoru += min(4, mikro_bonus)


                guclenme_bonus, guclenme_notlari = guclenme_bonusu_hesapla(
                    symbol,
                    genel_skor,
                    hacim_kat,
                    degisim3
                )

                if guclenme_bonus > 0:
                    genel_skor += guclenme_bonus


                # === V5.1 karar motoru: güçlenme artık sadece mesaj süsü değil ===
                hacim_gucleniyor_v5 = any("hacim güçleniyor" in str(n).lower() for n in (guclenme_notlari or []))
                momentum_gucleniyor_v5 = any("momentum güçleniyor" in str(n).lower() for n in (guclenme_notlari or []))

                if hacim_gucleniyor_v5 and momentum_gucleniyor_v5 and btcden_guclu:
                    genel_skor += V5_1_GUCLENME_SKOR_BONUS

                # 10x+ hacim, 3s momentum 4 altında kalıyorsa Telegram kalitesini bozmasın.
                zayif_trader_hacim_v5 = hacim_kat >= 10 and degisim3 < V5_1_ZAYIF_TRADER_MIN_MOMENTUM and not momentum_gucleniyor_v5
                if zayif_trader_hacim_v5:
                    genel_skor -= V5_1_ZAYIF_TRADER_CEZA
                # === /V5.1 karar motoru ===

                # V4.25 commit: BTC farkı da sadece ✅ değil, puana dönüşsün.
                btc_fark_bonus = 0
                if btc_fark3 >= 4:
                    btc_fark_bonus = 2
                elif btc_fark3 >= 2:
                    btc_fark_bonus = 1
                genel_skor += btc_fark_bonus

                lider_skoru = lider_skoru_hesapla(
                    hacim_kat,
                    degisim1,
                    degisim3,
                    degisim24,
                    btc_fark1,
                    btc_fark3,
                    btc_fark24,
                    zirve_yakin,
                    yeni_zirve
                )

                # V4.25 commit: liderlik ve zirve teyidi genel skorda da görünür olsun.
                lider_bonus = 0
                if lider_skoru >= 7:
                    lider_bonus = 2
                elif lider_skoru >= 5:
                    lider_bonus = 1
                genel_skor += lider_bonus

                # Geç Pump artık eleme/ceza değil; yalnızca DNA raporunda risk puanı olarak saklanır.
                gec_pump_puan = gec_pump_puani_hesapla(degisim1, degisim3, degisim24, hacim_kat, btcden_guclu, lider_skoru)
                gec_pump = False
                zirve_bonus = 1 if (zirve_yakin or yeni_zirve) else 0
                genel_skor += zirve_bonus

                guc_skoru = guc_skoru_hesapla(
                    hacim_kat,
                    degisim3,
                    btc_guc_skoru,
                    lider_skoru,
                    haber_skoru,
                    satis_baskisi,
                    gec_pump,
                    btc_fark3,
                    zirve_yakin,
                    yeni_zirve
                )

                if mikro_basamak and btcden_guclu:
                    guc_skoru = round(min(100, guc_skoru + (8 if mikro_mum_sayisi >= 3 else 6) + (3 if mikro_hacim_ivmesi >= 1.15 else 0)), 2)

                # V5.4: Güçlü coin yetmez; giriş kalitesi de yüksek olmak zorunda.
                giris_kalitesi, giris_uygun, giris_riskleri, giris_metrikleri = giris_kalitesi_hesapla(
                    o, h, l, c, v,
                    degisim1, degisim3, degisim24,
                    hacim_kat,
                    zirve_yakin=zirve_yakin,
                    yeni_zirve=yeni_zirve,
                    satis_baskisi=satis_baskisi,
                    gec_pump_puan=gec_pump_puan,
                )

                # V5.4.5 erken lider teyidi; raporda neden geçti/kaldı görebilelim.
                erken_lider_onayi = bool(
                    (hizli_lider_rank > 0 and hizli_lider_rank <= ERKEN_LIDER_MAX_RANK and
                     (hizli_fiyat_ivme >= 0.15 or hizli_hacim_ivme >= HIZLI_HACIM_ESIK))
                    or (lider_skoru >= ERKEN_LIDER_MIN_SKOR and btc_fark3 >= ERKEN_LIDER_MIN_BTC_FARK3)
                    or (lider_skoru >= 4 and mikro_hacim_ivmesi >= ERKEN_LIDER_MIN_MIKRO_IVME and btc_fark3 >= 0.5)
                )

                # Piyasa analizi: Sinyal üretmese bile tüm coinlerin son durumunu kaydet.
                # V5.4.6: Üst kategori kararında kullanılacak anlık Devam Gücü.
                devam_gucu_anlik = v5_devam_gucu_hesapla({
                    "degisim1": degisim1,
                    "degisim3": degisim3,
                    "degisim24": degisim24,
                    "hacim": hacim_kat,
                    "btc_fark": btc_fark,
                    "btc_guclu": btcden_guclu,
                    "btcden_guclu": btcden_guclu,
                    "lider_skoru": lider_skoru,
                    "lider_mi": lider_skoru >= 5,
                    "lider_guclu": lider_skoru >= 7,
                    "zirve_teyidi": zirve_yakin or yeni_zirve,
                    "momentum_gucleniyor": momentum_gucleniyor_v5,
                    "hacim_gucleniyor": hacim_gucleniyor_v5,
                    "gec_pump_puan": gec_pump_puan,
                })

                # Böylece son 3 günde %10+ gidip botun kaçırdığı coinler raporda bulunabilir.
                piyasa_kaydi_ekle(symbol, {
                    "fiyat": fiyat,
                    "degisim1": degisim1,
                    "degisim3": degisim3,
                    "degisim24": degisim24,
                    "hacim": hacim_kat,
                    "btc_guclu": btcden_guclu,
                    "btc_fark": btc_fark,
                    "lider_mi": lider_skoru >= 5,
                    "lider_skoru": lider_skoru,
                    "zirve_teyidi": zirve_yakin or yeni_zirve,
                    "zirve_yakin": zirve_yakin,
                    "yeni_zirve": yeni_zirve,
                    "haber_var": haber_skoru > 0,
                    "guc_skoru": guc_skoru,
                    "gec_pump_puan": gec_pump_puan,
                    "giris_kalitesi": giris_kalitesi,
                    "giris_uygun": bool(giris_uygun),
                    "tepe_riski": bool(giris_metrikleri.get("hard_block") or giris_kalitesi < GIRIS_KALITESI_MIN),
                    "runup6": giris_metrikleri.get("runup6", 0),
                    "ust_fitil_orani": giris_metrikleri.get("ust_fitil_orani", 0),
                    "mikro_basamak": bool(mikro_basamak),
                    "mikro_basamak_skor": mikro_basamak_skor,
                    "mikro_mum_sayisi": mikro_mum_sayisi,
                    "mikro_hacim_ivmesi": round(mikro_hacim_ivmesi, 3),
                    "hizli_lider_rank": hizli_lider_rank,
                    "hizli_fiyat_ivme": round(hizli_fiyat_ivme, 4),
                    "hizli_hacim_ivme": round(hizli_hacim_ivme, 4),
                    "erken_lider_onayi": erken_lider_onayi,
                    "hacim_gucleniyor": bool(hacim_gucleniyor_v5),
                    "momentum_gucleniyor": bool(momentum_gucleniyor_v5),
                    "devam_gucu": devam_gucu_anlik,
                    "sinyal_var": False,
                    "durum": None,
                })

                durum, alt_durum = kategori_belirle(
                    symbol,
                    genel_skor,
                    kalite_skoru,
                    hacim_kat,
                    haber_skoru,
                    btcden_guclu,
                    btc_fark,
                    degisim1,
                    degisim3,
                    degisim24,
                    zirve_yakin,
                    guclenme_bonus,
                    btc_guc_skoru,
                    lider_skoru,
                    guc_skoru,
                    yeni_zirve,
                    mikro_basamak,
                    mikro_basamak_skor,
                    mikro_hacim_ivmesi,
                    hizli_lider_rank,
                    hizli_fiyat_ivme,
                    hizli_hacim_ivme,
                    hacim_gucleniyor_v5,
                    momentum_gucleniyor_v5,
                    devam_gucu_anlik
                )
                if durum is None:
                    continue

                # Son eklenen piyasa kaydına sinyal durumunu işaretle.
                try:
                    if piyasa_kayitlari and piyasa_kayitlari[-1].get("symbol") == symbol:
                        piyasa_kayitlari[-1]["sinyal_var"] = (durum in TELEGRAM_KATEGORILERI and giris_uygun)
                        piyasa_kayitlari[-1]["durum"] = durum
                except Exception:
                    pass

                haftalik_kayit_ekle(
                    symbol,
                    durum,
                    genel_skor,
                    kalite_skoru,
                    haber_skoru,
                    hacim_kat,
                    degisim3
                )

                stop = fiyat * 0.985
                hedef1 = fiyat * 1.03
                hedef2 = fiyat * 1.06

                adaylar.append({
                    "symbol": symbol,
                    "skor": genel_skor,
                    "kalite_skoru": kalite_skoru,
                    "durum": durum,
                    "alt_durum": alt_durum,
                    "fiyat": fiyat,
                    "degisim1": degisim1,
                    "degisim3": degisim3,
                    "degisim24": degisim24,
                    "hacim": hacim_kat,
                    "btcden_guclu": btcden_guclu,
                    "btc_fark": btc_fark,
                    "btc_fark1": btc_fark1,
                    "btc_fark3": btc_fark3,
                    "btc_fark24": btc_fark24,
                    "btc_guc_skoru": btc_guc_skoru,
                    "lider_skoru": lider_skoru,
                    "guc_skoru": guc_skoru,
                    "zirve_yakin": zirve_yakin,
                    "yeni_zirve": yeni_zirve,
                    "haber_skoru": haber_skoru,
                    "guclenme_bonus": guclenme_bonus,
                    "hacim_bonus": hacim_bonus,
                    "btc_fark_bonus": btc_fark_bonus,
                    "lider_bonus": lider_bonus,
                    "zirve_bonus": zirve_bonus,
                    "gec_pump_puan": gec_pump_puan,
                    "giris_kalitesi": giris_kalitesi,
                    "giris_uygun": bool(giris_uygun),
                    "giris_riskleri": giris_riskleri,
                    "tepe_riski": bool(giris_metrikleri.get("hard_block") or giris_kalitesi < GIRIS_KALITESI_MIN),
                    "runup6": giris_metrikleri.get("runup6", 0),
                    "ust_fitil_orani": giris_metrikleri.get("ust_fitil_orani", 0),
                    "kapanis_pozisyonu": giris_metrikleri.get("kapanis_pozisyonu", 0),
                    "yesil_seri": giris_metrikleri.get("yesil_seri", 0),
                    "range_genisleme": giris_metrikleri.get("range_genisleme", 0),
                    "mikro_basamak": bool(mikro_basamak),
                    "mikro_basamak_skor": mikro_basamak_skor,
                    "mikro_mum_sayisi": mikro_mum_sayisi,
                    "mikro_hacim_ivmesi": round(mikro_hacim_ivmesi, 3),
                    "mikro_bonus": mikro_bonus,
                    "guclenme_notlari": guclenme_notlari,
                    "stop": stop,
                    "hedef1": hedef1,
                    "hedef2": hedef2
                })

            except Exception as e:
                print("Coin hata:", e)
                continue

        if len(adaylar) == 0:
            print("Şu an aday yok.")

        else:
            adaylar = sorted(adaylar, key=lambda x: x.get("guc_skoru", x["skor"]), reverse=True)

            simdi = time.time()
            gosterilecekler = []

            for a in adaylar:
                symbol = a["symbol"]
                durum = a["durum"]


                eski_durum = son_durumlar.get(symbol)

                if symbol not in ilk_tespitler:
                    ilk_tespitler[symbol] = {
                        "durum": durum,
                        "zaman": simdi,
                        "skor": a["skor"],
                        "hacim": a["hacim"],
                        "degisim3": a["degisim3"]
                    }

                onceki_veri = onceki_veriler.get(symbol)
                a["onceki_veri"] = onceki_veri

                # === V5.1 arka plan yıldız adayı ve zayıf Trader Hacim filtresi ===
                hacim_gucleniyor_now, momentum_gucleniyor_now = v5_1_guclenme_bayraklari(a)
                a["hacim_gucleniyor"] = bool(hacim_gucleniyor_now)
                a["momentum_gucleniyor"] = bool(momentum_gucleniyor_now)
                a["zayif_trader_hacim"] = bool(v5_1_zayif_trader_hacim_mi(a))

                if v5_1_yildiz_adayindan_guclendi_mi(symbol, a) and durum in ("🚀 Roket Adayı", "🚀 Roket", "🔥 Elit Roket"):
                    # Aday önceden arka planda yakalandıysa güçlenince seviye yükselt.
                    durum = "🔥 Elit Roket"
                    a["durum"] = durum
                    a["alt_durum"] = "V5.1 yıldız adayı güçlendi"

                if v5_1_yildiz_adayi_mi(a) and durum not in ("🚀 Roket", "🔥 Elit Roket", "⭐ Yıldız"):
                    v5_1_yildiz_adayi_kaydet(symbol, a)
                    durum = "⭐ Yıldız Adayı"
                    a["durum"] = durum
                    a["alt_durum"] = "V5.1 arka plan yıldız adayı"

                if v5_1_zayif_trader_hacim_mi(a) and durum == "📊 TRADER HACİM":
                    # Telegram'a düşürme; piyasa/DNA kaydı zaten tutuluyor.
                    durum = "📈 İzleme"
                    a["durum"] = durum
                    a["alt_durum"] = "10x+ hacim var ama 3s momentum zayıf; DNA'da izleniyor"
                # === /V5.1 arka plan filtresi ===

                durum_degisti = eski_durum is not None and eski_durum != durum

                durum_yukseldi = (
                    eski_durum is not None
                    and eski_durum in DURUM_SEVIYESI
                    and durum in DURUM_SEVIYESI
                    and DURUM_SEVIYESI[durum] > DURUM_SEVIYESI[eski_durum]
                )

                # V4.16: Kategori geriye düşmesin.
                # Roket Adayı -> Roket -> Elit -> Yıldız çıkışı korunur.
                # Üst seviyeye çıkan coin sonraki taramada alt seviyeye düşerse eski yüksek seviye korunur.
                if (
                    eski_durum is not None
                    and eski_durum in DURUM_SEVIYESI
                    and durum in DURUM_SEVIYESI
                    and DURUM_SEVIYESI[durum] < DURUM_SEVIYESI[eski_durum]
                    and (symbol in gonderilenler or symbol in aktif_sinyaller)
                ):
                    print(f"Kategori geriye düşmedi: {symbol} | {durum} yerine {eski_durum} korundu.")
                    durum = eski_durum
                    a["durum"] = eski_durum
                    durum_degisti = False
                    durum_yukseldi = False

                son_durumlar[symbol] = durum
                onceki_veriler[symbol] = {
                    "skor": a["skor"],
                    "hacim": a["hacim"],
                    "degisim3": a["degisim3"],
                    "giris_kalitesi": a.get("giris_kalitesi", 0),
                    "durum": durum
                }

                if durum not in TELEGRAM_KATEGORILERI:
                    print(f"Arka plan: {symbol} | {durum} | Güç: {a.get('guc_skoru', 0)}/100 | Hacim: {round(a['hacim'], 2)}x")
                    continue

                # Ana değişiklik: Roket/Elit/Yıldız güçlü olsa bile giriş kalitesi düşükse mesaj yok.
                if not a.get("giris_uygun", False):
                    neden = " • ".join(a.get("giris_riskleri", [])[:3]) or "giriş kalitesi yetersiz"
                    print(
                        f"Giriş filtresi: {symbol} | {durum} | "
                        f"Giriş {a.get('giris_kalitesi', 0)}/100 < {GIRIS_KALITESI_MIN} | {neden}"
                    )
                    continue

                son_gonderim = gonderilenler.get(symbol)
                tekrar_doldu = son_gonderim is None or simdi - son_gonderim >= TEKRAR_SURESI

                if not tekrar_doldu and not durum_yukseldi:
                    continue

                a["eski_durum"] = eski_durum
                a["durum_degisti"] = durum_degisti
                a["durum_yukseldi"] = durum_yukseldi
                a["onceki_veri"] = onceki_veri

                gosterilecekler.append(a)

                if len(gosterilecekler) >= 3:
                    break

            if len(gosterilecekler) == 0:
                print("Yeni gönderilecek aday yok.")

            else:
                # V5.5.1: Her coin ayrı Telegram mesajı alır; Roket Adayı main_13 teknik AL kapısından da geçer.
                # Başlık doğrudan coin adı + kategori olur; "SYMBOL" gibi sabit metin kullanılmaz.
                baslik_map = {
                    "📊 TRADER HACİM": "TRADER HACİM",
                    "🚀 Roket Adayı": "ROKET ADAYI",
                    "🚀 Roket": "ROKET",
                    "🔥 Elit Roket": "ELİT ROKET",
                    "⭐ Yıldız": "YILDIZ"
                }

                for a in gosterilecekler:
                    symbol = a["symbol"]
                    durum = a.get("durum", "")
                    sinyal_basligi = baslik_map.get(durum, "SİNYAL")
                    ikon = durum.split()[0] if durum else "🚀"
                    bildirim_basligi = f"{ikon} {symbol} | {sinyal_basligi}"

                    gonderilenler[symbol] = simdi

                    if symbol not in aktif_sinyaller:
                        aktif_sinyaller[symbol] = {
                            "giris": a["fiyat"],
                            "stop": a["stop"],
                            "hedef1": a["hedef1"],
                            "hedef2": a["hedef2"],
                            "durum": a["durum"],
                            "zaman": simdi,
                            "hedef1_bildi": False,
                            "hedef2_bildi": False,
                            "stop_bildi": False,
                            "zirve_fiyat": a["fiyat"],
                            "guc_kaybi_bildi": False,
                            "momentum_cokusu_bildi": False
                        }
                        basari_kayitlari.append(basari_kaydi_olustur(symbol, a, simdi))
                        basari_db_kaydet(basari_kayitlari)
                    else:
                        aktif_sinyaller[symbol]["durum"] = a["durum"]

                    if a["durum_yukseldi"]:
                        eski = a["eski_durum"]
                        yeni = a["durum"]
                        onceki = a["onceki_veri"]

                        mesaj_yukselis = (
                            f"⬆️ SEVİYE ATLADI\n\n"
                            f"{symbol}\n\n"
                            f"{eski} → {yeni}\n\n"
                        )
                        if onceki is not None:
                            mesaj_yukselis += (
                                f"Skor: {round(onceki['skor'], 2)} → {round(a['skor'], 2)}\n"
                                f"Hacim: {round(onceki['hacim'], 2)}x → {round(a['hacim'], 2)}x\n"
                            )
                        else:
                            mesaj_yukselis += (
                                f"Skor: {round(a['skor'], 2)}\n"
                                f"Kalite: {round(a['kalite_skoru'], 2)}\n"
                                f"Hacim: {round(a['hacim'], 2)}x\n"
                            )
                        mesaj_yukselis += f"3s: %{round(a['degisim3'], 2)}"
                        print("Seviye atladı ama Telegram'a gönderilmedi:")
                        print(mesaj_yukselis)

                    mesaj = (
                        f"{bildirim_basligi}\n"
                        f"COIN RADAR V5.5.1\n"
                        f"BTC 3s: %{round(btc, 2)}\n\n"
                        f"{ortak_sinyal_ozeti_olustur(a)}\n\n"
                    )

                    if a["durum_degisti"]:
                        mesaj += f"Geçiş: {a['eski_durum']} → {a['durum']}\n\n"

                    guclenme_mesaji = guclenme_mesaji_olustur(a)
                    mesaj += (
                        f"Skor: {round(a['skor'], 2)}\n"
                        f"Kalite: {round(a['kalite_skoru'], 2)}\n"
                        f"🎯 Giriş Kalitesi: {a.get('giris_kalitesi', 0)}/100 ✅\n"
                        f"🚀 Devam Gücü: {v5_devam_gucu_hesapla(a)}/100 ({v5_devam_gucu_seviye(v5_devam_gucu_hesapla(a))})\n"
                        f"Hacim: {round(a['hacim'], 2)}x\n"
                    )

                    if guclenme_mesaji:
                        mesaj += f"\n{guclenme_mesaji}\n"

                    mesaj += (
                        f"\n1s: %{round(a['degisim1'], 2)} | "
                        f"3s: %{round(a['degisim3'], 2)} | "
                        f"24s: %{round(a['degisim24'], 2)}\n\n"
                        f"Fiyat: {round(a['fiyat'], 4)}\n"
                        f"Stop: {round(a['stop'], 4)}\n"
                        f"H1: {round(a['hedef1'], 4)}\n"
                        f"H2: {round(a['hedef2'], 4)}"
                    )

                    print(mesaj)
                    if telegram_gonder(mesaj):
                        print(f"Telegram gönderildi: {symbol} | {sinyal_basligi}")
                    else:
                        print(f"Telegram gönderilemedi: {symbol} | {sinyal_basligi}")

        # Ana tarama 5 dakikada bir, sessiz ön tarama ise her 60 saniyede çalışır.
        print("60 sn bekleniyor...")
        time.sleep(HIZLI_ON_TARAMA_SURESI)

    except Exception as e:
        print("Bot genel hata:", e)
        time.sleep(30)
