# Futures Signal Tool

Scanner sinyal confluence untuk crypto futures (OKX SWAP).
Bisa dijalankan di **HP Android lewat Termux**. Tidak perlu API key.

Bukan saran investasi. Sinyal tidak menjamin profit.

## Termux (HP)

Panduan lengkap: [TERMUX.md](TERMUX.md)

Ringkas:

```bash
pkg update -y && pkg install -y python git
git clone https://github.com/wahyudi100715/futures-signal-tool.git
cd futures-signal-tool
pip install -r requirements.txt
python signal_tool.py
```

Ubah pair/timeframe di `config.json`, lalu jalankan lagi.

## Apa yang dihitung

| Lapisan | Fungsi |
|---|---|
| HTF (default 4H) | Bias tren: EMA21/50 + MACD |
| LTF (default 15m) | Timing: EMA, RSI, MACD, volume, Bollinger |
| Funding | Peringatan crowding |
| Risk | SL 1.5x ATR, TP1 1.5R, TP2 2.5R |

`LONG` / `SHORT` hanya jika skor cukup dan searah HTF. Kalau tidak: `WAIT`.

## TradingView

Paste `pine/futures_confluence.pine` ke Pine Editor.
