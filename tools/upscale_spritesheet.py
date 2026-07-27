#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스프라이트시트 고해상 업스케일.

원본 애니 프레임이 192x208밖에 없어서 오버레이를 크게 키우면 흐려진다.
셀 단위로 초해상 모델을 돌려 고해상 시트를 만들어 두면 어느 크기에서도 선명하다.

  python3 tools/upscale_spritesheet.py \
      --src pets/current-yui/spritesheet.png \
      --dst spritesheet-4x.png \
      --model 4x-AnimeSharp.pth --scale 4

모델 비교 결과(2026-07-25, 유이 v2 시트 기준):
  4x-AnimeSharp          선(線)과 미세 디테일 보존이 가장 좋음 — 채택
  4x_foolhardy_Remacri   비슷하나 미세 노이즈가 있어 평면적인 애니 그림엔 과함
  RealESRGAN_x4plus      전반적으로 무름, 눈 하이라이트 약함
  RealESRGAN_anime_6B    선은 매끈하나 눈 하이라이트·리본 매듭·옷 음영을 뭉갬

주의: 결과 파일명에 '@2x'/'@4x' 같은 접미사를 쓰지 말 것. Qt가 고밀도 에셋으로
      인식해 devicePixelRatio를 올려 버려 그림이 1/N 크기로 그려진다. '-4x'를 쓴다.

필요 패키지: torch(CUDA), spandrel, pillow, numpy
"""
import argparse
import os

import numpy as np
import torch
from PIL import Image
from spandrel import ModelLoader

CELL_W, CELL_H = 192, 208
SHEET_COLS, SHEET_ROWS = 8, 11


def bleed(rgb, alpha, iters=8):
    """불투명 픽셀 색을 투명 영역으로 확산시킨다.

    투명 픽셀의 RGB는 보통 검정이라, 그대로 확대하면 캐릭터 외곽에 검은 테두리가 생긴다.
    """
    rgb = rgb.astype(np.float32).copy()
    known = alpha > 0
    for _ in range(iters):
        if known.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(known.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc += np.roll(rgb, (dy, dx), (0, 1)) * np.roll(known, (dy, dx), (0, 1)).astype(np.float32)[..., None]
            cnt += np.roll(known, (dy, dx), (0, 1)).astype(np.float32)
        fill = (~known) & (cnt > 0)
        rgb[fill] = acc[fill] / cnt[fill][..., None]
        known = known | fill
    return rgb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="원본 시트(1x, 1536x2288)")
    ap.add_argument("--dst", required=True, help="출력 시트 (파일명에 @Nx 쓰지 말 것)")
    ap.add_argument("--model", required=True, help="초해상 모델 .pth")
    ap.add_argument("--scale", type=int, default=4, help="출력 배율(모델 배율 이하)")
    args = ap.parse_args()

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ModelLoader().load_from_file(args.model).eval().to(dev)
    print(f"model x{model.scale} on {dev}")

    @torch.no_grad()
    def run(arr3):
        t = torch.from_numpy(arr3).permute(2, 0, 1).unsqueeze(0).to(dev)
        return model(t).clamp(0, 1).squeeze(0).permute(1, 2, 0).cpu().numpy()

    sheet = np.array(Image.open(args.src).convert("RGBA"))
    ow, oh = CELL_W * args.scale, CELL_H * args.scale
    out = Image.new("RGBA", (ow * SHEET_COLS, oh * SHEET_ROWS), (0, 0, 0, 0))

    done = 0
    for r in range(SHEET_ROWS):
        for c in range(SHEET_COLS):
            cell = sheet[r * CELL_H:(r + 1) * CELL_H, c * CELL_W:(c + 1) * CELL_W]
            a = cell[..., 3]
            if not a.any():          # 빈 셀은 투명 그대로
                continue
            rgb = run(bleed(cell[..., :3], a) / 255.0)
            # 알파도 같은 모델로 확대해야 외곽선이 RGB와 정확히 맞는다
            al = run(np.repeat((a.astype(np.float32) / 255.0)[..., None], 3, axis=2))[..., :1]
            img = Image.fromarray(
                (np.concatenate([rgb, al], axis=2) * 255).round().clip(0, 255).astype(np.uint8), "RGBA")
            if img.size != (ow, oh):     # 모델 배율 > 요청 배율이면 축소
                img = img.resize((ow, oh), Image.LANCZOS)
            out.paste(img, (c * ow, r * oh))
            done += 1
            print(f"\rcells {done}", end="", flush=True)

    out.save(args.dst, "PNG", optimize=True)
    print(f"\nsaved {args.dst} {out.size} ({done} cells)")


if __name__ == "__main__":
    main()
