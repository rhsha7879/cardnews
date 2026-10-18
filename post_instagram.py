"""만들어 둔 카드뉴스 사진을 인스타그램에 캐러셀(넘겨보는 게시물)로 올립니다."""
import json, os, time, requests

API = "https://graph.facebook.com/v21.0"
UID = os.environ["IG_USER_ID"]
TOKEN = os.environ["IG_ACCESS_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

def call(path, **params):
    params["access_token"] = TOKEN
    r = requests.post(f"{API}/{path}", data=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"인스타 오류: {r.text}")
    return r.json()

def wait_ready(cid):
    for _ in range(30):
        r = requests.get(f"{API}/{cid}", params={"fields": "status_code", "access_token": TOKEN}, timeout=30).json()
        if r.get("status_code") == "FINISHED":
            return
        if r.get("status_code") == "ERROR":
            raise RuntimeError("인스타가 사진 처리에 실패했어요")
        time.sleep(5)
    raise RuntimeError("시간 초과")

folder = open("latest_dir.txt").read().strip()
meta = json.load(open(os.path.join(folder, "meta.json"), encoding="utf-8"))
ids = []
for i in range(1, meta["count"] + 1):
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{folder}/slide_{i}.jpg"
    ids.append(call(f"{UID}/media", image_url=url, is_carousel_item="true")["id"])
car = call(f"{UID}/media", media_type="CAROUSEL", children=",".join(ids), caption=meta["caption"])["id"]
wait_ready(car)
print("게시 완료:", call(f"{UID}/media_publish", creation_id=car))
