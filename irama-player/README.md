# Irama Nusantara CLI Streamer & Downloader

Alat bantu CLI untuk memutar dan mengunduh arsip musik Indonesia dari [Irama Nusantara](https://www.iramanusantara.org/) menggunakan arsitektur orkestrasi `mpv` dan `yt-dlp`.

## 📦 Prasyarat Sistem

1. **Python 3.8+**
2. **mpv** (untuk streaming langsung di terminal)
   - Ubuntu/Debian: `sudo apt install mpv`
   - macOS: `brew install mpv`
   - Windows: `winget install mpv.net`
3. **yt-dlp** & **ffmpeg** (untuk kebutuhan download dan konversi ID3)
   - `pip install yt-dlp`
   - `sudo apt install ffmpeg` / `brew install ffmpeg`

## 🚀 Instalasi & Persiapan

```bash
cd irama-player
pip install -r requirements.txt
pip install -e .
```

## 🎧 Penggunaan

```bash
# 1. Cari album berdasarkan judul (interaktif pilih album untuk diputar/diunduh)
irama-player search "koes plus"

# 2. Jalankan interaktif dengan memasukkan Album ID langsung (contoh: 7073)
irama-player 7073

# 3. Putar langsung seluruh album secara berurutan
irama-player 7073 --play-all

# 4. Putar satu lagu tertentu berdasarkan nomor urut (contoh: lagu ke-2)
irama-player 7073 --track 2

# 5. Unduh seluruh lagu di dalam album
irama-player 7073 --download-all --output-dir ./musik

# 6. Jika terkena proteksi Cloudflare Turnstile / WAF
irama-player 7073 --cookie "session=...; cf_clearance=..."

# 7. Manajemen Cache Lokal (SQLite)
# Membuka album dengan memaksa pembaruan data dari API (refresh cache)
irama-player 7073 --refresh-cache
# Menonaktifkan penggunaan cache
irama-player 7073 --no-cache
```

## 🧪 Menjalankan Pengujian

```bash
python3 -m unittest discover tests
```
