# Protokol preprocessing Threads MBG 2027

Pipeline aktif adalah satu file [preprocess.py](../preprocess.py), mengikuti spesifikasi ringkas tim 27 Oktober 2026. Input beku adalah data/raw/threads_units_2026-09_v1.csv (9.368 unit; SHA-256 95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df). Nama pada spesifikasi memiliki prefiks angka yang tidak ada di checkout lokal. Seluruh ID dibaca sebagai string agar hubungan reply–parent tidak kehilangan presisi.

Semua aturan kualitas menambah flag. Tabel penuh tetap 9.368 baris dan kolom text_raw identik dengan text sumber. Hanya dataset utama yang menyaring unit; script tidak menjalankan IndoBERT atau BERTopic.

| Langkah | Fungsi | Keputusan |
|---|---|---|
| 1 Validasi | step1_load_validate | Skema dan ID valid; tandai teks kosong dan waktu di luar 3–30 September WIB; metrik kosong tetap kosong. |
| 2 Karakter | step2_clean_characters | NFKC, hapus zero-width tertentu, rapikan spasi/baris baru; tanpa lowercase atau penghapusan kata. |
| 3 Duplikat | step3_duplicates | Teks penulis sama ditandai; teks identik lintas akun ditandai hanya jika kunci teks minimal 30 karakter. |
| 4 Kampanye/bot | step4_campaign_bot | Hashtag signature dan satu author_hash yang ditentukan spesifikasi ditandai. |
| 5 Relevansi | step5_relevance | MBG/BGN pada teks sendiri atau root yang terkumpul; pola off-topic; traversal parent dibatasi 50 langkah. |
| 6 Sentimen | step6_sentiment | Varian A mempertahankan kata/negasi; varian B menambah normalisasi slang pendek. |
| 7 Topik | step7_topic | Emoji/URL/mention dibuang, slang dari resource, 240T menjadi 240 triliun; stopword disimpan terpisah. |
| 8 Split | step8_split | GroupShuffleSplit 70/15/15 berdasarkan thread_root_id untuk unit utama yang bukan duplikat lintas akun. |

Dataset utama: teks ada, tanggal dalam jendela, relevan, bukan kampanye, bukan akun yang ditandai, dan bukan duplikat penulis sama. Unit duplikat lintas akun tetap dapat masuk analisis sentimen, tetapi dikeluarkan dari pelatihan topik dan split. Dokumen topik juga harus memiliki minimal lima kata. Reply pendek tetap ada untuk sentimen; topiknya dapat diwariskan dari root setelah model BERTopic dijalankan.

Run saat ini: 9.368 penuh, 6.962 utama, 5.933 layak untuk fit topik, 1.355 kampanye, 818 dari akun yang ditandai, dan 153 duplikat penulis. Audit relevansi meminta 50 unit per kelas, tetapi hanya 32 diprediksi tidak relevan; semua 32 disertakan. Angka ini adalah hasil aturan, bukan validasi manusia.

File privat yang dihasilkan: data/processed/threads_full.parquet, threads_main.csv, stopwords_topic.txt; data/annotation/to_label.csv; reports/funnel.csv dan relevance_check.csv. Semua path data/reports diabaikan Git. [README](../README.md) menjelaskan instalasi dan akses. Asumsi historis lama ada di [ringkasan v2](history/preprocessing_v2_summary.md), bukan pipeline aktif.

Sebelum laporan final, tim perlu memeriksa relevansi manual, memverifikasi akun yang ditandai melalui permalink, melabeli sampel, dan membandingkan macro F1 kedua varian teks sentimen. Split tidak menggantikan evaluasi label manusia.
