# MOMAZ POS - Sistem Point of Sale Retail Pakaian & Distro (Multi-Tenant)

Sistem POS Retail modern berarsitektur **Modular Monolith** dengan sistem **Multi-Tenant Database-per-Tenant (SQLite)** yang dirancang khusus untuk toko pakaian, distro, butik, dan fashion retail.

Dibangun dengan **Python FastAPI**, database **SQLite** teroptimasi (WAL Mode & PRAGMA Foreign Keys), dan antarmuka web interaktif menggunakan **HTML5, Vanilla JavaScript, CSS, serta Bootstrap 5 CDN** pada port **8181**.

---

## Fitur Utama Spesifik Retail Pakaian

1. **Multi-Tenant Architecture (Database-per-Tenant):**
   - **`master.db`**: Menyimpan akun pengguna global/pemilik toko (`MasterUser`) dan registrasi toko (`Tenant`).
   - **`tenants/{slug}.db`**: Setiap toko pakaian memiliki database SQLite tersendiri yang terisolasi secara fisik dan logis (produk, varian, transaksi penjualan, shift kasir, dan laporan).
   - **Alur Login & Setup Persisten**: Admin mendaftar atau login terlebih dahulu di `/login`. Jika admin belum memiliki toko, sistem mengarahkan ke Setup Wizard untuk membuat database toko baru. Jika sudah memiliki toko, sistem langsung membuka Backoffice/POS dan **tidak akan mengulang setup wizard** meskipun server di-restart berkali-kali.

2. **Katalog Produk Pakaian Lengkap & Impor/Ekspor Massal (CSV):**
   - Field Produk Induk: Nama, Deskripsi, **Harga Normal**, **Harga Diskon/Promo**, **SKU Induk**, **Barcode Induk**, Kategori, Brand, dan **Upload Foto Produk** langsung ke server.
   - **Impor Massal Produk (Upload CSV)**: Mendukung upload ratusan produk sekaligus dalam format *Row-per-Variant*. Otomatis membuat kategori, brand, SKU varian, dan barcode jika belum ada.
   - **Ekspor Katalog Produk (Download CSV)**: Mengekspor seluruh data pakaian ke file CSV berstandar UTF-8 BOM yang dapat langsung dibuka dan diedit di Microsoft Excel.
   - **Unduh Template CSV**: Format acuan siap pakai dengan contoh varian baju untuk memudahkan pengguna menginput data.
   - Manajemen Kategori & Brand: Tambah, edit, dan hapus kategori serta brand langsung dari modal interaktif di Backoffice.

3. **Matriks Varian Pakaian (Color & Size Matrix):**
   - Mendukung satu produk baju dengan banyak variasi warna (Navy, Hitam, Sage, Putih, dll.) dan ukuran (S, M, L, XL, XXL, All Size).
   - Dilengkapi *Matrix Permutation Generator* otomatis di Backoffice yang membuat seluruh kombinasi varian lengkap dengan Barcode dan SKU unik dalam 1 klik.

4. **Antarmuka Kasir Cepat (Fast POS Counter):**
   - Mendukung scanner barcode dengan auto-focus cepat & feedback audio beeper via Web Audio API.
   - Shortcut keyboard kasir:
     - `F1`: Cari nama pakaian
     - `F2`: Fokus ke scanner barcode
     - `F3`: Parkir bill (Hold Cart) saat pelanggan ke fitting room
     - `F4`: Panggil kembali transaksi terparkir (Recall Cart)
     - `F8`: Bayar tunai (Cash)
     - `F9`: Bayar non-tunai (QRIS / EDC)

5. **Multi-Payment & Quick Cash:**
   - Tombol pecahan cepat: Uang Pas, 50.000, 100.000, 200.000.
   - Kalkulator kembalian instan otomatis.
   - Simulasi QRIS dinamis & nomor referensi EDC.

6. **Cetak Struk Thermal (58mm & 80mm):**
   - Format struk thermal standar ritel dengan informasi nama baju, ukuran, warna, diskon, catatan kebijakan penukaran pakaian, dan rincian pembayaran.
   - Siap cetak langsung ke printer thermal kasir (`window.print()`).

7. **Manajemen Shift Kasir (Audit Laci Kas):**
   - Buka shift kasir wajib memasukkan modal kas awal (*cash float*).
   - Tutup shift kasir menghitung uang fisik aktual vs kalkulasi penjualan sistem (*cash over/short reconciliation*).

8. **Retur & Tukar Ukuran/Warna (Exchange Feature):**
   - Layanan penukaran size pakaian dengan verifikasi nomor invoice struk, menghitung selisih harga, dan otomatis mengembalikan mutasi stok.

9. **Inventori & Mutasi Stok:**
   - Deteksi otomatis stok menipis / kritis (*low stock alert*).
   - Penerimaan barang masuk dari konveksi/garmen (*Stock In*).
   - Penyesuaian stok opname fisik (*Stock Adjustment*).

10. **Backoffice & Laporan Keuangan:**
    - Dashboard analitik: Omset hari ini, Laba kotor (Omset - HPP), Jumlah transaksi, dan Produk terlaris.
    - Filter laporan penjualan per rentang tanggal & ekspor ke file CSV pembukuan.

---

## Arsitektur Modular Monolith Multi-Tenant

```
momaz-pos/
├── master.db                    # Database global akun admin & registrasi tenant
├── tenants/                     # Direktori file database per-tenant
│   ├── distro-bandung.db        # Database terisolasi Toko 1
│   └── boutique-jakarta.db      # Database terisolasi Toko 2
│
├── app/
│   ├── main.py                  # FastAPI application entrypoint & page routing
│   ├── config.py                # Konfigurasi master DB, direktori tenant & JWT
│   ├── database.py              # Dynamic TenantManager, MasterBase & WAL pragmas
│   │
│   ├── core/                    # Fondasi bersama (Auth security, Store settings)
│   ├── modules/                 # Modul-modul domain terisolasi:
│   │   ├── tenants/             # Registrasi Admin & Setup Wizard Tenant DB
│   │   ├── auth/                # Multi-tenant login, JWT token dengan tenant_slug
│   │   ├── catalog/             # Pakaian, Matrix Varian, Barcode, Diskon, Kategori, Brand
│   │   ├── inventory/           # Stok, Stock In, Opname, Log Mutasi
│   │   ├── sales/               # Kasir POS, Keranjang, Transaksi, Struk, Parkir Bill
│   │   ├── shifts/              # Buka/Tutup shift kasir, selisih kas
│   │   ├── returns/             # Retur & Tukar ukuran pakaian
│   │   ├── customers/           # Database member/pelanggan
│   │   └── reports/             # Laporan laba kotor, omset & ekspor CSV
│   │
│   ├── static/                  # CSS styling, Vanilla JS modular & Uploads
│   │   └── uploads/products/    # Tempat penyimpanan foto produk yang diupload
│   └── templates/               # HTML5 + Bootstrap 5 CDN + Jinja2
│       ├── base.html            # Layout master Backoffice
│       ├── login.html           # Halaman login & pendaftaran admin
│       ├── setup.html           # Setup Wizard database toko (post-login)
│       ├── pos/index.html       # Antarmuka kasir layar penuh (POS)
│       └── backoffice/          # Dashboard, Produk, Stok, Transaksi, Shift, dll.
│
├── tests/                       # Automated tests (Pytest)
│   ├── test_multi_tenant.py     # Verifikasi registrasi, setup wizard & isolasi data
│   ├── test_endpoints.py        # Verifikasi redirect halaman & API katalog/upload
│   ├── test_catalog.py          # Uji pembuatan produk, matriks varian, barcode lookup
│   ├── test_sales.py            # Uji checkout & pengurangan stok
│   ├── test_returns.py          # Uji tukar ukuran baju & pengembalian stok
│   └── test_shifts.py           # Uji lifecycle shift kasir
│
├── run.py                       # Skrip server (Port 8181)
└── requirements.txt             # Dependensi Python
```

---

## Cara Menjalankan Aplikasi

### 1. Instalasi Dependensi
Pastikan Python 3.10+ telah terinstal:
```powershell
pip install -r requirements.txt
```

### 2. Jalankan Aplikasi
```powershell
python run.py
```
Aplikasi akan berjalan di port **8181**:
- **Halaman Login & Daftar Admin:** [http://localhost:8181/login](http://localhost:8181/login)

### 3. Alur Penggunaan Pertama Kali
1. Buka [http://localhost:8181/login](http://localhost:8181/login).
2. Pilih tab **"Daftar Admin Baru"** dan daftarkan akun pemilik/admin.
3. Setelah mendaftar atau login, sistem mendeteksi bahwa admin ini belum memiliki database toko, dan otomatis membuka **Setup Wizard** ([http://localhost:8181/setup](http://localhost:8181/setup)).
4. Isi data toko, kebijakan retur pakaian, serta pilih kategori dan brand awal, lalu klik **"Inisialisasi Database Toko"**.
5. Database `tenants/{slug}.db` akan langsung dibuat dan diisi struktur tabel pos.
6. Admin langsung diarahkan ke Dashboard Backoffice atau POS Kasir.
7. **Persisten**: Saat server dimatikan dan dinyalakan kembali, login dengan akun admin tersebut akan langsung membawa Anda ke dashboard toko tanpa mengulang setup wizard.

---

## Menjalankan Pengujian Otomatis (Pytest)
Untuk menjalankan seluruh 12 automated unit & integration test:
```powershell
pytest tests/ -v
```
Semua 12 pengujian meliputi:
- Pembuatan produk induk & generator varian warna/ukuran.
- Redirect halaman unauthenticated dan authenticated.
- Endpoint kategori dan brand (tambah, tampil, hapus).
- Upload foto produk pakaian.
- Produk dengan harga diskon, SKU induk, barcode induk, dan matriks varian.
- Registrasi admin di `master.db` dan validasi username duplikat.
- Alur lengkap Setup Wizard tenant database (`tenants/{slug}.db`).
- **Verifikasi isolasi data multi-tenant**: memastikan katalog dan transaksi toko A tidak dapat dilihat atau tercampur dengan toko B.
- Checkout kasir dan pengurangan stok otomatis.
- Penolakan checkout bila stok tidak mencukupi.
- Retur struk pakaian dan tukar size busana.
- Lifecycle pembukaan dan penutupan shift kasir dengan rekonsiliasi uang fisik.
