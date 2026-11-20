# Cari Kerja Face Lab

Aplikasi uji lokal berbahasa Indonesia di atas **fork DeepFace ini**. Alur: isi nama/email → buka kamera dan ikuti panduan langsung → foto diambil otomatis → tinjau dan simpan → buka halaman terpisah untuk uji verifikasi. Tidak memerlukan layanan cloud, GPU, Node.js, TensorFlow, atau PyTorch untuk menjalankan aplikasi.

## Jalankan di Windows

Diuji dengan **Python 3.12 x64**. Dari direktori root repo:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-face-demo.ps1
```

Script membuat `.venv` bila belum ada, memasang dependensi sesuai `face_demo/constraints.txt`, lalu menjalankan server. Opsi `-ExecutionPolicy Bypass` hanya berlaku pada proses PowerShell tersebut. Startup pertama memerlukan internet untuk memasang paket dan mengunduh empat model (total sekitar 40 MB). Tunggu tulisan `Application startup complete`, kemudian buka **http://127.0.0.1:8000** di Edge atau Chrome dan izinkan kamera saat diminta. Setelah pemasangan dan model tersimpan, pemrosesan wajah berjalan offline.

Jika dependensi sudah terpasang:

```powershell
.\.venv\Scripts\python.exe -m face_demo
# Atau:
.\start-face-demo.ps1 -SkipInstall
# Jika port 8000 terpakai:
.\.venv\Scripts\python.exe -m face_demo --port 8001
```

Alternatif instalasi manual / Linux / macOS, dari root repo:

```bash
python -m venv .venv
# Windows: .venv\Scripts\python.exe; Linux/macOS: .venv/bin/python
python -m pip install -r face_demo/requirements.txt
python -m face_demo.prepare
python -m face_demo
```

Aktifkan virtual environment atau gunakan executable Python di `.venv` pada tiga perintah terakhir. Constraints yang disediakan merekam versi yang diuji di Windows; sistem lain dapat menggunakan requirements tanpa constraints jika wheel versinya belum tersedia.

## Cara mencoba

1. Buka **http://127.0.0.1:8000/register** (halaman `/` juga membuka pendaftaran). Isi nama dan email, centang persetujuan, lalu klik **Mulai kamera & panduan**. Izinkan kamera di browser; mikrofon tidak digunakan.
2. Posisikan wajah di dalam oval. Arahan berubah mengikuti hasil deteksi: satu wajah, jarak, posisi tengah, kepala tegak, pencahayaan, ketajaman, serta filter anti-spoof. Contohnya **Dekatkan wajah**, **Geser wajah ke kiri layar**, dan **Tambahkan cahaya dari depan wajah**. Arahan kiri/kanan mengikuti pratinjau kamera yang dicerminkan.
3. Setelah **tiga pemeriksaan siap dan stabil berturut-turut**, foto otomatis diambil dari frame terakhir yang diterima. Gerakan besar atau frame yang tidak memenuhi syarat mereset progres. Tombol kamera berhenti otomatis setelah pengambilan.
4. Tinjau foto. Pilih **Ambil ulang foto** bila perlu, atau **Simpan & lanjut uji verifikasi**. Data identitas permanen baru dibuat saat disimpan. Setelah berhasil, aplikasi membuka **`/verify?user=...`** dengan identitas tadi terpilih.
5. Pada **http://127.0.0.1:8000/verify**, klik **Nyalakan kamera uji**. Wajah kamera dibandingkan dengan foto referensi yang terlihat di sisi kiri. Status **Identitas terverifikasi** membutuhkan **tiga frame cocok berturut-turut**. Pemeriksaan berlanjut; wajah berbeda atau frame yang ditolak membatalkan status tersebut.
6. Uji wajah pemilik identitas, lalu orang lain yang setuju ikut uji, tanpa wajah, dua wajah, perubahan cahaya/jarak, kacamata, foto cetak, dan foto/video di layar. Tinjau jarak wajah, waktu proses, serta riwayat 10 frame terakhir. Riwayat hanya ada di memori halaman dan **bukan pengukuran persentase akurasi**.
7. Gunakan **Hapus** pada halaman uji untuk menghapus identitas, foto, dan embedding terkait. Tutup/hentikan kamera setelah selesai.

Draft pendaftaran dan foto sementara berlaku maksimal **5 menit** serta dibersihkan berkala dari memori server; batal/ambil ulang membuang draft lama. Foto sementara tidak ditulis ke disk. Sesi uji verifikasi berlangsung maksimal **3 menit**. Mulai kembali jika sesi berakhir. Kamera otomatis berhenti saat tab disembunyikan/ditutup. Kamera browser memerlukan **localhost atau HTTPS**. Jangan membuka aplikasi melalui IP LAN HTTP.

Panduan arah kepala memakai heuristik landmark mata dan framing, bukan estimasi pose 3-D. Ambang kualitas adalah nilai awal yang perlu diuji pada kamera pengguna.

## Pemrosesan CPU dan penyimpanan

- **DeepFace SFace (128 dimensi)** untuk embedding dan **YuNet** untuk deteksi. ONNX backend dan `CPUExecutionProvider` dipaksakan oleh aplikasi, bahkan bila shell memiliki konfigurasi GPU. Saat startup, provider setiap model diperiksa.
- **MiniFASNet ONNX** bawaan DeepFace aktif saat panduan pendaftaran kamera (setelah syarat framing terpenuhi) serta verifikasi kamera. Endpoint impor foto lama tetap tersedia untuk kompatibilitas API; endpoint tersebut tidak melewati filter anti-spoof.
- Default **2 thread per sesi ONNX**, inter-op 1, spinning dimatikan, OpenCV 2 thread, OpenCL dimatikan. Inference diserialkan oleh lock. Jalankan **satu worker** untuk menghindari duplikasi model/RAM.
- Frame dikurangi menjadi maksimal **640 px** pada sisi terpanjang. Panduan pendaftaran diperbarui maksimal **2 frame/detik**; uji verifikasi sekitar **1 frame/detik**, dengan satu request berjalan pada satu waktu.
- Panduan hanya menjalankan deteksi, pemeriksaan kualitas, dan filter yang diperlukan. Embedding referensi dihitung **sekali saat foto otomatis diambil**. Saat verifikasi hanya embedding frame baru dibandingkan dengan embedding tersimpan.
- Jarak menggunakan **cosine distance**, ambang awal **0.593** dari konfigurasi SFace pada fork DeepFace ini. Lebih kecil berarti lebih mirip. Angka tersebut **bukan probabilitas**. Threshold ini mengikuti preprocessing DeepFace dan berbeda dari contoh OpenCV `alignCrop` yang memakai pipeline lain.
- SQLite: `face_demo/data/users.sqlite3`. Menyimpan nama, email, waktu persetujuan, versi pipeline, embedding float32, dan foto JPEG yang diperkecil serta dibuang metadata EXIF-nya. **Hanya foto referensi yang dikonfirmasi disimpan; frame panduan/verifikasi lain tidak ditulis ke disk.** Data tidak dienkripsi pada disk; aplikasi ini untuk komputer uji lokal.
- Cache model: `face_demo/data/models/.deepface/weights/`. Data, model, virtualenv, serta hasil benchmark tidak masuk Git. Browser UI tidak memerlukan CDN atau font eksternal; halaman dokumentasi Swagger menggunakan aset CDN.

Pengaturan opsional sebelum menjalankan server:

```powershell
$env:FACE_DEMO_THREADS = '2'          # 1–8; coba 1 untuk CPU kecil
$env:FACE_DEMO_THRESHOLD = '0.593'    # turunkan agar lebih ketat; perlu kalibrasi
$env:FACE_DEMO_ANTI_SPOOF = 'true'    # false hanya untuk mengukur kecocokan tanpa filter
# $env:FACE_DEMO_DATA_DIR = 'D:\face-lab-data'
.\.venv\Scripts\python.exe -m face_demo
```

Ganti lokasi data hanya saat server mati. Jika mengganti model atau preprocessing, daftarkan ulang foto; embedding dari pipeline berbeda tidak dapat dibandingkan begitu saja. `DEEPFACE_ONNX_THREADS` ditambahkan sebagai opsi library; perilaku library lainnya tetap memakai default bila variabel tersebut tidak ditetapkan.

## API untuk persiapan integrasi

Dokumentasi interaktif: **http://127.0.0.1:8000/docs**. Semua mutasi membutuhkan header `X-Face-Demo: local`. Klik **Try it out** di Swagger tidak menyisipkan header ini otomatis; gunakan curl atau klien aplikasi berikut. Header ini adalah penghalang request lintas situs pada demo, **bukan autentikasi**.

| Endpoint | Fungsi |
| --- | --- |
| `GET /api/health` | Model, CPU provider, thread, threshold, filter, dan interval |
| `POST /api/enrollments` | JSON `name`, `email`, `consent=true`; mulai draft kamera |
| `POST /api/enrollments/{id}/frames` | Multipart `photo`; panduan, progres stabil, dan `captured` |
| `GET /api/enrollments/{id}/photo` | Tinjau foto otomatis sebelum disimpan |
| `POST /api/enrollments/{id}/complete` | Simpan foto/embedding yang disetujui server; mengembalikan `verification_url` |
| `DELETE /api/enrollments/{id}` | Batalkan draft dan buang foto sementara |
| `POST /api/users` | Impor foto kompatibilitas API: multipart `name`, `email`, `consent=true`, `photo` |
| `GET /api/users` | Daftar identitas; embedding tidak dikirim |
| `DELETE /api/users/{id}` | Hapus data dan batalkan sesi identitas |
| `POST /api/sessions` | JSON `{"user_id":"..."}`; sesi terikat ke identitas ini |
| `POST /api/sessions/{session_id}/frames` | Multipart `photo`; hasil frame dan status tiga kecocokan |

Contoh `curl.exe` di Windows:

```powershell
curl.exe -H "X-Face-Demo: local" -F "name=Demo User" -F "email=demo@example.test" -F "consent=true" -F "photo=@C:\foto\saya.jpg" http://127.0.0.1:8000/api/users
```

Perintah impor tersebut untuk klien API lama. Alur antarmuka menggunakan draft kamera dan tidak menyediakan unggah foto manual. Kirim frame baru pada interval >= 500 ms ke endpoint panduan; progres pengambilan ditentukan server. `complete` menolak sesi yang belum memiliki foto siap dan mendukung pengulangan request tanpa membuat identitas ganda.

Contoh klien Python:

```python
import requests

base = "http://127.0.0.1:8000"
headers = {"X-Face-Demo": "local"}
# user_id diperoleh dari respons pendaftaran.
r = requests.post(f"{base}/api/sessions", headers=headers,
                  json={"user_id": user_id}, timeout=10)
r.raise_for_status()
session_id = r.json()["session_id"]
# Kirim frame kamera baru tiap >= 1 detik. Jangan mengulang foto yang sama.
with open("frame.jpg", "rb") as photo:
    r = requests.post(f"{base}/api/sessions/{session_id}/frames",
                      headers=headers, files={"photo": photo}, timeout=15)
r.raise_for_status()
result = r.json()
print(result["verified"], result["status"], result["distance"])
```

`matched` berarti satu frame cocok; `verified` berarti tiga frame berturut-turut diterima. `no_face`, `multiple_faces`, `low_quality`, `spoof_detected`, atau `mismatch` mengembalikan `verified=false` dan mereset hitungan. Sesi baru/identitas baru tidak mewarisi kecocokan sebelumnya. Request terlalu cepat/paralel untuk sesi yang sama mengembalikan HTTP 429; sesi kedaluwarsa 404. Server mencatat error teknis tanpa menyimpan frame kamera.

Untuk integrasi Cari Kerja nantinya, backend yang sudah terautentikasi harus memilih `user_id` dari akun/sesi interview, bukan mempercayai pilihan ID dari browser. Tambahkan autentikasi antarservice, HTTPS, batas request, kebijakan penyimpanan, dan jalur tinjauan manusia ketika verifikasi gagal. Hasil model ini tidak boleh menjadi satu-satunya penentu keputusan rekrutmen.

## Pengujian dan benchmark

```powershell
.\.venv\Scripts\python.exe -m pip install -r face_demo/requirements-dev.txt -c face_demo/constraints.txt
$env:FACE_DEMO_MODEL_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest face_demo/tests tests/unit/test_onnx_providers.py -q
.\.venv\Scripts\python.exe -m face_demo.benchmark --frames 20 --interval 1
.\.venv\Scripts\python.exe -m face_demo.benchmark --mode guide --frames 20 --interval 0.5 --output face_demo/test-results/guide-benchmark.json
# Opsional untuk pengujian pengelolaan kamera JavaScript (memerlukan Node.js):
node --test face_demo/tests/camera.test.mjs
```

Tanpa `FACE_DEMO_MODEL_TESTS=1`, pengujian yang memerlukan model asli dilewati. Tes lainnya memakai engine uji untuk menguji API/state tanpa unduhan. Benchmark memakai model asli, filter default aktif, dan foto fixture repo. Hasil JSON ada di `face_demo/test-results/benchmark.json`; lihat [hasil pengujian yang dicatat](VALIDATION.md).

Benchmark mengukur waktu inference, RAM proses, dan CPU pada cadence terpilih, bukan akurasi webcam. Tidak mencakup RAM browser, waktu encode/decode JPEG, atau HTTP. Perangkat dan kualitas kamera akan mengubah hasil.

## Batas anti-fraud

Pendaftaran hanya mengikat sebuah foto dengan data yang dimasukkan; belum membuktikan kepemilikan akun atau identitas legal. Filter anti-spoof adalah klasifikasi gambar dan dapat salah menolak wajah asli atau menerima serangan. Tiga frame berurutan menstabilkan hasil, **bukan bukti liveness**. API juga tidak dapat membuktikan frame berasal dari kamera fisik. Replay video, virtual camera, injeksi frame, dan deepfake tetap memerlukan evaluasi serta kontrol tambahan. Uji lapangan dan kalibrasi threshold dibutuhkan sebelum dipakai untuk interview sungguhan.

Lisensi kode mengikuti [MIT repo](../LICENSE). Bobot model memiliki lisensi upstream masing-masing; rujukan: [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface), [YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), [Silent Face Anti Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing).
