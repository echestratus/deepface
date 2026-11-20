# Hasil validasi Face Lab

Diukur pada **20 November 2026, 11:43 WIB**. Ini hasil lokal pada perangkat pengembangan, bukan jaminan performa atau akurasi di perangkat lain.

## Lingkungan

- Windows 11 x64, Python 3.12.10.
- Intel Core i7-13700HX, 16 core / 24 logical CPU.
- DeepFace 0.0.105 dari fork ini; ONNX Runtime 1.32.0; OpenCV headless 5.1.0.95.
- Backend ONNX, seluruh model menggunakan `CPUExecutionProvider` saja, 2 thread per sesi, OpenCV 2 thread.
- TensorFlow dan PyTorch **tidak terpasang dan tidak diimpor**.
- SFace, YuNet, dan dua MiniFASNet aktif; total bobot 40.5 MiB.

## Pengukuran inference

Perintah dari root repo:

```powershell
.\.venv\Scripts\python.exe -m face_demo.benchmark --frames 20 --interval 1
```

Foto fixture `tests/unit/dataset/img1.jpg`, diperkecil menjadi 473 × 640 px, diproses 20 kali pada interval 1 detik. Filter anti-spoof aktif dan 20 frame dapat diproses. Pengukuran dilakukan setelah pemanasan model.

| Pengukuran | Hasil |
| --- | ---: |
| Median waktu inference | 33.2 ms/frame |
| p95 waktu inference | 65.0 ms/frame |
| Waktu maksimum | 71.9 ms/frame |
| RAM proses saat pengukuran | 185.5 MiB |
| Puncak RAM proses | 198.4 MiB |
| Rata-rata CPU, skala satu logical core = 100% | 6.65% |
| Rata-rata CPU relatif seluruh mesin, 24 logical CPU | 0.28% |
| Waktu memuat model dari cache, setelah import Python | 308.6 ms |

RAM ini milik proses benchmark dan tidak mencakup browser atau server HTTP. Waktu di atas mencakup deteksi, kualitas gambar, filter anti-spoof, dan embedding; tidak mencakup decode JPEG, HTTP, atau pengambilan frame browser. Frame kamera tidak diencode ulang atau disimpan oleh engine. `model_load_ms` tidak mencakup unduhan, import Python, atau seluruh waktu startup aplikasi. Skala CPU seluruh mesin menjadi kecil karena perangkat ini mempunyai 24 logical CPU. Angka CPU pada mesin kecil akan berbeda.

**Pengulangan foto fixture hanya mengukur runtime.** Model menerima piksel fixture tersebut pada filter ini; hasil itu tidak mengukur ketahanan terhadap foto cetak, replay video, atau liveness. Tidak ada klaim persentase akurasi webcam dari pengukuran ini.

Hasil JSON mentah tersimpan lokal di `face_demo/test-results/benchmark.json` dan diabaikan Git. Jalankan ulang perintah untuk perangkat tujuan.

## Cakupan pengujian

Pengujian otomatis mencakup:

- Model nyata SFace/YuNet: dua foto orang yang sama cocok, foto orang berbeda ditolak, tanpa wajah ditolak, dan komposit dua wajah ditolak.
- Provider CPU serta batas thread pada sesi model nyata; kedua model filter anti-spoof dimuat di CPU.
- API pendaftaran, persetujuan wajib, validasi gambar/data, email duplikat, persistensi SQLite, dan penghapusan foto/embedding.
- Sesi terikat pada satu identitas, tiga frame cocok diperlukan, wajah berbeda atau frame bermasalah mereset hasil, kedaluwarsa, dan pembatasan request paralel/terlalu cepat.
- EXIF orientation, pembatasan ukuran/resolusi, aset aplikasi, header keamanan lokal, penolakan origin/host asing, dan pengaturan thread ONNX yang valid/tidak valid.

Perintah pengujian model nyata:

```powershell
$env:FACE_DEMO_MODEL_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest face_demo/tests tests/unit/test_onnx_providers.py -q
```

Setelah penambahan alur kamera terpandu: **60 tes Python lulus**, dengan satu peringatan deprecation dari Starlette mengenai penggunaan `httpx` pada TestClient. Pemeriksaan regresi library terpisah (`test_onnx_providers.py` dan `test_onnx_directml_session.py`) sebelumnya juga lulus: 11 tes, termasuk 7 tes provider yang masuk perintah utama. Pemeriksaan dependensi `pip check`, instalasi requirements/constraints dengan `--dry-run`, sintaks seluruh modul JavaScript, referensi ID elemen HTML, kompilasi Python, dan parser PowerShell lulus. Workflow `.github/workflows/face-demo.yml` disediakan untuk menjalankan cek utama di Windows CI setelah perubahan didorong ke GitHub; workflow remote belum dijalankan.

Tambahan **5 tes JavaScript lulus** melalui `node --test face_demo/tests/camera.test.mjs`: pembatalan saat izin kamera masih tertunda, pembatalan request dan pengabaian respons lama, satu request frame berjalan pada satu waktu, ukuran frame maksimal 640 px, penolakan izin kamera, serta pelepasan track kamera ketika server gagal. Pengujian ini memakai media stream tiruan dan tidak mengakses kamera fisik.

Tes kamera terpandu memeriksa koreksi jarak/posisi/kemiringan/pencahayaan/ketajaman, tiga frame siap dan stabil, reset akibat gerakan atau frame bermasalah, persetujuan wajib, sesi berakhir/batal, batas jumlah draft, pencegahan penyimpanan sebelum capture, dan pengulangan simpan tanpa duplikasi. Tes model nyata juga mencakup capture tiga frame `img1.jpg`, simpan foto referensi, lalu verifikasi dengan foto berbeda `img2.jpg`.

Smoke test melalui HTTP ke server lokal asli juga lulus: pendaftaran `img1.jpg`, tiga frame `img2.jpg` dengan jarak 0.4489 menghasilkan status terverifikasi hanya pada frame ketiga, `img20.jpg` dengan jarak 0.9823 membatalkannya, dan gambar hitam menghasilkan `no_face`. Data fixture dihapus sesudah pengujian; galeri lokal kembali kosong. Ini memakai foto fixture, bukan pengujian kamera fisik.

Smoke test HTTP tambahan untuk alur baru lulus: mulai draft, tiga frame panduan `img1.jpg` (capture hanya frame ketiga), tinjau foto, simpan identitas, buka `/verify?user=...`, verifikasi `img2.jpg`, dan tolak `img20.jpg`. Halaman `/register`, `/verify`, serta semua modul kamera menghasilkan HTTP 200. Data fixture dihapus setelah pengujian.

Pada pemeriksaan lanjutan, halaman pendaftaran dan halaman uji berhasil dibuka serta diperiksa melalui accessibility tree dan screenshot desktop Microsoft Edge. Kamera tetap nonaktif sampai tombol pengguna ditekan. **Izin kamera, alur dengan kamera fisik, tampilan perangkat mobile, dan ketahanan spoof di perangkat pengguna belum diverifikasi langsung.** Gunakan langkah pengujian manual pada [README](README.md) sebelum menilai kelayakan untuk interview.

## Pengukuran panduan kamera

Diukur **20 November 2026, 16:09 WIB**, pada lingkungan CPU yang sama. Perintah:

```powershell
.\.venv\Scripts\python.exe -m face_demo.benchmark --mode guide --frames 20 --interval 0.5 --output face_demo/test-results/guide-benchmark.json
```

20 pengulangan foto fixture pada cadence maksimal 2 pemeriksaan/detik, semua berstatus `ready`, filter anti-spoof aktif:

| Pengukuran | Hasil |
| --- | ---: |
| Median inference panduan | 28.6 ms/frame |
| p95 inference panduan | 42.0 ms/frame |
| RAM proses | 183.2 MiB |
| Puncak RAM proses | 196.0 MiB |
| CPU rata-rata, satu logical core = 100% | 8.84% |
| CPU relatif seluruh mesin 24 logical CPU | 0.37% |

Pengukuran ini hanya untuk pemeriksaan panduan, tidak mencakup browser, decode JPEG, HTTP, atau pembuatan embedding pada capture akhir. Bobot model dan provider CPU sama; TensorFlow/PyTorch tidak diimpor. Hasil ini mengukur runtime fixture dan **bukan bukti liveness atau akurasi kamera**. Foto referensi yang sudah ada tetap memakai pipeline embedding yang sama.
