#!/usr/bin/env python3
"""
오늘은 어디로 갈까 — 백엔드 서버 (Supabase 버전)
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json, re, os, time, datetime, requests as req
import cloudinary, cloudinary.uploader
from supabase import create_client

cloudinary.config(
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME', ''),
    api_key    = os.environ.get('CLOUDINARY_API_KEY', ''),
    api_secret = os.environ.get('CLOUDINARY_API_SECRET', '')
)

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
sb = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

app = Flask(__name__)
CORS(app)

HTML_FILE = 'whereshouldigotoday.html'


# ── Supabase helpers ─────────────────────────────────────────────────────────

def sb_all(table):
    if not sb: return []
    res = sb.table(table).select('*').order('id').execute()
    return [r['data'] for r in res.data]

def sb_insert(table, item):
    if not sb: return item
    sb.table(table).insert({'id': item['id'], 'data': item}).execute()
    return item

def sb_update(table, id, item):
    if not sb: return item
    sb.table(table).update({'data': item}).eq('id', id).execute()
    return item

def sb_delete(table, id):
    if sb: sb.table(table).delete().eq('id', id).execute()


# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file(HTML_FILE)

# — cafes —
@app.route('/api/cafes', methods=['GET'])
def get_cafes():
    return jsonify(sb_all('cafes'))

@app.route('/api/cafes', methods=['POST'])
def create_cafe():
    cafe = request.json
    cafe['id'] = int(time.time() * 1000)
    return jsonify(sb_insert('cafes', cafe))

@app.route('/api/cafes/<int:cid>', methods=['PUT'])
def update_cafe(cid):
    updated = request.json
    updated['id'] = cid
    return jsonify(sb_update('cafes', cid, updated))

@app.route('/api/cafes/<int:cid>', methods=['DELETE'])
def delete_cafe(cid):
    sb_delete('cafes', cid)
    return jsonify({'ok': True})

# — upload —
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
    try:
        result = cloudinary.uploader.upload(file)
        return jsonify({'url': result['secure_url']})
    except Exception as e:
        return jsonify({'error': f'업로드 실패: {str(e)}'}), 500

# — last updated —
@app.route('/api/last-updated', methods=['GET'])
def last_updated():
    if sb:
        res = sb.table('cafes').select('id').order('id', desc=True).limit(1).execute()
        if res.data:
            ts = res.data[0]['id'] / 1000
            dt = datetime.datetime.utcfromtimestamp(ts) + datetime.timedelta(hours=9)
            return jsonify({'date': f'{dt.year}.{dt.month}.{dt.day}'})
    return jsonify({'date': None})

# — accounts —
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    return jsonify(sb_all('accounts'))

@app.route('/api/accounts', methods=['POST'])
def create_account():
    a = request.json
    a['id'] = int(time.time() * 1000)
    return jsonify(sb_insert('accounts', a))

@app.route('/api/accounts/<int:aid>', methods=['DELETE'])
def delete_account(aid):
    sb_delete('accounts', aid)
    return jsonify({'ok': True})

# — suggestions —
@app.route('/api/suggestions', methods=['GET'])
def get_suggestions():
    return jsonify(sb_all('suggestions'))

@app.route('/api/suggestions', methods=['POST'])
def create_suggestion():
    s = request.json
    s['id'] = int(time.time() * 1000)
    return jsonify(sb_insert('suggestions', s))

@app.route('/api/suggestions/<int:sid>', methods=['DELETE'])
def delete_suggestion(sid):
    sb_delete('suggestions', sid)
    return jsonify({'ok': True})

# — naver import —
@app.route('/api/import', methods=['POST'])
def import_from_naver():
    url = (request.json or {}).get('url', '').strip()
    if not url:
        return jsonify({'error': '링크를 입력해주세요'}), 400
    place_id = extract_place_id(url)
    if not place_id:
        return jsonify({'error': '네이버 지도 장소 링크를 넣어주세요'}), 400
    try:
        return jsonify(fetch_basic_info(place_id))
    except Exception as e:
        print(f'[오류] {e}')
        return jsonify({'error': f'정보를 가져오지 못했어요: {str(e)}'}), 500


# ── PLACE ID 추출 ────────────────────────────────────────────────────────────

def extract_place_id(url):
    m = re.search(r'/place/(\d+)', url)
    if m: return m.group(1)
    try:
        resp = req.get(url, allow_redirects=True, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        m = re.search(r'/place/(\d+)', resp.url)
        if m: return m.group(1)
    except Exception as e:
        print(f'[URL 리다이렉트 오류] {e}')
    return None


# ── 동 이름 추출 ─────────────────────────────────────────────────────────────

def extract_dong(addr):
    if not addr: return ''
    m = re.search(r'([가-힣]+동)(?!구)(\d*가?)?', addr)
    return m.group(1) if m else ''


# ── 기본 정보 추출 ────────────────────────────────────────────────────────────

def fetch_basic_info(place_id):
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    headers = {'User-Agent': UA, 'Accept-Language': 'ko-KR,ko;q=0.9', 'Referer': 'https://map.naver.com/'}
    name = addr = jibun_addr = ''
    lat = lng = None
    try:
        resp = req.get(f'https://pcmap.place.naver.com/place/{place_id}/home', headers=headers, timeout=12)
        resp.encoding = 'utf-8'
        html = resp.text
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html)
        if m:
            name = re.sub(r'\s*[:|]\s*네이버.*$', '', m.group(1).strip()).strip()
        for ld_text in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                ld = json.loads(ld_text)
                geo = ld.get('geo', {})
                if geo.get('latitude') and geo.get('longitude'):
                    lat, lng = float(geo['latitude']), float(geo['longitude'])
                if not addr:
                    loc = ld.get('address', {})
                    addr = (loc.get('streetAddress') or loc.get('addressLocality') or loc) if isinstance(loc, dict) else (loc if isinstance(loc, str) else '')
                if not name: name = ld.get('name', '')
            except: pass
        if lat is None:
            my = re.search(r'"y"\s*:\s*"?(3[3-9]\.\d{4,})"?', html)
            mx = re.search(r'"x"\s*:\s*"?(12[6-9]\.\d{4,}|130\.\d{4,})"?', html)
            if my and mx: lat, lng = float(my.group(1)), float(mx.group(1))
        if lat is None:
            my = re.search(r'"mapy"\s*:\s*"?(3[3-9]\.\d{4,})"?', html)
            mx = re.search(r'"mapx"\s*:\s*"?(12[6-9]\.\d{4,}|130\.\d{4,})"?', html)
            if my and mx: lat, lng = float(my.group(1)), float(mx.group(1))
        for key, target in [('roadAddress','addr'),('jibunAddress','jibun'),('address','addr')]:
            m = re.search(rf'"{key}"\s*:\s*"([^"{{}}\\]+)"', html)
            if m:
                c = m.group(1).strip()
                if re.search(r'서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충[남북]|전[남북]|경[남북]|제주', c):
                    if target == 'jibun' and not jibun_addr: jibun_addr = c
                    elif target == 'addr' and not addr: addr = c
        if not addr:
            m = re.search(r'(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충[남북]|전[남북]|경[남북]|제주)[가-힣\s\d]+(?:로|길|가)\s*\d+[^\s"\'<]{0,20}', html)
            if m: addr = m.group(0).strip()
    except Exception as e:
        print(f'[메타 파싱 오류] {e}')
    hood = extract_dong(jibun_addr) or extract_dong(addr)
    if not hood and addr:
        parts = addr.split()
        hood = ' '.join(parts[2:4]) if len(parts) >= 4 else ' '.join(parts[1:3])
    return {'place_id': place_id, 'name': name, 'hood': hood, 'addr': addr,
            'lat': lat, 'lng': lng, 'photos': [], 'reviews': [], '_reviewText': '',
            'tags': [], 'concept': '', 'insta': '', 'emoji': '📍', 'gr': 'warm'}


# ── 실행 ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('\n  ☕  오늘은 어디로 갈까 — 서버 시작!')
    print('  👉  http://localhost:5000\n')
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
