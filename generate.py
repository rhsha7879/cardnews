"""카드뉴스 1세트(5장)를 만드는 프로그램.
1) '세계 여행·문화' 안의 여러 주제를 돌아가며, Claude가 새 장소를 골라 위치·설명까지 글을 씀
2) Pexels에서 장소와 가장 잘 맞는 멋진 사진을 골라 가져옴
3) 사진 색감을 다듬고, 글자 뒤에만 부드러운 그림자를 깔아 output/ 에 저장
"""
import json, os, re, sys, datetime
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
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
1장(표지): title은 호기심을 끄는 제목(16자 이내), body는 한 줄 소개(35자 이내)
2장: 어디에 있는 무엇인가 (나라, 지역, 어떤 곳·어떤 문화인지 알기 쉽게)
3장: 왜 특별한가 (유래, 역사, 문화적 배경, 놀라운 사실)
4장: 직접 즐기는 법 (가는 법, 방문하기 좋은 시기, 꼭 해볼 것, 알아두면 좋은 팁)
5장: 마무리 한마디와 '저장해 두고 다음 여행 때 보세요' 같은 저장 유도 문구
2~5장: title은 16자 이내, body는 100자 이내, 쉬운 문장으로 쓰세요.
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
                         params={"query": q, "orientation": "portrait", "per_page": 15}, timeout=30)
        r.raise_for_status()
        for p in r.json().get("photos", []):
            alt = (p.get("alt") or "").lower()
            score = sum(1 for w in words if w in alt) * 10
            score += min(p.get("width", 0), 4000) / 1000  # 큰 사진일수록 가산점
            if p["id"] not in cands or score > cands[p["id"]][0]:
                cands[p["id"]] = (score, p["src"])
    if not cands:
        raise RuntimeError("사진을 찾지 못했어요")
    ranked = [src for _, src in sorted(cands.values(), key=lambda x: -x[0])]
    while len(ranked) < n:
        ranked += ranked
    return ranked[:n]

def download(src):
    """고화질 원본을 카드 크기로 줄여서 받고, 실패하면 보통 화질로 받습니다."""
    for url in (src["original"] + f"?auto=compress&cs=tinysrgb&fit=crop&w={W}&h={H}", src["large2x"]):
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            return Image.open(BytesIO(r.content))
        except Exception:
            continue
    raise RuntimeError("사진을 내려받지 못했어요")

def fit_cover(img):
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))

def grade(img):
    """사진작가 보정 느낌: 색을 선명하게, 대비를 살짝 높임."""
    img = ImageEnhance.Color(img).enhance(1.18)
    img = ImageEnhance.Contrast(img).enhance(1.08)
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

def shade(img, top_y, bottom_y):
    """글자가 있는 아래쪽과 위치가 있는 위쪽에만 부드러운 어두운 그라데이션을 깔아 사진은 밝게 유지."""
    ov = Image.new("L", (W, H), 0)
    px = ov.load()
    for y in range(H):
        a = 0
        if y < 230:                                   # 위쪽(위치 글자 뒤)
            a = max(a, int(130 * (1 - y / 230)))
        if y > top_y - 260:                           # 글자 덩어리 위쪽부터 서서히
            t = min(1.0, (y - (top_y - 260)) / 260)
            a = max(a, int(185 * t))
        for x in range(0, W, 1):
            px[x, y] = a
    black = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(black, img, ov)

def render(bg, title, body, idx, total, cover, location=""):
    img = grade(fit_cover(bg))
    probe = ImageDraw.Draw(img)
    ft = font(96 if cover else 80)
    fb = font(54 if cover else 46)
    tl = wrap(probe, title, ft, W - 160)
    bl = wrap(probe, body, fb, W - 160) if body else []
    th = len(tl) * (ft.size + 20)
    bh = len(bl) * (fb.size + 16)
    block = th + bh + (40 if bl else 0)
    y = H - 150 - block                      # 글자 덩어리를 아래쪽에 두어 사진이 잘 보이게
    img = shade(img, y, H)
    d = ImageDraw.Draw(img)
    if location:
        d.text((80, 70), "위치  " + location, font=font(40), fill=WHITE,
               stroke_width=4, stroke_fill="black")
    for ln in tl:                            # 제목만 노랑
        d.text((80, y), ln, font=ft, fill=YELLOW, stroke_width=6, stroke_fill="black")
        y += ft.size + 20
    y += 40
    for ln in bl:                            # 본문은 흰색
        d.text((80, y), ln, font=fb, fill=WHITE, stroke_width=4, stroke_fill="black")
        y += fb.size + 16
    d.text((W - 170, H - 90), f"{idx}/{total}", font=font(40), fill=WHITE,
           stroke_width=4, stroke_fill="black")
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
            os.path.join(out, f"slide_{i}.jpg"), quality=93)
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
