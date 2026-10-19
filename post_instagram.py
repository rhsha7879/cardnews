"""만들어 둔 카드뉴스 사진을 인스타그램에 캐러셀(넘겨보는 게시물)로 올립니다.
Instagram Login 방식(graph.instagram.com)을 쓰므로 페이스북 페이지가 필요 없습니다."""
import json, os, time, requests

HOST = os.environ.get("IG_GRAPH_HOST") or "graph.instagram.com"
API = f"https://{HOST}/v21.0"
UID = os.environ.get("IG_USER_ID") or "me"          # 비워 두면 토큰 주인 계정 사용
TOKEN = os.environ["IG_ACCESS_TOKEN"].strip()
REPO = os.environ["GITHUB_REPOSITORY"]
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")

def call(path, **params):
    params["access_token"] = TOKEN
    r = requests.post(f"{API}/{path}", data=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"인스타 오류: {r.text}")
    return r.json()

def wait_url(url):
    """GitHub에 사진이 공개 주소로 보일 때까지 기다립니다."""
    for _ in range(12):
        if requests.head(url, timeout=30).status_code == 200:
            return
        time.sleep(5)
    raise RuntimeError(f"사진 주소가 열리지 않아요(저장소가 Public인지 확인): {url}")

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
    wait_url(url)
    ids.append(call(f"{UID}/media", image_url=url, is_carousel_item="true")["id"])
car = call(f"{UID}/media", media_type="CAROUSEL", children=",".join(ids), caption=meta["caption"])["id"]
wait_ready(car)
print("게시 완료:", call(f"{UID}/media_publish", creation_id=car))
