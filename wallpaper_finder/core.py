"""Videolardan duvar kağıdı / arka plan olarak kullanılabilecek kareleri bulur.

Akış:
  1. Videodan belirli aralıklarla kare örnekle (hızlı, küçültülmüş) ve ucuz metrikleri ölç
     (netlik, parlaklık, gren/pürüzsüzlük, detay yoğunluğu, renk canlılığı).
  2. Karanlık / düşük kontrastlı / neredeyse aynı kareleri ele.
  3. YOLO ile insan tespiti: ana özneyi bul (büyüklük, konum, netlik).
  4. CLIP ile kullanıcının seçtiği stile (styles.py) benzerlik puanı.
  5. Profil ağırlıklarıyla puanları birleştir, birbirine benzemeyen en iyi K kareyi seç.
  6. Tam çözünürlükte kaydet + özneye ortalanmış kırpımlar üret.
"""

from __future__ import annotations

import io
import json
import math
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .styles import Preferences, Profile, build_profile

ProgressFn = Callable[[float, str], None]


@dataclass
class Settings:
    interval: float = 0.5          # kaç saniyede bir kare örneklenecek
    top_k: int = 20                # kaç sonuç dönecek
    min_gap: float = 2.0           # seçilen kareler arası min. saniye
    min_brightness: float = 18.0   # 0-255, altı "siyah ekran" sayılır
    dedupe_threshold: int = 6      # dHash Hamming mesafesi, altı "aynı kare"
    candidate_pool: int = 150      # CLIP'e gidecek aday sayısı
    use_clip: bool = True
    crops: tuple[str, ...] | None = None  # None = kullanım yerine göre (Preferences.use)
    yolo_model: str = str(Path(__file__).resolve().parent.parent / "modeller" / "yolo11s.pt")  # yoksa otomatik iner
    device: str = ""               # "" = otomatik (cuda varsa cuda)
    prefs: Preferences = field(default_factory=Preferences)
    denoise: bool = False          # kaydederken greni azalt (yavaş)

    @property
    def profile(self) -> Profile:
        if getattr(self, "_profile_key", None) != repr(self.prefs):
            self._profile = build_profile(self.prefs)
            self._profile_key = repr(self.prefs)
        return self._profile


@dataclass
class Candidate:
    t: float
    frame_idx: int
    sharpness: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    noise: float = 0.0             # gren tahmini (düşük = pürüzsüz)
    edges: float = 0.0             # kenar yoğunluğu (düşük = sade/minimal)
    colorfulness: float = 0.0
    dhash: int = 0
    # özne
    person_box: tuple[float, float, float, float] | None = None  # normalize x1,y1,x2,y2
    person_conf: float = 0.0
    person_count: int = 0
    person_area_max: float = 0.0
    subject_sharpness: float = 0.0
    subject_score: float = 0.0
    clip_score: float = 0.0
    clip_emb: np.ndarray | None = field(default=None, repr=False)
    thumb: bytes = field(default=b"", repr=False)  # analiz için küçültülmüş JPEG
    score: float = 0.0
    files: dict = field(default_factory=dict)


# ---------------------------------------------------------------- yardımcılar

def _dhash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


_NOISE_K = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)


def _noise(gray: np.ndarray) -> float:
    """Immerkær gürültü tahmini: görüntüdeki gren/kumlanma miktarı."""
    h, w = gray.shape
    conv = cv2.filter2D(gray.astype(np.float32), -1, _NOISE_K)
    return float(np.abs(conv[1:-1, 1:-1]).sum() * math.sqrt(math.pi / 2) / (6 * (w - 2) * (h - 2)))


def _colorfulness(bgr: np.ndarray) -> float:
    """Hasler & Süsstrunk renk canlılığı ölçüsü."""
    b, g, r = [x.astype(np.float32) for x in cv2.split(bgr)]
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))


def _norm(values: np.ndarray) -> np.ndarray:
    """Değerleri yüzdelik sıraya göre 0-1 aralığına çeker (aykırı değerlere dayanıklı)."""
    if len(values) == 0:
        return values
    lo, hi = np.percentile(values, 5), np.percentile(values, 95)
    if hi - lo < 1e-9:
        return np.full_like(values, 0.5, dtype=float)
    return np.clip((values - lo) / (hi - lo), 0, 1)


def _device(pref: str) -> str:
    if pref:
        return pref
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def download_video(url: str, out_dir: Path, progress: ProgressFn | None = None) -> Path:
    """yt-dlp ile videoyu indirir (en iyi kalite, mp4)."""
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress(0.1 * d.get("downloaded_bytes", 0) / total, "Video indiriliyor...")

    opts = {
        "format": "bv*[height<=2160]+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(title).80s [%(id)s].%(ext)s"),
        "progress_hooks": [hook],
        "quiet": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        path = path.with_suffix(".mp4")
    return path


def _imwrite(path: Path, img: np.ndarray) -> None:
    # cv2.imwrite Windows'ta Türkçe/Almanca karakterli yollarda sessizce başarısız olur
    ok, buf = cv2.imencode(path.suffix, img)
    if ok:
        path.write_bytes(buf.tobytes())


def probe(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
         "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    d = json.loads(out.stdout)
    st = d["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) in (90, 270):  # telefonda dikey çekilmiş videolar
        w, h = h, w
    num, den = st.get("r_frame_rate", "30/1").split("/")
    return {"width": w, "height": h, "fps": float(num) / float(den or 1),
            "duration": float(d.get("format", {}).get("duration", 0) or 0)}


# ---------------------------------------------------------------- aşamalar

SAMPLE_SIDE = 960  # analiz kareleri bu boyuta küçültülür


def sample_frames(video: Path, s: Settings, progress: ProgressFn | None = None) -> tuple[list[Candidate], dict]:
    """ffmpeg ile tek geçişte, istenen aralıkta küçültülmüş kareleri okur."""
    meta = probe(video)
    W, H = meta["width"], meta["height"]
    sc = SAMPLE_SIDE / max(W, H)
    ow, oh = int(round(W * sc / 2)) * 2, int(round(H * sc / 2)) * 2
    # fps filtresi yerine select: kareler gerçek zaman damgalarıyla gelir, showinfo bunları stderr'e yazar.
    # (fps filtresi etiketten farklı kare verebiliyor; strobe ışıklı kliplerde bu tamamen başka bir kare demek.)
    cmd = [
        "ffmpeg", "-v", "info", "-nostats", "-hwaccel", "auto", "-i", str(video),
        "-vf", f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{s.interval * 0.999})',"
               f"scale={ow}:{oh}:flags=area,showinfo",
        "-fps_mode", "passthrough", "-an",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=ow * oh * 3 * 4)
    times: list[float] = []

    def read_times():
        for line in io.TextIOWrapper(proc.stderr, encoding="utf-8", errors="ignore"):
            m = re.search(r"pts_time:\s*([-\d.]+)", line)
            if m and "Parsed_showinfo" in line:
                times.append(float(m.group(1)))

    reader = threading.Thread(target=read_times, daemon=True)
    reader.start()
    size = ow * oh * 3
    cands: list[Candidate] = []
    last_hash = None
    i = 0
    while True:
        raw = proc.stdout.read(size)
        if len(raw) < size:
            break
        frame = np.frombuffer(raw, np.uint8).reshape(oh, ow, 3)
        # showinfo satırı kare stdout'a yazılmadan önce basılır; nadiren geride kalırsa kısa bekle
        for _ in range(50):
            if len(times) > i:
                break
            time.sleep(0.01)
        t = times[i] if len(times) > i else i * s.interval
        i += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        c = Candidate(t=t, frame_idx=int(round(t * meta["fps"])))
        c.brightness = float(gray.mean())
        c.contrast = float(gray.std())
        c.sharpness = _sharpness(cv2.resize(gray, None, fx=2 / 3, fy=2 / 3, interpolation=cv2.INTER_AREA))
        c.dhash = _dhash(gray)
        small = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        c.noise = _noise(small)
        c.edges = float((cv2.Canny(small, 60, 160) > 0).mean())
        c.colorfulness = _colorfulness(cv2.resize(frame, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA))
        dup = last_hash is not None and _hamming(c.dhash, last_hash) < s.dedupe_threshold
        if c.brightness >= s.min_brightness and c.contrast > 8 and not dup:
            c.thumb = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
            cands.append(c)
            last_hash = c.dhash
        if progress and i % 10 == 0 and meta["duration"]:
            progress(0.05 + 0.35 * min(1, t / meta["duration"]),
                     f"Kareler taranıyor... {t:.0f}s / {meta['duration']:.0f}s")
    proc.wait()
    reader.join(timeout=2)
    if i == 0:
        raise RuntimeError(f"Video okunamadı: {video}")
    return cands, meta


def _thumb(c: Candidate) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(c.thumb, np.uint8), cv2.IMREAD_COLOR)


def grab_full(video: Path, t: float) -> np.ndarray | None:
    """Tam çözünürlükte tek kare (ffmpeg doğru konuma seek eder)."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t - 0.001):.4f}", "-i", str(video), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True,
    )
    if not out.stdout:
        return None
    return cv2.imdecode(np.frombuffer(out.stdout, np.uint8), cv2.IMREAD_COLOR)


def detect_subjects(video: Path, cands: list[Candidate], s: Settings, progress: ProgressFn | None = None) -> None:
    from ultralytics import YOLO

    model = YOLO(s.yolo_model)
    device = _device(s.device)
    batch = 16
    for b in range(0, len(cands), batch):
        chunk = cands[b:b + batch]
        imgs = [_thumb(c) for c in chunk]
        results = model.predict(imgs, classes=[0], conf=0.25, device=device, verbose=False, imgsz=640)
        for c, img, r in zip(chunk, imgs, results):
            _score_subject(c, img, r, s.profile.area)
        if progress:
            progress(0.4 + 0.35 * (b + len(chunk)) / len(cands), f"Özne aranıyor... {b + len(chunk)}/{len(cands)}")


def _score_subject(c: Candidate, img: np.ndarray, r, target_area: float = 0.15) -> None:
    H, W = img.shape[:2]
    boxes = r.boxes
    if boxes is None or len(boxes) == 0:
        return
    xyxy = boxes.xyxy.cpu().numpy()
    conf = boxes.conf.cpu().numpy()
    best, best_s = None, 0.0
    big = 0
    for (x1, y1, x2, y2), cf in zip(xyxy, conf):
        bw, bh = (x2 - x1) / W, (y2 - y1) / H
        area = bw * bh
        if area > 0.02:
            big += 1
        c.person_area_max = max(c.person_area_max, float(area))
        cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
        # ideal: stilin hedef büyüklüğüne yakın, yatayda ortaya yakın, alt kenara yapışık "seyirci kafası" değil
        size_s = math.exp(-((math.log(max(area, 1e-4)) - math.log(target_area)) ** 2) / 1.2)
        center_s = 1 - min(1, abs(cx - 0.5) * 1.6)
        crowd_pen = 0.35 if (y1 / H > 0.6 and bh < 0.4) else 1.0  # alt kısımdaki kafa kalabalığı
        sc = cf * (0.55 * size_s + 0.45 * center_s) * crowd_pen
        if sc > best_s:
            best_s, best = sc, (x1, y1, x2, y2, cf)
    if best is None:
        return
    x1, y1, x2, y2, cf = best
    c.person_box = (float(x1 / W), float(y1 / H), float(x2 / W), float(y2 / H))
    c.person_conf = float(cf)
    c.person_count = big
    roi = img[int(y1):int(y2), int(x1):int(x2)]
    if roi.size:
        g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, (256, int(256 * g.shape[0] / max(g.shape[1], 1)) or 1))
        c.subject_sharpness = _sharpness(g)
    many_pen = 1.0 if big <= 2 else max(0.4, 1 - 0.12 * (big - 2))
    c.subject_score = best_s * many_pen


def clip_scores(video: Path, cands: list[Candidate], s: Settings, progress: ProgressFn | None = None) -> None:
    import open_clip
    import torch
    from PIL import Image

    device = _device(s.device)
    prof = s.profile
    model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k", device=device)
    tok = open_clip.get_tokenizer("ViT-B-32")
    model.eval()
    with torch.no_grad():
        t = model.encode_text(tok(prof.pos + prof.neg).to(device))
        t = t / t.norm(dim=-1, keepdim=True)
    npos = len(prof.pos)

    batch = 32
    for b in range(0, len(cands), batch):
        valid = cands[b:b + batch]
        ims = torch.stack([
            preprocess(Image.fromarray(cv2.cvtColor(_thumb(c), cv2.COLOR_BGR2RGB))) for c in valid
        ]).to(device)
        with torch.no_grad():
            e = model.encode_image(ims)
            e = e / e.norm(dim=-1, keepdim=True)
            probs = (100 * e @ t.T).softmax(dim=-1).cpu().numpy()
        for c, p, emb in zip(valid, probs, e.cpu().numpy()):
            c.clip_score = float(p[:npos].sum())
            c.clip_emb = emb
        if progress:
            progress(0.75 + 0.15 * (b + len(valid)) / len(cands), f"Estetik puanlanıyor... {b + len(valid)}/{len(cands)}")


def combine(cands: list[Candidate], s: Settings) -> None:
    """Profil ağırlıklarıyla tüm metrikleri tek puanda birleştirir (0-1 civarı)."""
    if not cands:
        return
    prof = s.profile
    w = dict(prof.w)
    if not s.use_clip:
        w.pop("clip", None)
    total = sum(w.values()) or 1.0
    bright = np.array([c.brightness for c in cands])
    color = np.array([c.colorfulness for c in cands])
    f = {
        "subject": np.array([c.subject_score for c in cands]),
        "subject_sharp": _norm(np.log1p([c.subject_sharpness for c in cands])),
        "sharp": _norm(np.log1p([c.sharpness for c in cands])),
        "contrast": _norm(np.array([c.contrast for c in cands])),
        "clip": np.array([c.clip_score for c in cands]),
        "smooth": 1 - _norm(np.array([c.noise for c in cands])),
        "simple": 1 - _norm(np.array([c.edges for c in cands])),
        "color": _norm(color),
        "mono": 1 - np.clip(color / 25, 0, 1),
        "dark": np.exp(-((bright - 55) / 40) ** 2),
        "bright": np.exp(-((bright - 150) / 50) ** 2),
    }
    for i, c in enumerate(cands):
        has_person = 1.0 if c.person_box else 0.0
        sc = 0.0
        for k, wk in w.items():
            v = f[k][i]
            if k == "subject_sharp":
                v *= has_person
            sc += wk * v
        sc /= total
        if prof.people == "gerekli" and not has_person:
            sc *= 0.4
        elif prof.people == "olmasın" and c.person_area_max > 0.01:
            sc *= max(0.15, 1 - 6 * c.person_area_max)
        c.score = float(sc)


def select(cands: list[Candidate], s: Settings) -> list[Candidate]:
    chosen: list[Candidate] = []
    for c in sorted(cands, key=lambda c: c.score, reverse=True):
        if any(abs(c.t - o.t) < s.min_gap for o in chosen):
            continue
        if any(_hamming(c.dhash, o.dhash) < s.dedupe_threshold + 4 for o in chosen):
            continue
        if c.clip_emb is not None and any(
            o.clip_emb is not None and float(c.clip_emb @ o.clip_emb) > 0.95 for o in chosen
        ):
            continue
        chosen.append(c)
        if len(chosen) >= s.top_k:
            break
    return chosen


def _crop_box(W: int, H: int, ratio: float, box_n) -> tuple[int, int, int, int] | None:
    """Verilen en/boy oranında, özneyi ortalayan en büyük kırpımı döndürür."""
    if W / H > ratio:
        cw, ch = int(H * ratio), H
    else:
        cw, ch = W, int(W / ratio)
    if cw < 300 or ch < 300:
        return None
    if box_n:
        cx = (box_n[0] + box_n[2]) / 2 * W
        cy = (box_n[1] * 0.7 + box_n[3] * 0.3) * H  # biraz yukarı (yüz/üst gövde) odaklan
    else:
        cx, cy = W / 2, H / 2
    x = int(min(max(cx - cw / 2, 0), W - cw))
    y = int(min(max(cy - ch / 2, 0), H - ch))
    return x, y, cw, ch


def export(video: Path, chosen: list[Candidate], out_dir: Path, s: Settings) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ratios = {"9:16": 9 / 16, "16:9": 16 / 9, "4:5": 4 / 5, "1:1": 1.0}
    for rank, c in enumerate(chosen, 1):
        img = grab_full(video, c.t)
        if img is None:
            img = _thumb(c)
        if s.denoise:
            img = cv2.fastNlMeansDenoisingColored(img, None, 4, 4, 7, 21)
        mm, ss = divmod(int(c.t), 60)
        base = f"{rank:02d}_{mm:02d}m{ss:02d}s"
        p = out_dir / f"{base}_full.png"
        _imwrite(p, img)
        c.files["full"] = str(p)
        H, W = img.shape[:2]
        box_n = c.person_box if s.profile.people != "olmasın" else None
        for name in (s.crops if s.crops is not None else s.profile.crops):
            box = _crop_box(W, H, ratios[name], box_n)
            if not box:
                continue
            x, y, cw, ch = box
            if abs(cw / ch - W / H) < 0.01:
                continue  # zaten bu oranda
            p = out_dir / f"{base}_{name.replace(':', 'x')}.png"
            _imwrite(p, img[y:y + ch, x:x + cw])
            c.files[name] = str(p)
    report = [
        {k: v for k, v in asdict(c).items() if k not in ("clip_emb", "dhash", "thumb")} for c in chosen
    ]
    doc = {"tercihler": asdict(s.prefs), "kareler": report}
    (out_dir / "sonuclar.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False, default=float), encoding="utf-8")


def find_wallpapers(video: str | Path, out_dir: str | Path, s: Settings | None = None,
                    progress: ProgressFn | None = None) -> list[Candidate]:
    s = s or Settings()
    video = Path(video)
    out_dir = Path(out_dir)
    p = progress or (lambda *_: None)

    p(0.1, "Kareler taranıyor...")
    cands, meta = sample_frames(video, s, p)
    if not cands:
        return []

    p(0.4, f"{len(cands)} aday kare. Özne aranıyor...")
    detect_subjects(video, cands, s, p)

    # CLIP pahalı: önce ucuz puanla sırala, en iyi havuzu CLIP'e gönder
    s_clip = s.use_clip
    s.use_clip = False
    combine(cands, s)
    s.use_clip = s_clip
    pool = sorted(cands, key=lambda c: c.score, reverse=True)[:max(s.candidate_pool, s.top_k)]
    if s.use_clip:
        clip_scores(video, pool, s, p)
    combine(pool, s)

    p(0.9, "En iyiler seçiliyor ve kaydediliyor...")
    chosen = select(pool, s)
    export(video, chosen, out_dir, s)
    p(1.0, f"Bitti: {len(chosen)} kare kaydedildi.")
    return chosen
