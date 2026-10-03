#!/usr/bin/env python3
# ██ DRAFT V129d1 — JANGAN SWAP KE VPS — PEMBANGUNAN BELUM LENGKAP (batch-2: orderLinkId,
# ██ EXITFIX ladder, registry posisi, statistik group MASIH ANTRE) — swap hanya di batas jendela W5
# ██ setelah sidang #4 + ritual lengkap BUILD_PROTOCOL. File live = winrate2_FINAL_V128p3_OPS.py.
# V125 GOLD35 SALDO-JELAS & BTC/IDR RAKSASA — DISPLAY ONLY, logika trading TIDAK berubah
#   - baris BTC & IDR jadi baris penuh background + karakter spasi (terlihat 2x lebih besar)
#   - label saldo eksplisit: SALDO BURSA (total akun futures) vs MODAL BOT (cap yang dipakai)
#   - dibangun dari V125 GOLD35 EPOCH-FLEX (env GE_MARGIN_PCT & GE_EPOCH_MS tetap) — GE_EPOCH_MS=now mereset jendela vonis SINCE (mis. saat ganti size margin);
#   default tetap epoch V114 pertama. LOGIKA TRADING TIDAK BERUBAH.
#   TOTAL RIWAYAT = rolling 100 closed terakhir, bukan seumur hidup -> tracker ini patokan vonis yang sah.
#   sumber: positionMargin Bybit, fallback size*entry/lev. LOGIKA TRADING TIDAK BERUBAH.
#   pasangan kartu tetap 2 kolom; LOGIKA TRADING TIDAK BERUBAH.
#   1 posisi = stacked 3 baris. LOGIKA TRADING TIDAK BERUBAH (gate rezim, crash guard, entry, exit tetap).
#   wallet demo/top-up exchange tampil kompak di baris cap (tidak menakuti dgn Rp miliaran)
#   (closed_pnl_cache & cached_futures_balance belum declared global di main() -> assignment jadi variabel lokal)
#   hijau kedip = BULL: ENTRY LONG SAJA | kuning kedip = NON-BULL: ENTRY SHORT SAJA | merah kedip cepat = CRASH: NO NEW LONG
#   (BTC 20jam < -3% ATAU 7hari < -5%) walau badge 30-hari masih BULL — asuransi tail-risk, EV netral di backtest
#   bukti: validasi 6 bulan data asli 187 hari x 21 coin, EV +0.030R -> +0.183R (6x), total +224.9R
# EDGE TERUJI DATA ASLI BINANCE 21 HARI x 22 COIN (44000 candle 15m):
#   SINYAL ROC-20H+RSI14 (ROC 80x15m = ±20 jam — V129d1 RENAME: dulu SALAH LABEL "trend 1H") + zona>=4.0
#   BUY: roc20h>+1.0% RSI>52 | SELL: roc20h<-2.0% RSI<46 + BTC roc20h juga turun
#   SL 2.0xATR anti-hunt 0.05 buffer 0.15 (cap 2.5% floor 0.8%) | TP 1.5R/2.5R/3.5R split 50/30/20 + BE + TRAIL
#   VALIDASI SEMUA CANDLE 21 HARI x 22 COIN (44000 candle asli, fee 0.145%):
#   3943 trades WR 50.2% EV +0.147R/trade TOTAL +578R | EV Buy +0.21R | 15/22 coin profit
# RANDOM FALLBACK DIHAPUS TOTAL — kalau kline gagal = NO-DATA = SKIP ENTRY (bukan angka acak)
# BUG 1: POSISI AKTIF /3 -> /GE_MAX_POS
# BUG 2: WATCHDOG THRESHOLD 6.0->5.5, 5.0->4.5, 4.0->3.5, 3.0->2.8 biar 86% SIAP ada 2-3 coin bukan 0
# BUG 3: ZONA FORMULA 2.0+vol*0.8+trend*0.22 -> 1.8+vol*0.6+trend*0.18+fuel*0.25 biar avg 3.5-4.0 variasi lebih banyak merah orange
# BUG 4: RR DI POSISI AKTIF PAKAI REAL RR, BUKAN pnl_pct/75
# BUG 5: TP BERTAHAP REAL DI API — 50%@1R 30%@2R 20%@3R+trail via limit reduceOnly
# BUG 6: FETCH KLINE RETRY 3x + API.BYBIT.COM DULU baru DEMO
print("V125 GOLD35 INDIKATOR REAL — HTFRSI EDGE TERUJI DATA ASLI — TANPA RANDOM")

import os, json, time, threading, random, math, sys, re
from decimal import Decimal, ROUND_DOWN
from decimal import getcontext as _dgctx
_dgctx().prec = 50  # V128: presisi desimal koin mikro (anti InvalidOperation)
from datetime import datetime

GE_R1 = os.environ.get("GE_R1","LONGGA").upper().strip()
if GE_R1 not in ["LONGGA","KETAT"]:
    GE_R1 = "LONGGA"
GE_ZONA = float(os.environ.get("GE_ZONA","4.0"))  # V111: default 4.0 = setting teruji data asli (EV +0.18R/7698 trades)
GE_AKUN_ENV = os.environ.get("GE_AKUN","")
GE_CAP = float(os.environ.get("GE_CAP","100"))
GE_MARGIN_PCT = float(os.environ.get("GE_MARGIN_PCT","10"))
GE_MAX_POS = int(os.environ.get("GE_MAX_POS","10"))

LEV_STD_MAJOR = 50
LEV_STD_ALT = 25
MAX_LEVERAGE = 50
LEV_SL_GAP = 1.5
LEV_MR_PCT = 0.015
ANTI_HUNT_ATR = 0.05
FINAL_BUFFER_ATR = 0.15
# V111: SL DEKAT (2.0 ATR, cap 2.5%, floor 0.8%) + TP JAUH (1.5R/2.5R/3.5R) — teruji data asli EV +0.14R
SL_ATR_MULT = 2.0
SL_PCT_MAX = 0.025
SL_PCT_MIN = 0.008
TP1_R = 1.5
TP2_R = 2.5
TP3_R = 3.5
# V111 FINAL: threshold sinyal HTFRSI teruji data asli (varian F terbaik EV +0.147R/trade, total +578R/21hari)
SIG_BUY_ROC20H = 1.0     # ROC-20H coin (80 bar 15m) > +1.0% — V129d1 rename dari SIG_BUY_ROC20H (dulu salah label "trend 1H")
SIG_BUY_RSI = 52.0    # RSI14 > 52
SIG_SELL_ROC20H = -2.0   # ROC-20H coin < -2.0% (ketat — short cuma saat downtrend kuat)
SIG_SELL_RSI = 46.0   # RSI14 < 46
# V125 GOLD35 ANTI-PUCUK & ANTI-CHURN (teruji data asli 41 hari):
SIG_BUY_RSI_MAX = 75.0   # jangan BUY saat overbought ekstrem (RSI>75 = mengejar pump)
SIG_SELL_RSI_MIN = 25.0  # jangan SELL saat oversold ekstrem
PULLBACK_ATR = 0.5       # harga boleh maks 0.5 ATR di atas EMA9 (BUY) / bawah EMA9 (SELL) — tunggu harga napas dulu
COOLDOWN_SEC = 7200      # 2 jam per coin setelah entry — cegah re-entry churn di harga lebih buruk
# V125 GOLD35 REZIM-GATE — hasil validasi 6 bulan data asli (2026-03-20 s/d 09-24, 21 coin, 2037 trades):
#   V113 polos lintas rezim EV cuma +0.030R (Mar/Apr/Mei negatif — bulan whipsaw dua sisi sama-sama rugi)
#   + gate rezim BTC ROC-30-hari: LONG hanya saat BULL (>+5%), SHORT hanya di luar BULL
#   => EV +0.183R (6x lipat), total +224.9R/6bln, bulan negatif 3->2, Agu +0.59 Sep +0.20
#   bukti per sisi: LONG hanya untung Agu(+0.60R)/Sep(+0.20R) = bulan BULL; SHORT untung Mar/Jun/Jul = non-BULL
_epoch_env = os.environ.get("GE_EPOCH_MS","")
# V127 FAIL-LOUD: tanpa epoch eksplisit bot MENOLAK hidup (mencegah instance bayangan epoch default)
if not (_epoch_env=="now" or _epoch_env.isdigit()):
    print("V127 FAIL-LOUD: set GE_EPOCH_MS=<ms> atau GE_EPOCH_MS=now. Bot menolak hidup tanpa epoch eksplisit.", flush=True)
    raise SystemExit(2)
V114_START_MS = int(time.time()*1000) if _epoch_env=="now" else int(_epoch_env)
# default 2026-09-24 07:57:56 UTC = saat V114 pertama start di VPS; GE_EPOCH_MS=now -> reset jendela vonis (ganti size dll)
REGIME_ENABLED = True        # True = gate aktif; False = perilaku persis V113
REGIME_ROC30_LONG_MIN = 5.0  # LONG butuh BTC ROC 30 hari > +5.0%; SHORT butuh <= +5.0% (gate BTC htf<0 lama tetap)
# V115 CRASH-GUARD: circuit breaker CEPAT (reaksi hitungan jam, bukan 30 hari)
# LONG baru diblokir kalau BTC sendiri jatuh keras: ROC 20 jam < -3% ATAU ROC 7 hari < -5%
# backtest 6 bln: EV netral (+0.1626 vs +0.1628) = asuransi gratis, bukan sumber edge
CRASH_GUARD_ENABLED = True
CRASH_BTC20H_MIN = -3.0   # BTC ROC 20 jam (htf states) di bawah ini = crash -> NO NEW LONG
CRASH_BTC7D_MIN  = -5.0   # BTC ROC 7 hari di bawah ini = crash -> NO NEW LONG
# + short butuh BTC htf < 0 (alignmen market) — dicek di force_loop
FEE_R = 0.15
FUNDING_R = 0.02
SLIP_PCT = 0.08
LOOP_API = 5
LOOP_FORCE = 30

SPINNER_BRAILLE = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

def rgb_fg(r,g,b): return f"\033[38;2;{int(r)};{int(g)};{int(b)}m"
def _sp(s): return ' '.join(s)  # V125: karakter direnggangkan biar terlihat besar
def get_pulse_color(br,bg,bb, speed=3.2, min_mult=0.45, max_mult=1.0):
    # V106 NO BLINK: return warna tetap, tidak pakai sin() kedip
    return rgb_fg(br,bg,bb)

def get_leverage_std(sym): 
    # V104 BULLETPROOF: tier leverage aman
    up=sym.upper()
    if any(x in up for x in ["BTC"]):
        return (30,"MAJOR")  # BTC max 30x biar liq jauh
    elif any(x in up for x in ["ETH"]):
        return (25,"MAJOR")
    elif any(x in up for x in ["SOL","BNB"]):
        return (15,"MAJOR")
    else:
        return (12,"ALT")  # ALT max 12x bulletproof

def calc_liquidation_price(entry, lev, side="Buy"):
    # Bybit UTA cross: liq ≈ entry * (1 - 0.9/lev) long, (1+0.9/lev) short — 0.9 = 1 - maint 0.5% - fee 0.5%
    try:
        if lev<=0: lev=1
        if side=="Buy":
            return entry * (1 - 0.85/lev)  # 0.85 lebih konservatif
        else:
            return entry * (1 + 0.85/lev)
    except:
        return entry*0.85 if side=="Buy" else entry*1.15

def smart_leverage_safe(sym, entry, sl, atr=None, side="Buy"):
    # V104 BULLETPROOF AUDIT TOTAL — pastikan liq selalu di luar SL + 0.5*ATR buffer
    try:
        std, kelas = get_leverage_std(sym)
        if atr is None or atr<=0:
            atr = entry*0.02
        if atr>entry*0.08: atr=entry*0.03  # cap ATR max 3%
        # sl sudah final termasuk anti-hunt + final buffer di caller, tapi kita hitung ulang total untuk audit
        # total SL distance = |entry-sl|
        dist_total = abs(entry - sl) / entry if entry!=0 else 0.03
        if dist_total<0.008: dist_total=0.008  # minimal 0.8%
        if dist_total>0.12: dist_total=0.12  # maximal 12%
        # extra safety buffer 0.5*ATR harus di luar SL
        extra_buf = (atr*0.5)/entry if entry!=0 else 0.005
        dist_for_liq = dist_total + extra_buf  # jarak yang harus dilampaui liq
        # lev dari likuidasi: 0.85/lev > dist_for_liq * 1.4 (40% safety)
        lev_by_liq = 0.85 / (dist_for_liq * 1.4) if dist_for_liq>0 else std
        # lev dari gap SL: 1/(dist*1.5+0.015)
        lev_by_gap = 1.0 / (dist_total * LEV_SL_GAP + LEV_MR_PCT) if dist_total>0 else std
        # lev aman = min keduanya + std
        lev_aman = min(lev_by_liq, lev_by_gap, std)
        # tier by price — harga kecil leverage harus lebih kecil
        if entry<0.1:  # BONK, PEPE, SHIB
            lev_aman = min(lev_aman, 8)
        elif entry<1.0:  # IMX 0.15, ADA 0.45
            lev_aman = min(lev_aman, 10)
        elif entry<10:  # XRP 0.5, DOGE 0.15, ARB 1.2, OP 2.5, RNDR 7.5
            lev_aman = min(lev_aman, 12)
        elif entry<100:  # SOL 150? actually SOL 150 >100, so 15x
            lev_aman = min(lev_aman, 15)
        else:  # BTC 86k, ETH 3k
            lev_aman = min(lev_aman, std)
        lev = int(max(1, min(MAX_LEVERAGE, lev_aman)))
        # final bulletproof loop: turunkan lev sampai liq di luar SL + 0.5*ATR
        for _ in range(15):
            liq = calc_liquidation_price(entry, lev, side)
            if side=="Buy":
                # LONG: liq harus < SL - 0.3*ATR (liq lebih bawah dari SL)
                required_liq_max = sl - atr*0.3
                if liq < required_liq_max:
                    break
            else:
                required_liq_min = sl + atr*0.3
                if liq > required_liq_min:
                    break
            lev = max(1, lev-1)
        # minimal lev 1, maximal sesuai tier
        lev = max(1, min(lev, std))
        return lev, kelas, dist_total
    except:
        return 8, "ALT", 0.03
def calc_fee_aware_tp(sl_dist, rr, leverage, px=50000.0):
    fee_r=FEE_R; funding_r=FUNDING_R; slip_r=SLIP_PCT/100*px/sl_dist if sl_dist>0 else 0.05
    rr_kotor=rr+fee_r+funding_r+slip_r
    return sl_dist*rr_kotor, rr_kotor, fee_r, funding_r, slip_r

def filter_BN_detail(zona, rdy, fuel, regime, rr, trend, atr, price):
    ok=True
    if regime!="BULL TREND": ok=False
    if zona<4.8: ok=False
    if rr<1.8: ok=False
    if rdy<55: ok=False
    if trend<=1.0: ok=False
    if fuel<40: ok=False
    return ok, 85, f"BULL zona{zona:.1f} RR{rr:.1f} RDY{rdy} trend{trend:.1f} fuel{fuel}%"

def filter_BM_detail(zona, rdy, fuel, regime, rr, trend, atr, price):
    ok = fuel>25 and zona>=4.5 and rr>=2.0 and rdy>=55
    return ok, 80, f"COMBO fuel{fuel}% zona{zona:.1f} RR{rr:.1f} RDY{rdy}"

def filter_M_detail(zona, rdy, fuel, regime, rr, trend, atr, price):
    keras=(1 if zona>=5.5 else 0)+(1 if rr>=1.3 else 0)+(1 if rdy>=50 else 0)+(1 if fuel>=40 else 0)
    ok = zona>=5.5 and rr>=1.3 and rdy>=50 and keras>=3
    return ok, 80, f"SUPER zona{zona:.1f} RR{rr:.1f} RDY{rdy} KERAS{keras}/4"

def filter_W_detail(zona, rdy, fuel, regime, rr, trend, atr, price):
    ok = regime in ["SIDEWAYS","ROTATION"] and zona>=3.0 and rr>=1.5 and rdy>=45 and fuel>=30
    return ok, 75, f"BEST {regime} zona{zona:.1f} RR{rr:.1f} RDY{rdy} fuel{fuel}%"

def filter_BQ_detail(zona, rdy, fuel, regime, rr, trend, atr, price):
    # V110: BQ filter lebih longgar biar ride max 15%+ lebih sering — zona>=3.5 RR>=2.0 (dulu 4.0/2.5)
    ok = zona>=3.5 and rr>=2.0 and rdy>=45 and fuel>=30
    return ok, 70, f"IFVG zona{zona:.1f} RR{rr:.1f} RDY{rdy} fuel{fuel}%"

def filter_BR_detail(zona, rdy, fuel, regime, rr, trend, price):
    ok = zona>=3.5 and rr>=2.0 and rdy>=45
    return ok, 68, f"BOS zona{zona:.1f} RR{rr:.1f} RDY{rdy}"

# V99 FIX: GET QTY STEP PER COIN — biar tidak ENTRY FAIL karena qty invalid
qty_step_cache={}
# Hardcode table Bybit linear (karena API CloudFront block di sandbox, fallback by price)
HARDCODE_QTY = {
    "BTCUSDT":(0.001,0.001),
    "ETHUSDT":(0.01,0.01),
    "SOLUSDT":(0.1,0.1),
    "BNBUSDT":(0.01,0.01),
    "XRPUSDT":(1,1),
    "ADAUSDT":(1,1),
    "DOGEUSDT":(1,1),
    "AVAXUSDT":(0.1,0.1),
    "LINKUSDT":(0.1,0.1),
    "LTCUSDT":(0.1,0.1),  # V112 FIX: Bybit linear qtyStep 0.1 (dulu 0.01 -> Qty invalid)
    "TRXUSDT":(1,1),
    "DOTUSDT":(0.1,0.1),
    "BCHUSDT":(0.01,0.01),
    "NEARUSDT":(0.1,0.1),
    "MATICUSDT":(1,1),
    "ETCUSDT":(0.1,0.1),
    "FILUSDT":(0.1,0.1),
    "ATOMUSDT":(0.1,0.1),
    "APTUSDT":(0.1,0.1),
    "ARBUSDT":(0.1,0.1),
    "OPUSDT":(0.1,0.1),
    "INJUSDT":(0.1,0.1),
    "STXUSDT":(1,1),
    "IMXUSDT":(0.1,0.1),
    "RNDRUSDT":(0.1,0.1),
    "TAOUSDT":(0.01,0.01),
    "SEIUSDT":(1,1),
    "PEPEUSDT":(1000,1000),
    "WIFUSDT":(1,1),
    "BONKUSDT":(1000,1000),
}
# V107: PRICE TICK SIZE per coin biar SL TP tidak 0 untuk coin kecil
HARDCODE_PRICE_TICK = {
    "BTCUSDT":0.1,
    "ETHUSDT":0.01,
    "SOLUSDT":0.01,
    "BNBUSDT":0.01,
    "XRPUSDT":0.0001,
    "ADAUSDT":0.0001,
    "DOGEUSDT":0.00001,
    "AVAXUSDT":0.001,
    "LINKUSDT":0.001,
    "LTCUSDT":0.01,
    "TRXUSDT":0.00001,
    "DOTUSDT":0.001,
    "BCHUSDT":0.1,
    "NEARUSDT":0.0001,
    "MATICUSDT":0.0001,
    "ETCUSDT":0.001,
    "FILUSDT":0.001,
    "ATOMUSDT":0.001,
    "APTUSDT":0.001,
    "ARBUSDT":0.0001,
    "OPUSDT":0.0001,
    "INJUSDT":0.001,
    "STXUSDT":0.0001,
    "IMXUSDT":0.0001,
    "RNDRUSDT":0.001,
    "TAOUSDT":0.01,
    "SEIUSDT":0.0001,
    "PEPEUSDT":0.0000001,
    "WIFUSDT":0.0001,
    "BONKUSDT":0.0000001,
}
def get_price_tick(sym):
    if sym in qty_step_cache and len(qty_step_cache[sym])>2 and qty_step_cache[sym][2]>0:
        return qty_step_cache[sym][2]
    return HARDCODE_PRICE_TICK.get(sym, 0.01 if "BTC" in sym else 0.0001)

def format_price_by_tick(price, sym):
    # format sesuai tick biar tidak jadi 0 untuk coin kecil
    try:
        tick = get_price_tick(sym)
        # tentukan decimals dari tick
        if tick>=1:
            return f"{price:.0f}"
        elif tick>=0.1:
            return f"{price:.1f}"
        elif tick>=0.01:
            return f"{price:.2f}"
        elif tick>=0.001:
            return f"{price:.3f}"
        elif tick>=0.0001:
            return f"{price:.4f}"
        elif tick>=0.00001:
            return f"{price:.5f}"
        elif tick>=0.000001:
            return f"{price:.6f}"
        else:
            return f"{price:.8f}"
    except:
        if price>1000:
            return f"{price:.1f}"
        elif price>10:
            return f"{price:.2f}"
        elif price>1:
            return f"{price:.4f}"
        else:
            return f"{price:.6f}"
def get_qty_step(sym, price=0):
    try:
        if sym in qty_step_cache:
            return qty_step_cache[sym]
        import requests
        for base in ["https://api.bybit.com","https://api-demo.bybit.com"]:
            try:
                r=requests.get(f"{base}/v5/market/instruments-info", params={"category":"linear","symbol":sym}, timeout=5, headers={"User-Agent":"Mozilla/5.0"})
                j=r.json()
                if j.get("retCode")==0 and j.get("result",{}).get("list"):
                    info=j["result"]["list"][0]
                    lot=info.get("lotSizeFilter",{})
                    qty_step=float(lot.get("qtyStep","0.001") or "0.001")
                    min_qty=float(lot.get("minOrderQty","0.001") or "0.001")
                    tick=float((info.get("priceFilter",{}) or {}).get("tickSize","0") or 0)
                    qty_step_cache[sym]=(qty_step, min_qty, tick)
                    return qty_step, min_qty, tick
            except:
                continue
        if sym in HARDCODE_QTY:
            qty_step_cache[sym]=(HARDCODE_QTY[sym][0], HARDCODE_QTY[sym][1], HARDCODE_PRICE_TICK.get(sym,0.0001))
            return qty_step_cache[sym]
    except:
        pass
    return None

# V111: FALLBACK BINANCE PUBLIC (data-api.binance.vision) kalau Bybit kline gagal — data REAL, bukan random
def fetch_kline_binance(sym, interval="15m", limit=100):
    try:
        import requests
        r=requests.get("https://data-api.binance.vision/api/v3/klines", params={"symbol":sym,"interval":interval,"limit":limit}, timeout=6, headers={"User-Agent":"Mozilla/5.0"})
        j=r.json()
        kl=[]
        for row in j:
            try: kl.append([int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
            except: continue
        if len(kl)>=20: return kl
    except: pass
    return []

# BUG 6 FIX: FETCH KLINE RETRY 3x + API.BYBIT.COM DULU baru DEMO, terakhir BINANCE PUBLIC
def fetch_kline(sym, interval="15", limit=100, strict=False):
    try:
        import requests
        # BUG 6 FIX: coba real dulu baru demo, retry 3x per base
        for base in ["https://api.bybit.com","https://api-demo.bybit.com"]:
            for attempt in range(3):
                try:
                    r=requests.get(f"{base}/v5/market/kline", params={"category":"linear","symbol":sym,"interval":interval,"limit":limit}, timeout=6, headers={"User-Agent":"Mozilla/5.0"})
                    j=r.json()
                    if j.get("retCode")==0 and j.get("result",{}).get("list"):
                        rows=list(reversed(j["result"]["list"]))
                        kl=[]
                        for row in rows:
                            try: kl.append([int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])])
                            except: continue
                        if len(kl)>=20:
                            KLINE_SRC[(sym,str(interval))]="bybit"; return kl
                except:
                    pass
                time.sleep(0.3)
    except: pass
    # V111: Bybit gagal -> fallback Binance public (REAL data, hindari NO-DATA)
    if strict: return []
    try:
        iv=f"{interval}m" if not str(interval).endswith("m") else str(interval)
        kl=fetch_kline_binance(sym, iv, limit)
        if kl:
            KLINE_SRC[(sym,str(interval))]="binance"; return kl
    except: pass
    return []

# V125 GOLD35: rezim BTC dari candle daily — cache 15 menit, Bybit D -> fallback Binance 1d
# mengembalikan (roc30_hari, roc7_hari); roc7 dipakai CRASH-GUARD
_btc_roc30_cache = {"v": None, "r7": None, "t": 0.0}
REGIME_STATUS="OK"
def get_btc_regime():
    global REGIME_STATUS
    now = time.time()
    if _btc_roc30_cache["v"] is not None and now - _btc_roc30_cache["t"] < 900:
        REGIME_STATUS="OK"
        return _btc_roc30_cache["v"], _btc_roc30_cache["r7"]
    val = None; r7 = None
    for fetcher, iv in ((fetch_kline, "D"),):
        try:
            kl = fetcher("BTCUSDT", iv, 40, strict=True)
            if kl and len(kl) >= 31:
                val = (kl[-1][4] / kl[-31][4] - 1.0) * 100.0
                r7  = (kl[-1][4] / kl[-8][4]  - 1.0) * 100.0
                break
        except: pass
    if val is not None:
        _btc_roc30_cache["v"] = val; _btc_roc30_cache["r7"] = r7; _btc_roc30_cache["t"] = now
        REGIME_STATUS="OK"
        return val, r7
    REGIME_STATUS="STALE"
    # belum pernah dapat data: 0.0 = non-BULL (konservatif: LONG blok, SHORT boleh); r7 0.0 = guard tidak aktif
    return (_btc_roc30_cache["v"] if _btc_roc30_cache["v"] is not None else 0.0), (_btc_roc30_cache["r7"] if _btc_roc30_cache["r7"] is not None else 0.0)
def get_btc_roc30():
    return get_btc_regime()[0]

filter_logs=[]
filter_logs_lock=threading.Lock()
def add_filter_log(msg):
    with filter_logs_lock:
        ts=datetime.now().strftime("%H:%M:%S")
        clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', msg)
        filter_logs.append(f"{ts} {clean}")
        if len(filter_logs)>15: filter_logs.pop(0)

# V111 ============================================================
# INDIKATOR 100% REAL DETERMINISTIK — TANPA RANDOM SAMA SEKALI
# Sinyal entry = ROC-20H+RSI14: ROC 80 bar 15m (±20 jam) + konfirmasi RSI14
#   (V129d1 rename — dulu salah label "trend 1H"; perilaku TIDAK berubah)
#   roc20h > +1.0% dan RSI > 52  -> SIG Buy  (LONG)
#   roc20h < -2.0% dan RSI < 46  -> SIG Sell (SHORT)
# Teruji data asli Binance 21 hari x 22 coin: EV +0.14R/trade WR 52%
# Kalau kline gagal / data kurang -> NO-DATA (zona 0, sig kosong) -> TIDAK entry
# ============================================================
def _ema_vals(vals, n):
    k = 2.0/(n+1); e = vals[0]; out=[e]
    for v in vals[1:]:
        e = v*k + e*(1.0-k); out.append(e)
    return out

def _rsi_calc(closes, n=14):
    if len(closes) < n+2: return 50.0
    gains=[0.0]; losses=[0.0]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]; gains.append(max(d,0.0)); losses.append(max(-d,0.0))
    ag=sum(gains[1:n+1])/n; al=sum(losses[1:n+1])/n
    for i in range(n+1,len(closes)):
        ag=(ag*(n-1)+gains[i])/n; al=(al*(n-1)+losses[i])/n
    if al<=0: return 100.0
    return 100.0-100.0/(1.0+ag/al)

def calc_real_full_with_filter_log(sym):
    # return 14 field: zona,rdy,fuel,atr,price,regime,best_var,ai,rr,trend,reason,sig,htf,rsi
    NODATA=(0.0,0,0,0.0,0.0,"NO DATA","W",0,0.0,0.0,f"{sym} NO-DATA skip entry","",0.0,50.0)
    try:
        kl=fetch_kline(sym,"15",100)
        if not kl or len(kl)<86:
            return NODATA
        # V129d1 CLOSED-BAR: buang candle yang MASIH BERJALAN — semua indikator (harga, ATR,
        # trend, ROC-20H, RSI, EMA9, mom, fuel) lahir dari candle yang SUDAH close, sama
        # persis dengan definisi backtest/lab tersertifikasi (bar closed).
        # Usia candle terakhir <900s = masih forming -> pangkas. Bila API hanya mengembalikan
        # candle closed (usia >=900s) tidak dipangkas (anti double-trim). Saat data meragukan
        # (ts<=0 atau usia 0<age<60s di ambang rollover) -> NODATA fail-closed, bukan menebak.
        _ts_last=int(kl[-1][0] or 0)
        if _ts_last<=0:
            return NODATA
        _age_last=(time.time()*1000.0)-_ts_last
        if _age_last<0 or _age_last<60000.0:
            return NODATA
        if _age_last<900000.0:
            kl=kl[:-1]
            if len(kl)<85:
                return NODATA
        closes=[x[4] for x in kl]; highs=[x[2] for x in kl]; lows=[x[3] for x in kl]
        price=closes[-1]
        if price<=0: return NODATA
        # ATR-range20 (rata-rata high-low 20 bar) — V129d2 LABEL JUJUR: BUKAN True Range;
        # lab & live memakai definisi SAMA (backtest_6m.py) => sertifikat internal konsisten;
        # True Range = bahan studi gerbang R29, bukan patch buta.
        atr=sum(highs[i]-lows[i] for i in range(-20,0))/20.0
        vol_pct=atr/price*100.0
        trend=(closes[-1]-closes[-21])/closes[-21]*100.0 if closes[-21]>0 else 0.0
        htf=(closes[-1]-closes[-81])/closes[-81]*100.0 if closes[-81]>0 else 0.0
        rsi=_rsi_calc(closes[-60:])
        bull=sum(1 for i in range(-20,-1) if closes[i+1]>closes[i])
        fuel=int(bull/20*100); fuel=max(10,min(90,fuel))
        mom=(closes[-1]-closes[-6])/closes[-6]*100.0 if closes[-6]>0 else 0.0
        # SINYAL HTFRSI — deterministik, edge teruji data asli
        sig=""
        # V113: EMA9 untuk filter pullback — jangan kejar pump/dump yang sudah jalan jauh
        e9=_ema_vals(closes,9)[-1]
        gap_up = price-e9; gap_dn = e9-price
        if htf>SIG_BUY_ROC20H and rsi>SIG_BUY_RSI and rsi<=SIG_BUY_RSI_MAX and gap_up<=PULLBACK_ATR*atr:
            sig="Buy"
        elif htf<SIG_SELL_ROC20H and rsi<SIG_SELL_RSI and rsi>=SIG_SELL_RSI_MIN and gap_dn<=PULLBACK_ATR*atr:
            sig="Sell"
        # rdy = kekuatan sinyal (bukan random): >=50 saat sig aktif, <50 saat tidak
        if sig=="Buy": strength=(htf-SIG_BUY_ROC20H)*4.0+(rsi-SIG_BUY_RSI)*0.8+mom*0.6
        elif sig=="Sell": strength=(SIG_SELL_ROC20H-htf)*4.0+(SIG_SELL_RSI-rsi)*0.8-mom*0.6
        else: strength=-5.0-abs(htf)*1.5-abs(trend)*0.5
        rdy=int(min(95,max(5,50+strength*2)))
        # zona = rumus persis backtest data asli (deterministik)
        zona=2.0+vol_pct*1.0+abs(trend)*0.3+fuel/100.0*0.5
        zona=min(6.8,max(2.0,zona))
        if trend>1.2: regime="BULL TREND"
        elif trend<-1.2: regime="BEAR TREND"
        elif abs(trend)<0.7: regime="SIDEWAYS"
        elif abs(trend)<1.6: regime="ROTATION"
        else: regime="VOLATILE"
        rr_base={"BULL TREND":2.5,"BEAR TREND":2.3,"SIDEWAYS":1.8,"ROTATION":2.2,"VOLATILE":2.8}.get(regime,2.0)
        if GE_R1=="KETAT": rr_base+=0.2
        rr=max(1.0,min(3.6,rr_base))
        # AI score deterministik dari komponen nyata (zona, rdy, sinyal) — BUKAN random 50-85
        ai_base=int(min(95,max(40, 40+(zona-2.0)*5+(rdy-50)*0.4+(10 if sig else 0))))
        sig_txt=f" SIG-{sig.upper()}" if sig else " NOSIG"
        candidates=[]
        wr_map={"BN":83.3,"BM":80.0,"M":80.0,"W":66.4,"BQ":70.0,"BR":68.0}
        filters=[(filter_BN_detail,"BN"),(filter_BM_detail,"BM"),(filter_M_detail,"M"),(filter_W_detail,"W"),(filter_BQ_detail,"BQ"),(filter_BR_detail,"BR")]
        for func, name in filters:
            try:
                if name=="BR": ok,score,reason = func(zona,rdy,fuel,regime,rr,trend,price)
                else: ok,score,reason = func(zona,rdy,fuel,regime,rr,trend,atr,price)
            except: ok,score,reason=False,0,"error"
            wr=wr_map[name]
            if ok:
                if zona < GE_ZONA: continue
                coin_match=10 if sym in ["BTCUSDT","ETHUSDT"] and name=="BN" else 8 if sym in ["SOLUSDT","BNBUSDT"] and name=="W" else 0
                # V110 PRIORITAS BQ & BN — dipertahankan, deterministik (tanpa undian 85%)
                priority_bonus=0
                if name=="BQ":
                    priority_bonus=25
                    if rr>=2.5: priority_bonus+=8
                    if zona>=5.0: priority_bonus+=5
                elif name=="BN":
                    priority_bonus=18
                    if regime=="BULL TREND": priority_bonus+=7
                    if zona>=5.5: priority_bonus+=5
                elif name=="M":
                    priority_bonus=8
                elif name=="BM":
                    priority_bonus=5
                elif name=="W":
                    priority_bonus=-10 if zona<4.0 else -5
                elif name=="BR":
                    priority_bonus=-8 if zona<4.5 else -3
                # V111: bonus keselarasan sinyal HTFRSI — varian trend ikut arah sinyal
                sig_align=6 if (sig=="Buy" and regime in ["BULL TREND","ROTATION"]) or (sig=="Sell" and regime in ["BEAR TREND","ROTATION"]) else 0
                total=zona*1.5+rdy*0.1+fuel*0.1+ai_base*0.05+coin_match+wr*0.1+score*0.2+priority_bonus+sig_align
                candidates.append((total,name,reason,wr))
                add_filter_log(f"OK {sym} {name} WR{wr}% z{zona:.1f} rdy{rdy} f{fuel}% {regime} RR{rr:.1f} AI{ai_base}% S{total:.0f} htf{htf:+.1f} rsi{rsi:.0f}{sig_txt} [{GE_R1}]")
        if candidates:
            has_bq_bn = any(c[1] in ["BQ","BN"] for c in candidates)
            if has_bq_bn:
                candidates = [c for c in candidates if c[1] not in ["W","BR"]]
            candidates.sort(reverse=True)
            best_score,best_var,reason,wr = candidates[0]
            ai_final=min(95,max(40,ai_base))
            detail_reason=f"{best_var} WR{wr}% {reason} S{best_score:.0f} AI{ai_final}%{sig_txt} [{GE_R1}]"
            return round(zona,1),rdy,fuel,atr,price,regime,best_var,ai_final,round(rr,1),round(trend,1),detail_reason,sig,round(htf,2),round(rsi,1)
        else:
            no_sig_why=""
            if not sig:
                if htf>SIG_BUY_ROC20H and rsi>SIG_BUY_RSI_MAX: no_sig_why=" OVERBOUGHT"
                elif htf<SIG_SELL_ROC20H and rsi<SIG_SELL_RSI_MIN: no_sig_why=" OVERSOLD"
                elif htf>SIG_BUY_ROC20H and rsi>SIG_BUY_RSI and gap_up>PULLBACK_ATR*atr: no_sig_why=" NGEJAR-PUMP"
                elif htf<SIG_SELL_ROC20H and rsi<SIG_SELL_RSI and gap_dn>PULLBACK_ATR*atr: no_sig_why=" NGEJAR-DUMP"
            return round(zona,1),rdy,fuel,atr,price,regime,"W",ai_base,round(rr,1),round(trend,1),f"NO z{zona:.1f} {regime} RR{rr:.1f} htf{htf:+.1f} rsi{rsi:.0f}{no_sig_why}{sig_txt} [{GE_R1}]",sig,round(htf,2),round(rsi,1)
    except Exception as e:
        return 0.0,0,0,0.0,0.0,"NO DATA","W",0,0.0,0.0,f"ERR {str(e)[:40]}","",0.0,50.0

def load_keys_and_select_akun():
    ak=""; sec=""; akun_type="DEMO"; base_url="https://api-demo.bybit.com"; is_demo=True; status="KOSONG"
    has_demo=False; has_real=False
    demo_key={}; real_key={}
    try:
        if os.path.exists("ge_keys.json"):
            with open("ge_keys.json","r") as f:
                j=json.load(f)
            if "demo" in j and isinstance(j["demo"], dict) and j["demo"].get("api_key"):
                has_demo=True; demo_key=j["demo"]
            if "real" in j and isinstance(j["real"], dict) and j["real"].get("api_key"):
                has_real=True; real_key=j["real"]
            if not has_demo and not has_real and j.get("api_key"):
                has_demo=True; demo_key={"api_key":j.get("api_key"),"api_secret":j.get("api_secret")}
    except: pass
    chosen = GE_AKUN_ENV.upper().strip() if GE_AKUN_ENV else ""
    if not chosen:
        chosen="DEMO"
        if os.environ.get("GE_AKUN")=="REAL" and has_real: chosen="REAL"
        if chosen=="REAL" and os.environ.get("GE_LIVE_CONFIRM")!="YES":
            add_log("REAL DITOLAK: butuh GE_LIVE_CONFIRM=YES — jatuh ke DEMO")
            chosen="DEMO"
    if chosen=="REAL" and has_real:
        ak=real_key.get("api_key",""); sec=real_key.get("api_secret","")
        akun_type="REAL"; base_url="https://api.bybit.com"; is_demo=False
        status=f"REAL TERISI {ak[:6]}... api.bybit.com"
    elif chosen=="REAL" and not has_real and has_demo:
        ak=demo_key.get("api_key",""); sec=demo_key.get("api_secret","")
        akun_type="DEMO (FALLBACK REAL KOSONG)"; base_url="https://api-demo.bybit.com"; is_demo=True
        status=f"REAL KOSONG -> FALLBACK DEMO {ak[:6]}..."
    else:
        if has_demo:
            ak=demo_key.get("api_key",""); sec=demo_key.get("api_secret","")
            akun_type="DEMO"; base_url="https://api-demo.bybit.com"; is_demo=True
            status=f"DEMO TERISI {ak[:6]}... api-demo.bybit.com"
        elif has_real:
            ak=real_key.get("api_key",""); sec=real_key.get("api_secret","")
            akun_type="REAL"; base_url="https://api.bybit.com"; is_demo=False
            status=f"REAL TERISI {ak[:6]}..."
        else:
            akun_type="KOSONG"; status="KOSONG isi ge_keys.json"
    return ak, sec, akun_type, base_url, is_demo, status, has_demo, has_real

AK_API_KEY=""; AK_API_SECRET=""; AK_TYPE="DEMO"; AK_BASE="https://api-demo.bybit.com"; AK_IS_DEMO=True; AK_STATUS=""; AK_HAS_DEMO=False; AK_HAS_REAL=False
GE_AKUN="DEMO"
def refresh_akun_state():
    global AK_API_KEY, AK_API_SECRET, AK_TYPE, AK_BASE, AK_IS_DEMO, AK_STATUS, AK_HAS_DEMO, AK_HAS_REAL, GE_AKUN
    ak,sec,tipe,base,is_demo,status,has_demo,has_real = load_keys_and_select_akun()
    AK_API_KEY=ak; AK_API_SECRET=sec; AK_TYPE=tipe; AK_BASE=base; AK_IS_DEMO=is_demo; AK_STATUS=status; AK_HAS_DEMO=has_demo; AK_HAS_REAL=has_real
    GE_AKUN="REAL" if "REAL" in tipe and "FALLBACK" not in tipe else "DEMO"
    return ak,sec,tipe,base,is_demo,status

BALANCE_STATUS="UNKNOWN"
KLINE_SRC={}
POS_STATUS="OK"
def get_real_positions():
    global POS_STATUS
    try:
        from pybit.unified_trading import HTTP
        if not AK_API_KEY:
            POS_STATUS="NO_KEY"; return None
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        pos=sess.get_positions(category="linear",settleCoin="USDT")
        if pos.get("retCode")==0:
            POS_STATUS="OK"
            return [p for p in pos["result"]["list"] if float(p.get("size","0") or 0)!=0]
        POS_STATUS="API_ERROR"; return None
    except Exception as e_pos:
        POS_STATUS="API_ERROR"
        add_log(f"POSITION API ERROR: {str(e_pos)[:100]}")
        return None
def get_real_performance():
    try:
        from pybit.unified_trading import HTTP
        if not AK_API_KEY: return {"today_count":0,"today_w":0,"today_l":0,"today_pnl":0,"total_count":0,"total_wr":0,"total_pnl":0}
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        pnl_resp=sess.get_closed_pnl(category="linear", limit=100)
        if pnl_resp.get("retCode")!=0: return {"today_count":0,"today_w":0,"today_l":0,"today_pnl":0,"total_count":0,"total_wr":0,"total_pnl":0}
        lst=pnl_resp["result"]["list"]
        today_start=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        today_ts=int(today_start.timestamp()*1000)
        today_trades=[]; total_pnl=0
        for item in lst:
            try:
                closed_pnl=float(item.get("closedPnl","0") or 0); total_pnl+=closed_pnl
                if int(item.get("createdTime","0") or 0)>=today_ts: today_trades.append(item)
            except: continue
        today_pnl=sum(float(x.get("closedPnl","0") or 0) for x in today_trades)
        today_w=sum(1 for x in today_trades if float(x.get("closedPnl","0") or 0)>0)
        return {"today_count":len(today_trades),"today_w":today_w,"today_l":len(today_trades)-today_w,"today_pnl":today_pnl,"total_count":len(lst),"total_wr":int(sum(1 for x in lst if float(x.get("closedPnl","0") or 0)>0)/len(lst)*100) if lst else 0,"total_pnl":total_pnl}
    except:
        return {"today_count":0,"today_w":0,"today_l":0,"today_pnl":0,"total_count":0,"total_wr":0,"total_pnl":0}

def get_futures_balance():
    global BALANCE_STATUS
    try:
        from pybit.unified_trading import HTTP
        if not AK_API_KEY:
            BALANCE_STATUS="NO_KEY"; return None
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        # Bybit wallet-balance UNIFIED
        bal=sess.get_wallet_balance(accountType="UNIFIED")
        if bal.get("retCode")==0:
            lst=bal["result"]["list"]
            if lst:
                # totalEquity, totalWalletBalance
                acc=lst[0]
                total_eq=float(acc.get("totalEquity","0") or 0)
                wallet_bal=float(acc.get("totalWalletBalance","0") or 0)
                # coin USDT
                coin_list=acc.get("coin",[])
                usdt_bal=0.0
                for c in coin_list:
                    if c.get("coin")=="USDT":
                        usdt_bal=float(c.get("walletBalance","0") or c.get("equity","0") or 0)
                        break
                total = usdt_bal if usdt_bal>0 else (total_eq if total_eq>0 else wallet_bal)
                if total<=0:
                    BALANCE_STATUS="API_ERROR"; return None
                raw_avail=acc.get("totalAvailableBalance")
                # V129d1 FAIL-CLOSED FIELD: totalAvailableBalance hilang/kosong/bukan angka =
                # BALANCE_status API_ERROR -> entry terblokir (gerbang NO-BALANCE di place_order_smart)
                # sampai saldo terverifikasi. DULU: fallback ke total wallet balance (fail-open) —
                # saldo total TIDAK memperhitungkan margin terpakai/order terbuka -> margin_per_pos
                # bisa dihitung kelewat besar. Catatan: total<=0 sudah fail-closed sejak V128p3.
                try:
                    avail=float(raw_avail)
                except (TypeError,ValueError):
                    BALANCE_STATUS="API_ERROR"
                    add_log("BALANCE FIELD totalAvailableBalance HILANG/INVALID — fail-closed, entry diblokir sampai saldo terverifikasi [V129d1]")
                    return None
                BALANCE_STATUS="OK"
                return {"total":total,"available":avail,"equity":total_eq or total}
    except Exception as e_bal:
        BALANCE_STATUS="API_ERROR"
        add_log(f"BALANCE API ERROR: {str(e_bal)[:100]}")
        return None
    BALANCE_STATUS="API_ERROR"; return None

def get_closed_pnl_detailed():
    try:
        from pybit.unified_trading import HTTP
        if not AK_API_KEY: return []
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        pnl_resp=sess.get_closed_pnl(category="linear", limit=20)
        if pnl_resp.get("retCode")!=0: return []
        lst=pnl_resp["result"]["list"]
        detailed=[]
        for item in lst:
            try:
                sym=item.get("symbol","")
                pnl=float(item.get("closedPnl","0") or 0)
                entry=float(item.get("avgEntryPrice","0") or 0)
                exitp=float(item.get("avgExitPrice","0") or 0)
                side=item.get("side","")  # Buy/Sell
                ctime=int(item.get("createdTime","0") or 0)
                # V117: infer exit type dari estimasi R (pnl / risiko-$ perkiraan) — tahan perubahan size/cap
                # risiko-$ ~ qty * entry * 1.5% (SL tipisan bot: min(2ATR,2.5%) floor 0.8%)
                var_info = open_trades_info.get(sym, {}).get("var","W") if sym in open_trades_info else states.get(sym,{}).get("best_var","W") if sym in states else "W"
                qty=float(item.get("qty","0") or 0)
                # V129d2: risiko = qty x risk_dist tersimpan (registry); estimasi 1.5% HANYA bila
                # registry tak memuat entry ini (trade lama pasca-restart) — jujur, bukan tebakan tetap.
                _rd_p=float((open_trades_info.get(sym,{}) or {}).get("risk_dist",0) or 0)
                risk_usd = qty*_rd_p if (qty>0 and _rd_p>0) else (qty*entry*0.015 if (qty>0 and entry>0) else 1.0)
                r_est = pnl/risk_usd if risk_usd>0 else 0.0
                if r_est>=1.8:
                    exit_type="RIDE 3.5R"
                elif r_est>=1.1:
                    exit_type="TP1+TP2"
                elif r_est>=0.4:
                    exit_type="TP1"
                elif r_est>=-0.35:
                    exit_type="BE"
                else:
                    exit_type="SL"
                detailed.append({
                    "symbol":sym,
                    "pnl":pnl,
                    "entry":entry,
                    "exit":exitp,
                    "side":side,
                    "var":var_info,
                    "exit_type":exit_type,
                    "time":ctime,
                    "reason": open_trades_info.get(sym,{}).get("reason","")[:40] if sym in open_trades_info else ""
                })
            except:
                continue
        return detailed[:10]
    except:
        return []
def check_and_fix_sl():
    try:
        from pybit.unified_trading import HTTP
        if not AK_API_KEY: return []
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        pos=sess.get_positions(category="linear",settleCoin="USDT")
        if pos.get("retCode")!=0: return []
        fixed=[]
        for p in pos["result"]["list"]:
            if float(p.get("size","0") or 0)==0: continue
            avg=float(p.get("avgPrice","0") or 0)
            if avg==0: continue
            # V129d2 REGISTRY GATE: hanya posisi MILIK BOT (terdaftar + side cocok + pos_idx cocok)
            # yang dikelola; posisi manual/bot-lain dilaporkan SEKALI lalu DILEWATI (tidak diadopsi).
            _sym0=p.get("symbol",""); _vi=open_trades_info.get(_sym0,{}) or {}
            _idx0=int(p.get("positionIdx",0) or 0)
            _owned = bool(_vi) and _vi.get("side")==p.get("side") and int(_vi.get("pos_idx",_idx0) or _idx0)==_idx0
            if not _owned:
                _ext_mark(_sym0, p.get("side",""), _idx0)
                continue
            sl=p.get("stopLoss","")
            if not sl or sl=="0":
                if p.get("symbol") in states:
                    atr=states[p.get("symbol")].get("atr",500)
                    if atr<=0 or atr>5000: atr=avg*0.02
                    sl_dist = min(atr*SL_ATR_MULT, avg*SL_PCT_MAX); sl_dist = max(sl_dist, avg*SL_PCT_MIN)
                    if p.get("side")=="Buy":
                        sl_price = avg - sl_dist - atr*ANTI_HUNT_ATR - atr*FINAL_BUFFER_ATR
                        if sl_price >= avg: sl_price = avg * 0.98
                    else:
                        sl_price = avg + sl_dist + atr*ANTI_HUNT_ATR + atr*FINAL_BUFFER_ATR
                        if sl_price <= avg: sl_price = avg * 1.02
                    try:
                        sess.set_trading_stop(category="linear", symbol=p.get("symbol"), stopLoss=str(round(sl_price,2)), slTriggerBy="MarkPrice", positionIdx=int(p.get("positionIdx",0)))
                        fixed.append(f"AUTO-SL {p.get('symbol')} SL {sl_price:.2f}")
                    except: pass
        return fixed
    except: return []

# V97 BARU: BE 1R + TRAIL R2.0+T2.0 + RIDE MAX 3R LIVE REAL
def manage_trailing_live():
    try:
        from pybit.unified_trading import HTTP
        if not AK_API_KEY: return []
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        pos_resp=sess.get_positions(category="linear",settleCoin="USDT")
        if pos_resp.get("retCode")!=0: return []
        actions=[]
        for p in pos_resp["result"]["list"]:
            try:
                if float(p.get("size","0") or 0)==0: continue
                sym=p.get("symbol","")
                side=p.get("side","Buy")
                # V129d2 REGISTRY GATE: trailing/BE/ride hanya untuk posisi MILIK BOT
                _vig=open_trades_info.get(sym,{}) or {}
                if not _vig or _vig.get("side")!=side or int(_vig.get("pos_idx",p.get("positionIdx",0)) or 0)!=int(p.get("positionIdx",0) or 0):
                    _ext_mark(sym, side, int(p.get("positionIdx",0) or 0))
                    continue
                avg=float(p.get("avgPrice","0") or 0)
                if avg==0: continue
                mark_price=float(p.get("markPrice","0") or 0) or avg
                live_px=mark_price if mark_price>0 else (states[sym].get("px",avg) if sym in states and states[sym].get("px",0)>0 else avg)
                atr=states.get(sym,{}).get("atr",avg*0.02) if sym in states else avg*0.02
                if atr<=0 or atr>avg*0.10: atr=avg*0.02
                _inf0=open_trades_info.get(sym,{}) or {}
                _rd0=float(_inf0.get("risk_dist",0) or 0)
                sl_dist = _rd0 if _rd0>0 else min(atr*SL_ATR_MULT, avg*SL_PCT_MAX); sl_dist = max(sl_dist, avg*SL_PCT_MIN)
                r = (live_px - avg)/sl_dist if side=="Buy" and sl_dist>0 else (avg - live_px)/sl_dist if sl_dist>0 else 0
                with trailing_lock:
                    st=trailing_states.get(sym)
                    if not st:
                        st={"be_done":False,"trail_start":False,"last_sl":0,"peak_r":r,"entry":avg,"sl_dist":sl_dist,"side":side}
                        trailing_states[sym]=st
                    else:
                        st["peak_r"]=max(st.get("peak_r",r), r)
                        st["sl_dist"]=sl_dist
                        st["entry"]=avg
                        st["side"]=side
                if r>=TP1_R and not st["be_done"]:
                    be_price=avg + sl_dist*0.05 if side=="Buy" else avg - sl_dist*0.05
                    try:
                        sess.set_trading_stop(category="linear", symbol=sym, stopLoss=str(round(be_price,2)), slTriggerBy="MarkPrice", positionIdx=int(p.get("positionIdx",0)))
                        with trailing_lock:
                            trailing_states[sym]["be_done"]=True
                            trailing_states[sym]["last_sl"]=be_price
                        actions.append(f"BE {TP1_R}R {sym} R{r:.2f} SL->BE {be_price:.2f}")
                        add_filter_log(f"BE {TP1_R}R LIVE {sym} R{r:.2f} SL->BE {be_price:.0f} [{GE_R1}]")
                        add_log(f"BE {TP1_R}R {sym} R{r:.2f} SL->BE {be_price:.0f}")
                    except Exception as e_be:
                        _eb=str(e_be).replace("\n"," | ")[:140]
                        if "34040" in _eb or "not modified" in _eb.lower():
                            with trailing_lock:
                                trailing_states[sym]["be_done"]=True
                            add_filter_log(f"BE SKIP {sym} Bybit: nilai sudah sama (34040) — retry dihentikan [{GE_R1}]")
                        else:
                            add_filter_log(f"BE FAIL {sym} {_eb}")
                if r>=TP2_R:
                    if side=="Buy":
                        lock_sl = avg + sl_dist*1.0
                        ratchet_sl = live_px - sl_dist*0.8
                        new_sl = max(lock_sl, ratchet_sl)
                        if new_sl > st.get("last_sl",0) and new_sl < live_px:
                            try:
                                sess.set_trading_stop(category="linear", symbol=sym, stopLoss=str(round(new_sl,2)), slTriggerBy="MarkPrice", positionIdx=int(p.get("positionIdx",0)))
                                with trailing_lock:
                                    trailing_states[sym]["last_sl"]=new_sl
                                    trailing_states[sym]["trail_start"]=True
                                actions.append(f"TRAIL R{TP2_R} {sym} R{r:.2f} SL {new_sl:.2f} lock 1R")
                                add_filter_log(f"TRAIL R{TP2_R} LIVE {sym} R{r:.2f} SL {new_sl:.0f} lock1R [{GE_R1}]")
                            except: pass
                    else:
                        lock_sl = avg - sl_dist*1.0
                        ratchet_sl = live_px + sl_dist*0.8
                        new_sl = min(lock_sl, ratchet_sl)
                        if (st.get("last_sl",0)==0 or new_sl < st.get("last_sl",0)) and new_sl > live_px:
                            try:
                                sess.set_trading_stop(category="linear", symbol=sym, stopLoss=str(round(new_sl,2)), slTriggerBy="MarkPrice", positionIdx=int(p.get("positionIdx",0)))
                                with trailing_lock:
                                    trailing_states[sym]["last_sl"]=new_sl
                                    trailing_states[sym]["trail_start"]=True
                                actions.append(f"TRAIL R{TP2_R} {sym} R{r:.2f} SL {new_sl:.2f} lock 1R")
                                add_filter_log(f"TRAIL R{TP2_R} LIVE {sym} R{r:.2f} SL {new_sl:.0f} lock1R [{GE_R1}]")
                            except: pass
                _inf=open_trades_info.get(sym,{}) or {}
                if _inf.get("tp_pending") and (time.time()-st.get("tp_retry_t",0))>60:
                    with trailing_lock: st["tp_retry_t"]=time.time()
                    try:
                        # V129d2: retry memakai LADDER+linkId yang sama (idempoten; 110072 = sudah ada)
                        _qst=float(_inf.get("qstep",0) or 0); _qmn=float(_inf.get("qmin",0) or 0)
                        _psz=float(p.get("size","0") or 0)
                        if _qst>0 and _psz>0:
                            _lad=place_tp_ladder(sess,sym,side,int(_inf.get("pos_idx",p.get("positionIdx",0)) or 0),_psz,
                                                 _inf.get("lid_base",f"GEV129{sym}"),
                                                 float(_inf.get("tp1",0) or 0),float(_inf.get("tp2",0) or 0),float(_inf.get("tp3",0) or 0),
                                                 _qst,_qmn)
                            _done_all=bool(_lad.get("done1") and _lad.get("done2") and _lad.get("done3"))
                            with trailing_lock:
                                if sym in open_trades_info:
                                    open_trades_info[sym]["tp_ladder"]=_lad
                                    open_trades_info[sym]["tp_pending"]=not _done_all
                            add_filter_log(f"TP LADDER RETRY {sym} size{_psz} done[{_lad.get('done1')},{_lad.get('done2')},{_lad.get('done3')}] {_lad.get('warn','')} [{GE_R1}]")
                        else:
                            add_filter_log(f"TP LADDER RETRY-SKIP {sym} qstep{_qst} size{_psz} [{GE_R1}]")
                    except Exception as e_tpr:
                        add_filter_log(f"TP LADDER RETRY FAIL {sym} {str(e_tpr)[:60]} [{GE_R1}]")
                if r>=TP3_R:
                    try:
                        with trailing_lock:
                            st3=trailing_states.setdefault(sym,{})
                            if st3.get("close_requested"):
                                qty_close="0"
                            else:
                                st3["close_requested"]=True; qty_close=p.get("size","0")
                        opposite_side="Sell" if side=="Buy" else "Buy"
                        if float(qty_close)>0:
                            _rc=sess.place_order(category="linear",symbol=sym,side=opposite_side,orderType="Market",qty=str(qty_close),timeInForce="GTC",positionIdx=int(p.get("positionIdx",0)),reduceOnly=True)
                            if _rc.get("retCode")==0:
                                actions.append(f"RIDE MAX {TP3_R}R {sym} R{r:.2f} CLOSE {qty_close} @ {live_px:.0f}")
                                add_filter_log(f"RIDE MAX {TP3_R}R LIVE {sym} R{r:.2f} CLOSE {qty_close} @ {live_px:.0f} [{GE_R1}]")
                                add_log(f"RIDE MAX {TP3_R}R {sym} R{r:.2f} CLOSE profit ride max")
                                with trailing_lock:
                                    trailing_states.pop(sym,None)
                            else:
                                with trailing_lock:
                                    if sym in trailing_states:
                                        trailing_states[sym]["close_requested"]=False
                                add_filter_log(f"CLOSE FAIL {sym} ret{_rc.get('retCode')} {str(_rc.get('retMsg'))[:60]} [{GE_R1}]")
                    except Exception as e_ride:
                        add_filter_log(f"RIDE MAX FAIL {sym} {e_ride}")
            except: continue
        # V129d2 CLOSE-CLEANUP: registry hanya boleh memuat posisi HIDUP. Posisi milik bot yang
        # sudah NOL (TP ladder/SL/ride selesai) dibersihkan setelah 2x berturut tak terlihat
        # (anti glitch API sesaat) — mencegah state basi menutup posisi BARU di symbol sama.
        try:
            _live=set()
            for _p in pos_resp["result"]["list"]:
                if float(_p.get("size","0") or 0)>0:
                    _live.add((_p.get("symbol",""), _p.get("side",""), int(_p.get("positionIdx",0) or 0)))
            with trailing_lock:
                for _s in list(open_trades_info.keys()):
                    _v=open_trades_info.get(_s,{}) or {}
                    _k=(_s, _v.get("side",""), int(_v.get("pos_idx",0) or 0))
                    if _k in _live:
                        _POS_MISS.pop(_s,None); continue
                    _POS_MISS[_s]=_POS_MISS.get(_s,0)+1
                    if _POS_MISS[_s]>=2:
                        _et=(time.time()-float(_v.get("entry_time",0) or 0))/60.0
                        open_trades_info.pop(_s,None); trailing_states.pop(_s,None); _POS_MISS.pop(_s,None)
                        add_filter_log(f"REGISTRY CLEAN {_s} — posisi 0 (trade selesai) durasi {_et:.0f}mnt [{GE_R1}]")
        except Exception as e_cl:
            add_filter_log(f"REGISTRY CLEAN FAIL {str(e_cl)[:60]}")
        return actions
    except Exception as e:
        return [f"trail fail {str(e)[:50]}"]

# ============ V129d2 EXITFIX + REGISTRY IDENTITAS ============
# EXITFIX: entry HANYA memasang SL. TP1/TP2/TP3 = Limit reduceOnly dari UKURAN POSISI
# AKTUAL (50/30/20+sisa), lahir setelah fill — bukan takeProfit attached (yang menutup 100%).
# orderLinkId per maksud-order: retry memakai link SAMA; Bybit menolak duplikat (110072)
# => bot adopsi order yang sudah hidup, bukan menggandakan (idempotensi).
_EXT_SEEN=set()          # identitas posisi bukan-bot yang sudah pernah dilaporkan (cegah spam)
_POS_MISS={}             # hitungan posisi registry tak terlihat di API (butuh 2x sebelum dibersihkan)
def _ext_mark(sym, side, idx):
    try:
        k=f"{sym}:{side}:{idx}"
        if k not in _EXT_SEEN:
            _EXT_SEEN.add(k)
            add_filter_log(f"EXTERNAL-SKIP {k} — bukan posisi bot (tanpa/≠ identitas registry) — TIDAK dikelola [{GE_R1}]")
    except Exception:
        pass
def place_tp_ladder(sess, sym, side, idx, pos_size, lid_base, tp1, tp2, tp3, qty_step, min_qty):
    # EXITFIX ladder: total qty SELALU = pos_size; tiap leg <min_qty di-merge ke leg berikut;
    # orderLinkId f"{lid_base}T{n}" — retry aman (110072 = sudah ada = dianggap beres).
    out={"size":pos_size,"idx":idx,"lid":lid_base,"p1":tp1,"p2":tp2,"p3":tp3,
         "done1":False,"done2":False,"done3":False,"q1":0.0,"q2":0.0,"q3":0.0,"warn":""}
    try:
        opp="Sell" if side=="Buy" else "Buy"
        step=Decimal(str(qty_step)) if (qty_step and qty_step>0) else Decimal("0.001")
        mn=Decimal(str(min_qty)) if (min_qty and min_qty>0) else Decimal("0.001")
        pos_d=Decimal(str(pos_size))
        q1=((pos_d*Decimal("0.5"))//step)*step
        q2=((pos_d*Decimal("0.3"))//step)*step
        q3=pos_d-q1-q2
        if q1<mn: q2+=q1; q1=Decimal("0")
        if q2<mn: q3+=q2; q2=Decimal("0")
        if q3<mn: q2+=q3; q3=Decimal("0")
        if q2<mn: q1+=q2; q2=Decimal("0")
        legs=[(1,q1,out["p1"]),(2,q2,out["p2"]),(3,q3,out["p3"])]
        tot=Decimal("0")
        for n,qq,pp in legs:
            out[f"q{n}"]=float(qq)
            if qq<=0:
                out[f"done{n}"]=True
                continue
            tot+=qq
            try:
                _r=sess.place_order(category="linear",symbol=sym,side=opp,orderType="Limit",qty=str(qq),
                                    price=str(format_price_by_tick(float(pp),sym)),timeInForce="GTC",
                                    positionIdx=int(idx),reduceOnly=True,orderLinkId=f"{lid_base}T{n}")
                rc=_r.get("retCode")
                if rc==0 or rc==110072:
                    out[f"done{n}"]=True
                else:
                    out["warn"]=f"T{n} ret{rc} {str(_r.get('retMsg',''))[:40]}"
            except Exception as e_leg:
                out["warn"]=f"T{n} exc {str(e_leg)[:40]}"
        if tot!=pos_d:
            out["warn"]=(out["warn"]+" | " if out["warn"] else "")+f"QTY-MISMATCH sum{tot}!=size{pos_d}"
        return out
    except Exception as e_lad:
        out["warn"]=f"exc {str(e_lad)[:60]}"
        return out

# BUG 5 FIX: TP BERTAHAP REAL DI API — 50%@1R 30%@2R 20%@3R+trail via limit reduceOnly
# V99 FIX: QTY STEP PER COIN + LOG ERROR JELAS
def place_order_smart(sym="BTCUSDT", side="Buy", qty="0.002"):
    try:
        from pybit.unified_trading import HTTP
        import requests
        if not AK_API_KEY: return False, "akun kosong", 0,0,0,0
        sess=HTTP(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET,timeout=10)
        px=None
        try:
            r=requests.get(f"{AK_BASE}/v5/market/kline",params={"category":"linear","symbol":sym,"interval":"1","limit":1},timeout=5,headers={"User-Agent":"Mozilla/5.0"})
            _qp=float(r.json()["result"]["list"][0][4])
            if _qp>0: px=_qp
        except: px=None
        if px is None:
            return False, f"NO-QUOTE fail-closed {sym}", 0,0,0,0
        if BALANCE_STATUS!="OK":
            return False, f"NO-BALANCE fail-closed {sym} ({BALANCE_STATUS})", 0,0,0,0
        # V104 BULLETPROOF: qty step per coin + margin check + lev real (bukan 50 fixed)
        _meta = get_qty_step(sym, px)
        if _meta is None:
            return False, f"NO-META fail-closed {sym}", 0,0,0,0
        qty_step, min_qty, tick_meta = _meta
        tick_ops = get_price_tick(sym)
        if tick_ops and tick_ops <= 1e-7:
            return False, f"microtick-skip {sym} tick{tick_ops}", 0,0,0,0
        # margin per pos dari cap
        margin_per_pos=GE_CAP*GE_MARGIN_PCT/100/max(1,GE_MAX_POS)
        # cek saldo future real kalau ada
        try:
            with cached_futures_lock:
                fut_bal = dict(cached_futures_balance)
            avail = fut_bal.get("available", GE_CAP) or GE_CAP
            # jangan pakai lebih dari 90% available dibagi sisa slot
            remaining_slots = max(1, GE_MAX_POS - len(cached_positions))
            margin_per_pos = min(margin_per_pos, avail*0.85/remaining_slots)
        except:
            pass
        # V104: qty harus pakai lev real, bukan 50 fixed — biar margin nyampe
        # lev sudah dihitung nanti, tapi untuk qty awal pakai estimasi lev dari smart_leverage_safe
        # hitung sl_dist dulu untuk lev
        data_tmp=states.get(sym,{}); atr_tmp=data_tmp.get("atr",px*0.02) if data_tmp else px*0.02
        if atr_tmp<=0 or atr_tmp>px*0.08: atr_tmp=px*0.02
        sl_dist_tmp = min(atr_tmp*SL_ATR_MULT, px*SL_PCT_MAX); sl_dist_tmp = max(sl_dist_tmp, px*SL_PCT_MIN)
        if side=="Buy":
            sl_tmp = px - sl_dist_tmp - atr_tmp*ANTI_HUNT_ATR - atr_tmp*FINAL_BUFFER_ATR
        else:
            sl_tmp = px + sl_dist_tmp + atr_tmp*ANTI_HUNT_ATR + atr_tmp*FINAL_BUFFER_ATR
        lev_est, _, _ = smart_leverage_safe(sym, px, sl_tmp, atr_tmp, side)
        # qty = margin * lev / price
        qty_calc = margin_per_pos * lev_est / px if px>0 else min_qty
        # quantize sesuai qty_step
        try:
            step_str = str(qty_step)
            if "e" in step_str.lower():
                step_str = "0.001"
            q_step = Decimal(step_str)
            qty_dec = Decimal(str(qty_calc))
            if q_step>0:
                qty_floor = (qty_dec // q_step) * q_step
                qty_calc = float(qty_floor)
            else:
                qty_calc = float(qty_dec.quantize(Decimal("0.001"),rounding=ROUND_DOWN))
            if qty_calc < min_qty:
                qty_calc = min_qty
            if qty_calc < 0.001 and min_qty<0.001:
                qty_calc = min_qty
            # V104: pastikan margin = qty*px/lev <= margin_per_pos*1.1 (jangan over margin)
            # kalau over, kecilkan qty
            margin_needed = qty_calc * px / lev_est if lev_est>0 else qty_calc*px
            if margin_needed > margin_per_pos*1.2:
                qty_calc = margin_per_pos * lev_est / px * 0.9
                qty_dec = Decimal(str(qty_calc))
                qty_floor = (qty_dec // q_step) * q_step if q_step>0 else qty_dec
                qty_calc = float(qty_floor)
                if qty_calc < min_qty:
                    qty_calc = min_qty
        except:
            qty_calc = max(min_qty, 0.001)
        if qty=="0.002": qty=str(qty_calc)
        data=states.get(sym,{}); atr=data.get("atr",px*0.02)
        if atr<=0 or atr>px*0.10: atr=px*0.02
        sl_dist = min(atr*SL_ATR_MULT, px*SL_PCT_MAX); sl_dist = max(sl_dist, px*SL_PCT_MIN)
        if side=="Buy":
            sl_price = px - sl_dist - atr*ANTI_HUNT_ATR - atr*FINAL_BUFFER_ATR
            if sl_price >= px: sl_price = px * 0.98
        else:
            sl_price = px + sl_dist + atr*ANTI_HUNT_ATR + atr*FINAL_BUFFER_ATR
            if sl_price <= px: sl_price = px * 1.02
        rr=data.get("rr",2.2) if data else 2.2
        tp_dist, rr_kotor, fee_r, funding_r, slip_r = calc_fee_aware_tp(sl_dist, rr, 25, px)
        tp_price = px + tp_dist if side=="Buy" else px - tp_dist
        tp1 = px + sl_dist*TP1_R if side=="Buy" else px - sl_dist*TP1_R
        tp2 = px + sl_dist*TP2_R if side=="Buy" else px - sl_dist*TP2_R
        tp3 = px + sl_dist*TP3_R if side=="Buy" else px - sl_dist*TP3_R
        lev, kelas, dist = smart_leverage_safe(sym, px, sl_price, atr, side)
        try:
            _lr=sess.set_leverage(category="linear", symbol=sym, buyLeverage=str(lev), sellLeverage=str(lev))
            if _lr.get("retCode") not in (0,110043):
                return False, f"SET-LEV fail-closed {sym} ret{_lr.get('retCode')}", 0,0,0,0
        except Exception as e_lev:
            return False, f"SET-LEV exc fail-closed {sym} {str(e_lev)[:60]}", 0,0,0,0
        # qty untuk TP bertahap
        try:
            qty_f=float(qty)
        except:
            qty_f=0.002
        qty_tp1 = float(Decimal(str(qty_f*0.5)).quantize(Decimal("0.001"),rounding=ROUND_DOWN))
        qty_tp2 = float(Decimal(str(qty_f*0.3)).quantize(Decimal("0.001"),rounding=ROUND_DOWN))
        qty_tp3 = float(Decimal(str(qty_f*0.2)).quantize(Decimal("0.001"),rounding=ROUND_DOWN))
        if qty_tp1<0.001: qty_tp1=0.001
        if qty_tp2<0.001: qty_tp2=0.001
        if qty_tp3<0.001: qty_tp3=0.001

        last_err="unknown"
        # V107: price rounding pakai tick size, bukan 2 desimal fix
        price_tick = tick_meta if (tick_meta and tick_meta>0) else get_price_tick(sym)
        # quantize price ke tick
        def round_to_tick(p):
            try:
                t=Decimal(str(price_tick))
                pd=Decimal(str(p))
                if t>0:
                    return float((pd // t) * t)
                return p
            except:
                return p
        sl_price_r = round_to_tick(sl_price)
        tp1_r = round_to_tick(tp1)
        # kalau hasil 0 karena tick terlalu besar vs price kecil, pakai format asli
        if sl_price_r==0:
            sl_price_r=sl_price
        if tp1_r==0:
            tp1_r=tp1
        # V125 GOLD35: QTY SELF-HEAL — kalau exchange tolak "Qty invalid",
        # step otomatis dikasar-kan x10 (cache diperbarui) lalu order dicoba ulang.
        # Mencegah gagal entry berulang untuk coin yang step-nya tidak sesuai tabel.
        def _heal_qty():
            global qty_step_cache
            qty_step2 = qty_step*10
            _tk = qty_step_cache[sym][2] if len(qty_step_cache[sym])>2 else HARDCODE_PRICE_TICK.get(sym,0.0001)
            qty_step_cache[sym]=(qty_step2, max(min_qty, qty_step2), _tk)
            qty_dec2=Decimal(str(qty_calc)); q_s2=Decimal(str(qty_step2))
            qty_calc2=float((qty_dec2//q_s2)*q_s2)
            if qty_calc2 < min_qty: qty_calc2=min_qty
            qty_tp2b=float(Decimal(str(qty_calc2*0.3)).quantize(Decimal(str(qty_step2)),rounding=ROUND_DOWN))
            qty_tp3b=float(Decimal(str(qty_calc2*0.2)).quantize(Decimal(str(qty_step2)),rounding=ROUND_DOWN))
            if qty_tp2b<min_qty: qty_tp2b=min_qty
            if qty_tp3b<min_qty: qty_tp3b=min_qty
            add_filter_log(f"QTY SELF-HEAL {sym} step {qty_step}->{qty_step2} qty->{qty_calc2} [{GE_R1}]")
            return qty_step2, qty_calc2, qty_tp2b, qty_tp3b
        last_err="unknown"
        # V129d2 IDEMPOTENSI + EXITFIX: link unik & STABIL per idx; TP TIDAK lagi di order entry
        _lid_base=f"GEV129{int(time.time())}{sym}"
        _lid_made={}
        def _lid_for(i):
            if i not in _lid_made:
                _lid_made[i]=f"{_lid_base}E{i}"
            return _lid_made[i]
        def _adopt_by_lid(lid):
            # respons hilang (timeout) != order gagal: buktikan lewat status by ID sebelum kirim ulang
            try:
                _o=sess.get_open_orders(category="linear",symbol=sym,orderLinkId=lid)
                if _o.get("retCode")==0 and _o.get("result",{}).get("list"): return True
            except: pass
            try:
                _h=sess.get_order_history(category="linear",symbol=sym,orderLinkId=lid)
                if _h.get("retCode")==0 and _h.get("result",{}).get("list"): return True
            except: pass
            return False
        def _pos_probe(i):
            # kebenaran tanah: posisi ada di idx/side ini? -> order market SUDAH fill
            try:
                _pq=sess.get_positions(category="linear",symbol=sym)
                if _pq.get("retCode")==0:
                    for _pp in _pq["result"]["list"]:
                        if int(_pp.get("positionIdx",0) or 0)==i and _pp.get("side")==side and float(_pp.get("size","0") or 0)>0:
                            return float(_pp.get("size","0") or 0)
            except: pass
            return 0.0
        for _qr in range(5):
          heal=False
          for idx in [0,1,2]:
            _ok_success=False
            try:
                resp=sess.place_order(category="linear",symbol=sym,side=side,orderType="Market",qty=str(qty),timeInForce="GTC",positionIdx=idx,stopLoss=str(sl_price_r),slTriggerBy="MarkPrice",orderLinkId=_lid_for(idx))
                rc=resp.get("retCode",-1)
                if rc==0:
                    _ok_success=True
                elif rc==110072:
                    time.sleep(1.0)
                    if _adopt_by_lid(_lid_for(idx)) or _pos_probe(idx)>0:
                        _ok_success=True
                        add_filter_log(f"ENTRY DUP-ADOPT {sym} idx{idx} link{_lid_for(idx)} — order hidup, TIDAK kirim ulang [{GE_R1}]")
                    else:
                        last_err=f"dup-unverified idx{idx} link{_lid_for(idx)} qty{qty}"
                else:
                    last_err = f"retCode {rc} {resp.get('retMsg')} idx{idx} qty{qty} step{qty_step} min{min_qty}"
                    if _qr<4 and "qty" in str(resp.get("retMsg","")).lower():
                        qty_step, qty_calc, qty_tp2, qty_tp3 = _heal_qty()
                        qty=str(qty_calc); qty_f=qty_calc
                        heal=True; break
            except Exception as e_idx:
                last_err = f"idx{idx} exc {str(e_idx)[:100]} qty{qty} step{qty_step}"
                try:
                    _adopted = _adopt_by_lid(_lid_for(idx)) or _pos_probe(idx)>0
                except Exception:
                    _adopted=False
                if _adopted:
                    _ok_success=True
                    add_filter_log(f"ENTRY TIMEOUT-ADOPT {sym} idx{idx} link{_lid_for(idx)} — respons hilang tapi order/posisi hidup, TIDAK kirim ulang [{GE_R1}]")
                elif _qr<4 and "qty" in str(e_idx).lower():
                    qty_step, qty_calc, qty_tp2, qty_tp3 = _heal_qty()
                    qty=str(qty_calc); qty_f=qty_calc
                    heal=True; break
            if _ok_success:
                reason = data.get("reason","")
                pos_size=_pos_probe(idx)
                add_filter_log(f"ENTRY {sym} {side} {qty} @ {px:.0f} SL {sl_price:.0f} TP-ladder 50/30/20 (TP1 {tp1:.0f} TP2 {tp2:.0f} TP3 {tp3:.0f}) size{pos_size} lev={lev}x {kelas} RR{rr_kotor:.1f} {reason} [{GE_R1}]")
                ladder=None
                if pos_size>0:
                    ladder=place_tp_ladder(sess,sym,side,idx,pos_size,_lid_base,tp1,tp2,tp3,qty_step,min_qty)
                    add_filter_log(f"TP LADDER {sym} size{pos_size} q[{ladder.get('q1')},{ladder.get('q2')},{ladder.get('q3')}] done[{ladder.get('done1')},{ladder.get('done2')},{ladder.get('done3')}] {ladder.get('warn','')} [{GE_R1}]")
                else:
                    add_filter_log(f"TP LADDER TUNDA {sym} — ukuran belum terbaca; retry engine menyusulkan [{GE_R1}]")
                try:
                    best_var_info = data.get("best_var","W")
                    _lent = ladder or {}
                    with trailing_lock:
                        open_trades_info[sym] = {
                            "var": best_var_info,
                            "rr": rr,
                            "zona": data.get("zona",0),
                            "side": side,
                            "entry_time": time.time(),
                            "entry_price": px,
                            "risk_dist": abs(px-sl_price),
                            "sl0": sl_price,
                            "tp1": tp1, "tp2": tp2, "tp3": tp3,
                            "tp2q": _lent.get("q2",0.0), "tp3q": _lent.get("q3",0.0),
                            "tp_ladder": _lent,
                            "tp_pending": not (_lent.get("done1") and _lent.get("done2") and _lent.get("done3")),
                            "pos_idx": idx,
                            "qstep": qty_step, "qmin": min_qty,
                            "link_entry": _lid_for(idx),
                            "lid_base": _lid_base,
                            "reason": reason[:80]
                        }
                except:
                    pass
                _dump_state()  # V128: ingatan tertulis saat lahir
                return True, f"ENTRY {sym} {side} {qty} @ {px:.0f} SL {sl_price:.0f} TP LADDER 50/30/20 lev={lev}x {kelas} RR{rr_kotor:.1f} [{GE_R1}]", tp1, tp2, tp_price, lev
          if not heal:
            return False, f"fail {last_err}", 0,0,0,0
        return False, f"fail {last_err}", 0,0,0,0
    except Exception as e:
        return False, f"fail {e}", 0,0,0,0

states={}
last_entry_time={}   # V113: cooldown per coin
trailing_states={}
trailing_lock=threading.Lock()
open_trades_info={}  # sym -> {var, rr, zona, side, entry_time, entry_price}
STATE_FN="open_trades_state.json"
def _dump_state():
    try:
        with trailing_lock:
            tmp=STATE_FN+".tmp"
            json.dump({"v2":True,"info":open_trades_info,"trail":trailing_states,
                       "cool":{k:v for k,v in last_entry_time.items()}},open(tmp,"w"))
            os.replace(tmp,STATE_FN)
    except Exception:
        pass
def _load_state():
    try:
        if os.path.exists(STATE_FN):
            d=json.load(open(STATE_FN))
            isv2=isinstance(d,dict) and d.get("v2")
            info=d.get("info",{}) if isv2 else (d if isinstance(d,dict) else {})
            trail=d.get("trail",{}) if isv2 else {}
            cool=d.get("cool",{}) if isv2 else {}
            with trailing_lock:
                for k,v in info.items(): open_trades_info.setdefault(k,v)
                for k,v in trail.items(): trailing_states.setdefault(k,v)
                for k,v in cool.items(): last_entry_time.setdefault(k,v)
            return len(info)
        return 0
    except Exception:
        return 0

# ============ V126-ops LEDGER (26-Sep): jurnal close ke trade_ledger.csv ============
# TULIS-SAJA untuk otopsi/rapor; TIDAK menyentuh logika trade/size/exit mana pun.
# Dedup lintas restart lewat file yang sudah ada; backfill 100 closed terakhir saat start
# (jendela lama ikut terjurnal — filter per jendela pakai kolom time vs epoch).
LEDGER_FILE="trade_ledger.csv"
_ledger_seen=set()
try:
    import csv as _csv_l
    if os.path.exists(LEDGER_FILE):
        with open(LEDGER_FILE,"r") as _lf:
            for _row in _csv_l.reader(_lf):
                if len(_row)>=11: _ledger_seen.add((_row[1],_row[10],_row[6]))
    else:
        with open(LEDGER_FILE,"w") as _lf:
            _lf.write("time,sym,side,qty,entry,exit_px,pnl_usd,var,exit_type,reason,ctime\n")
except Exception:
    pass
def ledger_note(items):
    try:
        import csv as _csv_l
        from datetime import datetime as _dt_l
        with open(LEDGER_FILE,"a") as _lf:
            _w=_csv_l.writer(_lf)
            for it in items:
                try:
                    sym=it.get("symbol",""); ctime=str(it.get("createdTime","") or "")
                    pnl=float(it.get("closedPnl","0") or 0)
                    key=(sym,ctime,f"{pnl:.4f}")  # V127: format kunci HARUS sama dgn format tulis (:4f) agar dedup hidup
                    if key in _ledger_seen: continue
                    _ledger_seen.add(key)
                    qty=float(it.get("qty","0") or 0); entry=float(it.get("avgEntryPrice","0") or 0)
                    exitp=float(it.get("avgExitPrice","0") or 0); side=it.get("side","")
                    vi=open_trades_info.get(sym,{})
                    var=vi.get("var","?"); reason=str(vi.get("reason",""))[:40]
                    # V129d2: risiko aktual = qty x jarak SL tersimpan; fallback 1.5% utk trade lama
                    _rd_l=float(vi.get("risk_dist",0) or 0)
                    risk_usd = qty*_rd_l if (qty>0 and _rd_l>0) else (qty*entry*0.015 if (qty>0 and entry>0) else 1.0)
                    r_est=pnl/risk_usd if risk_usd>0 else 0.0
                    et="RIDE 3.5R" if r_est>=1.8 else "TP1+TP2" if r_est>=1.1 else "TP1" if r_est>=0.4 else "BE" if r_est>=-0.35 else "SL"
                    ts=_dt_l.fromtimestamp(int(ctime)/1000).strftime("%Y-%m-%d %H:%M:%S") if ctime.isdigit() else ctime
                    _w.writerow([ts,sym,side,qty,entry,exitp,f"{pnl:.4f}",var,et,reason,ctime])
                except Exception:
                    continue
    except Exception:
        pass
closed_pnl_cache=[]
closed_pnl_lock=threading.Lock()
symbols=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","TRXUSDT","DOTUSDT","BCHUSDT","NEARUSDT","MATICUSDT","ETCUSDT","FILUSDT","ATOMUSDT","APTUSDT","ARBUSDT","OPUSDT","INJUSDT","STXUSDT","IMXUSDT","RNDRUSDT","TAOUSDT","SEIUSDT","PEPEUSDT","WIFUSDT","BONKUSDT"][:30]
logs=[]
kurs_idr=17840
cached_positions=[]
cached_positions_lock=threading.Lock()
last_api_fetch_time=time.time()
api_cycle_interval=LOOP_API
ui_running=True
spinner_frame_idx=0
cached_perf={"today_count":0,"today_w":0,"today_l":0,"today_pnl":0,"total_count":0,"total_wr":0,"total_pnl":0}
cached_futures_balance={"total":0.0,"available":0.0,"equity":0.0}
since_v114_cache={"n":0,"pnl":0.0,"w":0}  # V123: akumulasi closed sejak V114_START_MS
cached_futures_lock=threading.Lock()

def add_log(msg):
    ts=datetime.now().strftime("%H:%M:%S")
    clean = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', msg)
    clean = clean.replace('\x1b','')
    for bad in ["[A","[B","[C","[D","[2J","[H","[K","[J","?25l","?25h"]:
        clean = clean.replace(bad,"")
    logs.append(f"{ts} {clean}")
    if len(logs)>6: logs.pop(0)

def get_term_size():
    try:
        cols, rows = os.get_terminal_size()
        return max(50, cols), max(20, rows)
    except:
        return 80, 24

# BUG 2 FIX: WATCHDOG THRESHOLD 6.0->5.5, 5.0->4.5, 4.0->3.5, 3.0->2.8 biar 86% SIAP ada 2-3 coin bukan 0 — TAMPILAN WARNA TETAP
def get_watchdog_bar_V95(zona):
    # BUG 2 FIX: threshold turun biar variasi nyata, 86% SIAP muncul 2-3 coin, bukan 0
    if zona >= 5.5:
        color = "\033[92m\033[1m"
        bar = f"{color}█████\033[90m░░░░░\033[0m"
        status = f"\033[92m\033[1m86% SIAP ★\033[0m"
        arrow = f"\033[92m▲H\033[0m"
    elif zona >= 4.5:
        color = "\033[93m\033[1m"
        bar = f"{color}████\033[90m░░░░░░\033[0m"
        status = f"\033[93m\033[1m67% DEKAT ★\033[0m"
        arrow = f"\033[93m•H\033[0m"
    elif zona >= 3.5:
        color = f"{rgb_fg(255,165,0)}\033[1m"
        bar = f"{color}███\033[90m░░░░░░░\033[0m"
        status = f"{rgb_fg(255,165,0)}\033[1m50% PANTAU ★\033[0m"
        arrow = f"{rgb_fg(255,165,0)}▼H\033[0m"
    elif zona >= 2.8:
        color = "\033[91m"
        bar = f"{color}██\033[90m░░░░░░░░\033[0m"
        status = f"\033[91m30% JAUH ★\033[0m"
        arrow = f"\033[91m▼M\033[0m"
    else:
        color = "\033[90m"
        bar = f"\033[90m█\033[90m░░░░░░░░░\033[0m"
        status = f"\033[90m15% JAUH ★\033[0m"
        arrow = f"\033[90m▼L\033[0m"
    return bar, status, arrow, color

def get_global_market_trend():
    try:
        # hitung dari BTC trend + mayoritas regime 30 coin
        btc_trend = states.get("BTCUSDT",{}).get("trend",0)
        regimes = [s.get("regime","SIDEWAYS") for s in states.values()]
        bull_c = sum(1 for r in regimes if "BULL" in r)
        bear_c = sum(1 for r in regimes if "BEAR" in r)
        side_c = sum(1 for r in regimes if r=="SIDEWAYS")
        rot_c = sum(1 for r in regimes if r=="ROTATION")
        vol_c = sum(1 for r in regimes if r=="VOLATILE")
        total = len(regimes) or 1
        # tentukan global
        if btc_trend>1.5 and bull_c>bear_c and bull_c>=total*0.35:
            return "BULLISH", bull_c, bear_c, btc_trend
        elif btc_trend<-1.5 and bear_c>bull_c and bear_c>=total*0.30:
            return "BEARISH", bull_c, bear_c, btc_trend
        elif side_c>=total*0.40:
            return "NEUTRAL SIDEWAYS", bull_c, bear_c, btc_trend
        elif rot_c>=total*0.35:
            return "NEUTRAL ROTATION", bull_c, bear_c, btc_trend
        elif vol_c>=total*0.25:
            return "VOLATILE", bull_c, bear_c, btc_trend
        else:
            if btc_trend>0.7:
                return "NEUTRAL BULL BIAS", bull_c, bear_c, btc_trend
            elif btc_trend<-0.7:
                return "NEUTRAL BEAR BIAS", bull_c, bear_c, btc_trend
            else:
                return "NEUTRAL", bull_c, bear_c, btc_trend
    except:
        return "NEUTRAL", 0,0,0

def get_filter_log_color_by_score(log_clean):
    score = 0
    zona = 0.0
    try:
        m = re.search(r'S(\d+)', log_clean)
        if m: score = int(m.group(1))
        m2 = re.search(r'z(\d+\.?\d*)', log_clean)
        if m2: zona = float(m2.group(1))
    except: pass
    if score >= 22 or zona >= 5.5:
        return "\033[92m\033[1m"
    elif score >= 18 or zona >= 4.5:
        return "\033[92m"
    elif score >= 15 or zona >= 4.0:
        return "\033[96m\033[1m"
    elif score >= 12 or zona >= 3.5:
        return "\033[93m\033[1m"
    elif score >= 9 or zona >= 2.8:
        return f"{rgb_fg(255,165,0)}\033[1m"
    else:
        return "\033[91m"

def ansi_truncate(s, max_visual):
    result=""; visual=0; i=0
    while i < len(s) and visual < max_visual:
        if s[i] == '\x1b' and i+1 < len(s) and s[i+1]=='[':
            j=i+2
            while j < len(s) and s[j] != 'm' and j-i < 20: j+=1
            if j < len(s) and s[j]=='m':
                result+=s[i:j+1]
                i=j+1
                continue
        result+=s[i]; visual+=1; i+=1
    return result

def clean_line(s, term_w):
    return ansi_truncate(s, term_w-1) + "\033[0m\033[K"

def render_dashboard_string():
    global spinner_frame_idx
    spinner_frame_idx = (spinner_frame_idx + 1) % 10000
    TERM_W, TERM_H = get_term_size()
    cap = GE_CAP
    with cached_positions_lock:
        positions = list(cached_positions)
        perf = dict(cached_perf)
        with filter_logs_lock:
            flogs = list(filter_logs)
    total_pnl = 0.0
    for p in positions:
        try: total_pnl += float(p.get("unrealisedPnl","0") or 0)
        except: pass
    total_pnl_idr = total_pnl * kurs_idr
    profit_count = sum(1 for p in positions if float(p.get("unrealisedPnl","0") or 0) > 0)
    now = time.time()
    # V105 NO BLINK: warna tetap + spinner realtime
    pulse_red = rgb_fg(255, 60, 60)
    pulse_green = rgb_fg(0, 255, 130)
    pulse_cyan = rgb_fg(0, 220, 255)
    spin = SPINNER_BRAILLE[spinner_frame_idx % len(SPINNER_BRAILLE)]
    time_until_api = max(0, int(api_cycle_interval - (now - last_api_fetch_time)))
    api_badge = f"{pulse_cyan}[SYNC {time_until_api:02d}s {spin}]\033[0m" if time_until_api>0 else f"{pulse_green}[SYNCING {spin}]\033[0m"

    is_compact = TERM_W < 100
    watchdog_n = 8 if is_compact else 12

    lines = []
    btc_price = states.get("BTCUSDT", {}).get("px", 85773.20)
    total_pnl_pct = (total_pnl/cap*100) if cap>0 else 0
    # V101 BARU: HARGA BTC BESAR + IDR FUTURES BESAR DARI SALDO FUTURE REAL (beda dengan cap)
    with cached_futures_lock:
        fut_bal = dict(cached_futures_balance) if 'cached_futures_balance' in globals() else {"total":cap,"available":cap,"equity":cap}
    wallet_usdt = fut_bal.get("total",cap) or cap
    futures_usdt = min(cap, wallet_usdt)  # V118: modal trade REAL = min(cap, wallet); top-up demo tidak menggeleungkan tampilan besar
    futures_idr = futures_usdt * kurs_idr
    # big display seperti script dulu: BTC besar + IDR futures besar
    btc_big = f"{btc_price:,.0f}"
    idr_big = f"Rp{wallet_usdt*kurs_idr:,.0f}"  # V125d: IDR figlet = SALDO BURSA keseluruhan (permintaan user), bukan modal bot
    # tetap ada pnl kecil sebagai info tambahan tapi yang besar adalah BTC + IDR futures

    mode_color = "\033[92m\033[1m" if GE_R1=="LONGGA" else "\033[93m\033[1m"
    h1 = f"\033[93m\033[1mV125 GOLD35\033[0m {mode_color}[{GE_R1}]\033[0m \033[90mTOP30\033[0m \033[96mZONA{GE_ZONA}\033[0m \033[93m{AK_TYPE}\033[0m \033[92m${cap:.0f}\033[0m"
    btc_line = f"\033[93m\033[1mBTCUSDT {btc_price:,.0f}\033[0m \033[90m[{len(symbols)}]\033[0m \033[92m${cap:.0f}=Rp{cap*kurs_idr:,.0f}\033[0m \033[96m{AK_TYPE}\033[0m {spin} {api_badge} {mode_color}MODE:{GE_R1}\033[0m"
    lines.append(clean_line(h1, TERM_W))
    lines.append(clean_line(btc_line, TERM_W))
    mode_desc = "LONGGA=TP dekat entry banyak" if GE_R1=="LONGGA" else "KETAT=TP jauh profit besar"
    # V107: BTC + IDR LEBIH BESAR — pakai background + bold + underline biar kelihatan besar
    # V125c: BTC+IDR model FIGLET KOTAK — gede nya SAMA seperti tulisan LONG/SHORT di kartu,
    # 3 baris bersebelahan, TANPA tulisan "BTC", IDR tetap berlabel RP, berkedip pelan
    def _fig3(s):
        G={'0':["╔═╗","║ ║","╚═╝"],'1':[" ║ "," ║ ","═╩═"],'2':["╔═╗","╔═╝","╚══"],'3':["╔═╗"," ═║","╚═╝"],
           '4':["╦ ╦","╚═╣","  ║"],'5':["╔══","╚═╗","╚═╝"],'6':["╔══","╠═╗","╚═╝"],'7':["╔═╗","  ║","  ║"],
           '8':["╔═╗","╠═╣","╚═╝"],'9':["╔═╗","╚═╣","╚═╝"],',':["   ","   ","  ╶"],'.':["   ","   ","  ╴"],
           'R':["╔═╗","╠╦╝","╩ ╩"],'P':["╔═╗","╠╦╝","╩  "],' ':["   ","   ","   "]}
        rows=["","",""]
        for ch in s:
            g=G.get(ch.upper(),G[' '])
            for i in range(3): rows[i]+=g[i]+" "
        return rows
    _on = (int(time.time()/2) % 2) == 0
    _c_btc = "\033[93m\033[1m" if _on else "\033[33m\033[1m"
    _c_idr = "\033[92m\033[1m" if _on else "\033[32m\033[1m"
    _fb=_fig3(btc_big); _fi=_fig3(idr_big.replace('Rp','RP'))
    if TERM_W >= len(_fb[0])+len(_fi[0])+6:
        for i in range(3):
            lines.append(clean_line(f" {_c_btc}{_fb[i]}\033[0m  \033[90m|\033[0m {_c_idr}{_fi[i]}\033[0m", TERM_W))
    else:
        for i in range(3): lines.append(clean_line(f" {_c_btc}{_fb[i]}\033[0m", TERM_W))
        for i in range(3): lines.append(clean_line(f" {_c_idr}{_fi[i]}\033[0m", TERM_W))
    # V125 GOLD35: BANNER REZIM BESAR BERKEDIP FULL-WIDTH — saklar induk arah semua entry
    # hijau kedip 1Hz = BULL (LONG saja) | kuning kedip 1Hz = NON-BULL (SHORT saja) | merah kedip 2Hz = CRASH (no new long)
    roc30_ui,roc7_ui=get_btc_regime()
    btc20h_ui=states.get("BTCUSDT",{}).get("htf",0.0)
    crash_ui = CRASH_GUARD_ENABLED and (btc20h_ui<CRASH_BTC20H_MIN or roc7_ui<CRASH_BTC7D_MIN)
    tnow=time.time()
    if crash_ui:
        txt=f" ██ CRASH! 20h{btc20h_ui:+.1f}% 7d{roc7_ui:+.1f}% ▶ NO NEW LONG • SHORT SIAGA ██ "
        on=(int(tnow*2)%2)==0
        rezim_banner=(f"\033[41m\033[97m\033[1m{txt.ljust(TERM_W-1)}\033[0m" if on else f"\033[47m\033[31m\033[1m{txt.ljust(TERM_W-1)}\033[0m")
    elif roc30_ui>REGIME_ROC30_LONG_MIN:
        txt=f" ██ REZIM: BULL {roc30_ui:+.1f}%  ▶  ENTRY: LONG SAJA • SHORT DIBLOKIR ██ "
        on=(int(tnow)%2)==0
        rezim_banner=(f"\033[42m\033[30m\033[1m{txt.ljust(TERM_W-1)}\033[0m" if on else f"\033[92m\033[1m{txt.ljust(TERM_W-1)}\033[0m")
    else:
        if roc30_ui < -REGIME_ROC30_LONG_MIN:
            txt=f" ██ REZIM: BEAR {roc30_ui:+.1f}%  ▶  ENTRY: SHORT SAJA • LONG DIBLOKIR ██ "
        else:
            txt=f" ██ REZIM: CHOP {roc30_ui:+.1f}%  ▶  FLAT: TIADA ENTRY BARU (sertifikat: long@BULL, short@BEAR) ██ "
        on=(int(tnow)%2)==0
        rezim_banner=(f"\033[43m\033[30m\033[1m{txt.ljust(TERM_W-1)}\033[0m" if on else f"\033[93m\033[1m{txt.ljust(TERM_W-1)}\033[0m")
    lines.append(clean_line(rezim_banner, TERM_W))
    # V129d1: penanda DRAFT permanen di dashboard — cegah swap keliru (file ini belum lengkap)
    _dtxt=" ██ DRAFT V129d2 — JANGAN SWAP KE VPS — BELUM VERIFIKASI LAPANGAN ██ "
    lines.append(clean_line(f"\033[45m\033[97m\033[1m{_dtxt.ljust(TERM_W-1)}\033[0m", TERM_W))
    # baris kedua info cap tetap
    wtxt = f"${wallet_usdt/1e6:.2f}M" if wallet_usdt>=1e6 else f"${wallet_usdt:,.0f}"
    cap_line = f"   \033[90mSALDO BURSA (futures): {wtxt} | MODAL BOT: ${futures_usdt:.2f} PnL{total_pnl:+.2f}$\033[0m {mode_color}{GE_R1}\033[0m \033[90m| {mode_desc}\033[0m"
    lines.append(clean_line(cap_line, TERM_W))
    # V102 BARU: KONDISI MARKET TREN BULL/BEAR/NEUTRAL + KEDIP SPINNER BAGUS
    try:
        m_trend, bull_c, bear_c, btc_tr = get_global_market_trend()
        # warna + icon + kedip spinner
        if "BULLISH" in m_trend:
            m_color = rgb_fg(0,255,120)  # V105 hijau tetap
            m_icon = "▲"
            m_bar = f"{m_color}█████\033[90m░░░░░\033[0m"
        elif "BEARISH" in m_trend:
            m_color = rgb_fg(255,60,60)  # V105 merah tetap
            m_icon = "▼"
            m_bar = f"{m_color}█████\033[90m░░░░░\033[0m"
        elif "VOLATILE" in m_trend:
            m_color = rgb_fg(255,165,0)  # V105 orange tetap
            m_icon = "⚡"
            m_bar = f"{m_color}███\033[90m░░░░░░░\033[0m"
        else:  # NEUTRAL
            m_color = rgb_fg(0,220,255)  # V105 cyan tetap
            m_icon = "●"
            m_bar = f"{m_color}███\033[90m░░░░░░░\033[0m"
        # spinner kedua untuk market
        spin2 = SPINNER_BRAILLE[(spinner_frame_idx+3) % len(SPINNER_BRAILLE)]
        market_line = f"   \033[96m\033[1mMARKET\033[0m {m_bar} {m_color}{m_icon} {m_trend}\033[0m \033[90mBULL{bull_c} BEAR{bear_c} BTC{btc_tr:+.1f}%\033[0m {spin} {spin2} {m_color}● LIVE\033[0m"
        lines.append(clean_line(market_line, TERM_W))
    except:
        pass

    lines.append(clean_line(f"   \033[96m\033[1mWATCHDOG\033[0m \033[90m({watchdog_n} dari {len(symbols)} sisa {max(0,len(symbols)-watchdog_n)} pos {len(positions)})\033[0m {mode_color}— GOLD21 INDIKATOR REAL HTFRSI — SL 2.0ATR TP 1.5/2.5/3.5R\033[0m", TERM_W))
    sorted_syms = sorted(states.items(), key=lambda x: x[1].get("zona",0), reverse=True)
    for idx, (sym, data) in enumerate(sorted_syms[:watchdog_n]):
        zona = data.get("zona", 0); rdy = data.get("rdy", 0); fuel = data.get("fuel", 0); rr = data.get("rr", 2.0)
        best_var = data.get("best_var", "W"); ai = data.get("ai", 60)
        bar, status, arrow, color = get_watchdog_bar_V95(zona)
        # V111: bukan random — estimasi gerak dari trend 15m REAL coin itu
        pnl_pct = max(-2.5, min(2.5, data.get("trend",0)*0.25))
        pnl_col = f"\033[92m+{pnl_pct:.1f}%\033[0m" if pnl_pct>=0 else f"\033[91m{pnl_pct:.1f}%\033[0m"
        _sig=data.get("sig","")
        sig_tag = f" \033[92m\033[1mSIG-BUY\033[0m" if _sig=="Buy" else (f" \033[91m\033[1mSIG-SELL\033[0m" if _sig=="Sell" else "")
        if is_compact:
            lines.append(clean_line(f" {color}{sym:8s}\033[0m {arrow} \033[96mF{rdy:2.0f}%\033[0m {bar} {status} {pnl_col} \033[96mAI{ai}%\033[0m \033[93mRR{rr:.1f}\033[0m \033[92m{best_var}\033[0m{sig_tag} \033[90mz{zona:.1f}\033[0m", TERM_W))
        else:
            lines.append(clean_line(f"   {color}{sym:10s}\033[0m {arrow} •m \033[96mF {rdy:2.0f}%\033[0m {bar} {status} {pnl_col} \033[96mAI{ai}%\033[0m \033[93mRR{rr:.1f}\033[0m \033[92mAUTO-{best_var}\033[0m{sig_tag} \033[90mz{zona:.1f}\033[0m", TERM_W))

    active_count = len(positions)
    status_dot = f"{pulse_red}●\033[0m" if active_count > 0 else f"{pulse_cyan}○\033[0m"
    if total_pnl>=0:
        pnl_color = f"\033[92m\033[1m{total_pnl:+.2f}$ Rp{total_pnl_idr:,.0f}\033[0m"
    else:
        pnl_color = f"\033[91m\033[1m{total_pnl:+.2f}$ Rp{total_pnl_idr:,.0f}\033[0m"
    # BUG 1 FIX: /3 -> /GE_MAX_POS — biar Cap 100 Max 10 tampil (1/10) bukan (1/3)
    pos_header = f"{status_dot} \033[93m\033[1mPOSISI AKTIF\033[0m \033[90m({active_count}/{GE_MAX_POS})\033[0m {pnl_color} \033[92m{profit_count}/{active_count} profit\033[0m {mode_color}— {GE_R1} MODE\033[0m"
    lines.append(clean_line(pos_header, TERM_W))
    lines.append(clean_line(f"\033[90m{'-'*min(TERM_W-2,60)}\033[0m", TERM_W))

    if positions:
        cards=[]  # V120: data kartu posisi, dirender sesudah loop (2 kolom / stacked)
        for p in positions:
            sym=p.get("symbol","BTCUSDT"); side=p.get("side","Sell"); size=p.get("size","0")
            avg=p.get("avgPrice","0")
            try: avg_f=float(avg)
            except: avg_f=0.0
            try: pnl=float(p.get("unrealisedPnl","0") or 0)
            except: pnl=0.0
            try: pnl_pct=pnl/(float(size)*avg_f)*100*50 if float(size)*avg_f!=0 else 0
            except: pnl_pct=0.0
            st=states.get(sym,{}); best_var=st.get("best_var","W"); atr=st.get("atr",500)
            if atr<=0 or atr>5000: atr=avg_f*0.02
            sl_dist = min(atr*SL_ATR_MULT, avg_f*SL_PCT_MAX); sl_dist = max(sl_dist, avg_f*SL_PCT_MIN)
            if side=="Buy": sl_price = avg_f - sl_dist - atr*ANTI_HUNT_ATR - atr*FINAL_BUFFER_ATR; tp_price = avg_f + sl_dist*TP2_R
            else: sl_price = avg_f + sl_dist + atr*ANTI_HUNT_ATR + atr*FINAL_BUFFER_ATR; tp_price = avg_f - sl_dist*TP2_R
            tp1 = avg_f + sl_dist*TP1_R if side=="Buy" else avg_f - sl_dist*TP1_R
            tp2 = avg_f + sl_dist*TP2_R if side=="Buy" else avg_f - sl_dist*TP2_R
            tp3 = avg_f + sl_dist*TP3_R if side=="Buy" else avg_f - sl_dist*TP3_R
            # V107: format price sesuai tick biar tidak 0
            sl_fmt = format_price_by_tick(sl_price, sym)
            tp_fmt = format_price_by_tick(tp_price, sym)
            tp1_fmt = format_price_by_tick(tp1, sym)
            tp2_fmt = format_price_by_tick(tp2, sym)
            tp3_fmt = format_price_by_tick(tp3, sym)
            live_fmt = format_price_by_tick(st.get('px',avg_f), sym)
            entry_fmt = format_price_by_tick(avg_f, sym)
            # V108 BARU: ambil SL/TP sesuai Bybit (stopLoss, takeProfit) + hitung % dari entry
            try:
                bybit_sl_raw = p.get("stopLoss","") or p.get("stopLossPrice","")
                bybit_tp_raw = p.get("takeProfit","") or p.get("takeProfitPrice","")
                bybit_sl_f = float(bybit_sl_raw) if bybit_sl_raw and bybit_sl_raw!="0" else 0.0
                bybit_tp_f = float(bybit_tp_raw) if bybit_tp_raw and bybit_tp_raw!="0" else 0.0
                # hitung % jarak dari entry
                if avg_f!=0 and bybit_sl_f!=0:
                    sl_pct = abs(bybit_sl_f - avg_f)/avg_f*100
                    sl_pct_str = f"{sl_pct:.1f}%"
                    bybit_sl_fmt = format_price_by_tick(bybit_sl_f, sym)
                else:
                    sl_pct_str = ""
                    bybit_sl_fmt = "0"
                if avg_f!=0 and bybit_tp_f!=0:
                    tp_pct = abs(bybit_tp_f - avg_f)/avg_f*100
                    tp_pct_str = f"{tp_pct:.1f}%"
                    bybit_tp_fmt = format_price_by_tick(bybit_tp_f, sym)
                else:
                    tp_pct_str = ""
                    bybit_tp_fmt = "0"
                # qty TP/SL % dari Bybit (kalau ada tpSlMode, tapi kita pakai 50%/100%)
                # untuk TP bertahap, kita tampilkan 50% @1R, 30% @2R, 20% @3R sesuai bot, tapi juga TP Bybit
            except:
                bybit_sl_f=0.0; bybit_tp_f=0.0; sl_pct_str=""; tp_pct_str=""; bybit_sl_fmt="0"; bybit_tp_fmt="0"
            try: lev=int(float(p.get("leverage","0") or 0))
            except: lev=25
            if lev==0: lev,_ ,_ = smart_leverage_safe(sym, avg_f, sl_price, atr, side)
            # V129d2: LIQ NYATA dari API Bybit (sudah mencakup maint-tier/mode/saldo) — bukan klaim;
            # fallback formula konservatif hanya bila field kosong, dan itu DITANDAI "est".
            try: liq_api=float(p.get("liqPrice","0") or 0)
            except: liq_api=0.0
            liq_src="API"
            if liq_api<=0:
                liq_api=calc_liquidation_price(avg_f, lev, side) if lev>0 else 0.0
                liq_src="est"
            liq_fmt = format_price_by_tick(liq_api, sym) if liq_api>0 else "-"
            # V122: margin $ yang dipakai posisi ini (request user tampil di kartu)
            try: m_usd=float(p.get("positionMargin","0") or 0)
            except: m_usd=0.0
            if m_usd<=0:
                try: m_usd=float(size)*avg_f/lev if lev>0 else 0.0
                except: m_usd=0.0
            idr=int(pnl*kurs_idr)
            is_short = (side != "Buy")
            zona = st.get("zona",0)
            rr_real = st.get("rr",2.2)

            # V120: kumpulkan data kartu (render berdampingan dilakukan sesudah loop)
            sidetxt = "SHORT" if is_short else "LONG"
            reason_full = st.get("reason","")
            tag=""
            for kw in ("NGEJAR-PUMP","NGEJAR-DUMP","OVERBOUGHT","OVERSOLD","SIG-BUY","SIG-SELL"):
                if kw in reason_full: tag=kw; break
            if not tag: tag = "NOSIG" if "NOSIG" in reason_full else ""
            try:
                sl_pnl_pct = float(sl_pct_str.replace('%','')) * lev if sl_pct_str else 0.0
                tp_pnl_pct = float(tp_pct_str.replace('%','')) * lev if tp_pct_str else 0.0
            except:
                sl_pnl_pct=0.0; tp_pnl_pct=0.0
            if bybit_sl_f!=0 or bybit_tp_f!=0:
                sl_show, tp_show = bybit_sl_fmt, bybit_tp_fmt
            else:
                sl_show, tp_show = sl_fmt, tp_fmt
            cards.append({"side":sidetxt,"is_short":is_short,"sym":sym,"pnl":pnl,"pnl_pct":pnl_pct,
                "rr":rr_real,"var":best_var,"zona":zona,"lev":lev,"entry":entry_fmt,"live":live_fmt,
                "size":size,"idr":idr,"tag":tag,"sl":sl_show,"slp":sl_pnl_pct,"slpct":sl_pct_str,
                "tp":tp_show,"tpp":tp_pnl_pct,"tpct":tp_pct_str,"bsl":sl_fmt,"btp":tp_fmt,
                "tp1":tp1_fmt,"tp2":tp2_fmt,"tp3":tp3_fmt,"reason":reason_full,"m":m_usd,"liq":liq_fmt,"liqsrc":liq_src})
    else:
        # BUG 1 FIX: (0/3) -> (0/GE_MAX_POS)
        lines.append(clean_line(f"   \033[90mPOSISI (0/{GE_MAX_POS}) Menunggu sinyal... R1:{GE_R1} ZONA{GE_ZONA} {GE_AKUN} — {GE_R1} MODE\033[0m", TERM_W))

    # V125 GOLD35 RENDER KARTU POSISI: >=2 posisi berdampingan 2 kolom (4 baris/pasang, wrap ke bawah);
    # 1 posisi = stacked 3 baris penuh. Murni tampilan — logika trading tidak disentuh.
    if positions:
        W_CARD = max(34, (TERM_W-3)//2)
        def _pj(sx,w):
            return sx + " "*(w-len(sx)) if len(sx)<w else sx[:w]
        # V125 GOLD35: teks BESAR 3 baris LONG/SHORT (figlet block) berkedip pelan — request user
        FIG_LONG  = ["\u2588   \u2554\u2550\u2557 \u2554\u2557\u2554 \u2554\u2550\u2557",
                     "\u2588   \u2551 \u2551 \u2551\u2551\u2551 \u2551 \u2566",
                     "\u255a\u2550\u255d \u255a\u2550\u255d \u255d\u255a\u255d \u255a\u2550\u255d"]
        FIG_SHORT = ["\u2554\u2550\u2557 \u2566 \u2566 \u2554\u2550\u2557 \u2566\u2550\u2557 \u2554\u2566\u2557",
                     "\u255a\u2550\u2557 \u2560\u2550\u2563 \u2551 \u2551 \u2560\u2566\u255d  \u2551",
                     "\u255a\u2550\u255d \u2569 \u2569 \u255a\u2550\u255d \u2569\u255a\u2550  \u2569"]
        FIGW = 20
        def _pos_lines(cd, W):
            fig = FIG_SHORT if cd["is_short"] else FIG_LONG
            phase = int(time.time()/2)%2  # kedip PELAN: ganti gaya tiap 2 detik
            if cd["is_short"]:
                fcol = "\033[41m\033[97m\033[1m" if phase==0 else "\033[91m\033[1m"
            else:
                fcol = "\033[42m\033[30m\033[1m" if phase==0 else "\033[92m\033[1m"
            RW = max(12, W-FIGW-1)
            r1=_pj(f" {cd['sym']} {cd['pnl']:+.2f}$",RW)
            r2=_pj(f" {cd['pnl_pct']:+.1f}% {cd['var']} z{cd['zona']:.1f} {cd['lev']}x Sz{cd['size']}",RW)
            r3=_pj(f" MARGIN PAKAI ${cd['m']:.2f}",RW)  # V122c: teks polos sesuai request user (saldo jaminan posisi)
            out=[]
            for i,r in enumerate((r1,r2,r3)):
                out.append(fcol+_pj(fig[i],FIGW)+"\033[0m \033[97m"+r+"\033[0m")
            slt=f" SL {cd['sl']}({cd['slp']:+.1f}%)"
            tpt=f" TP {cd['tp']}({cd['tpp']:+.1f}%)"
            _tm={"NGEJAR-PUMP":"PUMP","NGEJAR-DUMP":"DUMP","OVERBOUGHT":"OVBUY","OVERSOLD":"OVSEL","SIG-BUY":"SIG-B","SIG-SELL":"SIG-S","NOSIG":"NOSIG"}
            tag=_tm.get(cd['tag'], cd['tag'][:6] if cd['tag'] else "")
            wt=max(0,W-len(slt)-7)
            L4="\033[91m"+_pj(slt,min(len(slt),W))+"\033[0m\033[92m"+_pj(tpt,wt)+"\033[0m \033[90m"+_pj(tag,6)+"\033[0m"
            L5="\033[90m"+_pj(f" ENTRY {cd['entry']} LIVE {cd['live']} LIQ {cd['liq']}({cd['liqsrc']}) | 50/30/20+tr",W)+"\033[0m"
            return out+[L4,L5]
        if len(cards)==1:
            for ln in _pos_lines(cards[0], TERM_W-2):
                lines.append(clean_line(ln, TERM_W))
        else:
            for i in range(0, len(cards), 2):
                pr = cards[i:i+2]
                cl = _pos_lines(pr[0], W_CARD)
                if len(pr)==2:
                    cr = _pos_lines(pr[1], W_CARD)
                    for x,y in zip(cl,cr):
                        lines.append(clean_line(x+" "+y, TERM_W))
                else:
                    for x in cl:
                        lines.append(clean_line(x, TERM_W))

    # V100 BARU: RIWAYAT TP/SL 5 BARIS + INDIKATOR + WINRATE WARNA
    with closed_pnl_lock:
        closed_list = list(closed_pnl_cache)
    with cached_positions_lock:
        perf_local = dict(cached_perf)
    total_wr = perf_local.get("total_wr",0)
    today_wr = int(perf_local.get("today_w",0)/perf_local.get("today_count",1)*100) if perf_local.get("today_count",0)>0 else 0
    total_count = perf_local.get("total_count",0)
    today_count = perf_local.get("today_count",0)
    total_pnl_perf = perf_local.get("total_pnl",0)
    wr_color = "\033[92m\033[1m" if total_wr>=70 else "\033[93m\033[1m" if total_wr>=50 else "\033[91m\033[1m"
    lines.append(clean_line(f" \033[96m\033[1mRIWAYAT TP/SL (5)\033[0m {wr_color}WR{total_wr}%\033[0m \033[90m({total_count} trades)\033[0m \033[93mTODAY {today_count} WR{today_wr}% PnL{perf_local.get('today_pnl',0):+.2f}$\033[0m \033[92mTOTAL {total_pnl_perf:+.2f}$\033[0m", TERM_W))
    if closed_list:
        for item in closed_list[:5]:
            sym=item.get("symbol","")
            pnl=item.get("pnl",0)
            var=item.get("var","W")
            exit_type=item.get("exit_type","")
            side=item.get("side","")
            # warna sesuai TP/SL
            if pnl>0:
                if "RIDE" in exit_type or "TP1+TP2+TP3" in exit_type:
                    color="\033[92m\033[1m"  # hijau terang ride max
                    icon="🚀"
                elif "TP1+TP2" in exit_type:
                    color="\033[92m"  # hijau TP2
                    icon="✅"
                else:
                    color="\033[96m\033[1m"  # cyan TP1
                    icon="💰"
            else:
                if "BE" in exit_type:
                    color="\033[93m\033[1m"  # kuning BE
                    icon="🟡"
                else:
                    color="\033[91m\033[1m"  # merah SL
                    icon="❌"
            pnl_str = f"{pnl:+.2f}$"
            # WR per var
            wr_map={"BN":83.3,"BM":80.0,"M":80.0,"W":66.4,"BQ":70.0,"BR":68.0}
            wr_claim=wr_map.get(var,66.4)
            lines.append(clean_line(f"  {color}{icon} {sym:10s} {side:4s} {pnl_str:8s} {exit_type:12s} [{var} WR{wr_claim:.0f}%] {wr_color}WR{total_wr}%\033[0m", TERM_W))
    else:
        lines.append(clean_line(f"   \033[90mBelum ada riwayat closed — {AK_TYPE} {total_count} trades WR{total_wr}% — TP/SL akan muncul setelah close\033[0m", TERM_W))

    sv=since_v114_cache
    sv_wr=int(sv["w"]/sv["n"]*100) if sv["n"]>0 else 0
    sv_col="\033[92m\033[1m" if sv["pnl"]>0 else "\033[91m\033[1m"
    _ep_lbl=time.strftime("%d-%b %H:%M", time.localtime(V114_START_MS/1000))
    lines.append(clean_line(f" \033[96m\033[1mSINCE {_ep_lbl}:\033[0m {sv_col}{sv['n']} closes WR{sv_wr}% {sv['pnl']:+.2f}$\033[0m \033[90m| target >=30 closes utk vonis real\033[0m", TERM_W))
    lines.append(clean_line(f" \033[93m6 IND\033[0m \033[92mBN83%\033[0m \033[92mBM80%\033[0m \033[92mM80%\033[0m \033[92mW66%\033[0m \033[96mBQ70%\033[0m \033[96mBR68%\033[0m {mode_color}AUTO {GE_R1}\033[0m \033[90mZONA{GE_ZONA}\033[0m", TERM_W))
    lines.append(clean_line(f" \033[96mSMART LEV\033[0m \033[92m{LEV_STD_MAJOR}x\033[0m \033[90mALT\033[0m \033[93m{LEV_STD_ALT}x\033[0m \033[90mSL gap {LEV_SL_GAP}x HUNT {ANTI_HUNT_ATR}x+buff {FINAL_BUFFER_ATR}x FEE {FEE_R}R FUND {FUNDING_R}R SLIP {SLIP_PCT}% TRAIL R2.0 BE 1R DEMO=REAL\033[0m", TERM_W))

    lines.append(clean_line(f"\033[96m\033[1m=== ENTRY FILTER LOG [{GE_R1}] — WARNA BEDA BY SKOR — 6BUG FIX ===\033[0m", TERM_W))
    if flogs:
        for fl in flogs[-8:]:
            cl = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', fl)
            for bad in ["[A","[B","[C","[D","[2J","[H","[K","[J","?25l","?25h"]:
                cl = cl.replace(bad,"")
            if "OK" in cl or "ENTRY" in cl:
                color = get_filter_log_color_by_score(cl)
                lines.append(clean_line(f"{color}{cl[:TERM_W-2]}\033[0m", TERM_W))
            else:
                lines.append(clean_line(f"\033[90m{cl[:TERM_W-2]}\033[0m", TERM_W))
    else:
        lines.append(clean_line("\033[90m(log terisi saat ada kandidat: coin ber-SIG dievaluasi -> SKIP/TRY/ENTRY; market tenang = kosong; buffer reset tiap restart)\033[0m", TERM_W))

    lines.append(clean_line("", TERM_W))
    lines.append(clean_line(f" \033[96mLIVE LOG — V125 GOLD35 {GE_R1} — {GE_AKUN}\033[0m", TERM_W))
    for log in logs[-4:]:
        cl = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', log)
        for bad in ["[A","[B","[C","[D","[2J","[H","[K","[J","?25l","?25h"]:
            cl = cl.replace(bad,"")
        lines.append(clean_line(f"   \033[97m{cl[:TERM_W-4]}\033[0m", TERM_W))

    footer_alive = f"{pulse_green}● ALIVE {spin} (1s)\033[0m"
    lines.append(clean_line(f" \033[90mCtrl+C stop •\033[0m {footer_alive} \033[90m• {GE_AKUN} {AK_BASE} • V125 GOLD35 TAMPILAN TETAP — {GE_R1}\033[0m", TERM_W))

    if len(lines) > TERM_H-1:
        lines = lines[:TERM_H-1]

    return "\n".join(lines)

def ui_render_loop():
    # V106 NO BLINK TOTAL: jangan pakai 2J (clear screen) yang bikin kedip, pakai H (home) saja
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    try:
        # clear sekali di awal
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        while ui_running:
            t0 = time.time()
            buf = render_dashboard_string()
            # V106: H saja, tidak 2J, biar tidak berkedip — overwrite + clear down
            sys.stdout.write("\033[H" + buf + "\n\033[J")
            sys.stdout.flush()
            elapsed = time.time() - t0
            time.sleep(max(0.05, 1.0 - elapsed))
    finally:
        sys.stdout.write("\033[?25h\033[0m\n")
        sys.stdout.flush()

def force_loop():
    time.sleep(10)
    add_log(f"force loop V125 GOLD35 {GE_R1} AKUN {AK_TYPE} — ENTRY HANYA SIG HTFRSI z>=4.0")
    last_count=0
    while True:
        try:
            active=get_real_positions()
            if active is None:
                add_log(f"TRADING BLOCKED: posisi exchange tak terverifikasi ({POS_STATUS}) [{GE_R1}]")
                time.sleep(LOOP_FORCE); continue
            active_syms=set(p.get("symbol","") for p in active)
            if len(active)!=last_count:
                add_log(f"POSISI {last_count}->{len(active)} {list(active_syms)} [{GE_R1}]")
                last_count=len(active)
                        # V107 FIX: entry LONG/SHORT sesuai tren, bukan LONG semua — cek market bearish
            if len(active) < GE_MAX_POS:
                # sort states by zona desc — prioritaskan 86% SIAP dulu
                sorted_states=sorted(states.items(), key=lambda x: x[1].get("zona",0), reverse=True)
                # global market trend untuk tentukan long vs short
                try:
                    m_trend_global, _, _, _ = get_global_market_trend()
                except:
                    m_trend_global="NEUTRAL"
                for sym, data in sorted_states:
                    if len(active) >= GE_MAX_POS: break
                    if sym in active_syms: continue
                    zona=data.get("zona",0)
                    best_var=data.get("best_var","W")
                    rdy=data.get("rdy",0)
                    rr=data.get("rr",0)
                    regime=data.get("regime","SIDEWAYS")
                    trend=data.get("trend",0)
                    # V111: ENTRY HANYA KALAU SINYAL ROC-20H+RSI14 AKTIF — edge teruji data asli
                    # (ROC 80x15m=±20 jam + RSI14; V129d1 rename dari salah-label "trend 1H"):
                    # roc20h>+1% RSI>52 -> LONG, roc20h<-2% RSI<46 -> SHORT (konstanta SIG_*_ROC20H)
                    # tanpa sinyal = tidak entry (dulu entry pakai arah trend 15m yang 47.7% = koin toss)
                    sig=data.get("sig","")
                    if sig not in ("Buy","Sell"): continue
                    # V113 COOLDOWN 2 jam per coin — cegah churn re-entry habis closed (kasus LTC 69.67)
                    if time.time()-last_entry_time.get(sym,0) < COOLDOWN_SEC:
                        continue
                    if zona < 4.0: continue  # zona gate teruji (edge zona>=4.0)
                    if zona < GE_ZONA: continue
                    if rr < 1.5: continue
                    if rdy < 45: continue
                    side=sig  # LONG/SHORT murni dari sinyal HTF per coin — bear market otomatis SHORT
                    if side=="Sell":
                        # V111: SHORT hanya kalau BTC ROC-20H juga turun (alignmen market — teruji EV lebih baik)
                        btc_htf=states.get("BTCUSDT",{}).get("htf",0.0)
                        if btc_htf>=0:
                            add_filter_log(f"SKIP SHORT {sym} htf{data.get('htf',0):+.1f} tapi BTC htf{btc_htf:+.1f} belum turun [{GE_R1}]")
                            continue
                    # V115 REZIM-GATE + CRASH-GUARD:
                    #  LONG hanya saat BTC BULL bulanan (ROC30d>+5%) DAN BTC tidak sedang crash cepat
                    #  SHORT hanya di luar BULL (gate BTC htf<0 lama tetap)
                    if REGIME_ENABLED:
                        roc30,roc7=get_btc_regime()
                        btc20h=states.get("BTCUSDT",{}).get("htf",0.0)
                        crash = CRASH_GUARD_ENABLED and (btc20h<CRASH_BTC20H_MIN or roc7<CRASH_BTC7D_MIN)
                        if side=="Buy" and roc30<=REGIME_ROC30_LONG_MIN:
                            add_filter_log(f"SKIP LONG {sym} SIG-BUY z{zona:.1f} tapi REZIM BTC30D {roc30:+.1f}% <= +{REGIME_ROC30_LONG_MIN:.0f}% bukan-BULL [V115 gate]")
                            continue
                        if side=="Buy" and crash:
                            add_filter_log(f"SKIP LONG {sym} CRASH-GUARD BTC20h{btc20h:+.1f}% 7d{roc7:+.1f}% — market jatuh keras, no new long [V115]")
                            continue
                        if side=="Sell" and roc30 > -REGIME_ROC30_LONG_MIN:
                            add_filter_log(f"SKIP SHORT {sym} REZIM BTC30D {roc30:+.1f}% bukan-BEAR — short hanya di BEAR [R19 gate]")
                            continue
                    # cek reason ada OK
                    reason=data.get("reason","")
                    # entry
                    atr=data.get("atr",500)
                    price=data.get("px",0) or 0
                    if atr<=0 or atr>5000: atr=price*0.02 if price>0 else 0
                    if price<=0 or atr<=0:
                        add_filter_log(f"ENTRY SKIP {sym} NO-PX fail-closed [{GE_R1}]")
                        continue
                    if POS_STATUS!="OK":
                        add_filter_log(f"ENTRY SKIP {sym} POS-API {POS_STATUS} fail-closed [{GE_R1}]")
                        continue
                    if REGIME_STATUS!="OK":
                        add_filter_log(f"ENTRY SKIP {sym} REGIME-STALE fail-closed [{GE_R1}]")
                        continue
                    if KLINE_SRC.get((sym,"15"),"bybit")!="bybit":
                        add_filter_log(f"ENTRY SKIP {sym} NO-BYBIT-15M-DATA fail-closed [{GE_R1}]")
                        continue
                    sl_dist = min(atr*SL_ATR_MULT, price*SL_PCT_MAX); sl_dist = max(sl_dist, price*SL_PCT_MIN)
                    if side=="Buy":
                        sl_price = price - sl_dist - atr*ANTI_HUNT_ATR - atr*FINAL_BUFFER_ATR
                        if sl_price >= price: sl_price = price * 0.98
                    else:
                        sl_price = price + sl_dist + atr*ANTI_HUNT_ATR + atr*FINAL_BUFFER_ATR
                        if sl_price <= price: sl_price = price * 1.02
                    rr_val=data.get("rr",2.2)
                    tp_dist, rr_kotor, _, _, _ = calc_fee_aware_tp(sl_dist, rr_val, 25, price)
                    tp_price = price + tp_dist if side=="Buy" else price - tp_dist
                    lev, kelas, _ = smart_leverage_safe(sym, price, sl_price, atr, side)
                    add_log(f"TRY ENTRY {sym} z{zona:.1f} {best_var} RR{rr_val:.1f} RDY{rdy} {reason[:50]} [{GE_R1}]")
                    add_filter_log(f"TRY ENTRY {sym} z{zona:.1f} {best_var} RR{rr_val:.1f} RDY{rdy} S{data.get('zona',0)*1.5+rdy*0.1:.0f} {reason} [{GE_R1}]")
                    ok,msg,tp1,tp2,tp3,lev_r=place_order_smart(sym, side, "0.002")
                    if ok:
                        last_entry_time[sym]=time.time()  # V113 mulai cooldown coin ini
                        add_log(f"{msg} OK {AK_TYPE} DEMO=REAL [{GE_R1}] TP LADDER 50/30/20 (EXITFIX)")
                        add_filter_log(f"ENTRY OK {sym} z{zona:.1f} {best_var} RR{rr_kotor:.1f} lev{lev_r}x [{GE_R1}]")
                        # update active list
                        _na=get_real_positions()
                        if _na is not None:
                            active=_na
                            active_syms=set(p.get("symbol","") for p in active)
                        time.sleep(2)
                    else:
                        add_filter_log(f"ENTRY FAIL {sym} {msg} [{GE_R1}]")
                    # jangan spam semua sekaligus — entry 1 per cycle
                    if ok:
                        break
            for f in check_and_fix_sl(): add_log(f)
            for f in manage_trailing_live(): add_log(f)
        except Exception as e:
            add_log(f"force fail {str(e)[:80]}")
        _reconcile_state()
        _dump_state()  # V128: ingatan disegarkan tiap siklus
        add_log(f"HB {int(time.time())} force-loop hidup")
        time.sleep(LOOP_FORCE)

def _reconcile_state():
    try:
        live = get_real_positions()
        if live is None or POS_STATUS != "OK": return
        syms = set(p.get("symbol","") for p in live)
        with trailing_lock:
            for k in list(open_trades_info):
                if k not in syms: del open_trades_info[k]
            for p in live:
                k = p.get("symbol","")
                if k and k not in open_trades_info:
                    open_trades_info[k] = {"var": states.get(k,{}).get("best_var","W"), "rr": 2.5,
                        "zona": 0, "side": p.get("side","Buy"), "entry_time": time.time(),
                        "entry_price": float(p.get("avgPrice",0) or 0), "reason": "RECONCILE-OPS"}
    except Exception:
        pass

_n_state=_load_state()
add_log("V128p1-OPS: timeout10s + reconcile-exchange + microtick-guard + heartbeat + none-fix")
add_log("V128p2-OPS: fail-closed NO-QUOTE/NO-PX/POS-API/REGIME-STALE + reconcile side-aware + TP-orders transparency")
add_log("V128p3-OPS: None-semantics + balance fail-closed(global-fix) + metadata API-first+tickSize + slip px-aware + side-aware + mark-first + persist-trail + order-guards + bybit-only entry")
add_log("V128p3.2-OPS: KLINE_SRC tuple-key + regime bybit-strict + close retCode-checked + risk_dist tersimpan + TP-retry + tiada auto-REAL + avail-0 jujur")
add_log("V128p3.3-OPS: ROC30 CLOSE-based + saklar 3-state (long@BULL, short@BEAR, FLAT@CHOP) = selaras sertifikat lab+R19")
add_log("V129d1-DRAFT: closed-bar signal (candle forming dibuang) + rename ROC-20H (dulu salah label 'trend 1H') + balance field fail-closed")
add_log("V129d2-DRAFT: EXITFIX ladder 50/30/20 dari ukuran AKTUAL (TP tidak lagi attached) + orderLinkId idempoten + registry bot-vs-manual + cleanup posisi nol + risk_dist di ledger + liq API display + label ATR-range — MASIH DRAFT, JANGAN SWAP")
add_log(f"V128 MEMORY: state warisan dimuat: {_n_state} simbol")
threading.Thread(target=force_loop,daemon=True,name="V96-FORCE").start()

def main():
    global last_api_fetch_time, cached_positions, cached_perf, ui_running, closed_pnl_cache, cached_futures_balance, since_v114_cache
    refresh_akun_state()
    add_log(f"{AK_STATUS} V125 GOLD35 {GE_R1} {AK_TYPE} {AK_BASE} R1:{GE_R1} ZONA{GE_ZONA} FEE{FEE_R}R FUND{FUNDING_R}R")
    add_filter_log(f"START V125 GOLD35 REZIM-BANNER — R1:{GE_R1} ZONA>={GE_ZONA} {AK_TYPE} — banner rezim berkedip = saklar induk arah entry; LONG hanya BTC30D>+{REGIME_ROC30_LONG_MIN:.0f}% & tidak crash; SHORT hanya non-BULL")
    for sym in symbols:
        zona,rdy,fuel,atr,price,regime,best_var,ai,rr,trend,reason,sig,htf,rsi=calc_real_full_with_filter_log(sym)
        states[sym]={"zona":zona,"rdy":rdy,"fuel":fuel,"atr":atr,"px":price,"regime":regime,"best_var":best_var,"ai":ai,"rr":rr,"trend":trend,"reason":reason,"sig":sig,"htf":htf,"rsi":rsi}
    threading.Thread(target=ui_render_loop, daemon=True, name="V96-UI").start()
    scan_idx=0
    while True:
        try:
            last_api_fetch_time = time.time()
            # V98 FIX: scan 30 coin rotasi 6 per cycle biar ARB dll ke-scan, bukan cuma 4 pertama
            batch = symbols[scan_idx:scan_idx+6]
            if len(batch)<6:
                batch = batch + symbols[:6-len(batch)]
            for sym in batch:
                zona,rdy,fuel,atr,price,regime,best_var,ai,rr,trend,reason,sig,htf,rsi=calc_real_full_with_filter_log(sym)
                states[sym]={"zona":zona,"rdy":rdy,"fuel":fuel,"atr":atr,"px":price,"regime":regime,"best_var":best_var,"ai":ai,"rr":rr,"trend":trend,"reason":reason,"sig":sig,"htf":htf,"rsi":rsi}
            scan_idx = (scan_idx+6) % len(symbols)
            real_pos = get_real_positions()
            perf = get_real_performance()
            closed_detailed = get_closed_pnl_detailed()
            # V123: akumulasi closed SEJAK V114 start (fetch 100 terakhir, filter createdTime)
            try:
                from pybit.unified_trading import HTTP as _H
                _sess=_H(testnet=False,demo=AK_IS_DEMO,api_key=AK_API_KEY,api_secret=AK_API_SECRET)
                _resp=_sess.get_closed_pnl(category="linear", limit=100)
                _n=0; _pnl=0.0; _w=0
                if _resp.get("retCode")==0:
                    for _it in _resp["result"]["list"]:
                        try:
                            _ct=int(_it.get("createdTime","0") or 0)
                            if _ct>=V114_START_MS:
                                _n+=1; _v=float(_it.get("closedPnl","0") or 0); _pnl+=_v
                                if _v>0: _w+=1
                        except: continue
                ledger_note(_resp["result"]["list"])
                since_v114_cache={"n":_n,"pnl":_pnl,"w":_w}
            except: pass
            fut_bal = get_futures_balance()
            if real_pos is not None:
                with cached_positions_lock:
                    cached_positions = real_pos
                    cached_perf = perf
            with closed_pnl_lock:
                closed_pnl_cache = closed_detailed
            if fut_bal is not None:
                with cached_futures_lock:
                    cached_futures_balance = fut_bal
            time.sleep(LOOP_API)
        except KeyboardInterrupt:
            ui_running=False
            break
        except Exception as e:
            add_log(f"main fail {str(e)[:50]}")
            time.sleep(5)

if __name__=="__main__":
    main()
