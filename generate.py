"""카드뉴스 1세트(5장)를 만드는 프로그램.
1) '세계 여행·문화' 안의 여러 주제를 돌아가며, Claude가 새 장소를 골라 위치·설명까지 글을 씀
2) Pexels에서 장소와 가장 잘 맞는 멋진 사진을 골라 가져옴
3) 사진 색감을 다듬고, 글자 뒤에만 부드러운 그림자를 깔아 output/ 에 저장
"""
import json, os, re, sys, datetime
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageChops, ImageCms
from io import BytesIO

W, H = 1080, 1350
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
# 주제 목록: 실행할 때마다 위에서부터 하나씩 돌아가며 씁니다.
# 바꾸고 싶으면 저장소에 topics.txt 파일을 만들어 한 줄에 주제 하나씩 적으세요.
DEFAULT_TOPICS = [
    "신비한 자연 풍경",
    "세계 축제와 행사",
    "이색 음식과 시장",
    "전통 문화와 의상",
    "역사 유적과 고대 도시",
    "이색 마을과 건축",
    "야경이 아름다운 도시",
    "신기한 자연 현상",
    "세계의 사원과 성지",
    "비밀스러운 섬과 해변",
]

def load_topics():
    if os.path.exists("topics.txt"):
        lines = [l.strip() for l in open("topics.txt", encoding="utf-8") if l.strip()]
        if lines:
            return lines
    return DEFAULT_TOPICS

YELLOW = "#FFE600"   # 제목 색
WHITE = "#FFFFFF"    # 본문·위치·쪽번호 색

def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise RuntimeError("한글 폰트를 찾지 못했어요")

def ask_claude(used, topic):
    import anthropic
    client = anthropic.Anthropic()
    prompt = f"""인스타그램 카드뉴스 큰 주제: '세계 여행·문화'.
이번 세부 주제: '{topic}'.
이 세부 주제에 딱 맞으면서, 보는 사람이 "꼭 가보고 싶다, 직접 경험해 보고 싶다"고 느낄 만큼 매력적인 장소(또는 그곳의 문화) 1곳을 골라 5장짜리 카드뉴스를 만들어 주세요.
이미 사용한 장소(겹치면 안 됨): {used}

각 장의 역할:
1장(표지): title은 호기심을 끄는 제목(14자 이내), body는 한 줄 소개(30자 이내)
2장: 어디에 있는 무엇인가 (나라, 지역, 어떤 곳·어떤 문화인지 알기 쉽게)
3장: 왜 특별한가 (유래, 역사, 문화적 배경, 놀라운 사실)
4장: 직접 즐기는 법 (가는 법, 방문하기 좋은 시기, 꼭 해볼 것, 알아두면 좋은 팁)
5장: 마무리 한마디와 '저장해 두고 다음 여행 때 보세요' 같은 저장 유도 문구
2~5장: title은 14자 이내, body는 80자 이내, 쉬운 문장으로 핵심만 쓰세요.
사실이 확실한 내용만 쓰고, 정확한 숫자가 불확실하면 '약'을 붙이거나 숫자를 빼세요.
종교·민족·문화를 존중하는 표현을 쓰고, 비하하거나 고정관념을 담지 마세요.

사진 검색어(search)는 영어로 정확히 4개 쓰세요. 모두 장소의 영어 이름을 포함하고,
이 주제에 어울리는 서로 다른 구도를 담으세요(예: 전체 전경, 분위기가 살아 있는 장면, 디테일, 해 질 녘이나 밤 풍경).
전문 사진작가가 찍은 듯한 사진이 검색되도록 'aerial', 'golden hour', 'dramatic', 'travel photography' 같은 단어를 적절히 섞으세요.
place_en은 사진 설명에 흔히 쓰이는 영어 장소 이름(예: Uyuni Salt Flat)입니다.

반드시 아래 JSON만 출력하세요(설명 금지):
{{"place":"장소 이름","place_en":"English place name","country":"나라","region":"도시 또는 지역",
"search":["영어 검색어1","영어 검색어2","영어 검색어3","영어 검색어4"],
"slides":[{{"title":"","body":""}}],
"caption":"인스타 본문 4~6줄(위치, 한 줄 소개, 방문 팁 포함)",
"hashtags":["#여행","#세계여행"]}}"""
    msg = client.messages.create(
        model="claude-sonnet-5-5", max_tokens=4000,
        messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)

def get_photos(queries, place_en, n):
    """여러 검색어로 후보를 모은 뒤, 장소 이름이 사진 설명에 들어 있고 해상도가 큰 사진을 우선 고릅니다."""
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", place_en) if len(w) > 2]
    cands = {}
    for q in queries:
        r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                         params={"query": q, "orientation": "portrait", "per_page": 30}, timeout=30)
        r.raise_for_status()
        for p in r.json().get("photos", []):
            alt = (p.get("alt") or "").lower()
            w, h = p.get("width", 0), p.get("height", 0)
            score = sum(1 for x in words if x in alt) * 10
            score += min(w, 4000) / 1000                      # 큰 사진일수록 가산점
            if w < 1600 or h < 2000:                          # 화질이 낮은 사진은 큰 감점
                score -= 15
            if h and abs(w / h - 0.8) < 0.08:                 # 4:5 비율에 가까우면 덜 잘려서 가산점
                score += 1.5
            if p["id"] not in cands or score > cands[p["id"]][0]:
                cands[p["id"]] = (score, p["src"])
    if not cands:
        raise RuntimeError("사진을 찾지 못했어요")
    ranked = [src for _, src in sorted(cands.values(), key=lambda x: -x[0])]
    while len(ranked) < n:
        ranked += ranked
    return ranked[:n]

def to_srgb(im):
    """사진에 들어 있는 색 정보를 인스타 표준 색(sRGB)으로 맞춥니다."""
    im = im.convert("RGB") if im.mode != "RGB" else im
    icc = im.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            im = ImageCms.profileToProfile(im, src, dst, outputMode="RGB")
        except Exception:
            pass
    return im

def download(src):
    """압축하지 않은 고화질 원본을 받아서, 카드 크기보다 크게 읽은 뒤 나중에 줄입니다."""
    for url in (src["original"], src["large2x"]):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            im = Image.open(BytesIO(r.content))
            im.draft("RGB", (W * 2, H * 2))   # 아주 큰 사진도 메모리 걱정 없이, 최소 2배 크기로 읽기
            return to_srgb(im)
        except Exception:
            continue
    raise RuntimeError("사진을 내려받지 못했어요")

def fit_cover(img):
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s + 0.5), int(img.height * s + 0.5)), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((x, y, x + W, y + H))
    # 줄이면서 흐려진 윤곽을 아주 약하게 또렷하게
    return img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=45, threshold=2))

def grade(img):
    """자연스러운 보정: 색을 조금만 선명하게, 대비를 살짝 높임."""
    img = ImageEnhance.Color(img).enhance(1.10)
    img = ImageEnhance.Contrast(img).enhance(1.05)
    return img

def wrap(draw, text, fnt, max_w):
    """단어(띄어쓰기) 단위로 줄바꿈해서 단어가 중간에 끊기지 않게 합니다."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            if draw.textlength(cur + ch, font=fnt) > max_w:
                lines.append(cur); cur = ch
            else:
                cur += ch
    if cur:
        lines.append(cur)
    return lines

def shade(img, zone_top):
    """글자 뒤 아래쪽과 위쪽 가장자리에만 아주 부드러운 어두운 그라데이션을 깔아 사진 대부분은 그대로 둡니다."""
    gh = H - zone_top
    g = Image.linear_gradient("L").resize((W, gh))
    bottom = g.point(lambda v: int(175 * ((v / 255) ** 1.6)))
    mask = Image.new("L", (W, H), 0)
    mask.paste(bottom, (0, zone_top))
    gt = Image.linear_gradient("L").transpose(Image.FLIP_TOP_BOTTOM).resize((W, 190))
    top = Image.new("L", (W, H), 0)
    top.paste(gt.point(lambda v: int(85 * ((v / 255) ** 1.5))), (0, 0))
    mask = ImageChops.lighter(mask, top)
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, mask)

def render(bg, title, body, idx, total, cover, location=""):
    img = grade(fit_cover(bg))
    probe = ImageDraw.Draw(img)
    pad = 70
    ft = font(78 if cover else 58)       # 제목 (이전보다 작게)
    fb = font(38 if cover else 36)       # 본문 (이전보다 작게)
    tl = wrap(probe, title, ft, W - pad * 2)
    bl = wrap(probe, body, fb, W - pad * 2) if body else []
    t_lh, b_lh = int(ft.size * 1.22), int(fb.size * 1.5)
    block = len(tl) * t_lh + (18 + len(bl) * b_lh if bl else 0)
    y0 = H - 100 - block                 # 글자 덩어리를 맨 아래쪽에 모음
    img = shade(img, max(0, y0 - 230))

    items = []                           # (x, y, 글자, 글꼴, 색)
    f_loc, f_pg = font(30), font(28)
    if location:
        items.append((pad, 62, "위치  " + location, f_loc, WHITE))
    pg = f"{idx} / {total}"
    items.append((W - pad - int(probe.textlength(pg, font=f_pg)), 64, pg, f_pg, WHITE))
    y = y0
    for ln in tl:
        items.append((pad, y, ln, ft, YELLOW)); y += t_lh
    y += 18
    for ln in bl:
        items.append((pad, y, ln, fb, WHITE)); y += b_lh

    # 부드러운 그림자 (굵은 검정 테두리 대신)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    for x, yy, t, f, c in items:
        sd.text((x + 1, yy + 3), t, font=f, fill=(0, 0, 0, 190))
    sh = sh.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img.convert("RGBA"), sh).convert("RGB")

    d = ImageDraw.Draw(img)
    d.rectangle((pad, y0 - 26, pad + 56, y0 - 21), fill=YELLOW)   # 제목 위 노란 포인트 줄
    for x, yy, t, f, c in items:
        d.text((x, yy), t, font=f, fill=c)
    return img

def main():
    used = json.load(open("used_topics.json", encoding="utf-8"))
    topics = load_topics()
    topic = topics[len(used) % len(topics)]      # 실행할 때마다 다음 주제로
    data = ask_claude(used[-100:], topic)
    slides = data["slides"][:5]
    location = f'{data.get("country", "")} · {data.get("region", "")}'.strip(" ·")
    photos = get_photos(data["search"], data.get("place_en", data["place"]), len(slides))
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out = os.path.join("output", stamp)
    os.makedirs(out, exist_ok=True)
    for i, (s, src) in enumerate(zip(slides, photos), 1):
        render(download(src), s["title"], s["body"], i, len(slides), i == 1, location).save(
            os.path.join(out, f"slide_{i}.jpg"), quality=95, subsampling=0, optimize=True)
    caption = data["caption"] + "\n\n" + " ".join(data["hashtags"])
    json.dump({"topic": topic, "place": data["place"], "location": location, "caption": caption,
               "count": len(slides)},
              open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    used.append(data["place"])
    json.dump(used, open("used_topics.json", "w", encoding="utf-8"), ensure_ascii=False)
    open("latest_dir.txt", "w").write(out)
    print("완료:", out, topic, "-", data["place"])

if __name__ == "__main__":
    main()
