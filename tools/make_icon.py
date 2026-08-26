"""바탕화면 바로가기용 .ico 를 스프라이트에서 뽑는다.

    python make_icon.py <spritesheet.png> <out.ico>

첫 셀(idle 0번 프레임)의 얼굴을 잘라 16~256px 멀티사이즈 아이콘으로 저장한다.
Pillow 없이 PySide6(QImage)로 PNG를 만들고 ICO 컨테이너만 직접 쓴다.
Vista 이후 ICO는 PNG를 그대로 담을 수 있어서 헤더 몇 바이트면 끝난다.

스프라이트를 다시 그리면 이 스크립트로 아이콘도 같이 다시 만든다.
"""
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QImage

# 셀 안에서 얼굴이 차지하는 자리(현재 5등신 스프라이트 기준, 셀 크기에 대한 비율)
FACE_X, FACE_Y, FACE_SIDE = 217 / 768, 0.0, 220 / 768
SIZES = (256, 128, 64, 48, 32, 16)


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    src, out = sys.argv[1], sys.argv[2]

    QGuiApplication(sys.argv)
    sheet = QImage(src)
    if sheet.isNull():
        print("스프라이트를 못 읽었다: %s" % src, file=sys.stderr)
        return 1

    cw, ch = sheet.width() // 8, sheet.height() // 11
    cell = sheet.copy(0, 0, cw, ch)
    side = int(cw * FACE_SIDE)
    face = cell.copy(int(cw * FACE_X), int(ch * FACE_Y), side, side)

    pngs = []
    for size in SIZES:
        im = face.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.WriteOnly)
        im.save(buf, "PNG")
        buf.close()
        pngs.append((size, bytes(ba)))

    header = struct.pack("<HHH", 0, 1, len(pngs))   # reserved, type=icon, count
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        d = 0 if size >= 256 else size              # 256은 0으로 적는 게 규격
        entries += struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data

    with open(out, "wb") as f:
        f.write(header + entries + blobs)
    print("%s (%d bytes, %s)" % (out, offset, "·".join(str(s) for s in SIZES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
