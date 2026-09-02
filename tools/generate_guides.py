from pathlib import Path
import shutil
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'pdf'
ASSETS = ROOT / 'src' / 'emss' / 'assets' / 'guides'
OUT.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)
BLUE = colors.HexColor('#0B4F7C')
CYAN = colors.HexColor('#0086B3')
PALE = colors.HexColor('#EAF2FF')
AMBER = colors.HexColor('#FFF7D6')
TEXT = colors.HexColor('#1F2937')

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='TitleEMAS', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=24, leading=29, textColor=BLUE, spaceAfter=12, alignment=TA_LEFT))
styles.add(ParagraphStyle(name='SubTitleEMAS', parent=styles['Heading2'], fontName='Helvetica', fontSize=12, leading=17, textColor=CYAN, spaceAfter=18))
styles.add(ParagraphStyle(name='H1E', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=17, leading=21, textColor=BLUE, spaceBefore=5, spaceAfter=10))
styles.add(ParagraphStyle(name='H2E', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=CYAN, spaceBefore=8, spaceAfter=5))
styles.add(ParagraphStyle(name='BodyE', parent=styles['BodyText'], fontName='Helvetica', fontSize=9.5, leading=14, textColor=TEXT, spaceAfter=6))
styles.add(ParagraphStyle(name='BulletE', parent=styles['BodyText'], fontName='Helvetica', fontSize=9.3, leading=13.5, leftIndent=13, firstLineIndent=-8, textColor=TEXT, spaceAfter=4))
styles.add(ParagraphStyle(name='Callout', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=9.5, leading=14, textColor=colors.HexColor('#854D0E'), backColor=AMBER, borderColor=colors.HexColor('#E8C85A'), borderWidth=.7, borderPadding=8, spaceBefore=6, spaceAfter=8))
styles.add(ParagraphStyle(name='SmallE', parent=styles['BodyText'], fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#526372')))
styles.add(ParagraphStyle(name='TableE', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=TEXT))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#CBD5E1'))
    canvas.line(18*mm, 14*mm, 192*mm, 14*mm)
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(colors.HexColor('#526372'))
    canvas.drawString(18*mm, 9*mm, doc.title)
    canvas.drawRightString(192*mm, 9*mm, f'Halaman {doc.page}')
    canvas.restoreState()


def p(text, style='BodyE'):
    return Paragraph(text, styles[style])


def bullets(items):
    return [p('- ' + item, 'BulletE') for item in items]

def wrapped_table(rows, **kwargs):
    return Table([[p(cell, 'TableE') if isinstance(cell, str) and len(cell) > 45 else cell
        for cell in row] for row in rows], **kwargs)

def cover(title, subtitle, version='1.0.0'):
    return [Spacer(1, 28*mm), p('E-MAS Farmasi', 'TitleEMAS'), p('electronic Medication Alert System', 'SubTitleEMAS'),
            Spacer(1, 14*mm), p(title, 'H1E'), p(subtitle, 'BodyE'), Spacer(1, 10*mm),
            wrapped_table([['Versi panduan', version], ['Tanggal', '1 September 2026'], ['Sasaran', 'Instalasi lokal SIMRS Khanza']], colWidths=[42*mm, 105*mm], style=TableStyle([
                ('BACKGROUND',(0,0),(0,-1),PALE), ('TEXTCOLOR',(0,0),(0,-1),BLUE), ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
                ('FONTNAME',(1,0),(1,-1),'Helvetica'), ('FONTSIZE',(0,0),(-1,-1),9), ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#A9C4ED')), ('PADDING',(0,0),(-1,-1),7)])),
            Spacer(1, 12*mm), p('Pendamping kajian resep. Hasil pDDI bukan bukti kesalahan peresep atau apoteker dan tidak menggantikan penilaian klinis.', 'Callout')]


def build_install(path):
    story = cover('Panduan Instalasi Awal', 'Persiapan PC, instalasi, koneksi read-only, pemilihan Rawat Jalan atau Rawat Inap, dan pemeriksaan awal.')
    story += [PageBreak(), p('1. Sebelum memasang', 'H1E'), p('Siapkan satu PC farmasi yang akan menjalankan E-MAS. Tentukan sejak awal apakah instalasi ini melayani resep RALAN atau RANAP. Pilihan tersimpan pada PC agar alert tidak lintas instalasi.', 'BodyE')]
    story += bullets(['Windows 10/11 64-bit dan akun Windows dengan hak administrator untuk instalasi.', 'SIMRS Khanza dan MariaDB/MySQL dapat diakses dari PC ini.', 'Akun database khusus read-only. E-MAS tidak membuat trigger dan tidak menulis data klinis ke Khanza.', 'Speaker aktif. Volume aplikasi awal 75%; volume Windows dan perangkat tetap harus diperiksa.', 'Cadangkan folder data E-MAS lama bila melakukan penggantian PC.'])
    story += [p('Pemisahan layanan', 'H2E'), p('Instalasi RALAN hanya membaca dan menampilkan resep RALAN. Instalasi RANAP hanya membaca dan menampilkan resep RANAP. Jika asal layanan tidak tersedia, aplikasi berhenti dengan pesan diagnostik dan tidak menebak asal resep.', 'BodyE'),
              p('Uninstall versi lama tidak menghapus data E-MAS di ProgramData. Walaupun demikian, pencadangan sebelum perubahan besar tetap dianjurkan.', 'Callout'),
              PageBreak(), p('2. Instalasi', 'H1E')]
    story += bullets(['Tutup E-MAS yang sedang berjalan.', 'Jalankan E-MAS-Farmasi-Setup-1.0.0-x64.exe sebagai administrator.', 'Pilih ikon Desktop dan Startup sesuai kebijakan unit.', 'Selesaikan instalasi. Installer membundel aplikasi, dua panduan, serta enam audio orisinal tanpa akun, kredensial, sampel eksternal, atau materi pihak ketiga.'])
    story += [p('Lokasi penting', 'H2E'), wrapped_table([
        ['Komponen','Lokasi'], ['Program', r'C:\Program Files\eMSS Farmasi RS'], ['Konfigurasi/data', r'C:\ProgramData\eMSSFarmasi'], ['Database internal', r'C:\ProgramData\eMSSFarmasi\Database'], ['Log', r'C:\ProgramData\eMSSFarmasi\Logs']], colWidths=[42*mm,112*mm], style=TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),8.5),('PADDING',(0,0),(-1,-1),6)])),
        PageBreak(), p('3. Menyiapkan view Khanza', 'H1E'), p('Minta petugas IT memasang atau memperbarui view integrasi dari template SQL E-MAS. View adalah lapisan baca; kolom asal_layanan, validation_token, item_basis, dan composition_complete merupakan hasil query view dan bukan kolom baru pada tabel transaksi Khanza.', 'BodyE')]
    story += bullets(['vw_emss_prescription_header: identitas resep, pasien, unit, status final, asal layanan, token validasi, dan status komposisi.', 'vw_emss_prescription_item: item obat final yang akan diskrining.', 'Akun E-MAS diberi SELECT hanya pada view yang diperlukan.', 'Uji query dengan akun read-only yang sama sebelum membuka E-MAS.'])
    story += [p('Jangan memberikan hak INSERT, UPDATE, DELETE, CREATE, DROP, atau TRIGGER kepada akun integrasi.', 'Callout'),
              PageBreak(), p('4. Pengaturan pertama dan verifikasi', 'H1E')]
    story += bullets(['Buka E-MAS. Saat masuk Mode Farmasi pertama kali, pilih RALAN atau RANAP tanpa kata sandi. Pilihan melekat pada PC.', 'Buka Status Sistem &amp; Diagnostik dan pastikan koneksi serta pemantauan aktif. Mode Farmasi menampilkan status ringkas; rincian teknis hanya untuk Admin/IT.', 'Buka Suara Peringatan. Pastikan enam kategori tersedia dan volume aplikasi 75%. Uji speaker sesuai prosedur lokal.', 'Validasikan satu resep uji final. Resep FINAL diproses pada siklus pertama. Waktu aktual bergantung pada interval polling, query, antrean, dan beban PC. Ukur waktu saat UAT; tidak ada jaminan bebas delay.', 'Pastikan resep dari layanan lain tidak muncul pada antrean PC ini.'])
    story += [p('Kriteria siap uji', 'H2E'), p('Koneksi aktif, cakupan RALAN/RANAP benar, resep FINAL terbaca, tidak ada status UNMAPPED/NOT_ASSESSED untuk obat uji yang seharusnya sudah dipetakan, popup dan suara sesuai kategori, serta antrean dapat ditinjau oleh akun petugas.', 'BodyE'),
              PageBreak(), p('5. Pemecahan masalah singkat', 'H1E')]
    story += [wrapped_table([
        ['Gejala','Pemeriksaan'], ['DISCONNECTED','Buka pesan diagnostik; periksa host, port, layanan database, firewall, dan kredensial read-only.'], ['Asal layanan tidak tersedia','Pasang ulang view terbaru; aplikasi sengaja berhenti agar RALAN/RANAP tidak bercampur.'], ['Tidak ada popup','Pastikan resep berstatus FINAL, pemantauan otomatis aktif, kategori memang memerlukan popup, dan hasil belum pernah ditampilkan.'], ['Suara tidak terdengar','Periksa speaker, mixer Windows, dan perangkat output. Aplikasi tidak dapat memaksa perangkat fisik yang mute.'], ['Obat belum dipetakan','Impor master pemetaan terbaru lalu lakukan pemeriksaan ulang yang tercatat.']], colWidths=[43*mm,111*mm], repeatRows=1, style=TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),8.3),('LEADING',(0,0),(-1,-1),11),('PADDING',(0,0),(-1,-1),6)])),
        p('Simpan log diagnostik dan waktu kejadian bila meminta bantuan IT. Jangan mengirim kata sandi database.', 'Callout')]
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=19*mm, title='Panduan Instalasi Awal E-MAS Farmasi')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def build_use(path):
    story = cover('Panduan Penggunaan', 'Alur antrean resep, arti hasil pDDI, popup dan audio, tinjauan, intervensi, data referensi, serta dashboard admin.')
    story += [PageBreak(), p('1. Prinsip penggunaan', 'H1E'), p('E-MAS membaca resep dari view Khanza secara read-only dan menyimpan hasil pemeriksaan pada database internal E-MAS. Resep RALAN dan RANAP dipisahkan sesuai pengaturan instalasi.', 'BodyE')]
    story += bullets(['Gunakan hasil sebagai dukungan kajian, bukan keputusan terapi otomatis.', 'Tidak ditemukannya pDDI berarti tidak ditemukan pada pasangan obat yang terbaca dan basis aktif, bukan jaminan terapi aman.', 'UNMAPPED, NOT_ASSESSED, INCOMPLETE, atau ERROR berbeda dari status belum ditinjau.', 'Identitas pasien dipakai untuk operasional resep dan deteksi potensi duplikasi; dashboard admin menyajikan agregat tanpa peringkat dokter atau apoteker.'])
    story += [p('Resep FINAL diproses langsung pada siklus pertama. Resep selesai tidak diskrining ulang setiap detik; cursor perubahan menangkap resep baru, sementara rekonsiliasi berkala menjadi jaring pengaman.', 'Callout'),
              PageBreak(), p('2. Antrean Resep', 'H1E'), p('Antrean Resep dan Perlu Perhatian disatukan. Gunakan filter Semua yang perlu perhatian untuk melihat hasil yang perlu tindakan. Kolom Mode dihapus karena cakupan instalasi sudah jelas.', 'BodyE')]
    story += bullets(['Pilih satu baris untuk membuka seluruh pasangan. Kolom Jenis Temuan, Pasangan Obat, dan kategori Kontraindikasi/Mayor/Signifikan/Minor ditampilkan berurutan. Kontraindikasi dan Mayor memakai teks merah tebal. Kendala Pemetaan Obat ditampilkan terpisah dengan kode dan nama obat.', 'Warna menunjukkan hasil pemeriksaan. Kolom Tinjauan menjadi hijau dan menampilkan waktu setelah ditinjau; penanda risiko merah tetap dipertahankan.', 'Tandai Sudah Ditinjau mencatat hasil terkait hingga revisi yang dipilih dalam layanan yang sama. Revisi baru yang belum dilihat tetap memerlukan tinjauan.', 'Dalam Mode Farmasi, klik Tandai Sudah Ditinjau lalu verifikasi akun petugas klinis. Aplikasi tetap berada dalam Mode Farmasi; tidak membuka menu admin. Membatalkan verifikasi tidak mencatat tinjauan.', 'Catat Intervensi Apoteker hanya bila benar-benar ada tindakan klinis atau komunikasi yang perlu didokumentasikan.'])
    story += [p('Status data', 'H2E'), wrapped_table([
        ['Status','Arti'], ['COMPLETE','Semua obat terpetakan dan semua pasangan yang terbentuk memiliki penilaian eksplisit.'], ['UNMAPPED','Sedikitnya satu obat belum memiliki pemetaan kandungan aktif yang disetujui.'], ['NOT_ASSESSED','Sedikitnya satu pasangan belum memiliki penilaian eksplisit pada basis aktif.'], ['INCOMPLETE','Komposisi akhir sumber belum terverifikasi atau item belum lengkap.'], ['ERROR/FAILED','Proses tidak selesai. Hasil tidak boleh dianggap tanpa interaksi.']], colWidths=[34*mm,120*mm], repeatRows=1, style=TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),8.5),('PADDING',(0,0),(-1,-1),6)])),
        PageBreak(), p('3. Popup dan suara', 'H1E')]
    story += [wrapped_table([
        ['Kategori','Perilaku dan tindakan'], ['Kontraindikasi','Popup prioritas tertinggi dan suara khusus. Hentikan proses sesuai SOP dan lakukan penilaian klinis segera.'], ['Mayor/serius','Popup persisten dan suara mayor. Tinjau manfaat-risiko, alternatif, dosis, dan monitoring.'], ['Signifikan','Popup pemberitahuan dan suara khusus. Rekonsiliasi, atur waktu minum atau monitoring sesuai konteks.'], ['Potensi duplikasi','POTENSI DUPLIKASI OBAT - PERLU DITINJAU. Obat dengan kandungan yang sama tercatat pada resep sebelumnya. Pastikan apakah obat tersebut masih digunakan dan apakah pemberian ulang diperlukan. Klik untuk melihat obat dan resep terkait.'], ['High-alert','Suara high-alert ikut diputar bila obat termasuk master high-alert aktif.'], ['Pemeriksaan lengkap','Suara konfirmasi tanpa popup bila resep final lengkap, semua pasangan dinilai, tidak ditemukan pDDI, dan tidak ada temuan lain.']], colWidths=[38*mm,116*mm], repeatRows=1, style=TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.5,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),8.2),('LEADING',(0,0),(-1,-1),10.5),('PADDING',(0,0),(-1,-1),6)])),
        p('Suara dapat diganti dengan file WAV/MP3 lokal. Volume awal 75% dan minimum aplikasi 1%. E-MAS tidak dapat mencegah mute pada Windows, speaker, kabel, atau perangkat fisik.', 'Callout'),
        PageBreak(), p('4. Potensi duplikasi antarresep', 'H1E'), p('E-MAS membandingkan kandungan resep FINAL baru dengan resep FINAL pasien yang sama yang sudah tersimpan di E-MAS dalam 24 jam. Perbandingan menggunakan nomor RM/patient_id, bukan nama pasien, dan tidak menambah query longitudinal ke Khanza.', 'BodyE')]
    story += bullets(['Periksa apakah resep sebelumnya masih aktif.', 'Periksa rujukan antar poli atau perpindahan unit.', 'Dokumentasikan apakah obat diteruskan, diganti, dihentikan, atau memang sengaja diberikan kembali.', 'Jika nomor RM kosong, E-MAS tidak menyimpulkan duplikasi antarpasien berdasarkan nama.'])
    story += [p('Temuan ini adalah sinyal rekonsiliasi; riwayat 24 jam tidak membuktikan obat masih digunakan. E-MAS juga membandingkan pasangan zat aktif antar resep pasien yang sama pada konteks lokal yang memenuhi syarat. Temuan lintas resep dimiliki oleh resep pemicu dan harus direkonsiliasi; penggunaan obat sebelumnya tetap UNKNOWN sampai ditinjau.', 'Callout'),
              PageBreak(), p('5. Intervensi dan riwayat', 'H1E')]
    story += bullets(['Antrean awal menampilkan hasil efektif hari ini; pilih Semua data / Riwayat untuk melihat revisi lama. Riwayat tidak menjadi antrean aktif.', 'Jika konteks lintas resep berubah, label evaluasi ulang konteks berarti hasil akhir belum dapat disimpulkan sampai pemeriksaan lokal selesai.', 'Intervensi Apoteker hanya berisi data setelah tindakan klinis disimpan; meninjau resep saja tidak membuat intervensi palsu.', 'Gunakan catatan yang objektif: temuan, konteks, pihak yang dihubungi, keputusan, dan status penyelesaian.', 'Hasil HIGH_RISK/CRITICAL dapat ditandai sudah ditinjau oleh petugas berwenang tanpa membuat intervensi. Peninjauan tidak menyetujui terapi. Catat intervensi hanya bila benar-benar ada tindakan klinis atau komunikasi.'])
    story += [p('6. Dashboard Kajian Potensi Interaksi Obat (pDDI)', 'H1E'), p('Dashboard hanya tampil bagi SUPER_ADMIN. Mode Farmasi tanpa kata sandi tidak dapat melihat atau mengekspor data agregat ini.', 'BodyE')]
    story += bullets(['Menggunakan hasil efektif terbaru per resep pada periode, sehingga revisi lama tidak dihitung berulang.', 'Menampilkan kontraindikasi, mayor/serius, signifikan, minor, pasangan dinilai tanpa pDDI, pasangan belum dinilai, pasangan pDDI unik, serta jumlah temuan lintas resep.', 'Ekspor CSV menyatakan basis metrik dan bahwa temuan lintas resep tidak dihitung ganda.', 'Menampilkan distribusi per unit/depo dan angka per 100 resep.', 'Tidak membuat peringkat dokter atau apoteker.', 'Demografi ditunda agar jalur alert pelayanan tetap ringan.'])
    story += [p('pDDI adalah potensi interaksi berdasarkan pasangan obat dan basis pengetahuan aktif. Angka agregat tidak membuktikan kesalahan peresepan atau pelayanan farmasi.', 'Callout'),
              PageBreak(), p('7. Data referensi dan pembaruan', 'H1E')]
    story += bullets(['Obat & Kandungan menyimpan master obat dan kandungan yang telah dipetakan.', 'Pengelola SUPER_ADMIN atau KFT dapat menambah obat/pasangan dan memilih Simpan & Aktifkan. Aktivasi menerbitkan snapshot basis internal dan berlaku pada skrining berikutnya; bukan keputusan klinis otomatis.', 'Data Interaksi Obat dan Impor Data Interaksi mengelola pasangan DDI serta sumber/referensinya.', 'Master yang telah valid tetap melekat pada database internal E-MAS. Pembaruan installer tidak menghapus database tersebut.', 'Setelah memperbaiki pemetaan, pilih resep yang masih berkendala lalu klik Coba Periksa Ulang. Verifikasi akun petugas bila memakai Mode Farmasi. Hanya resep itu yang dijadwalkan ulang; histori tetap disimpan.'])
    story += [p('Pembaruan 1.0.0', 'H2E'), p('Rilis final ini menyatukan alur ringkas master/pasangan untuk SUPER_ADMIN dan KFT, skrining pasangan DDI lintas resep berbasis konteks lokal, antrean efektif hari ini, serta interaksi antarmuka yang lebih jelas. Basis data Khanza tetap hanya dibaca; perubahan ini bukan approval klinis baru.', 'BodyE'), p('Status dan akses', 'H2E'), p('Mode Farmasi tidak menampilkan Validasi Klinis &amp; UAT. Status Sistem &amp; Diagnostik tetap menyediakan koneksi, pemantauan, pembacaan terakhir, dan gangguan yang relevan. Nomor resep bersumber dari Khanza; metadata asal data dan status DRAFT tetap dipertahankan di internal.', 'BodyE'), p('8. Checklist singkat per giliran', 'H1E')]
    story += bullets(['Pastikan status Terhubung dan pemantauan otomatis aktif.', 'Pastikan cakupan RALAN/RANAP sesuai PC.', 'Pastikan speaker dan volume perangkat berfungsi.', 'Tinjau antrean baru dan filter Perlu Perhatian.', 'Dokumentasikan tindakan klinis yang benar-benar dilakukan.', 'Laporkan ERROR, UNMAPPED, atau NOT_ASSESSED kepada petugas yang sesuai; jangan menganggapnya tanpa interaksi.'])
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=19*mm, title='Panduan Penggunaan E-MAS Farmasi')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


install = OUT / 'Panduan-Instalasi-Awal-E-MAS-Farmasi.pdf'
use = OUT / 'Panduan-Penggunaan-E-MAS-Farmasi.pdf'
build_install(install)
build_use(use)
for source in (install, use):
    shutil.copy2(source, ASSETS / source.name)
print(install)
print(use)
