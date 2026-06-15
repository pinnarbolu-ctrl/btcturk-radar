


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
son_haftalik_rapor = time.time()

STABLE_COINLER = [
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "USDP"
]


DURUM_SEVIYESI = {
    "📈 İzleme": 1,
    "⚡ GÜÇLÜ HACİM": 2,
    "📊 TRADER HACİM": 3,
    "📈 GÜÇLENİYOR": 4,
    "🚀 Roket Adayı": 5,
    "🔥 Elit Roket": 6,
    "⭐ Yıldız": 7
}

# V4.25: Telegram sadeleşti. Bu kategoriler dışındakiler sadece arka planda izlenir.
TELEGRAM_KATEGORILERI = {
    "📊 TRADER HACİM",
    "🚀 Roket Adayı",
    "🔥 Elit Roket",
    "⭐ Yıldız"
}

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


def basari_db_kaydet(veriler):
    try:
        with open(BASARI_DB_DOSYA, "w", encoding="utf-8") as f:
            json.dump(veriler[-500:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Başarı veritabanı kaydedilemedi:", e)


basari_kayitlari = basari_db_yukle()


def basari_kaydi_olustur(symbol, a, simdi):
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
    if not BOT_TOKEN:
        print("BOT_TOKEN bulunamadı. Railway Variables kontrol et.")
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
    hacim_puan = min(hacim_kat / 15, 1) * 30
    momentum_puan = min(max(degisim3, 0) / 6, 1) * 25
    btc_puan = (btc_guc_skoru / 10) * 20
    lider_puan = (lider_skoru / 10) * 15
    haber_puan = (min(haber_skoru, 20) / 20) * 10

    toplam = hacim_puan + momentum_puan + btc_puan + lider_puan + haber_puan

    # Trader ince ayar bonusları: güçlü ama spam üretmeyen küçük ödüller.
    if hacim_kat >= 20:
        toplam += 3
    elif hacim_kat >= 15:
        toplam += 2
    elif hacim_kat >= 10:
        toplam += 1

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

    # STOP raporu telegrama gonderilmiyor, sadece veri tutuluyor

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

def haftalik_rapor_gonder():
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


def kategori_belirle(symbol, genel_skor, kalite_skoru, hacim_kat, haber_skoru, btcden_guclu, btc_fark, degisim1, degisim3, degisim24, zirve_yakin, guclenme_bonus=0, btc_guc_skoru=0, lider_skoru=0, guc_skoru=0, yeni_zirve=False):
    """
    V4.25 kategori mantığı.

    Telegram sadeleşti:
    - 📊 TRADER HACİM
    - 🚀 Roket Adayı
    - 🔥 Elit Roket
    - ⭐ Yıldız

    İzleme ve Güçlü Hacim arka planda kalır; Telegram'a gönderilmez.
    Geç Pump kategori değildir; yalnızca DNA raporunda risk puanı olarak tutulur.
    """

    # 1) ⭐ YILDIZ - en seçici seviye
    if (
        guc_skoru >= 88
        and lider_skoru >= 7
        and btc_guc_skoru >= 7
        and kalite_skoru >= 14
        and hacim_kat >= 6
        and degisim1 > 1
        and degisim3 > 2
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
        and degisim3 >= 1
        and btcden_guclu
    ):
        return "🔥 Elit Roket", "Güç skoru yüksek aday"

    # 3) 🚀 ROKET ADAYI - haberli veya sessiz güçlü aday
    if (
        guc_skoru >= 62
        and kalite_skoru >= 8
        and hacim_kat >= 5
        and degisim1 > 0
        and degisim3 > 0.5
        and btcden_guclu
        and btc_guc_skoru >= 4
        and (haber_skoru > 0 or lider_skoru >= 5)
    ):
        if haber_skoru > 0:
            return "🚀 Roket Adayı", "Haberli güçlü aday"
        return "🚀 Roket Adayı", "Sessiz güçlü aday"

    # 4) 📊 TRADER HACİM - erken hacim/fiyat hareketi
    if (
        guc_skoru >= 58
        and hacim_kat >= 15
        and btcden_guclu
        and btc_guc_skoru >= 4
        and (degisim1 >= 0.2 or degisim3 >= 1)
        and (zirve_yakin or yeni_zirve)
    ):
        return "📊 TRADER HACİM", "Trader hacim + BTC gücü + fiyat teyidi"

    # Arka plan güçlü hacim
    if hacim_kat >= 12 and btcden_guclu and not (degisim1 < 0 and degisim3 < 0):
        return "⚡ GÜÇLÜ HACİM", "Arka plan güçlü hacim"

    # Arka plan izleme
    if genel_skor >= 8.5 and 5 <= hacim_kat < 12 and degisim3 > 1 and btcden_guclu:
        return "📈 İzleme", "Arka plan izleme"

    return None, None


while True:
    try:
        print()
        print("COIN RADAR V4.26.1")
        print("--------------------------------")

        hedef_stop_kontrol()
        stop_raporu_gonder()

        btc_d = btc_degisimleri()
        btc = btc_d.get("3s", 0)

        ticker = requests.get(
            "https://api.btcturk.com/api/v2/ticker",
            timeout=10
        ).json()["data"]

        adaylar = []

        for coin in ticker:
            try:
                symbol = coin["pair"]

                if not symbol.endswith("TRY"):
                    continue

                if symbol == "BTCTRY":
                    continue

                if stable_coin_mi(symbol):
                    continue

                if len(symbol) > 15:
                    continue

                d = veri_getir(symbol, 24)

                o = d["o"]
                h = d["h"]
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

                hacim_skoru = min(hacim_kat * 2, 10)
                momentum_skoru = max(0, degisim3 * 2)
                btc_skoru = btc_guc_skoru
                mum_skoru = 1 if son_mum_yesil else 0
                zirve_skoru = 1 if zirve_yakin else 0

                genel_skor = (
                    hacim_skoru * 0.50
                    + momentum_skoru * 0.20
                    + btc_skoru * 0.15
                    + haber_skoru * 0.20
                    + mum_skoru
                    + zirve_skoru
                )

                kalite_skoru = (
                    hacim_skoru * 0.55
                    + momentum_skoru * 0.30
                    + btc_skoru * 0.15
                    + mum_skoru
                    + zirve_skoru
                )

                if hacim_kat >= 5:
                    genel_skor += 4

                if hacim_kat >= 8:
                    genel_skor += 6

                # V4.25 commit: çok yüksek trader hacmini daha net ödüllendir.
                hacim_bonus = 0
                if hacim_kat >= 20:
                    hacim_bonus = 3
                elif hacim_kat >= 15:
                    hacim_bonus = 2
                elif hacim_kat >= 10:
                    hacim_bonus = 1
                genel_skor += hacim_bonus

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


                guclenme_bonus, guclenme_notlari = guclenme_bonusu_hesapla(
                    symbol,
                    genel_skor,
                    hacim_kat,
                    degisim3
                )

                if guclenme_bonus > 0:
                    genel_skor += guclenme_bonus

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

                # Piyasa analizi: Sinyal üretmese bile tüm coinlerin son durumunu kaydet.
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
                    yeni_zirve
                )
                if durum is None:
                    continue

                # Son eklenen piyasa kaydına sinyal durumunu işaretle.
                try:
                    if piyasa_kayitlari and piyasa_kayitlari[-1].get("symbol") == symbol:
                        piyasa_kayitlari[-1]["sinyal_var"] = durum in TELEGRAM_KATEGORILERI
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

                durum_degisti = eski_durum is not None and eski_durum != durum

                durum_yukseldi = (
                    eski_durum is not None
                    and eski_durum in DURUM_SEVIYESI
                    and durum in DURUM_SEVIYESI
                    and DURUM_SEVIYESI[durum] > DURUM_SEVIYESI[eski_durum]
                )

                # V4.16: Kategori geriye düşmesin.
                # Roket -> Elit -> Yıldız çıkışı korunur.
                # Elit olmuş coin sonraki taramada tekrar Roket'e düşerse eski yüksek seviye korunur.
                if (
                    eski_durum is not None
                    and eski_durum in DURUM_SEVIYESI
                    and durum in DURUM_SEVIYESI
                    and DURUM_SEVIYESI[durum] < DURUM_SEVIYESI[eski_durum]
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
                    "durum": durum
                }

                if durum not in TELEGRAM_KATEGORILERI:
                    print(f"Arka plan: {symbol} | {durum} | Güç: {a.get('guc_skoru', 0)}/100 | Hacim: {round(a['hacim'], 2)}x")
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
                # Bildirim başlığı: kilit ekranında sinyal tipi ilk satırda görünsün.
                # Birden fazla coin varsa en yüksek kategori başlığa yazılır.
                en_ust_sinyal = sorted(
                    gosterilecekler,
                    key=lambda x: DURUM_SEVIYESI.get(x.get("durum"), 0),
                    reverse=True
                )[0].get("durum")

                baslik_map = {
                    "🚀 Roket Adayı": "🚀 ROKET ADAYI",
                    "🔥 Elit Roket": "🔥 ELİT ROKET",
                    "⭐ Yıldız": "⭐ YILDIZ"
                }
                bildirim_basligi = baslik_map.get(en_ust_sinyal, "COIN RADAR")

                mesaj = (
                    f"{bildirim_basligi}\n"
                    f"COIN RADAR V4.29\n"
                    f"BTC 3s: %{round(btc, 2)}\n\n"
                )

                for sira, a in enumerate(gosterilecekler, start=1):
                    symbol = a["symbol"]

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

                    elif symbol in aktif_sinyaller:
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

                    satir = (
                        f"{sira}. {a['symbol']}\n"
                        f"{ortak_sinyal_ozeti_olustur(a)}\n\n"
                    )

                    if a["durum_degisti"]:
                        satir += f"Geçiş: {a['eski_durum']} → {a['durum']}\n\n"

                    guclenme_mesaji = guclenme_mesaji_olustur(a)

                    satir += (
                        f"Skor: {round(a['skor'], 2)}\n"
                        f"Kalite: {round(a['kalite_skoru'], 2)}\n"
                        f"Hacim: {round(a['hacim'], 2)}x\n"
                    )

                    if guclenme_mesaji:
                        satir += f"\n{guclenme_mesaji}\n"

                    satir += (
                        f"\n1s: %{round(a['degisim1'], 2)} | "
                        f"3s: %{round(a['degisim3'], 2)} | "
                        f"24s: %{round(a['degisim24'], 2)}\n\n"
                        f"Fiyat: {round(a['fiyat'], 4)}\n"
                        f"Stop: {round(a['stop'], 4)}\n"
                        f"H1: {round(a['hedef1'], 4)}\n"
                        f"H2: {round(a['hedef2'], 4)}\n\n"
                    )

                    print(satir)
                    mesaj += satir

                telegram_gonder(mesaj)
                print("Telegram gönderildi.")

        print("5 dk bekleniyor...")
        time.sleep(TARAMA_SURESI)

    except Exception as e:
        print("Bot genel hata:", e)
        time.sleep(30)

