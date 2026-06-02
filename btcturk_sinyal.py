
import requests
import time
import feedparser
from deep_translator import GoogleTranslator

BOT_TOKEN = "8553499613:AAHkPbN5W4MS3NlwtN0HRH7PyFt_aXLiChQ"

CHAT_IDS = [
    2097448038,
    1877715122
]

TEKRAR_SURESI = 3 * 60 * 60
TARAMA_SURESI = 5 * 60

gonderilenler = {}
son_durumlar = {}
aktif_sinyaller = {}

RSS_KAYNAKLARI = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"
]

POZITIF = [
    "listing", "listed", "binance", "coinbase",
    "partnership", "etf", "airdrop", "burn",
    "launch", "mainnet", "upgrade",
    "integration", "support", "investment",
    "funding", "approval", "adoption",
    "bullish", "surge", "rally"
]

NEGATIF = [
    "hack", "exploit", "lawsuit", "delist",
    "sec", "attack", "scam", "fraud",
    "investigation", "outage", "halted",
    "stopped", "shutdown", "pressure",
    "bearish", "loss", "dump",
    "decline", "crash", "selloff",
    "down", "weakness"
]

def telegram_gonder(mesaj):
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

def cevir_tr(metin):
    try:
        return GoogleTranslator(source="auto", target="tr").translate(metin)
    except:
        return metin

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

def btc_gucu():
    try:
        d = veri_getir("BTCTRY", 6)
        c = d["c"]

        if len(c) < 4:
            return 0

        return ((c[-1] - c[-4]) / c[-4]) * 100
    except:
        return 0

def sure_yaz(saniye):
    dakika = int(saniye // 60)
    saat = dakika // 60
    kalan_dakika = dakika % 60

    if saat > 0:
        return f"{saat} saat {kalan_dakika} dk"

    return f"{dakika} dk"

def haber_puani(symbol):
    coin = symbol.replace("TRY", "").lower()

    puan = 0
    haberler = []
    negatif_haber = False

    for kaynak in RSS_KAYNAKLARI:
        try:
            feed = feedparser.parse(kaynak)

            for item in feed.entries[:25]:
                baslik = item.title.lower()

                if coin in baslik:
                    puan += 8
                    haberler.append(cevir_tr(item.title))

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

    return puan, haberler[:2]

def hedef_stop_kontrol():
    kapanacaklar = []

    for symbol, s in list(aktif_sinyaller.items()):
        fiyat = anlik_fiyat(symbol)

        if fiyat is None:
            continue

        giris = s["giris"]
        kazanc = ((fiyat - giris) / giris) * 100
        gecen_sure = sure_yaz(time.time() - s["zaman"])

        if not s["stop_bildi"] and fiyat <= s["stop"]:
            mesaj = (
                f"❌ STOP OLDU\n"
                f"{symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Stop: {round(s['stop'], 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Sonuç: %{round(kazanc, 2)}\n"
                f"Süre: {gecen_sure}"
            )
            telegram_gonder(mesaj)
            print(mesaj)
            kapanacaklar.append(symbol)
            continue

        if not s["hedef1_bildi"] and fiyat >= s["hedef1"]:
            mesaj = (
                f"✅ HEDEF 1 GELDİ\n"
                f"{symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Hedef 1: {round(s['hedef1'], 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Kazanç: %{round(kazanc, 2)}\n"
                f"Süre: {gecen_sure}"
            )
            telegram_gonder(mesaj)
            print(mesaj)
            s["hedef1_bildi"] = True

        if not s["hedef2_bildi"] and fiyat >= s["hedef2"]:
            mesaj = (
                f"🚀 HEDEF 2 GELDİ\n"
                f"{symbol}\n"
                f"Kategori: {s['durum']}\n"
                f"Giriş: {round(giris, 4)}\n"
                f"Hedef 2: {round(s['hedef2'], 4)}\n"
                f"Anlık: {round(fiyat, 4)}\n"
                f"Kazanç: %{round(kazanc, 2)}\n"
                f"Süre: {gecen_sure}"
            )
            telegram_gonder(mesaj)
            print(mesaj)
            kapanacaklar.append(symbol)

    for symbol in kapanacaklar:
        aktif_sinyaller.pop(symbol, None)

while True:

    try:
        print()
        print("AKILLI PARA RADARI")
        print("--------------------------------")

        hedef_stop_kontrol()

        btc = btc_gucu()

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

                btcden_guclu = degisim3 > btc
                son_mum_yesil = c[-1] > o[-1]
                zirve_yakin = fiyat > max(h[-12:-1]) * 0.995

                satis_baskisi = (
                    son_hacim > ort_hacim * 5
                    and degisim1 < 0
                )

                haber_skoru, haberler = haber_puani(symbol)

                hacim_skoru = min(hacim_kat * 2, 10)
                momentum_skoru = max(0, degisim3 * 2)
                btc_skoru = 3 if btcden_guclu else 0
                mum_skoru = 1 if son_mum_yesil else 0
                zirve_skoru = 1 if zirve_yakin else 0

                genel_skor = (
                    hacim_skoru * 0.40
                    + momentum_skoru * 0.30
                    + btc_skoru * 0.15
                    + haber_skoru * 0.15
                    + mum_skoru
                    + zirve_skoru
                )

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

                if haber_skoru >= 15 and genel_skor >= 18 and hacim_kat >= 5 and btcden_guclu:
                    durum = "💎 SÜPER ROKET"

                elif haber_skoru > 0 and genel_skor >= 13 and hacim_kat >= 2.5 and btcden_guclu:
                    durum = "🚀 ROKET ADAYI"

                elif genel_skor >= 10 and hacim_kat >= 2.2 and btcden_guclu:
                    durum = "🔥 GÜÇLÜ ADAY"

                elif genel_skor >= 7.5 and hacim_kat >= 3 and degisim3 > 1 and btcden_guclu:
                    durum = "📈 İZLEME ADAYI"

                else:
                    continue

                stop = fiyat * 0.985
                hedef1 = fiyat * 1.03
                hedef2 = fiyat * 1.06

                adaylar.append({
                    "symbol": symbol,
                    "skor": genel_skor,
                    "durum": durum,
                    "fiyat": fiyat,
                    "degisim1": degisim1,
                    "degisim3": degisim3,
                    "degisim24": degisim24,
                    "hacim": hacim_kat,
                    "btc": btc,
                    "btcden_guclu": btcden_guclu,
                    "haber_skoru": haber_skoru,
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
            adaylar = sorted(adaylar, key=lambda x: x["skor"], reverse=True)

            mesaj = (
                f"🚀 AKILLI PARA RADARI\n"
                f"BTC 3s: %{round(btc, 2)}\n\n"
            )

            simdi = time.time()
            gosterilecekler = []

            for a in adaylar:
                symbol = a["symbol"]
                durum = a["durum"]

                eski_durum = son_durumlar.get(symbol)
                
                durum_seviyesi = {
                    "📈 İZLEME ADAYI": 1,
                    "🔥 GÜÇLÜ ADAY": 2,
                    "🚀 ROKET ADAYI": 3,
                    "💎 SÜPER ROKET": 4
                } 

                if (
                    eski_durum is not None
                    and eski_durum in durum_seviyesi
                    and durum in durum_seviyesi
                    and durum_seviyesi[durum] > durum_seviyesi[eski_durum]
                ):
    
                    	mesaj_yukselis = (
                        f"⬆️ DURUM YÜKSELDİ\n\n"
                        f"{symbol}\n\n"
                        f"{eski_durum}\n"
                        f"⬆️\n"
                        f"{durum}\n\n"
                        f"Skor: {round(a['skor'], 2)}"
                    ) 

                    	telegram_gonder(mesaj_yukselis)
                    	print(mesaj_yukselis)
 
                if eski_durum == durum:
                    if symbol in gonderilenler:
                        if simdi - gonderilenler[symbol] < TEKRAR_SURESI:
                            continue

                a["eski_durum"] = eski_durum
                a["durum_degisti"] = durum_degisti
                gosterilecekler.append(a)

                if len(gosterilecekler) >= 5:
                    break

            if len(gosterilecekler) == 0:
                print("Yeni gönderilecek aday yok.")

            else:
                for sira, a in enumerate(gosterilecekler, start=1):
                    symbol = a["symbol"]

                    gonderilenler[symbol] = simdi
                    son_durumlar[symbol] = a["durum"]

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
                            "stop_bildi": False
                        }
                    else:
                        aktif_sinyaller[symbol]["durum"] = a["durum"]

                    satir = (
                        f"{sira}. {a['symbol']}\n"
                        f"{a['durum']}\n"
                    )

                    if a["durum_degisti"]:
                        satir += (
                            f"🔄 Durum değişti: "
                            f"{a['eski_durum']} → {a['durum']}\n"
                        )

                    satir += (
                        f"Genel Skor: {round(a['skor'], 2)}\n"
                        f"1s: {round(a['degisim1'], 2)}%\n"
                        f"3s: {round(a['degisim3'], 2)}%\n"
                        f"24s: {round(a['degisim24'], 2)}%\n"
                        f"Hacim: {round(a['hacim'], 2)} kat\n"
                        f"BTC'den güçlü: {a['btcden_guclu']}\n"
                        f"Haber skoru: {a['haber_skoru']}\n"
                        f"Fiyat: {round(a['fiyat'], 4)}\n"
                        f"Stop: {round(a['stop'], 4)}\n"
                        f"Hedef 1: {round(a['hedef1'], 4)}\n"
                        f"Hedef 2: {round(a['hedef2'], 4)}\n\n"
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