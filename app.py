"""Tarayıcıda açılan arayüz:  python app.py  (ya da baslat.bat)"""

import os
import shutil
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import gradio as gr

from wallpaper_finder import (CLEAN, MOODS, PEOPLE, STYLES, USES, Preferences, Settings,
                              download_video, find_wallpapers)

ROOT = Path(__file__).parent
# Kurulu sürümde başlatıcı bunları kullanıcının Resimler / Videolar klasörüne yönlendirir
OUT = Path(os.environ.get("FINDWALLPAPER_OUT") or ROOT / "cikti")
DOWNLOADS = Path(os.environ.get("FINDWALLPAPER_DOWNLOADS") or ROOT / "indirilenler")


def run(video_file, link, styles, mood, people, clean, use, extra,
        adet, aralik, estetik, denoise, gorunum, progress=gr.Progress()):
    def prog(f, msg):
        progress(f, desc=msg)

    if not styles:
        raise gr.Error("En az bir görüntü tarzı seç.")
    if link and link.strip():
        link = link.strip().strip('"')
        if Path(link).is_file():
            video = Path(link)
        elif link.startswith("http"):
            progress(0, desc="Video indiriliyor...")
            video = download_video(link, DOWNLOADS, prog)
        else:
            raise gr.Error("Link ya da dosya yolu geçersiz.")
    elif video_file:
        video = Path(video_file)
    else:
        raise gr.Error("Bir video yükle ya da YouTube linki / dosya yolu yapıştır.")

    prefs = Preferences(styles=list(styles), mood=mood, people=people, clean=clean, use=use, extra=extra or "")
    s = Settings(interval=aralik, top_k=int(adet), use_clip=estetik, prefs=prefs, denoise=denoise)
    out = OUT / video.stem[:80]
    if out.exists():
        shutil.rmtree(out)
    chosen = find_wallpapers(video, out, s, prog)
    if not chosen:
        raise gr.Error("Uygun kare bulunamadı (video çok karanlık olabilir ya da seçtiğin tarza uyan sahne yok).")

    items = []
    for i, c in enumerate(chosen, 1):
        f = c.files.get(gorunum) or c.files["full"]
        mm, ss = divmod(int(c.t), 60)
        items.append((f, f"#{i}  {mm:02d}:{ss:02d}  puan {c.score:.2f}"))
    zip_path = shutil.make_archive(str(out), "zip", out)
    tarz = ", ".join(STYLES[k]["label"] for k in prefs.styles)
    return items, zip_path, f"✅ **{len(chosen)} kare** kaydedildi ({tarz}) → `{out}`"


style_choices = [(f"{v['label']} — {v['desc']}", k) for k, v in STYLES.items()]

with gr.Blocks(title="Duvar Kağıdı Bulucu") as demo:
    gr.Markdown("# 🎬 Videodan duvar kağıdı bul\n"
                "Önce nasıl görüntüler istediğini seç, sonra videoyu ver. "
                "Seçimlerine göre en uygun kareler bulunup kırpılır.")
    with gr.Row():
        with gr.Column(scale=1):
            with gr.Group():
                gr.Markdown("### 1 · Nasıl wallpaper istiyorsun?")
                styles = gr.CheckboxGroup(style_choices, value=["sanatci"], label="Görüntü tarzı (birden fazla seçebilirsin)")
                mood = gr.Radio(list(MOODS), value="fark etmez", label="Ruh hali / renk")
                people = gr.Radio(PEOPLE, value="stile göre", label="Görüntüde insan")
                clean = gr.Radio(CLEAN, value="fark etmez", label="Doku")
                use = gr.Radio(list(USES), value="hepsi", label="Nerede kullanacaksın? (kırpımlar buna göre)")
                extra = gr.Textbox(label="Eklemek istediğin tarif (isteğe bağlı, İngilizce en iyi sonucu verir)",
                                   placeholder="ör. red lasers, foggy stage, ufo")
            with gr.Group():
                gr.Markdown("### 2 · Video")
                video = gr.Video(label="Video yükle", sources=["upload"])
                link = gr.Textbox(label="…ya da YouTube linki / dosya yolu",
                                  placeholder="https://youtube.com/watch?v=...  veya  C:\\Videolar\\konser.mp4")
            with gr.Accordion("Gelişmiş ayarlar", open=False):
                adet = gr.Slider(4, 60, value=20, step=1, label="Kaç kare bulunsun")
                aralik = gr.Slider(0.2, 3, value=0.5, step=0.1, label="Kaç saniyede bir incelensin (küçük = daha detaylı, daha yavaş)")
                estetik = gr.Checkbox(True, label="Tarz benzerliği (CLIP) — kapatırsan daha hızlı ama tarz seçimi zayıflar")
                denoise = gr.Checkbox(False, label="Kaydederken greni azalt (yavaş)")
                gorunum = gr.Radio([("Tam kare", "full"), ("9:16", "9:16"), ("16:9", "16:9"), ("4:5", "4:5")],
                                   value="full", label="Galeride göster")
            btn = gr.Button("Kareleri bul", variant="primary", size="lg")
        with gr.Column(scale=2):
            status = gr.Markdown()
            gallery = gr.Gallery(label="Sonuçlar (en iyiden kötüye)", columns=4, height=760, object_fit="contain", preview=False)
            zip_file = gr.File(label="Hepsini indir (.zip)")

    btn.click(run, [video, link, styles, mood, people, clean, use, extra, adet, aralik, estetik, denoise, gorunum],
              [gallery, zip_file, status])


if __name__ == "__main__":
    demo.queue().launch(inbrowser=not os.environ.get("NO_BROWSER"), allowed_paths=[str(OUT)])
