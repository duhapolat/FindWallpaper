"""Kullanıcının "nasıl bir wallpaper istiyorum" cevaplarını puanlama profiline çevirir.

Her stil; CLIP istemleri, insan kuralı, ideal özne büyüklüğü ve metrik ağırlıklarından oluşur.
Birden fazla stil seçilirse istemler birleşir, ağırlıkların ortalaması alınır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# people: "gerekli" = ana planda insan olmalı, "olmasın" = büyük insan figürü cezalandırılır,
#         "fark etmez" = insan puana katkı verir ama şart değil
STYLES: dict[str, dict] = {
    "sanatci": {
        "label": "Sanatçı / konser sahnesi",
        "desc": "Sanatçı ana planda, sahne ışıkları, mikrofon",
        "pos": [
            "a cinematic concert photo of a rapper performing on stage",
            "a high quality live music photograph of an artist holding a microphone",
            "an aesthetic moody wallpaper of a performer under stage lights",
        ],
        "neg": ["a crowd of people holding up phones", "a close-up of the audience", "an empty stage with no people"],
        "people": "gerekli", "area": 0.15,
        "w": {"subject": 0.30, "subject_sharp": 0.20, "sharp": 0.10, "contrast": 0.05, "clip": 0.35},
    },
    "portre": {
        "label": "Portre / yakın plan",
        "desc": "Yüz ve üst gövde kadrajı dolduruyor",
        "pos": [
            "a close-up portrait photo of a man's face",
            "a cinematic portrait of a rapper, shallow depth of field",
            "a detailed headshot with dramatic lighting",
        ],
        "neg": ["a wide shot of a stage", "a small person far away", "a crowd of people"],
        "people": "gerekli", "area": 0.40,
        "w": {"subject": 0.30, "subject_sharp": 0.30, "sharp": 0.05, "contrast": 0.05, "clip": 0.30},
    },
    "siluet": {
        "label": "Siluet & atmosfer",
        "desc": "Arkadan ışık, sis/duman, karanlık ve gizemli",
        "pos": [
            "a dark silhouette of a person backlit by a bright light in fog",
            "a moody cinematic silhouette with smoke and haze",
            "a lone figure standing in mist under a spotlight",
        ],
        "neg": ["a brightly lit evenly exposed photo", "a crowd of people holding up phones"],
        "people": "gerekli", "area": 0.10,
        "w": {"subject": 0.20, "subject_sharp": 0.05, "sharp": 0.05, "contrast": 0.15, "clip": 0.45, "dark": 0.10},
    },
    "sahne": {
        "label": "Sahne & ışık şovu",
        "desc": "Lazerler, sahne dekoru, ışık hüzmeleri (insan şart değil)",
        "pos": [
            "a concert stage with laser beams and stage lights in smoke",
            "a dramatic stage design with spotlights and fog",
            "a futuristic spaceship stage set lit by beams of light",
        ],
        "neg": ["a blurry low quality photo", "a close-up of the audience", "a screenshot with text"],
        "people": "fark etmez", "area": 0.08,
        "w": {"subject": 0.05, "subject_sharp": 0.0, "sharp": 0.10, "contrast": 0.15, "clip": 0.55, "color": 0.15},
    },
    "manzara": {
        "label": "Manzara / şehir / doğa",
        "desc": "Gökyüzü, şehir ışıkları, yol, doğa — insansız geniş kadraj",
        "pos": [
            "a beautiful landscape photograph, wide shot",
            "a city skyline at night with lights",
            "a scenic view of nature, sky and clouds",
            "an empty road or street at night, cinematic",
        ],
        "neg": ["a close-up of a person", "a portrait of a man", "a crowd of people", "an indoor room"],
        "people": "olmasın", "area": 0.0,
        "w": {"subject": 0.0, "subject_sharp": 0.0, "sharp": 0.15, "contrast": 0.10, "clip": 0.60, "smooth": 0.15},
    },
    "minimal": {
        "label": "Pürüzsüz / minimal",
        "desc": "Sade, az detaylı, temiz geçişler — üstüne yazı koymaya uygun",
        "pos": [
            "a minimal clean wallpaper with lots of empty space",
            "a smooth soft gradient background",
            "a simple aesthetic photo with negative space",
        ],
        "neg": ["a busy cluttered scene with many objects", "a noisy grainy photo", "a crowd of people"],
        "people": "fark etmez", "area": 0.10,
        "w": {"subject": 0.05, "subject_sharp": 0.0, "sharp": 0.0, "contrast": 0.0, "clip": 0.40,
              "smooth": 0.30, "simple": 0.25},
    },
    "neon": {
        "label": "Neon & renkli",
        "desc": "Canlı renkler, neon ışıklar, renkli sis",
        "pos": [
            "a vibrant neon lit scene with colorful lights",
            "a colorful aesthetic wallpaper with purple and blue light",
            "a vivid photo with saturated neon colors",
        ],
        "neg": ["a black and white photo", "a dull grey washed out photo"],
        "people": "fark etmez", "area": 0.12,
        "w": {"subject": 0.10, "subject_sharp": 0.05, "sharp": 0.05, "contrast": 0.05, "clip": 0.45, "color": 0.30},
    },
}

# Her zaman istemediğimiz şeyler
BASE_NEG = ["a blurry low quality photo", "a black screen", "a screenshot with text and subtitles"]

MOODS = {
    "fark etmez": {},
    "karanlık": {"pos": ["a dark moody low key photo"], "w": {"dark": 0.15}},
    "aydınlık": {"pos": ["a bright well lit photo"], "neg": ["a very dark underexposed photo"], "w": {"bright": 0.15}},
    "renkli": {"pos": ["a colorful vibrant photo"], "neg": ["a black and white photo"], "w": {"color": 0.15}},
    "siyah-beyaz": {"pos": ["a black and white monochrome photo"], "w": {"mono": 0.20}},
}

PEOPLE = ["stile göre", "ana planda olsun", "olmasın", "fark etmez"]
CLEAN = ["fark etmez", "pürüzsüz olsun", "kumlu / film efekti olabilir"]
USES = {
    "telefon (9:16)": ("9:16",),
    "YouTube / masaüstü (16:9)": ("16:9",),
    "Instagram (4:5)": ("4:5",),
    "hepsi": ("9:16", "16:9", "4:5"),
}


@dataclass
class Preferences:
    styles: list[str] = field(default_factory=lambda: ["sanatci"])
    mood: str = "fark etmez"
    people: str = "stile göre"
    clean: str = "fark etmez"
    use: str = "hepsi"
    extra: str = ""          # serbest tarif — CLIP İngilizce anlar, en iyi sonuç İngilizce yazınca


@dataclass
class Profile:
    pos: list[str]
    neg: list[str]
    people: str              # gerekli | olmasın | fark etmez
    area: float              # ideal özne alanı (kadrajın oranı)
    w: dict[str, float]
    crops: tuple[str, ...]


def build_profile(p: Preferences) -> Profile:
    keys = [k for k in p.styles if k in STYLES] or ["sanatci"]
    st = [STYLES[k] for k in keys]
    pos = [x for s in st for x in s["pos"]]
    neg = [x for s in st for x in s["neg"]]

    w: dict[str, float] = {}
    for s in st:
        for k, v in s["w"].items():
            w[k] = w.get(k, 0.0) + v / len(st)

    modes = {s["people"] for s in st}
    people = modes.pop() if len(modes) == 1 else "fark etmez"
    people = {"ana planda olsun": "gerekli", "olmasın": "olmasın", "fark etmez": "fark etmez"}.get(p.people, people)
    if people == "olmasın":
        neg += ["a photo of a person", "a portrait of a man"]
    areas = [s["area"] for s in st if s["area"] > 0]
    area = sum(areas) / len(areas) if areas else 0.15

    m = MOODS.get(p.mood, {})
    pos += m.get("pos", [])
    neg += m.get("neg", [])
    for k, v in m.get("w", {}).items():
        w[k] = w.get(k, 0.0) + v

    if p.clean == "pürüzsüz olsun":
        w["smooth"] = w.get("smooth", 0.0) + 0.20
        neg.append("a noisy grainy photo")
    elif p.clean.startswith("kumlu"):
        w.pop("smooth", None)

    if p.extra.strip():
        # kullanıcının tarifi diğer istemlerden daha ağır bassın diye iki kez eklenir
        pos += [p.extra.strip()] * 2

    neg += [x for x in BASE_NEG if x not in neg]
    pos = list(dict.fromkeys(pos))
    neg = [x for x in dict.fromkeys(neg) if x not in pos]
    return Profile(pos=pos, neg=neg, people=people, area=area, w=w, crops=USES.get(p.use, USES["hepsi"]))


def ask_cli() -> Preferences:
    """Terminalde soru-cevap ile tercihleri toplar."""
    def pick(question: str, options: list[str], multi: bool = False, default: int = 0):
        print(f"\n{question}")
        for i, o in enumerate(options, 1):
            print(f"  {i}) {o}")
        hint = "virgülle birden fazla seçebilirsin" if multi else "numara"
        while True:
            raw = input(f"Seçim ({hint}, boş = {default + 1}): ").strip()
            if not raw:
                return [default] if multi else default
            try:
                idx = [int(x) - 1 for x in raw.replace(" ", "").split(",")]
                if all(0 <= i < len(options) for i in idx) and (multi or len(idx) == 1):
                    return idx if multi else idx[0]
            except ValueError:
                pass
            print("  Geçersiz seçim, tekrar dene.")

    keys = list(STYLES)
    st = pick("1. Nasıl görüntüler istiyorsun?", [f"{STYLES[k]['label']} — {STYLES[k]['desc']}" for k in keys], multi=True)
    moods = list(MOODS)
    mood = pick("2. Ruh hali / renk?", moods)
    people = pick("3. Görüntüde insan?", PEOPLE)
    clean = pick("4. Görüntü dokusu?", CLEAN)
    uses = list(USES)
    use = pick("5. Nerede kullanacaksın?", uses, default=uses.index("hepsi"))
    extra = input("\n6. Eklemek istediğin bir tarif var mı? (İngilizce en iyisi, ör. 'red lasers, foggy stage'; boş geç): ").strip()
    return Preferences(styles=[keys[i] for i in st], mood=moods[mood], people=PEOPLE[people],
                       clean=CLEAN[clean], use=uses[use], extra=extra)
