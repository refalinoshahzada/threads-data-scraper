# Reproduksibilitas

## Run offline

Dari checkout Windows yang memiliki file privat data/raw/threads_units_2026-09_v1.csv:

1. python -m venv .venv
2. .venv\Scripts\python -m pip install -r requirements.txt
3. .venv\Scripts\python preprocess.py
4. .venv\Scripts\python -m unittest discover -s tests

Dependensi langsung dipin di requirements.txt. Semua parameter preprocessing ada sebagai konstanta di bagian atas preprocess.py; resources/slang_id.csv dan resources/stopwords_id.txt ikut repo. Hash input beku dikunci dan diperiksa sebelum pemrosesan. Output berada di folder data/ dan reports/ yang diabaikan Git. Ulangi perintah pada input serta kode yang sama, lalu bandingkan hash output untuk memeriksa determinisme. Jangan menimpa atau mengubah data/raw/.

Hash input beku: 95c2af37f13bbacbebff1a04c7ac311c6e972e2c5cb67ce64b85e3d882d728df. Ekspor enam kolom data/raw/threads_team_export_2026-09_v1.csv memiliki hash 1d7bccf6826f08cc5a1da44ec27f44dfc15224bb40e30cafadd0224ebb3b9597 dan tidak dipakai oleh preprocess.py. Kedua file CSV privat tidak tersedia pada clone publik; peroleh melalui handoff tim.

## Batas reproduksibilitas

Audit [snapshot koleksi](../metadata/collection_snapshot_2026-10-27.json) membuktikan struktur dan konsistensi internal ekspor 9.368 unit, bukan bahwa seluruh pencarian Threads telah selesai. Checkpoint/log final dari laptop produksi belum ada di checkout. Run live baru dapat berbeda karena ranking, penghapusan konten, rate limit, atau perubahan antarmuka. Resume koleksi lama memerlukan salt asli dalam config_local.py, state/, output/, dan profil login privat; jangan membuat salt baru. Catat versi Chrome/driver, parameter scraper, hash keyword, status pekerjaan, alasan berhenti, dan hanya fingerprint salt sebelum menyatakan run produksi lengkap.

Pipeline lama v2 tidak dapat diulang persis karena script aslinya tidak tersedia. Kode saat ini mengikuti spesifikasi ringkas dan bukan reproduksi v2. Tidak ada label sentimen final atau hasil model saat ini.
