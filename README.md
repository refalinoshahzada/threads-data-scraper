# Threads MBG 2027: collection and preprocessing

Proyek Analitika Media Sosial UI ini mengumpulkan post dan reply Threads tentang anggaran Makan Bergizi Gratis (MBG) 2027, diterbitkan **3–30 September 2026 WIB**. RQ1 membahas sentimen, RQ2 tema, dan RQ3 hubungan keduanya. Repo ini menyiapkan data; IndoBERT dan BERTopic belum dilatih/dijalankan.

## Alur singkat

1. **Koleksi**: `scraper.py` (Selenium + Chrome login) mencari 12 kueri di `keywords.txt`, meng-crawl reply, lalu menulis `output/threads_raw.csv` (17 kolom) dan `output/threads_dataset.csv` (6 kolom). Panduan langkah demi langkah ada di **[docs/collection_pipeline.md](docs/collection_pipeline.md)**.
2. **Pembekuan**: ekspor disalin ke `data/raw/` dan hash-nya dicatat di `metadata/`.
3. **Preprocessing**: `preprocess.py` menambah flag dan teks turunan, lalu menulis subset utama untuk IndoBERT/BERTopic.

Data (teks, permalink, anotasi) bersifat privat dan **tidak** ada di repo publik; yang dipublikasikan hanya kode, dokumentasi, dan ringkasan agregat.

## Input privat

`data/raw/threads_units_2026-09_v1.csv` adalah ekspor beku 9.368 unit dengan 17 kolom, SHA-256 `95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df`. Ini ekspor terstruktur, bukan observasi JSONL paling awal. Nama file di spesifikasi memiliki prefiks angka yang tidak ada pada file lokal; konstanta di [preprocess.py](preprocess.py) memakai nama lokal. `data/raw/threads_team_export_2026-09_v1.csv` adalah proyeksi enam kolom untuk tim, bukan input preprocessing. Data diperoleh melalui handoff privat; lihat [data/README.md](data/README.md).

## Menjalankan preprocessing (Windows)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python preprocess.py
.venv\Scripts\python -m unittest discover -s tests
```

Pipeline tidak mengunduh model maupun menghitung token IndoBERT. Semua parameter ada sebagai konstanta di bagian atas [preprocess.py](preprocess.py); untuk mengganti input atau ambang, edit konstanta lalu jalankan lagi. `resources/slang_id.csv` dan `resources/stopwords_id.txt` adalah daftar kata yang digunakan.

Delapan langkah: muat dan validasi → bersihkan karakter → tandai duplikat → tandai kampanye/bot → relevansi dan konteks root → teks sentimen varian A/B → teks topik → split berdasarkan thread. **Tabel penuh mempertahankan semua unit dan `text_raw` persis dari sumber.** Lihat [protokol preprocessing](docs/preprocessing_protocol.md).

| Keluaran privat | Isi |
|---|---|
| `data/processed/threads_full.parquet` | Seluruh unit, kolom input, flag, dan teks turunan. `permalink` dan `text_raw` tetap privat di sini. |
| `data/processed/threads_main.csv` | Subset utama dengan 14 kolom inti model; tanpa `permalink` dan `text_raw`. |
| `data/processed/stopwords_topic.txt` | Stopword Indonesia + domain untuk vectorizer BERTopic; tidak dihapus dari `text_topic`. |
| `data/annotation/to_label.csv` | Sampel 1.200 unit dari split train/val/test, teks parent dan mention dimasking, kolom label kosong. |
| `reports/funnel.csv` | Penyusutan data pada setiap aturan sampai subset utama dan kelayakan topik. |
| `reports/relevance_check.csv` | Sampel pemeriksaan relevansi manual. |

Flag inti: `flag_text_missing`, `flag_out_of_window`, `flag_dup_same_author`, `flag_dup_cross_author`, `flag_campaign`, `flag_bot`, `flag_no_context`, dan `is_relevant`. `in_main` adalah keputusan subset; `use_for_topic_fit` menandai dokumen yang cukup panjang dan tidak berulang lintas akun. Flag bot/kampanye adalah heuristik, bukan identitas atau koordinasi yang sudah terbukti.

Run saat ini menghasilkan **9.368 unit penuh**, **6.962 unit utama**, **5.933 unit layak untuk pelatihan topik**, 1.355 unit berhashtag kampanye, 818 unit dari akun yang ditandai, dan 153 duplikat penulis sama. Audit relevansi berisi 50 unit yang diprediksi relevan dan semua 32 unit yang diprediksi tidak relevan; target 50 negatif tidak tersedia. Tim mengisi `manual_relevant` pada salinan audit, bukan pada file hasil run.

## Resource dan keputusan tim

`resources/slang_id.csv` adalah kamus kecil yang dikurasi dari bentuk-bentuk pada spesifikasi tim; [Colloquial Indonesian Lexicon](https://github.com/nasalsabila/kamus-alay) adalah referensi untuk perluasan kamus nanti. `resources/stopwords_id.txt` diambil 27 Oktober 2026 dari [stopwords-iso/stopwords-id](https://github.com/stopwords-iso/stopwords-id) dengan [lisensi MIT](resources/LICENSE-stopwords-id.txt).

Hash akun `80ac16d6…` diberi flag manual sesuai spesifikasi karena 818 balasannya. **Verifikasi manusia melalui permalink belum dilakukan.** Sebelum analisis final, tim perlu mengisi audit relevansi dan label sentimen, lalu membandingkan macro F1 `text_sent_a` dan `text_sent_b`. Untuk jawaban RQ3, topik pada reply pendek yang tidak dilatih dapat diambil dari post root melalui `thread_root_id` setelah BERTopic dijalankan.

## Scraper

`scraper.py` adalah pintu masuk kompatibel ke `collection/scraper.py`. Untuk melanjutkan run akun A, pemilik repo harus memiliki salt asli dalam `config_local.py`, `state/`, dan `output/` dari handoff privat serta memeriksa fingerprint `6888537f`:

```powershell
.venv\Scripts\python scraper.py --profile account_a --keywords keywords.txt --resume
```

Login manual di Chrome. Jika exit code 2, baca log dan tunggu beberapa jam sebelum resume; jangan bypass challenge atau mengurangi jeda. Checkpoint/log final tidak ada di checkout ini, sehingga kelengkapan semua pencarian belum dapat dibuktikan. Lihat [pipeline koleksi](docs/collection_pipeline.md), [kualitas](docs/data_quality.md), [reproduksibilitas](docs/reproducibility.md), dan [bukti TK2](docs/tk2_evidence.md).

Data, laporan berisi teks, anotasi, profil, salt, log, dan output scraping tidak boleh di-commit. Riwayat Git lama mungkin masih memuat teks; lihat [etika](docs/ethics_and_limitations.md).
