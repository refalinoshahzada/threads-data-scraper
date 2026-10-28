# Panduan anotasi relevansi dan sentimen

Cakupan penelitian: sikap terhadap alokasi anggaran MBG 2027 pada Threads, 3–30 September 2026 WIB. File hasil run adalah bahan kerja privat; buat salinan sebelum mengisi label.

## Relevansi

reports/relevance_check.csv memuat sampel 50 unit yang diprediksi relevan dan 32 yang diprediksi tidak relevan (hanya 32 tersedia). Isi manual_relevant dengan penilaian manusia setelah membaca text_clean dan parent_text bila diperlukan. Sampel ini tidak mewakili prevalensi populasi, karena kelas dipilih sengaja. Kata MBG saja tidak membuktikan bahwa unit membahas anggaran 2027; periksa target anggaran, sumber dana, prioritas, atau konteks root. Bila konteks hilang, catat ketidakpastian alih-alih menebak.

## Sentimen

data/annotation/to_label.csv berisi 1.200 unit sampel dari split train/val/test, kolom unit_id, split, parent_text, text_clean, dan label kosong. Teks parent hanya konteks, bukan pendapat penulis reply. Isi label berdasarkan sikap terhadap anggaran MBG 2027:

| Label | Arti |
|---|---|
| positif | Mendukung atau menilai baik alokasi, prioritas, manfaat, atau pengelolaan anggaran. |
| negatif | Menolak atau mengkritik alokasi, pemborosan, prioritas, atau pengelolaannya. |
| netral | Informatif, pertanyaan, atau arah sikap tidak dapat ditentukan dari teks/konteks. |

Sarkasme dinilai menurut sikap tersirat bila jelas; kasus tidak jelas perlu ditandai untuk diskusi penilai. Bila unit ternyata tidak relevan, pisahkan dari data latih dan catat jumlahnya. Tim menentukan jumlah akhir yang dilabeli dan melakukan adjudikasi bila lebih dari satu penilai memberi label berbeda. Jangan melaporkan distribusi sentimen populasi dari sampel ini tanpa mempertimbangkan desain sampling.

Split dibuat berdasarkan thread_root_id sebelum label diisi, sehingga satu thread tidak berada di train dan test sekaligus. Duplikat teks identik lintas akun dikeluarkan dari populasi split. Bandingkan macro F1 IndoBERT pada text_sent_a dan text_sent_b dengan split yang sama. Untuk BERTopic, fit hanya unit use_for_topic_fit; reply pendek dapat menerima topik dari post root setelah model berjalan. Gabungkan hasil sentimen dan topik melalui unit_id.
