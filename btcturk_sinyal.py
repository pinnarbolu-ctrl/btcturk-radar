
import os
import time
import requests
import feedparser

BOT_TOKEN = os.getenv("BOT_TOKEN")

CHAT_IDS = [
    2097448038,
    1877715122
]

TEKRAR_SURESI = 3 * 60 * 60
TARAMA_SURESI = 5 * 60
STOP_RAPOR_SURESI = 2 * 60 * 60
SIRADISI_HACIM_SURESI = 6 * 60 * 60
LIDER_TAKIP_SURESI = 30 * 60
GUC_TAKIP_SURESI = 30 * 60
PUMP_TAKIP_SURESI = 30 * 60
HAFTALIK_RAPOR_SURESI = 7 * 24 * 60 * 60

gonderilenler = {}
son_durumlar = {}
aktif_sinyaller = {}
ilk_tespitler = {}
onceki_veriler = {}
stop_raporlari = []
son_stop_raporu = time.time()
siradisi_hacim_gonderilen = {}
lider_gecmisi = {}
guc_bildirimleri = {}
lider_bildirimleri = {}
pump_bildirimleri = {}
son_lider = None
yildiz_adaylari = {}

haftalik_kayitlar = []
son_haftalik_rapor = time.time()

STABLE_COINLER = [
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "USDP"
]


DURUM_SEVIYESI = {
    "📈 İzleme": 1,
    "🔥 Güçlü": 2,
    "🚀 Roket Adayı": 3,
    "🔥 Elit Roket": 4,
    "⭐ Yıldız": 5,
    "⚠️ Geç Pump": 0
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

    telegram_gonder(mesaj)
    print(mesaj)

    stop_raporlari = []
    son_stop_raporu = simdi


def haftalik_kayit_ekle(symbol, durum, skor, kalite_skoru, haber_skoru, hacim, degisim3):
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

    mesaj = "📊 HAFTALIK V4 RAPORU\n\n"
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

    telegram_gonder(mesaj)
    print(mesaj)

    haftalik_kayitlar = []
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

        if not s["stop_bildi"] and fiyat <= s["stop"]:
            stop_raporlari.append({
                "symbol": symbol,
                "durum": s["durum"],
                "sonuc": kazanc,
                "sure": gecen_sure
            })

            print(f"STOP RAPORA EKLENDİ: {symbol} {round(kazanc, 2)}%")

            s["stop_bildi"] = True
            kapanacaklar.append(symbol)
            continue

        if not s["hedef1_bildi"] and fiyat >= s["hedef1"]:
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
            s["hedef1_bildi"] = True

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
            s["hedef2_bildi"] = True
            kapanacaklar.append(symbol)

    for symbol in kapanacaklar:
        aktif_sinyaller.pop(symbol, None)


def siradisi_hacim_kontrol(
    symbol,
    hacim_kat,
    degisim1,
    degisim3,
    degisim24,
    fiyat,
    son_mum_yesil,
    satis_baskisi
):
    simdi = time.time()
    son_gonderim = siradisi_hacim_gonderilen.get(symbol, 0)

    if simdi - son_gonderim < SIRADISI_HACIM_SURESI:
        return

    # METRY gibi hem günlük hem 3 saatlik düşüşte hacim patlıyorsa
    # bunu "birikim" değil satış hacmi kabul ediyoruz ve mesaj atmıyoruz.
    if degisim24 < -8 and degisim3 < -2:
        return

    # Satış baskısı varsa mesaj atmıyoruz.
    if satis_baskisi:
        return

    # Sıradışı hacim artık sadece "birikim ihtimali" taşıyorsa gelsin.
    if (
        hacim_kat >= 8
        and degisim3 > -1
        and degisim24 < 15
        and degisim1 < 6
        and son_mum_yesil
    ):
        mesaj = (
            f"🚨 SIRADIŞI HACİM\\n\\n"
            f"{symbol}\\n\\n"
            f"Tür: Birikim ihtimali\\n"
            f"Hacim: {round(hacim_kat, 2)}x\\n"
            f"1s: %{round(degisim1, 2)}\\n"
            f"3s: %{round(degisim3, 2)}\\n"
            f"24s: %{round(degisim24, 2)}\\n"
            f"Fiyat: {round(fiyat, 4)}\\n\\n"
            f"Not: Hacim yüksek, satış baskısı yok, son mum yeşil."
        )

        telegram_gonder(mesaj)
        print(mesaj)

        siradisi_hacim_gonderilen[symbol] = simdi


def kategori_belirle(symbol, genel_skor, kalite_skoru, hacim_kat, haber_skoru, btcden_guclu, degisim1, degisim3, degisim24):
    gec_pump = degisim1 > 8 or degisim3 > 12 or degisim24 > 20

    if gec_pump and hacim_kat >= 4 and btcden_guclu:
        return "⚠️ Geç Pump", "Geç hareket"

    yildiz_sarti = (
        genel_skor >= 28
        and kalite_skoru >= 15
        and hacim_kat >= 5
        and btcden_guclu
    )

    # Yıldız tek taramada verilmez.
    # İlk yakalanışta aday hafızaya alınır ve Elit Roket olarak gösterilir.
    # Sonraki taramada skor ve hacim düşmemişse Yıldız olur.
    if yildiz_sarti:
        onceki_yildiz = yildiz_adaylari.get(symbol)

        if onceki_yildiz is not None:
            skor_dusmedi = genel_skor >= onceki_yildiz["skor"]
            hacim_dusmedi = hacim_kat >= onceki_yildiz["hacim"] * 0.90

            if skor_dusmedi and hacim_dusmedi:
                return "⭐ Yıldız", "Doğrulanmış güçlü aday"

        yildiz_adaylari[symbol] = {
            "skor": genel_skor,
            "hacim": hacim_kat,
            "zaman": time.time()
        }

        return "🔥 Elit Roket", "Yıldız adayı, doğrulama bekliyor"

    # Yıldız şartını kaybederse hafızadan çıkar.
    if symbol in yildiz_adaylari:
        yildiz_adaylari.pop(symbol, None)

    if (
        genel_skor >= 20
        and kalite_skoru >= 10
        and hacim_kat >= 4
        and degisim3 >= 1
        and btcden_guclu
    ):
        return "🔥 Elit Roket", "Yüksek kalite aday"

    if (
        haber_skoru > 0
        and genel_skor >= 12
        and kalite_skoru >= 8
        and hacim_kat >= 3
        and degisim3 > 0
        and btcden_guclu
    ):
        return "🚀 Roket Adayı", "Haberli"

    if (
        haber_skoru == 0
        and genel_skor >= 13
        and kalite_skoru >= 8
        and hacim_kat >= 4
        and degisim3 > 0.5
        and btcden_guclu
    ):
        return "🚀 Roket Adayı", "Sessiz"

    if genel_skor >= 12 and hacim_kat >= 4 and btcden_guclu:
        return "🔥 Güçlü", "Güçlü İzleme"

    if genel_skor >= 8.5 and hacim_kat >= 3.5 and degisim3 > 1 and btcden_guclu:
        return "📈 İzleme", "Arka plan"

    return None, None


while True:
    try:
        print()
        print("AKILLI PARA RADARI V4")
        print("--------------------------------")

        hedef_stop_kontrol()
        stop_raporu_gonder()

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

                btcden_guclu = degisim3 > btc
                son_mum_yesil = c[-1] > o[-1]
                zirve_yakin = fiyat > max(h[-12:-1]) * 0.995
                satis_baskisi = son_hacim > ort_hacim * 5 and degisim1 < 0

                haber_skoru = haber_puani(symbol)

                hacim_skoru = min(hacim_kat * 2, 10)
                momentum_skoru = max(0, degisim3 * 2)
                btc_skoru = 3 if btcden_guclu else 0
                mum_skoru = 1 if son_mum_yesil else 0
                zirve_skoru = 1 if zirve_yakin else 0

                genel_skor = (
                    hacim_skoru * 0.50
                    + momentum_skoru * 0.20
                    + btc_skoru * 0.10
                    + haber_skoru * 0.20
                    + mum_skoru
                    + zirve_skoru
                )

                kalite_skoru = (
                    hacim_skoru * 0.55
                    + momentum_skoru * 0.30
                    + btc_skoru * 0.10
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

                siradisi_hacim_kontrol(
                    symbol,
                    hacim_kat,
                    degisim1,
                    degisim3,
                    degisim24,
                    fiyat,
                    son_mum_yesil,
                    satis_baskisi
                )

                durum, alt_durum = kategori_belirle(
                    symbol,
                    genel_skor,
                    kalite_skoru,
                    hacim_kat,
                    haber_skoru,
                    btcden_guclu,
                    degisim1,
                    degisim3,
                    degisim24
                )

                if durum is None:
                    continue

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
                    "durum": durum,
                    "alt_durum": alt_durum,
                    "fiyat": fiyat,
                    "degisim1": degisim1,
                    "degisim3": degisim3,
                    "degisim24": degisim24,
                    "hacim": hacim_kat,
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
                        "hacim": a["hacim"]
                    }

                onceki_veri = onceki_veriler.get(symbol)

                durum_degisti = eski_durum is not None and eski_durum != durum

                durum_yukseldi = (
                    eski_durum is not None
                    and eski_durum in DURUM_SEVIYESI
                    and durum in DURUM_SEVIYESI
                    and DURUM_SEVIYESI[durum] > DURUM_SEVIYESI[eski_durum]
                )

                son_durumlar[symbol] = durum
                onceki_veriler[symbol] = {
                    "skor": a["skor"],
                    "hacim": a["hacim"],
                    "durum": durum
                }

                if durum == "📈 İzleme":
                    print(f"Arka plan izleme: {symbol}")
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

                if len(gosterilecekler) >= 5:
                    break

            if len(gosterilecekler) == 0:
                print("Yeni gönderilecek aday yok.")

            else:
                mesaj = (
                    f"🚀 AKILLI PARA RADARI V4\n"
                    f"BTC 3s: %{round(btc, 2)}\n\n"
                )

                for sira, a in enumerate(gosterilecekler, start=1):
                    symbol = a["symbol"]

                    gonderilenler[symbol] = simdi

                    if symbol not in aktif_sinyaller and a["durum"] != "⚠️ Geç Pump":
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

                        telegram_gonder(mesaj_yukselis)
                        print(mesaj_yukselis)

                    satir = (
                        f"{sira}. {a['symbol']}\n"
                        f"{a['durum']}\n"
                    )

                    if a["durum"] == "🚀 Roket Adayı":
                        satir += f"Tür: {a['alt_durum']}\n"

                    if a["durum"] == "🔥 Elit Roket":
                        satir += f"Not: {a['alt_durum']}\n"

                    if a["durum"] == "⭐ Yıldız":
                        satir += f"Not: {a['alt_durum']}\n"

                    if a["durum"] == "⚠️ Geç Pump":
                        satir += "Not: Hareketin önemli kısmı olmuş olabilir\n"

                    if a["durum_degisti"]:
                        satir += f"Geçiş: {a['eski_durum']} → {a['durum']}\n"

                    satir += (
                        f"Skor: {round(a['skor'], 2)}\n"
                        f"Kalite: {round(a['kalite_skoru'], 2)}\n"
                        f"Hacim: {round(a['hacim'], 2)} kat\n"
                        f"1s: %{round(a['degisim1'], 2)} | "
                        f"3s: %{round(a['degisim3'], 2)} | "
                        f"24s: %{round(a['degisim24'], 2)}\n"
                        f"BTC Gücü: {'✅' if a['btcden_guclu'] else '❌'}\n"
                        f"Haber: {a['haber_skoru']}\n"
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