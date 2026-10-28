# Threads MBG 2027: collection and preprocessing

Proyek Analitika Media Sosial UI ini mengumpulkan post dan reply Threads tentang anggaran Makan Bergizi Gratis (MBG) 2027, diterbitkan **3–30 September 2026 WIB**. RQ1 membahas sentimen, RQ2 tema, dan RQ3 hubungan keduanya. Repo ini menyiapkan data; IndoBERTweet belum dilatih/dijalankan.

## Alur singkat

1. **Koleksi**: `scraper.py` (Selenium + Chrome login) mencari 12 kueri di `keywords.txt`, meng-crawl reply, lalu menulis `output/threads_raw.csv` (17 kolom) dan `output/threads_dataset.csv` (6 kolom). Panduan langkah demi langkah ada di **[docs/collection_pipeline.md](docs/collection_pipeline.md)**.
2. **Pembekuan**: ekspor disalin ke `data/raw/` dan hash-nya dicatat di `metadata/`.
3. **Preprocessing**: `preprocessing/preprocess_v2.py` menambah flag dan teks model, lalu menulis satu dataset final untuk IndoBERTweet (`data/processed/`). `preprocess_v1.py` adalah iterasi sebelumnya.

Data (teks, permalink, anotasi) bersifat privat dan **tidak** ada di repo publik; yang dipublikasikan hanya kode, dokumentasi, dan ringkasan agregat.

## Input privat

`data/raw/threads_units_2026-09_v1.csv` adalah ekspor beku 9.368 unit dengan 17 kolom, SHA-256 `95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df`. Ini ekspor terstruktur, bukan observasi JSONL paling awal. Nama file di spesifikasi memiliki prefiks angka yang tidak ada pada file lokal; konstanta di [preprocessing/](preprocessing/) memakai nama lokal. `data/raw/threads_team_export_2026-09_v1.csv` adalah proyeksi enam kolom untuk tim, bukan input preprocessing. Data diperoleh melalui handoff privat.

## Menjalankan preprocessing (Windows)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python preprocessing\preprocess_v2.py
```

Pipeline tidak mengunduh model maupun melatih apa pun. Alurnya `data/raw` → `data/interim` → `data/processed`; masalah kualitas (bot, kampanye, akun repetitif, teks identik, teks kosong) hanya diberi flag sehingga analisis dapat dijalankan dengan (`in_all`) dan tanpa (`in_clean`) data tersebut. Teks model mengikuti format IndoBERTweet (`@USER`, `HTTPURL`, emoji jadi teks, negasi dipertahankan). Detail, iterasi v1 → v2, dan jejak reproduksi: [protokol preprocessing](docs/preprocessing_protocol.md) dan [reproduksibilitas](docs/reproducibility.md).

| Keluaran privat | Isi |
|---|---|
| `data/interim/threads_2026-09_pp1_*.csv`, `pp2_flagged.csv` | Hasil antara tiap iterasi (semua unit + flag). |
| `data/processed/threads_2026-09_pp2_final.csv` | **Satu** dataset final: 8.759 unit `in_all`, kolom `text_model`, `context_model`, flag, `in_clean`. |
| `reports/*_pp2.csv` | Funnel, ringkasan flag, 81 teks kosong untuk dicek manual. |
| `metadata/preprocessing_manifest_pp2.json` | Hash, parameter, versi library, commit git (tanpa teks). |

Run saat ini: **9.368 unit**, **8.759 `in_all`**, **6.762 `in_clean`**; 818 balasan dari satu akun otomatis, 1.354 unit kampanye (1.205 pada 30 September), 100 unit dari satu akun repetitif, 507 salinan teks identik dibuang. Flag bersifat sementara, bukan bukti identitas atau koordinasi.

## Keputusan terbuka

Akun `80ac16d6…` diberi flag sebagai bot Meta AI karena 818 balasannya; identitasnya sudah dicek pada 3 permalink publik (halaman bernama Meta AI, @meta.ai); 114 dari 120 induk reply yang terkumpul men-tag @meta.ai dan jawaban muncul median 26 detik kemudian. 81 teks kosong sudah diperiksa pada halaman publik dan seluruhnya berisi media tanpa caption (satu halaman tidak tersedia), sehingga dikeluarkan. Berikutnya: melabeli sampel sentimen, lalu split per `thread_root_id` dan melatih IndoBERTweet.

## Scraper

`scraper.py` adalah pintu masuk kompatibel ke `collection/scraper.py`. Untuk melanjutkan run akun A, pemilik repo harus memiliki salt asli dalam `config_local.py`, `state/`, dan `output/` dari handoff privat serta memeriksa fingerprint `6888537f`:

```powershell
.venv\Scripts\python scraper.py --profile account_a --keywords keywords.txt --resume
```

Login manual di Chrome. Jika exit code 2, baca log dan tunggu beberapa jam sebelum resume; jangan bypass challenge atau mengurangi jeda. Checkpoint/log final tidak ada di checkout ini, sehingga kelengkapan semua pencarian belum dapat dibuktikan. Lihat [pipeline koleksi](docs/collection_pipeline.md), [kualitas](docs/data_quality.md), [reproduksibilitas](docs/reproducibility.md), dan [bukti TK2](docs/tk2_evidence.md).

Data, laporan berisi teks, anotasi, profil, salt, log, dan output scraping tidak boleh di-commit. Riwayat Git lama mungkin masih memuat teks; lihat [etika](docs/ethics_and_limitations.md).
