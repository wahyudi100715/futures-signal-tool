#!/usr/bin/env python3
"""
Futures Signal Scanner — educational confluence tool.

Mengambil data publik OKX SWAP (tanpa API key), menghitung indikator,
lalu memberi skor LONG / SHORT / WAIT berdasarkan confluence multi-timeframe.

INI BUKAN SARAN INVESTASI.
Sinyal tidak menjamin profit. Futures + leverage = risiko kerugian besar.
Backtest dulu, paper trade dulu, jangan all-in.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

import numpy as np
import pandas as pd
import requests

OKX_BASE = "https://www.okx.com"
DEFAULT_PAIRS = [
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP",
    "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP",
    "BNB-USDT-SWAP",
]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def okx_get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{OKX_BASE}{path}"
    r = requests.get(url, params=params or {}, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if str(payload.get("code")) != "0":
        raise RuntimeError(f"OKX error {payload.get('code')}: {payload.get('msg')}")
    return payload.get("data", [])


def fetch_candles(inst_id: str, bar: str, limit: int = 200) -> pd.DataFrame:
    raw = okx_get(
        "/api/v5/market/candles",
        {"instId": inst_id, "bar": bar, "limit": str(limit)},
    )
    if not raw:
        return pd.DataFrame()
    # OKX: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    cols = ["ts", "open", "high", "low", "close", "volume", "vol_ccy", "vol_quote", "confirm"]
    df = pd.DataFrame(raw, columns=cols)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def fetch_funding(inst_id: str) -> float | None:
    try:
        data = okx_get("/api/v5/public/funding-rate", {"instId": inst_id})
        if data:
            return float(data[0]["fundingRate"])
    except Exception:
        return None
    return None


def fetch_oi_usd(inst_id: str) -> float | None:
    try:
        data = okx_get("/api/v5/public/open-interest", {"instId": inst_id})
        if data:
            return float(data[0].get("oiUsd") or data[0].get("oiCcy") or 0)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema21"] = ema(out["close"], 21)
    out["ema50"] = ema(out["close"], 50)
    out["ema200"] = ema(out["close"], 200) if len(out) >= 200 else ema(out["close"], min(200, max(20, len(out) // 2)))
    out["rsi"] = rsi(out["close"], 14)
    out["macd"], out["macd_sig"], out["macd_hist"] = macd(out["close"])
    out["atr"] = atr(out, 14)
    out["vol_sma"] = out["volume"].rolling(20).mean()
    out["vol_ratio"] = out["volume"] / out["vol_sma"]
    mid = ema(out["close"], 20)
    std = out["close"].rolling(20).std()
    out["bb_mid"] = mid
    out["bb_up"] = mid + 2 * std
    out["bb_dn"] = mid - 2 * std
    out["bb_width"] = (out["bb_up"] - out["bb_dn"]) / mid
    return out


# ---------------------------------------------------------------------------
# Signal engine
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    symbol: str
    timeframe: str
    bias_htf: str
    signal: str
    score: int
    price: float
    sl: float | None
    tp1: float | None
    tp2: float | None
    rr: float | None
    rsi: float | None
    funding_pct: float | None
    reasons: list[str]
    warnings: list[str]
    ts: str


def htf_bias(df: pd.DataFrame) -> tuple[str, list[str]]:
    last = df.iloc[-1]
    reasons = []
    score_up = 0
    score_dn = 0

    if last["close"] > last["ema50"]:
        score_up += 1
        reasons.append("HTF: harga di atas EMA50")
    else:
        score_dn += 1
        reasons.append("HTF: harga di bawah EMA50")

    if last["ema21"] > last["ema50"]:
        score_up += 1
        reasons.append("HTF: EMA21 > EMA50 (bull stack)")
    else:
        score_dn += 1
        reasons.append("HTF: EMA21 < EMA50 (bear stack)")

    if last["macd_hist"] > 0:
        score_up += 1
        reasons.append("HTF: MACD histogram positif")
    else:
        score_dn += 1
        reasons.append("HTF: MACD histogram negatif")

    if score_up >= 2 and score_up > score_dn:
        return "BULL", reasons
    if score_dn >= 2 and score_dn > score_up:
        return "BEAR", reasons
    return "NEUTRAL", reasons


def score_setup(ltf: pd.DataFrame, bias: str) -> tuple[str, int, list[str], list[str]]:
    last = ltf.iloc[-1]
    prev = ltf.iloc[-2]
    reasons: list[str] = []
    warnings: list[str] = []
    long_pts = 0
    short_pts = 0

    # Trend alignment (max 25)
    if last["close"] > last["ema21"] > last["ema50"]:
        long_pts += 25
        reasons.append("LTF: close > EMA21 > EMA50")
    elif last["close"] < last["ema21"] < last["ema50"]:
        short_pts += 25
        reasons.append("LTF: close < EMA21 < EMA50")
    elif last["close"] > last["ema21"]:
        long_pts += 10
        reasons.append("LTF: close di atas EMA21 (lemah)")
    elif last["close"] < last["ema21"]:
        short_pts += 10
        reasons.append("LTF: close di bawah EMA21 (lemah)")

    # RSI (max 20) — prefer pullback continuation, punish extremes against us
    rsi_v = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
    if 40 <= rsi_v <= 60:
        long_pts += 10
        short_pts += 10
        reasons.append(f"RSI netral ({rsi_v:.1f}) — ruang gerak masih ada")
    elif 30 <= rsi_v < 45:
        long_pts += 20
        reasons.append(f"RSI pullback bullish zone ({rsi_v:.1f})")
        short_pts += 5
    elif 55 < rsi_v <= 70:
        short_pts += 20
        reasons.append(f"RSI pullback bearish zone ({rsi_v:.1f})")
        long_pts += 5
    elif rsi_v < 30:
        long_pts += 12
        warnings.append(f"RSI oversold ({rsi_v:.1f}) — bisa bounce, tapi bisa lanjut jatuh")
    elif rsi_v > 70:
        short_pts += 12
        warnings.append(f"RSI overbought ({rsi_v:.1f}) — bisa retrace, tapi bisa lanjut naik")

    # MACD turn (max 20)
    if last["macd_hist"] > 0 and prev["macd_hist"] <= 0:
        long_pts += 20
        reasons.append("MACD histogram baru silang ke positif")
    elif last["macd_hist"] < 0 and prev["macd_hist"] >= 0:
        short_pts += 20
        reasons.append("MACD histogram baru silang ke negatif")
    elif last["macd_hist"] > prev["macd_hist"] and last["macd_hist"] > 0:
        long_pts += 12
        reasons.append("MACD histogram menguat di zona positif")
    elif last["macd_hist"] < prev["macd_hist"] and last["macd_hist"] < 0:
        short_pts += 12
        reasons.append("MACD histogram melemah di zona negatif")

    # Volume (max 15)
    vr = float(last["vol_ratio"]) if pd.notna(last["vol_ratio"]) else 1.0
    if vr >= 1.4:
        if last["close"] >= last["open"]:
            long_pts += 15
            reasons.append(f"Volume di atas rata-rata ({vr:.2f}x) + candle hijau")
        else:
            short_pts += 15
            reasons.append(f"Volume di atas rata-rata ({vr:.2f}x) + candle merah")
    elif vr >= 1.1:
        long_pts += 5
        short_pts += 5
        reasons.append(f"Volume sedikit di atas rata-rata ({vr:.2f}x)")
    else:
        warnings.append(f"Volume lemah ({vr:.2f}x) — sinyal kurang konfirmasi partisipasi")

    # Location vs BB (max 10)
    if pd.notna(last["bb_dn"]) and last["low"] <= last["bb_dn"]:
        long_pts += 10
        reasons.append("Harga menyentuh lower Bollinger")
    elif pd.notna(last["bb_up"]) and last["high"] >= last["bb_up"]:
        short_pts += 10
        reasons.append("Harga menyentuh upper Bollinger")

    # HTF filter
    if bias == "BULL":
        short_pts = int(short_pts * 0.35)
        long_pts += 10
        reasons.append("Filter HTF BULL — short dihukum")
    elif bias == "BEAR":
        long_pts = int(long_pts * 0.35)
        short_pts += 10
        reasons.append("Filter HTF BEAR — long dihukum")
    else:
        warnings.append("HTF netral — edge lebih kecil, mudah chop")

    if long_pts >= short_pts and long_pts >= 55:
        side = "LONG"
        score = min(100, long_pts)
    elif short_pts > long_pts and short_pts >= 55:
        side = "SHORT"
        score = min(100, short_pts)
    else:
        side = "WAIT"
        score = min(100, max(long_pts, short_pts))
        reasons.append("Skor confluence belum cukup untuk entry")

    return side, score, reasons, warnings


def levels(side: str, price: float, atr_v: float) -> tuple[float | None, float | None, float | None, float | None]:
    if atr_v <= 0 or side == "WAIT":
        return None, None, None, None
    risk = atr_v * 1.5
    if side == "LONG":
        sl = price - risk
        tp1 = price + risk * 1.5
        tp2 = price + risk * 2.5
    else:
        sl = price + risk
        tp1 = price - risk * 1.5
        tp2 = price - risk * 2.5
    return sl, tp1, tp2, 1.5


def analyze_symbol(inst_id: str, ltf_bar: str = "15m", htf_bar: str = "4H") -> Signal:
    ltf = add_indicators(fetch_candles(inst_id, ltf_bar, 200))
    htf = add_indicators(fetch_candles(inst_id, htf_bar, 200))
    if ltf.empty or htf.empty or len(ltf) < 30:
        raise RuntimeError(f"Data kurang untuk {inst_id}")

    bias, bias_reasons = htf_bias(htf)
    side, score, reasons, warnings = score_setup(ltf, bias)
    last = ltf.iloc[-1]
    price = float(last["close"])
    atr_v = float(last["atr"]) if pd.notna(last["atr"]) else 0.0
    sl, tp1, tp2, rr = levels(side, price, atr_v)
    funding = fetch_funding(inst_id)

    extra_warn = []
    if funding is not None:
        if funding > 0.0003 and side == "LONG":
            extra_warn.append(f"Funding positif tinggi ({funding*100:.4f}%/8h) — long bayar short, crowding risk")
        if funding < -0.0003 and side == "SHORT":
            extra_warn.append(f"Funding negatif dalam ({funding*100:.4f}%/8h) — short bayar long, crowding risk")

    return Signal(
        symbol=inst_id,
        timeframe=f"{ltf_bar} | HTF {htf_bar}",
        bias_htf=bias,
        signal=side,
        score=score,
        price=price,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        rr=rr,
        rsi=float(last["rsi"]) if pd.notna(last["rsi"]) else None,
        funding_pct=None if funding is None else funding * 100,
        reasons=bias_reasons + reasons,
        warnings=warnings + extra_warn,
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    )


def fmt_px(x: float | None) -> str:
    if x is None:
        return "-"
    if x >= 1000:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:,.4f}"
    return f"{x:.6f}"


def print_signal(s: Signal) -> None:
    color = {"LONG": "\033[92m", "SHORT": "\033[91m", "WAIT": "\033[93m"}.get(s.signal, "")
    reset = "\033[0m"
    print("=" * 72)
    print(f"{s.symbol}   HTF={s.bias_htf}   TF={s.timeframe}")
    print(f"{color}SIGNAL: {s.signal}   SCORE: {s.score}/100{reset}   price={fmt_px(s.price)}")
    print(f"SL={fmt_px(s.sl)}   TP1={fmt_px(s.tp1)}   TP2={fmt_px(s.tp2)}   R:R≈{s.rr or '-'}")
    if s.rsi is not None:
        print(f"RSI={s.rsi:.1f}   funding={s.funding_pct:.4f}%/8h" if s.funding_pct is not None else f"RSI={s.rsi:.1f}")
    print("Alasan:")
    for r in s.reasons:
        print(f"  • {r}")
    if s.warnings:
        print("Peringatan:")
        for w in s.warnings:
            print(f"  ! {w}")
    print()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Futures confluence signal scanner (OKX SWAP)")
    p.add_argument("--pairs", nargs="*", default=cfg.get("pairs", DEFAULT_PAIRS), help="Contoh: BTC-USDT-SWAP ETH-USDT-SWAP")
    p.add_argument("--ltf", default=str(cfg.get("ltf", "15m")), help="Timeframe entry: 5m, 15m, 1H")
    p.add_argument("--htf", default=str(cfg.get("htf", "4H")), help="Timeframe bias: 1H, 4H, 1D")
    p.add_argument("--min-score", type=int, default=int(cfg.get("min_score", 0)), help="Hanya tampilkan skor >= N")
    p.add_argument("--json", dest="json_out", default=str(cfg.get("json", "")), help="Simpan hasil ke file JSON")
    args = p.parse_args()

    print("Futures Signal Scanner (confluence, bukan prediksi ajaib)")
    print("Data: OKX public SWAP. Bukan financial advice.\n")

    results: list[Signal] = []
    for inst in args.pairs:
        try:
            sig = analyze_symbol(inst, args.ltf, args.htf)
            results.append(sig)
            if sig.score >= args.min_score:
                print_signal(sig)
        except Exception as e:
            print(f"[ERROR] {inst}: {e}", file=sys.stderr)

    actionable = [s for s in results if s.signal in ("LONG", "SHORT")]
    print("-" * 72)
    print(f"Scan {len(results)} pair | actionable {len(actionable)} | {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    print("Pakai SL selalu. Risk per trade 0.5–1% equity. Jangan market-order buta.")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump([asdict(s) for s in results], f, ensure_ascii=False, indent=2)
        print(f"JSON tersimpan: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
