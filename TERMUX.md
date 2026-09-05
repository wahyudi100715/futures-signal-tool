# Panduan Termux + GitHub (Android)

Ikuti urut dari atas. Jangan loncat langkah.

## 0) Persiapan HP

1. Install **Termux** dari F-Droid (disarankan) atau Play Store versi resmi Termux.
   Jangan pakai aplikasi "Termux" abal yang beda developer.
2. Buka Termux.
3. Kalau muncul izin storage, boleh skip dulu. Tool ini tidak butuh folder Download.

Ketik perintah di bawah **satu blok per langkah**. Setelah enter, tunggu sampai muncul `$` lagi.

## 1) Update Termux + install Python & Git

```bash
pkg update -y && pkg upgrade -y
pkg install -y python git
python --version
git --version
```

Kalau ditanya `Do you want to continue?` ketik `y` lalu enter.

## 2) Clone repo dari GitHub

```bash
cd ~
git clone https://github.com/wahyudi100715/futures-signal-tool.git
cd futures-signal-tool
ls
```

Harus kelihatan file `signal_tool.py`, `config.json`, `requirements.txt`.

## 3) Install library Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Di HP ini bisa 2–5 menit. Jangan tutup Termux.

Kalau error memory, coba:

```bash
pip install requests pandas numpy
```

## 4) Tes jalanin tool

```bash
python signal_tool.py
```

Kalau sukses, muncul scan BTC/ETH/SOL/dst plus LONG, SHORT, atau WAIT.

## 5) Ubah pair tanpa edit kode

Buka file config:

```bash
nano config.json
```

Contoh isi:

```json
{
  "pairs": [
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
    "SOL-USDT-SWAP"
  ],
  "ltf": "15m",
  "htf": "4H",
  "min_score": 55,
  "json": "last_scan.json"
}
```

Di nano:
- geser kursor, edit teks
- simpan: `CTRL + O`, enter
- keluar: `CTRL + X`

Lalu jalankan lagi:

```bash
python signal_tool.py
```

`min_score: 55` artinya yang skor rendah tidak ditampilkan detailnya.

## 6) Scan berulang tiap 15 menit

```bash
chmod +x run.sh watch.sh
./watch.sh
```

Berhenti: `CTRL + C`.

Interval custom (contoh 5 menit = 300 detik):

```bash
./watch.sh 300
```

HP jangan di-kill Termux-nya. Di Android, buka pengaturan baterai → Termux → **Unrestricted** / jangan dioptimasi.

## 7) Update tool kalau ada perubahan di GitHub

```bash
cd ~/futures-signal-tool
git pull
```

Kalau kamu sudah edit `config.json` dan `git pull` ribet, simpan dulu:

```bash
cp config.json config.local.json
git checkout -- config.json
git pull
```

Lalu salin pair kamu kembali ke `config.json`.

## 8) Kalau repo private (opsional)

Repo ini dibuat public biar clone mudah.
Kalau suatu saat kamu ubah jadi private, di Termux perlu login:

```bash
pkg install -y gh
gh auth login
```

Pilih GitHub.com → HTTPS → login via browser. Setelah itu `git clone` pakai URL repo-mu.

## Error umum

**`pkg: command not found`**
Bukan Termux. Install Termux yang benar.

**`Unable to locate package python`**
Jalankan `pkg update -y` dulu.

**`No module named pandas`**
Belum `pip install -r requirements.txt`.

**`OKX error` / timeout**
Internet HP bermasalah, atau OKX diblok. Coba WiFi lain / data seluler.

**Termux tertutup sendiri**
Baterai Android mematikan app. Set Termux unrestricted.

**Layar penuh warna aneh**
Normal. LONG hijau, SHORT merah, WAIT kuning.

## Belum ada di tool ini

- Auto order ke Binance/Bybit
- Notifikasi Telegram

Itu langkah berikutnya, setelah tool ini jalan lancar di HP.
