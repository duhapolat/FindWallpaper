"""Komut satırı kullanımı:

    python bul.py video.mp4 --sor                     # önce ne tarz wallpaper istediğini sorar
    python bul.py video.mp4 --stil manzara,neon --ruh karanlık --kullanim telefon
    python bul.py "https://youtube.com/watch?v=..." -k 30 --aralik 0.25
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from wallpaper_finder import (CLEAN, MOODS, PEOPLE, STYLES, USES, Preferences, Settings,
                              ask_cli, download_video, find_wallpapers)

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".avi"}
USE_ALIASES = {"telefon": "telefon (9:16)", "youtube": "YouTube / masaüstü (16:9)",
               "masaustu": "YouTube / masaüstü (16:9)", "instagram": "Instagram (4:5)", "hepsi": "hepsi"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Videodan duvar kağıdı olacak kareleri bul")
    ap.add_argument("girdi", nargs="+", help="Video dosyası/klasörü veya YouTube linki")
    ap.add_argument("-o", "--cikti", default=os.environ.get("FINDWALLPAPER_OUT", "cikti"), help="Çıktı klasörü (varsayılan: cikti)")
    ap.add_argument("-k", "--adet", type=int, default=20, help="Video başına kaç kare")
    ap.add_argument("--aralik", type=float, default=0.5, help="Kaç saniyede bir kare incelensin")

    g = ap.add_argument_group("ne tarz wallpaper istiyorsun?")
    g.add_argument("--sor", action="store_true", help="Tercihleri adım adım sor")
    g.add_argument("--stil", default="sanatci", help=f"Virgülle: {','.join(STYLES)}")
    g.add_argument("--ruh", default="fark etmez", choices=list(MOODS), help="Ruh hali / renk")
    g.add_argument("--insan", default="stile göre", choices=PEOPLE, help="Görüntüde insan")
    g.add_argument("--doku", default="fark etmez", choices=CLEAN, help="Gren / pürüzsüzlük")
    g.add_argument("--kullanim", default="hepsi", choices=list(USE_ALIASES), help="Kırpımlar buna göre seçilir")
    g.add_argument("--tarif", default="", help="Serbest tarif (İngilizce en iyisi), ör. 'red lasers, foggy stage'")

    ap.add_argument("--kirpim", default=None, help="Kırpımları elle ver (9:16,16:9,4:5,1:1) ya da 'yok'")
    ap.add_argument("--gren-temizle", action="store_true", help="Kaydederken greni azalt (yavaş)")
    ap.add_argument("--clip-yok", action="store_true", help="Estetik (CLIP) puanlamayı kapat (daha hızlı)")
    a = ap.parse_args()

    if a.sor:
        prefs = ask_cli()
    else:
        styles = [x.strip() for x in a.stil.split(",") if x.strip()]
        bad = [x for x in styles if x not in STYLES]
        if bad:
            ap.error(f"bilinmeyen stil: {', '.join(bad)} (seçenekler: {', '.join(STYLES)})")
        prefs = Preferences(styles=styles, mood=a.ruh, people=a.insan, clean=a.doku,
                            use=USE_ALIASES[a.kullanim], extra=a.tarif)

    crops = None
    if a.kirpim:
        crops = tuple() if a.kirpim == "yok" else tuple(x.strip() for x in a.kirpim.split(","))
    s = Settings(interval=a.aralik, top_k=a.adet, use_clip=not a.clip_yok, crops=crops,
                 prefs=prefs, denoise=a.gren_temizle)

    print("\nStil:", ", ".join(STYLES[k]["label"] for k in prefs.styles),
          f"| ruh hali: {prefs.mood} | insan: {prefs.people} | doku: {prefs.clean} | kullanım: {prefs.use}"
          + (f" | tarif: {prefs.extra}" if prefs.extra else ""))

    videos: list[Path] = []
    for item in a.girdi:
        if item.startswith("http"):
            videos.append(download_video(item, Path(os.environ.get("FINDWALLPAPER_DOWNLOADS", "indirilenler"))))
        elif Path(item).is_dir():
            videos += sorted(p for p in Path(item).iterdir() if p.suffix.lower() in VIDEO_EXT)
        else:
            videos.append(Path(item))

    def prog(f, msg):
        sys.stdout.write(f"\r[{f * 100:5.1f}%] {msg:<60}")
        sys.stdout.flush()

    for v in videos:
        print(f"\n== {v.name}")
        out = Path(a.cikti) / v.stem[:80]
        chosen = find_wallpapers(v, out, s, prog)
        print()
        for i, c in enumerate(chosen, 1):
            print(f"  {i:2d}. {int(c.t // 60):02d}:{int(c.t % 60):02d}  puan={c.score:.3f}")
        print(f"  -> {out.resolve()}")


if __name__ == "__main__":
    main()
