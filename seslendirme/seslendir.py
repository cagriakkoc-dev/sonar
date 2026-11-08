#!/usr/bin/env python3
"""ElevenLabs seslendirme (GitHub Actions'ta çalışır).

seslendirme/istek/<id>.json işlenir, sonuç seslendirme/cikti/<id>.* olarak yazılır.

İstek biçimi:
{
  "id": "anhyt-reel-1",
  "video": "medya/x.mp4",            # isteğe bağlı; yoksa yalnız ses üretilir
  "voice_id": "....",                # ElevenLabs ses kimliği
  "model": "eleven_multilingual_v2", # isteğe bağlı
  "alt_ses": 0.25,                   # videodaki mevcut sesin (müzik) seviyesi, 0 = sustur
  "ayar": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "speed": 1.0},
  "parcalar": [ {"t": 0.4, "metin": "..."}, {"t": 4.0, "metin": "..."} ]
}
Ses listesi için: {"id": "sesler", "sesleri_listele": true}
"""
import json, os, subprocess, sys, urllib.request, glob

API = "https://api.elevenlabs.io/v1"
KEY = os.environ.get("ELEVENLABS_API_KEY", "")
KOK = os.path.dirname(os.path.abspath(__file__))
CIKTI = os.path.join(KOK, "cikti")


def istek(url, veri=None):
    h = {"xi-api-key": KEY, "Accept": "application/json"}
    if veri is not None:
        h["Content-Type"] = "application/json"
        veri = json.dumps(veri).encode()
    req = urllib.request.Request(url, data=veri, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def sure(yol):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", yol],
                       capture_output=True, text=True)
    return float(o.stdout.strip() or 0)


def ses_akisi_var(yol):
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", yol],
                       capture_output=True, text=True)
    return bool(o.stdout.strip())


def sesleri_listele(i):
    d = json.loads(istek(f"{API}/voices"))
    liste = [{"ad": v.get("name"), "voice_id": v.get("voice_id"), "kategori": v.get("category"),
              "etiketler": v.get("labels"), "onizleme": v.get("preview_url")} for v in d.get("voices", [])]
    json.dump(liste, open(os.path.join(CIKTI, f"{i['id']}.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(liste)} ses listelendi")


def isle(i):
    sid = i["id"]
    model = i.get("model", "eleven_multilingual_v2")
    ayar = {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
    ayar.update(i.get("ayar", {}))
    gecici = os.path.join(CIKTI, f"_{sid}")
    os.makedirs(gecici, exist_ok=True)
    rapor = {"id": sid, "parcalar": []}
    girdiler, filtre = [], []
    for n, p in enumerate(i["parcalar"]):
        mp3 = os.path.join(gecici, f"{n:02d}.mp3")
        ses = istek(f"{API}/text-to-speech/{i['voice_id']}?output_format=mp3_44100_128",
                    {"text": p["metin"], "model_id": model, "voice_settings": ayar})
        open(mp3, "wb").write(ses)
        s = sure(mp3)
        rapor["parcalar"].append({"t": p["t"], "sure": round(s, 2), "bitis": round(p["t"] + s, 2), "metin": p["metin"]})
        girdiler += ["-i", mp3]
        ms = int(p["t"] * 1000)
        filtre.append(f"[{n}:a]adelay={ms}|{ms}[s{n}]")
    # çakışma kontrolü
    for a, b in zip(rapor["parcalar"], rapor["parcalar"][1:]):
        if a["bitis"] > b["t"]:
            rapor.setdefault("uyarilar", []).append(f"{a['t']} sn'deki parça {b['t']} sn'deki parçayla çakışıyor ({a['bitis']} sn'de bitiyor)")
    k = len(i["parcalar"])
    filtre.append("".join(f"[s{n}]" for n in range(k)) + f"amix=inputs={k}:normalize=0:dropout_transition=0[anlatim]")
    anlatim = os.path.join(CIKTI, f"{sid}.m4a")
    subprocess.run(["ffmpeg", "-y", *girdiler, "-filter_complex", ";".join(filtre), "-map", "[anlatim]",
                    "-c:a", "aac", "-b:a", "192k", anlatim], check=True)
    video = i.get("video")
    if video:
        vy = os.path.join(os.path.dirname(KOK), video)
        vs = sure(vy)
        rapor["video_suresi"] = round(vs, 2)
        if rapor["parcalar"][-1]["bitis"] > vs:
            rapor.setdefault("uyarilar", []).append(f"Anlatım {rapor['parcalar'][-1]['bitis']} sn'de bitiyor, video {vs:.1f} sn")
        cik = os.path.join(CIKTI, f"{sid}.mp4")
        alt = float(i.get("alt_ses", 0.25))
        if ses_akisi_var(vy) and alt > 0:
            fc = f"[0:a]volume={alt}[m];[1:a]apad[n];[m][n]amix=inputs=2:normalize=0:duration=first[a]"
            subprocess.run(["ffmpeg", "-y", "-i", vy, "-i", anlatim, "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", cik], check=True)
        else:
            subprocess.run(["ffmpeg", "-y", "-i", vy, "-i", anlatim, "-filter_complex", "[1:a]apad[a]", "-map", "0:v", "-map", "[a]",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", cik], check=True)
    for f in glob.glob(os.path.join(gecici, "*")):
        os.remove(f)
    os.rmdir(gecici)
    json.dump(rapor, open(os.path.join(CIKTI, f"{sid}.rapor.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(rapor, ensure_ascii=False, indent=1))


def main():
    if not KEY:
        sys.exit("ELEVENLABS_API_KEY tanımlı değil (repo Settings → Secrets → Actions)")
    os.makedirs(CIKTI, exist_ok=True)
    for yol in sorted(glob.glob(os.path.join(KOK, "istek", "*.json"))):
        i = json.load(open(yol))
        sid = i["id"]
        if glob.glob(os.path.join(CIKTI, f"{sid}.rapor.json")) or (i.get("sesleri_listele") and os.path.exists(os.path.join(CIKTI, f"{sid}.json"))):
            continue
        print("İşleniyor:", sid)
        try:
            sesleri_listele(i) if i.get("sesleri_listele") else isle(i)
        except urllib.error.HTTPError as e:
            hata = e.read().decode(errors="ignore")[:500]
            json.dump({"id": sid, "hata": f"{e.code} {hata}"}, open(os.path.join(CIKTI, f"{sid}.rapor.json"), "w"), ensure_ascii=False)
            print("HATA", sid, e.code, hata)


if __name__ == "__main__":
    main()
