# AGENT HANDOVER SPECIFICATION: IRAMA NUSANTARA CLI

Dokumen ini ditujukan sebagai panduan teknis bagi coding agent/developer untuk melanjutkan, mengembangkan, dan memelihara proyek **Irama Nusantara CLI Streamer & Downloader**.

---

## 1. Project Context & Philosophy

Tujuan proyek ini adalah menyediakan interface terminal yang cepat, andal, dan *lightweight* untuk mengeksplorasi arsip musik Irama Nusantara tanpa harus membuka browser berat.

### Filosofi Arsitektur: *Hybrid Orchestrator (Unix Way)*
Alih-alih menulis audio engine dan parser HLS sendiri dari nol (*reinventing the wheel*), proyek ini menerapkan prinsip pemisahan tanggung jawab (*Separation of Concerns*):
* **Python**: Bertanggung jawab atas *Reverse Engineering API*, autentikasi, ekstraksi metadata, validasi skema data Strapi, dan menyajikan UX CLI.
* **MPV**: Bertindak sebagai *Playback Engine*. Menangani jitter buffer streaming HLS, seeking, volume, dan terminal On-Screen Display (OSD).
* **YT-DLP & FFmpeg**: Bertindak sebagai *Ingestion Engine*. Menangani penarikan chunk `.ts`/`.aac`, remuxing, penulisan tag ID3 metadata, dan cover art embedding.

---

## 2. Struktur Repository

```text
irama-player/
├── AGENT.md                 <-- (Dokumen ini) Spesifikasi & panduan agen
├── README.md                <-- Dokumentasi umum pengguna
├── requirements.txt         <-- Dependensi Python minimal (requests)
├── setup.py                 <-- Setup packaging & binary entrypoint (irama-player)
├── irama/                   <-- Source code utama paket
│   ├── __init__.py          <-- Expose model & client utama
│   ├── config.py            <-- Konstanta, timeout, user-agent, base URL
│   ├── models.py            <-- Dataclass Album & Track, formatting vinyl
│   ├── client.py            <-- HTTP Engine, bypass header, Strapi v3/v4 parser
│   ├── player.py            <-- MPV orchestrator & generator playlist M3U on-the-fly
│   ├── downloader.py        <-- YT-DLP orchestrator & tagging ID3
│   └── cli.py               <-- Entrypoint CLI (argparse & interactive menu)
└── tests/                   <-- Unit & integration tests
    ├── __init__.py
    ├── test_models.py       <-- Validasi formatting nomor trek & sanitasi file
    └── test_client.py       <-- Validasi kompatibilitas payload Strapi v3/v4
```

---

## 3. Reverse Engineering Notes & API Contracts

### A. Endpoint Target
* **Album Detail**: `GET https://core.iramanusantara.org/api/records/{album_id}`
* **Web Referer**: `https://www.iramanusantara.org/`

### B. Karakteristik Server & Jaringan
1. **TTFB Lambat (~9 Detik)**:
   * Backend Strapi Irama Nusantara memiliki respons time awal yang tinggi.
   * `REQUEST_TIMEOUT` diatur ke `(10, 30)` (10 detik koneksi, 30 detik pembacaan data). **Jangan pernah menurunkan timeout di bawah 20 detik.**
2. **Anti-Bot & Hotlink Protection**:
   * Header `Referer: https://www.iramanusantara.org/` dan `User-Agent` modern **wajib** dikirim pada setiap request ke API maupun saat streaming audio.
   * Tanpa header ini, CDN media akan mengembalikan `403 Forbidden`.
3. **Cloudflare WAF / Turnstile**:
   * Jika WAF memicu interstitial challenge, `client.py` mendeteksi respons 403/503 dan memandu pengguna menyematkan cookie sesi dari browser (`--cookie`).

### C. Normalisasi Data & Format Audio
1. **Piringan Hitam (Vinyl Track Numbers)**:
   * Trek sering bernomor `"A1"`, `"A2"`, `"B1"` (bukan integer).
   * **Aturan**: Jangan gunakan `int(track_number)`. Selalu gunakan `format_track_number()` dari `models.py`.
2. **Format URL Audio**:
   * URL bisa berupa HLS Playlist (`.m3u8`) atau file statis `.mp3`.
   * Jika URL berupa path relatif (`/uploads/...`), skrip harus menyematkan prefix `https://core.iramanusantara.org`.
3. **Kompatibilitas Strapi v3 vs v4**:
   * `_parse_album_json()` di `client.py` memiliki *dual-parsing logic* yang mampu membaca payload berformat Strapi v4 (`data.attributes...`) maupun Strapi v3 (`root object`).

---

## 4. External Tool Contracts

### MPV Execution Contract
* Pemutaran multi-lagu menggunakan **M3U on-the-fly**:
  Skrip membuat file temporary `.m3u` dengan tag `#EXTINF:-1,Artist - Title`. Hal ini krusial agar MPV menampilkan judul lagu yang berganti secara otomatis di OSD saat user menekan `>` (next) atau `<` (prev).
* Header HTTP disuntikkan via:
  ```bash
  mpv --http-header-fields="Referer: https://www.iramanusantara.org/\r\nUser-Agent: ..." --playlist=/tmp/...
  ```

### YT-DLP Execution Contract
* Perintah baku download satu trek:
  ```bash
  yt-dlp \
    --add-header "Referer: https://www.iramanusantara.org/" \
    --add-header "User-Agent: ..." \
    --extract-audio --audio-format mp3 --audio-quality 0 \
    --embed-metadata \
    --parse-metadata "<ARTIST>:%(meta_artist)s" \
    --parse-metadata "<ALBUM>:%(meta_album)s" \
    -o "<OUTPUT_DIR>/<TRACK_NO>. %(title)s.%(ext)s" \
    "<STREAM_URL>"
  ```

---

## 5. Development Roadmap & Task Backlog untuk Agen Selanjutnya

Jika Anda ditugaskan mengembangkan proyek ini lebih lanjut, berikut adalah backlog fitur yang diprioritaskan:

### 🟡 Prioritas 1: Search Endpoint Integration
* Tambahkan fungsi pencarian album di `client.py` via Strapi query filter:
  `GET https://core.iramanusantara.org/api/records?filters[title][$containsi]={query}&populate=*`
* Tambahkan sub-command CLI: `irama-player search "koes plus"`.

### 🟡 Prioritas 2: IPC Socket Control untuk MPV
* Implementasikan kontrol dua arah dengan MPV via JSON IPC socket (`--input-ipc-server=/tmp/mpv-socket`).
* Memungkinkan skrip Python menampilkan progress bar durasi lagu real-time di terminal.

### 🟢 Prioritas 3: Terminal UI (TUI) Menggunakan Textual / Rich
* Tingkatkan tampilan CLI menggunakan library `rich` (untuk tabel metadata berwarna) atau `textual` untuk antarmuka TUI interaktif ala Spotify-TUI.

### 🟢 Prioritas 4: Local Cache Layer
* Simpan metadata album yang pernah di-fetch ke SQLite lokal (`~/.cache/irama/metadata.db`) untuk menghindari request berulang ke API Strapi yang TTFB-nya lambat.
