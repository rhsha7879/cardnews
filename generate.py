"""카드뉴스 1세트(5장)를 만드는 프로그램.
1) Claude가 '세계 신비한 풍경' 주제를 하나 골라 글을 씀
2) Pexels에서 사진을 가져옴
3) 사진 위에 글자를 얹어 output/ 폴더에 저장
"""
import json, os, re, sys, textwrap, datetime
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from io import BytesIO

W, H = 1080, 1350
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
YELLOW = "#FFE600"
GREEN = "#6BFF3D"

def font(size):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise RuntimeError("한글 폰트를 찾지 못했어요")

def ask_claude(used):
    import anthropic
    client = anthropic.Anthropic()
    prompt = f"""인스타그램 카드뉴스 주제: '세계의 신비한 풍경'.
아직 쓰지 않은 새로운 장소 1곳을 골라 5장짜리 카드뉴스를 만들어 주세요.
이미 사용한 장소(겹치면 안 됨): {used}
규칙: 한국어, 1장은 호기심을 끄는 제목, 2~4장은 흥미로운 사실, 5장은 마무리 한마디.
각 장의 title은 18자 이내, body는 60자 이내. 사실이 확실한 내용만 쓰세요.
반드시 아래 JSON만 출력하세요(설명 금지):
{{"place":"장소 이름","search":["영어 검색어1","영어 검색어2","영어 검색어3"],
"slides":[{{"title":"","body":""}}],"caption":"인스타 본문 2~3줄","hashtags":["#여행","#풍경"]}}"""
    msg = client.messages.create(
        model="claude-sonnet-5-5", max_tokens=4000,
        messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)

def get_photos(queries, n):
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    urls = []
    for q in queries:
        r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                         params={"query": q, "orientation": "portrait", "per_page": 5}, timeout=30)
        r.raise_for_status()
        for p in r.json().get("photos", []):
            u = p["src"]["large2x"]
            if u not in urls:
                urls.append(u)
    if not urls:
        raise RuntimeError("사진을 찾지 못했어요")
    while len(urls) < n:
        urls += urls
    return urls[:n]

def fit_cover(img):
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s), int(img.height * s)))
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))

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
        for ch in word:  # 한 단어가 너무 길면 글자 단위로 자름
            if draw.textlength(cur + ch, font=fnt) > max_w:
                lines.append(cur); cur = ch
            else:
                cur += ch
    if cur:
        lines.append(cur)
    return lines

def render(bg, title, body, idx, total, cover):
    img = ImageEnhance.Brightness(fit_cover(bg)).enhance(0.9)
    d = ImageDraw.Draw(img)
    ft = font(96 if cover else 80)
    fb = font(50)
    tl = wrap(d, title, ft, W - 160)
    bl = wrap(d, body, fb, W - 160) if body else []
    th = len(tl) * (ft.size + 20)
    bh = len(bl) * (fb.size + 16)
    y = (H - th - bh - (50 if bl else 0)) // 2
    for n, ln in enumerate(tl):
        # 표지는 첫 줄 노랑, 나머지 줄 초록 / 안쪽 장은 제목 노랑
        color = YELLOW if (n == 0 or not cover) else GREEN
        d.text((80, y), ln, font=ft, fill=color, stroke_width=6, stroke_fill="black")
        y += ft.size + 20
    y += 50
    for ln in bl:
        d.text((80, y), ln, font=fb, fill=GREEN, stroke_width=5, stroke_fill="black")
        y += fb.size + 16
    d.text((W - 170, H - 90), f"{idx}/{total}", font=font(40), fill=YELLOW,
           stroke_width=4, stroke_fill="black")
    return img

def main():
    used = json.load(open("used_topics.json", encoding="utf-8"))
    data = ask_claude(used[-100:])
    slides = data["slides"][:5]
    photos = get_photos(data["search"], len(slides))
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out = os.path.join("output", stamp)
    os.makedirs(out, exist_ok=True)
    for i, (s, u) in enumerate(zip(slides, photos), 1):
        bg = Image.open(BytesIO(requests.get(u, timeout=60).content))
        render(bg, s["title"], s["body"] if i > 1 else "", i, len(slides), i == 1).save(
            os.path.join(out, f"slide_{i}.jpg"), quality=92)
    caption = data["caption"] + "\n\n" + " ".join(data["hashtags"])
    json.dump({"place": data["place"], "caption": caption, "count": len(slides)},
              open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    used.append(data["place"])
    json.dump(used, open("used_topics.json", "w", encoding="utf-8"), ensure_ascii=False)
    open("latest_dir.txt", "w").write(out)
    print("완료:", out, data["place"])

if __name__ == "__main__":
    main()
