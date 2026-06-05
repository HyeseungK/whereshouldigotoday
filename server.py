#!/usr/bin/env python3
"""
오늘은 어디로 갈까 — 백엔드 서버 (간소화 버전)
네이버 링크에서 이름/주소 추출 + 사진 파일 업로드 지원
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import json, re, os, time, requests as req

app = Flask(__name__)
CORS(app)

DB_FILE          = 'cafes.json'
ACCOUNTS_FILE    = 'accounts.json'
SUGGESTIONS_FILE = 'suggestions.json'
HTML_FILE        = 'whereshouldigotoday.html'
UPLOAD_FOLDER    = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ── DB ──────────────────────────────────────────────────────────────────────

def load():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, encoding='utf-8') as f:
        return json.load(f)

def save(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── ROUTES ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file(HTML_FILE)

@app.route('/api/cafes', methods=['GET'])
def get_cafes():
    return jsonify(load())

@app.route('/api/cafes', methods=['POST'])
def create_cafe():
    cafe = request.json
    cafe['id'] = int(time.time() * 1000)
    cafes = load()
    cafes.append(cafe)
    save(cafes)
    return jsonify(cafe)

@app.route('/api/cafes/<int:cid>', methods=['PUT'])
def update_cafe(cid):
    updated = request.json
    updated['id'] = cid
    cafes = load()
    cafes = [updated if c.get('id') == cid else c for c in cafes]
    save(cafes)
    return jsonify(updated)

@app.route('/api/cafes/<int:cid>', methods=['DELETE'])
def delete_cafe(cid):
    save([c for c in load() if c.get('id') != cid])
    return jsonify({'ok': True})

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/upload', methods=['POST'])
def upload_photo():
    if 'photo' not in request.files:
        return jsonify({'error': '파일이 없어요'}), 400
    file = request.files['photo']
    if not file.filename:
        return jsonify({'error': '파일명이 없어요'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic']:
        return jsonify({'error': '이미지 파일만 업로드 가능해요'}), 400
    filename = f'{int(time.time() * 1000)}{ext}'
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({'url': f'/uploads/{filename}'})

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify(load_json(ACCOUNTS_FILE))

@app.route('/api/accounts', methods=['POST'])
def create_account():
    a = request.json
    a['id'] = int(time.time() * 1000)
    items = load_json(ACCOUNTS_FILE)
    items.append(a)
    save_json(ACCOUNTS_FILE, items)
    return jsonify(a)

@app.route('/api/accounts/<int:aid>', methods=['DELETE'])
def delete_account(aid):
    items = [a for a in load_json(ACCOUNTS_FILE) if a.get('id') != aid]
    save_json(ACCOUNTS_FILE, items)
    return jsonify({'ok': True})

@app.route('/api/suggestions', methods=['GET'])
def get_suggestions():
    return jsonify(load_json(SUGGESTIONS_FILE))

@app.route('/api/suggestions', methods=['POST'])
def create_suggestion():
    s = request.json
    s['id'] = int(time.time() * 1000)
    items = load_json(SUGGESTIONS_FILE)
    items.append(s)
    save_json(SUGGESTIONS_FILE, items)
    return jsonify(s)

@app.route('/api/suggestions/<int:sid>', methods=['DELETE'])
def delete_suggestion(sid):
    items = [s for s in load_json(SUGGESTIONS_FILE) if s.get('id') != sid]
    save_json(SUGGESTIONS_FILE, items)
    return jsonify({'ok': True})

@app.route('/api/import', methods=['POST'])
def import_from_naver():
    url = (request.json or {}).get('url', '').strip()
    if not url:
        return jsonify({'error': '링크를 입력해주세요'}), 400

    place_id = extract_place_id(url)
    if not place_id:
        return jsonify({'error': '네이버 지도 장소 링크를 넣어주세요'}), 400

    try:
        result = fetch_basic_info(place_id)
        return jsonify(result)
    except Exception as e:
        print(f'[오류] {e}')
        return jsonify({'error': f'정보를 가져오지 못했어요: {str(e)}'}), 500


# ── PLACE ID 추출 ────────────────────────────────────────────────────────────

def extract_place_id(url):
    m = re.search(r'/place/(\d+)', url)
    if m:
        return m.group(1)
    try:
        resp = req.get(url, allow_redirects=True, timeout=10,
                       headers={'User-Agent': 'Mozilla/5.0'})
        m = re.search(r'/place/(\d+)', resp.url)
        if m:
            return m.group(1)
    except Exception as e:
        print(f'[URL 리다이렉트 오류] {e}')
    return None


# ── 동 이름 추출 ─────────────────────────────────────────────────────────────

def extract_dong(addr):
    """지번/도로명 주소에서 '○○동' 추출. 예: '서울 성동구 성수동1가 12' → '성수동'"""
    if not addr:
        return ''
    # "성수동1가", "서교동", "익선동" 등
    # "동" 뒤에 "구"가 오는 건 제외 (성동구, 중동구 등 구 이름 걸러내기)
    m = re.search(r'([가-힣]+동)(?!구)(\d*가?)?', addr)
    if m:
        return m.group(1)
    return ''


# ── 기본 정보 추출 (메타 태그) ────────────────────────────────────────────────

def fetch_basic_info(place_id):
    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
          'AppleWebKit/537.36 (KHTML, like Gecko) '
          'Chrome/124.0.0.0 Safari/537.36')
    headers = {
        'User-Agent': UA,
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Referer': 'https://map.naver.com/',
    }

    name = addr = jibun_addr = ''
    lat = lng = None

    try:
        resp = req.get(
            f'https://pcmap.place.naver.com/place/{place_id}/home',
            headers=headers, timeout=12
        )
        resp.encoding = 'utf-8'
        html = resp.text

        # og:title → 이름 (": 네이버" 등 suffix 제거)
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html)
        if m:
            raw_name = m.group(1).strip()
            raw_name = re.sub(r'\s*[:|]\s*네이버.*$', '', raw_name).strip()
            name = raw_name

        # 1순위: JSON-LD 에서 주소/좌표 파싱
        ld_matches = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        for ld_text in ld_matches:
            try:
                ld = json.loads(ld_text)
                geo = ld.get('geo', {})
                if geo.get('latitude') and geo.get('longitude'):
                    lat = float(geo['latitude'])
                    lng = float(geo['longitude'])
                if not addr:
                    loc = ld.get('address', {})
                    if isinstance(loc, dict):
                        addr = (loc.get('streetAddress', '')
                                or loc.get('addressLocality', ''))
                    elif isinstance(loc, str):
                        addr = loc
                if not name:
                    name = ld.get('name', '')
            except Exception:
                pass

        # 2순위: 네이버 y/x 좌표 (lat=y, lng=x) 패턴
        if lat is None:
            m_y = re.search(r'"y"\s*:\s*"?(3[3-9]\.\d{4,})"?', html)
            m_x = re.search(r'"x"\s*:\s*"?(12[6-9]\.\d{4,}|130\.\d{4,})"?', html)
            if m_y and m_x:
                lat = float(m_y.group(1))
                lng = float(m_x.group(1))

        # 3순위: mapy/mapx 패턴
        if lat is None:
            m_y = re.search(r'"mapy"\s*:\s*"?(3[3-9]\.\d{4,})"?', html)
            m_x = re.search(r'"mapx"\s*:\s*"?(12[6-9]\.\d{4,}|130\.\d{4,})"?', html)
            if m_y and m_x:
                lat = float(m_y.group(1))
                lng = float(m_x.group(1))

        # 4순위: 스크립트 내 JSON 에서 roadAddress + jibunAddress 파싱
        for key, target in [('roadAddress', 'addr'), ('jibunAddress', 'jibun'), ('address', 'addr')]:
            m = re.search(rf'"{key}"\s*:\s*"([^"{{}}\\]+)"', html)
            if m:
                candidate = m.group(1).strip()
                if re.search(r'서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충[남북]|전[남북]|경[남북]|제주', candidate):
                    if target == 'jibun' and not jibun_addr:
                        jibun_addr = candidate
                    elif target == 'addr' and not addr:
                        addr = candidate

        # 5순위: HTML 전체에서 도로명 주소 패턴 검색
        if not addr:
            m = re.search(
                r'(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충[남북]|전[남북]|경[남북]|제주)'
                r'[가-힣\s\d]+(?:로|길|가)\s*\d+[^\s"\'<]{0,20}',
                html
            )
            if m:
                addr = m.group(0).strip()

        print(f'[기본정보] name={name!r}, addr={addr!r}, jibun={jibun_addr!r}, lat={lat}, lng={lng}')

    except Exception as e:
        print(f'[메타 파싱 오류] {e}')

    # 동네(hood) 추출: 지번 주소에서 "○○동" 파싱
    hood = extract_dong(jibun_addr) or extract_dong(addr)
    if not hood and addr:
        # 폴백: 주소 2~3번째 단어
        parts = addr.split()
        hood = ' '.join(parts[2:4]) if len(parts) >= 4 else ' '.join(parts[1:3])

    return {
        'place_id': place_id,
        'name':     name,
        'hood':     hood,
        'addr':     addr,
        'lat':      lat,
        'lng':      lng,
        'photos':   [],
        'reviews':  [],
        '_reviewText': '',
        'tags':     [],
        'concept':  '',
        'insta':    '',
        'emoji':    '📍',
        'gr':       'warm',
    }


# ── 실행 ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print()
    print('  ☕  오늘은 어디로 갈까 — 서버 시작!')
    print('  👉  브라우저에서 열기: http://localhost:5000')
    print('  Ctrl+C 로 종료')
    print()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
