"""ソース共通基盤: HTTP取得（UA明示・間隔制御・キャッシュ）とHTMLテキスト化。

設計方針:
  - 相手サーバーに優しく: リクエスト間に最低2秒空ける。同じURLは12時間キャッシュ。
  - User-Agent に用途と連絡先を明示する（隠れてクロールしない）。
  - 標準ライブラリのみ（urllib / html.parser）。
"""
import hashlib
import ssl
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
USER_AGENT = "TaxiDemandRadar/0.1 (personal research tool; contact: kodainegishi@gmail.com)"
REQUEST_INTERVAL_SEC = 2.0
CACHE_MAX_AGE_HOURS = 12

OFFLINE = False  # True ならキャッシュのみ使用（通信しない）

_last_request_at = 0.0


def _ssl_context():
    """macOSのシステムPythonは証明書ストア未設定のことがあるため、
    OS標準のバンドル(/etc/ssl/cert.pem)にフォールバックする。検証は無効化しない。"""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        for cafile in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
            if Path(cafile).exists():
                ctx = ssl.create_default_context(cafile=cafile)
                break
    return ctx


_SSL_CTX = _ssl_context()


class SourceError(Exception):
    pass


def http_get(url):
    """URLを取得して文字列で返す。キャッシュがあればそれを使う。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / (hashlib.md5(url.encode()).hexdigest()[:16] + ".html")

    if cache.exists() and (time.time() - cache.stat().st_mtime) < CACHE_MAX_AGE_HOURS * 3600:
        return cache.read_text(encoding="utf-8", errors="replace")
    if OFFLINE:
        raise SourceError(f"オフラインモードですがキャッシュがありません: {url}")

    global _last_request_at
    wait = REQUEST_INTERVAL_SEC - (time.time() - _last_request_at)
    if wait > 0:
        time.sleep(wait)

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as res:
            raw = res.read()
            charset = res.headers.get_content_charset() or "utf-8"
    except Exception as e:
        raise SourceError(f"取得失敗 {url}: {e}") from e
    finally:
        _last_request_at = time.time()

    text = raw.decode(charset, errors="replace")
    cache.write_text(text, encoding="utf-8")
    return text


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"tr", "p", "div", "li", "h1", "h2", "h3", "h4", "table", "section", "article", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag == "br" or tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "td" or tag == "th":
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def strip_tags(html):
    """HTMLを行指向テキストに変換する。<tr>等のブロック要素は改行、<td>はタブになる。"""
    p = _TextExtractor()
    p.feed(html)
    lines = [" ".join(chunk.split()) for chunk in "".join(p.parts).split("\n")]
    return "\n".join(line for line in lines if line)


# イベント名から客層を推定する共通語彙（各ソースで使う）
_YOUTH_WORDS = ["アニメ", "ゲーム", "コミック", "同人", "アイドル", "コスプレ", "eスポーツ",
                "K-POP", "KPOP", "フェス", "就活", "学園祭"]
_SENIOR_WEALTHY_WORDS = ["演歌", "歌謡", "クラシック", "交響楽", "フィルハーモニー", "オペラ",
                         "バレエ", "落語", "歌舞伎", "相撲"]
_FAMILY_WORDS = ["ファミリー", "こども", "子ども", "キッズ", "親子", "恐竜", "ヒーロー"]


def guess_audience(name, default="general"):
    """イベント名のキーワードから客層を推定する"""
    if any(w in name for w in _SENIOR_WEALTHY_WORDS):
        return "senior_wealthy"
    if any(w in name for w in _FAMILY_WORDS):
        return "family"
    if any(w in name for w in _YOUTH_WORDS):
        return "youth"
    return default


def make_event(date, name, venue, category, start, end, attendance, audience, notes="", source=""):
    """正規化イベント（csv_to_events.py と同じスキーマ + source）"""
    return {
        "date": date, "name": name, "venue": venue, "category": category,
        "start": start, "end": end, "attendance": int(attendance),
        "audience": audience, "notes": notes, "source": source,
    }
