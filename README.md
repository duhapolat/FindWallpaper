# FindWallpaper — videodan duvar kağıdı bulucu

Konser kayıtlarından, kliplerden ya da herhangi bir videodan **duvar kağıdı / arka plan olarak kullanılabilecek
en iyi kareleri** otomatik bulur. Önce nasıl bir görüntü istediğini sorar (sanatçı, manzara, pürüzsüz, neon…),
sonra videoyu tarayıp seçimine en uygun kareleri tam çözünürlükte ve telefon / YouTube / Instagram oranlarında kırpılmış olarak kaydeder.

*Finds the best wallpaper-worthy frames in a video, guided by the style you ask for (artist, landscape, minimal, neon…).
UI and docs are in Turkish.*

## Özellikler

- **Tarz seçimi:** 7 hazır stil, birden fazlası birlikte seçilebilir

  | Stil | Ne arar |
  |---|---|
  | Sanatçı / konser | Sanatçı ana planda, sahne ışıkları, mikrofon |
  | Portre / yakın plan | Yüz ve üst gövde kadrajı dolduruyor |
  | Siluet & atmosfer | Arkadan ışık, sis/duman, karanlık |
  | Sahne & ışık şovu | Lazerler, dekor, ışık hüzmeleri (insan şart değil) |
  | Manzara / şehir / doğa | İnsansız geniş kadraj; gökyüzü, deniz, şehir |
  | Pürüzsüz / minimal | Sade, az detaylı, gren yok; üstüne yazı koymaya uygun |
  | Neon & renkli | Canlı, doygun renkler, neon ışık |

- **Ek sorular:** ruh hali (karanlık / aydınlık / renkli / siyah-beyaz), insan olsun mu, doku (pürüzsüz / gren olabilir),
  nerede kullanılacak (telefon 9:16, YouTube 16:9, Instagram 4:5) ve serbest metinle tarif
  (ör. `red lasers, foggy stage`).
- **Akıllı kırpım:** kırpımlar ana özneye ortalanır.
- **Tekrar yok:** birbirine çok benzeyen ya da zamanca çok yakın kareler elenir.
- **YouTube linki** de verilebilir (yt-dlp ile indirir).
- NVIDIA ekran kartı varsa otomatik kullanılır.

## Nasıl çalışır?

1. **ffmpeg** videoyu tek geçişte tarar ve her ~0.5 sn'de bir kare alır. Her karede netlik, parlaklık, kontrast,
   gren (Immerkær gürültü tahmini), detay yoğunluğu (Canny) ve renk canlılığı (Hasler–Süsstrunk) ölçülür.
   Siyah ekranlar ve tekrar eden kareler (dHash) burada elenir.
2. **YOLO11** insanları bulur. Ana özne; stilin istediği büyüklüğe, ortaya yakınlığa ve netliğe göre seçilir.
   Alttaki seyirci kafaları ve kalabalık kareler cezalandırılır.
3. **CLIP (ViT-B/32)** en iyi ~150 adayı, seçilen stilin pozitif/negatif tariflerine benzerliğine göre puanlar.
4. Puanlar stilin ağırlıklarıyla birleştirilir ve birbirine benzemeyen en iyi K kare kaydedilir.

Stillerin tarifleri ve ağırlıkları [`wallpaper_finder/styles.py`](wallpaper_finder/styles.py) içinde.
Yeni bir stil eklemek için `STYLES` sözlüğüne bir kayıt eklemen yeterli.

## Kurulum (Windows, tek tık)

[**Releases**](../../releases/latest) sayfasından `FindWallpaper-Setup-x.y.z.exe` dosyasını indirip çalıştır.

- Setup küçüktür (~12 MB). Kurulumun sonunda gerekli paketleri internetten indirir:
  NVIDIA ekran kartı varsa GPU sürümü ~3 GB, yoksa CPU sürümü ~1 GB.
- Yönetici izni istemez, kullanıcı klasörüne kurulur. Python ya da ffmpeg kurulu olması gerekmez; ikisi de kurulumla gelir.
- Başlat menüsündeki **FindWallpaper** arayüzü tarayıcıda açar. Bulunan kareler `Resimler\FindWallpaper` klasörüne kaydedilir.
- Komut satırından da kullanılabilir: `FindWallpaper.exe video.mp4 --stil manzara`. Bir videoyu exe'nin üstüne sürüklemek de olur.
- Windows SmartScreen "tanınmayan uygulama" uyarısı verirse **Ek bilgi → Yine de çalıştır** de (setup dijital olarak imzalı değil).

Setup'ı kendin derlemek için: `powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Version 1.0.0`
(Inno Setup 6 gerekir: `winget install JRSoftware.InnoSetup`).

## Kaynak koddan kurulum

Gerekenler: **Python 3.10+** ve **ffmpeg** (komut satırından `ffmpeg` ile çalışabilmeli).

```bash
git clone <repo-adresi> FindWallpaper
cd FindWallpaper
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
```

NVIDIA ekran kartı varsa, hızlı çalışması için önce CUDA'lı PyTorch'u kur (yoksa bu adımı atla):

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
```

Sonra diğer paketleri kur:

```bash
pip install -r requirements.txt
```

Windows'ta bunların hepsini `baslat.bat` da yapar (ilk çalıştırmada kurulum, sonra arayüzü açar; GPU sürümünü kurmaz).
YOLO ve CLIP model ağırlıkları ilk çalıştırmada otomatik iner.

## Kullanım

### Arayüz

```bash
python app.py
```

Tarayıcıda açılır: önce **"Nasıl wallpaper istiyorsun?"** sorularını cevapla, sonra videoyu sürükle
ya da YouTube linki / dosya yolu yapıştır. Sonuçlar galeride gösterilir ve hepsi `.zip` olarak indirilebilir.

### Komut satırı

```bash
python bul.py video.mp4 --sor                                    # soruları terminalde adım adım sorar
python bul.py video.mp4 --stil manzara,neon --ruh karanlık --kullanim telefon
python bul.py video.mp4 --stil minimal --doku "pürüzsüz olsun" --gren-temizle
python bul.py "https://youtube.com/watch?v=..." -k 30 --aralik 0.25
python bul.py C:\Videolar\                                       # klasördeki tüm videolar
```

Tüm seçenekler için: `python bul.py --help`

Sonuçlar `cikti/<video adı>/` klasörüne kaydedilir: `01_02m55s_full.png`, `..._9x16.png`, `..._16x9.png`…
ve seçilen tercihlerle her karenin puanlarını içeren `sonuclar.json`.

## Performans

4.7 dakikalık 1080p bir klipte (20 kare): CPU ile ~58 sn, RTX 4070 Laptop ile ~24 sn.

## Bilinen sınırlar

- 1080p yatay videodan 9:16 kırpım ~607×1080 olur; dikey duvar kağıdı için 4K ya da dikey video daha iyi sonuç verir.
- Klipteki jenerik/başlık yazıları her zaman elenemiyor (CLIP'in "yazılı ekran" negatifi bazen kaçırıyor).
- Serbest tarif kutusu İngilizce yazıldığında en iyi sonucu verir (CLIP İngilizce eğitildi).

## Proje yapısı

```
app.py                     # Gradio arayüzü
bul.py                     # komut satırı
baslat.bat                 # Windows: tek tıkla kur + aç
wallpaper_finder/
  core.py                  # kare tarama, YOLO, CLIP, puanlama, kaydetme
  styles.py                # stiller, sorular ve tercih → profil dönüşümü
modeller/                  # model ağırlıkları (otomatik iner, git'e girmez)
installer/
  build.ps1                # setup'ı derler (gömülü Python + başlatıcı + Inno Setup)
  FindWallpaper.iss        # kurulum sihirbazı tanımı
  kurulum.ps1              # kurulumda paketleri ve ffmpeg'i indirir
  launcher.cs              # FindWallpaper.exe başlatıcısı
```
