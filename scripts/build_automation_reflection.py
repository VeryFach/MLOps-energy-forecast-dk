"""Generate the short LK-08 reflection PDF with Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "refleksi_code_as_trigger.pdf"


def font(size, bold=False):
    base = Path("C:/Windows/Fonts")
    preferred = base / ("arialbd.ttf" if bold else "arial.ttf")
    if preferred.exists():
        return ImageFont.truetype(str(preferred), size)
    linux = Path("/usr/share/fonts/truetype/dejavu") / (
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    )
    return ImageFont.truetype(str(linux), size)


def paragraph(draw, text, x, y, width, face, fill="#24344a", spacing=13):
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=face)[2] > width and line:
            draw.text((x, y), line, font=face, fill=fill)
            y += face.size + spacing
            line = word
        else:
            line = candidate
    if line:
        draw.text((x, y), line, font=face, fill=fill)
        y += face.size + spacing
    return y


def main():
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((0, 0, 1240, 27), fill="#1976a5")
    draw.text(
        (85, 80), "Refleksi: Code as a Trigger", font=font(49, True), fill="#173753"
    )
    draw.text(
        (85, 150),
        "Energy Forecast DK  |  Otomatisasi MLOps",
        font=font(25),
        fill="#567083",
    )
    y = 245
    sections = [
        (
            "Mengapa pemicu kode penting",
            "Perubahan kecil pada fitur, prapemrosesan, atau hyperparameter dapat membuat model tetap melayani prediksi, tetapi kualitasnya turun diam-diam. Push dan pull request memulai pengujian, penarikan snapshot DVC, pelatihan ulang, dan evaluasi. Dengan begitu, perubahan kode diperiksa terhadap data dan metrik sebelum model dipakai lebih jauh.",
        ),
        (
            "Gerbang yang mencegah silent failure",
            "Pytest menangkap kesalahan logika awal. DVC memastikan input berasal dari versi data yang tercatat. Training mencatat metrik dan hash data pada run MLflow. Evaluasi menolak MAPE di atas 5%, nilai metrik tidak valid, run yang belum selesai, serta ketidakcocokan hash. Hanya run yang lolos dapat menjadi versi Staging; versi Production tetap memerlukan keputusan promosi tersendiri.",
        ),
        (
            "Reproduksibilitas dan audit",
            "Commit Git, pointer DVC, parameter model, hash data olahan, run MLflow, dan laporan validasi membentuk jejak yang dapat diperiksa ulang. Artefak GitHub Actions menyimpan hasil setiap eksekusi. Ketika kualitas berubah, tim dapat membedakan perubahan kode, data, atau konfigurasi tanpa menebak dari perilaku API saja.",
        ),
        (
            "Batasan",
            "MAPE pada satu holdout kronologis tidak menjamin performa setelah deployment. Monitoring Prometheus dan Grafana tetap diperlukan untuk mendeteksi drift, latensi, dan penurunan kualitas setelah model dipakai. Kegagalan akses DVC atau MLflow harus menghentikan pipeline agar tidak tampak sukses palsu.",
        ),
    ]
    for title, body in sections:
        draw.text((85, y), title, font=font(31, True), fill="#1976a5")
        y += 57
        y = paragraph(draw, body, 85, y, 1070, font(25)) + 46
    draw.line((85, 1620, 1155, 1620), fill="#bfd0da", width=2)
    draw.text(
        (85, 1642),
        "Ambang LK-01: MAPE <= 5%  |  Hasil validasi: Staging",
        font=font(21),
        fill="#567083",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    page.save(OUTPUT, "PDF", resolution=150)
    print(OUTPUT)


if __name__ == "__main__":
    main()
