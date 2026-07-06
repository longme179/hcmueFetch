"""Core logic for fetching, parsing, and digesting university news."""

import calendar
import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

try:
    import feedparser

    HAVE_FEEDPARSER = True
except ImportError:
    HAVE_FEEDPARSER = False

VN_TZ = timezone(timedelta(hours=7))
USER_AGENT = "PersonalDigestBot/1.0 (+university-news-digest)"
TIMEOUT = 15
MAX_RETRIES = 2
BACKOFF_BASE = 2.0
DELAY_RANGE = (1.0, 2.0)

DEFAULT_CONFIG = "sources.json"
DEFAULT_SEEN = "seen.json"
DEFAULT_REPORT_DIR = "reports"


@dataclass
class Item:
    title: str
    link: str
    date: datetime = None
    excerpt: str = ""
    is_new: bool = False
    source_name: str = ""

    def date_str(self) -> str:
        if self.date is None:
            return "(không rõ ngày)"
        return self.date.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M")


# ----------------------------------------------------------------------------
# Date normalization
# ----------------------------------------------------------------------------
def normalize_date(text: str, now: datetime = None) -> datetime:
    if not text or not text.strip():
        return None
    text = text.strip()
    if now is None:
        now = datetime.now(VN_TZ)
    else:
        now = now.astimezone(VN_TZ)

    # 1) Relative: "N days/weeks/months/years ago" / "N ngày/tuần/tháng/năm trước"
    m = re.search(
        r"(\d+)\s+(day|week|month|year|ngày|tuần|tháng|năm)s?\s+(ago|trước)", text, re.I
    )
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        unit_map = {
            "day": 1,
            "week": 7,
            "month": 30,
            "year": 365,
            "ngày": 1,
            "tuần": 7,
            "tháng": 30,
            "năm": 365,
        }
        return (now - timedelta(days=n * unit_map[unit])).astimezone(VN_TZ)

    # 2) Static dates via dateutil (handles ISO 8601, dd/mm/yyyy, English abbrs)
    try:
        dt = dateparser.parse(
            text,
            dayfirst=True,
            default=now.replace(tzinfo=None),
            tzinfos={"ICT": VN_TZ, "UTC": timezone.utc},
        )
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=VN_TZ)
            # Nếu chuỗi không chứa năm và date parse bị ở tương lai -> lùi 1 năm
            has_year = bool(re.search(r"\b(19|20)\d{2}\b", text))
            if not has_year and dt.year == now.year and dt > now + timedelta(days=1):
                dt = dt.replace(year=now.year - 1)
            return dt.astimezone(VN_TZ)
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------------
# Network & Fetch
# ----------------------------------------------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "vi,en;q=0.9"})
    return s


def fetch_url(url: str, session: requests.Session, log_func=print) -> str:
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            if r.encoding is None or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE**attempt + random.uniform(0, 0.5)
                log_func(
                    f"  Lỗi tải {url} (lần {attempt + 1}): {e}. Thử lại sau {wait:.1f}s."
                )
                time.sleep(wait)
            else:
                log_func(f"  Không tải được {url} sau {MAX_RETRIES + 1} lần.")
                return None


def can_fetch(url: str, cache: dict, session: requests.Session) -> bool:
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    if domain not in cache:
        rp = RobotFileParser()
        try:
            r = session.get(f"{domain}/robots.txt", timeout=TIMEOUT)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                cache[domain] = rp
            else:
                cache[domain] = None
        except:
            cache[domain] = None
    rp = cache[domain]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def fetch_with_playwright(url: str, log_func=print) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log_func(
            "  Trang cần JS-render nhưng Playwright chưa cài. Cài: pip install playwright && playwright install chromium"
        )
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(user_agent=USER_AGENT).new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            time.sleep(2)  # extra time for late JS hydration
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log_func(f"  Lỗi Playwright: {e}")
        return None


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------
def find_rss_feed(html: str, base_url: str) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
        for link in soup.select('link[rel="alternate"]'):
            if (
                "rss" in (link.get("type") or "").lower()
                or "atom" in (link.get("type") or "").lower()
            ):
                href = link.get("href")
                if href:
                    return urljoin(base_url, href)
    except:
        pass
    return None


def parse_feed(feed_url: str, session: requests.Session) -> list[Item]:
    if not HAVE_FEEDPARSER:
        return []
    text = fetch_url(feed_url, session)
    if not text:
        return []
    items = []
    for e in feedparser.parse(text).entries:
        try:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            dt = None
            for k in ("published_parsed", "updated_parsed"):
                t = e.get(k)
                if t:
                    try:
                        dt = datetime.fromtimestamp(
                            calendar.timegm(t), tz=timezone.utc
                        ).astimezone(VN_TZ)
                        break
                    except:
                        pass
            if not dt:
                for k in ("published", "updated"):
                    s = e.get(k)
                    if s:
                        dt = normalize_date(s)
                        if dt:
                            break
            items.append(Item(title=title, link=link, date=dt))
        except:
            continue
    return items


def parse_with_selectors(
    soup: BeautifulSoup, base_url: str, selectors: dict
) -> list[Item]:
    items = []
    for el in soup.select(selectors.get("item", "")):
        try:
            title = (
                el.select_one(selectors["title"]).get_text(" ", strip=True)
                if selectors.get("title")
                else el.get_text(" ", strip=True)
            )
            link = ""
            if selectors.get("link"):
                l_el = el.select_one(selectors["link"])
                if l_el and l_el.get("href"):
                    link = urljoin(base_url, l_el["href"])
            else:
                a = el.find("a")
                if a and a.get("href"):
                    link = urljoin(base_url, a["href"])

            dt = None
            if selectors.get("date"):
                d_el = el.select_one(selectors["date"])
                if d_el:
                    ds = (
                        d_el["datetime"]
                        if d_el.has_attr("datetime")
                        else d_el.get_text(" ", strip=True)
                    )
                    dt = normalize_date(ds)
            if title and link:
                items.append(Item(title=title, link=link, date=dt))
        except:
            continue
    return items


def parse_heuristic(soup: BeautifulSoup, base_url: str) -> list[Item]:
    items, seen_links = [], set()
    for a in soup.find_all("a"):
        try:
            if a.find_parent(["nav", "header", "footer", "aside"]):
                continue
            text = a.get_text(" ", strip=True)
            if not (10 <= len(text) <= 200) or text.lower() in {
                "đọc tiếp",
                "xem thêm",
                "read more",
            }:
                continue
            href = a.get("href", "")
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            link = urljoin(base_url, href)
            if (
                link in seen_links
                or link.rstrip("/").split("?")[0] == base_url.rstrip("/").split("?")[0]
            ):
                continue

            search_parts = []
            for anc in (a.parent, a.parent.parent if a.parent else None):
                if not anc:
                    continue
                for t in anc.find_all("time"):
                    search_parts.append(t.get("datetime") or t.get_text())
                p_text = anc.get_text(" ", strip=True)
                if len(p_text) < 2000:
                    search_parts.append(p_text)

            dt = normalize_date(" ".join(search_parts)) if search_parts else None
            if dt:
                items.append(Item(title=text, link=link, date=dt))
                seen_links.add(link)
        except:
            continue
    return items


def parse_items_from_html(html: str, base_url: str, source: dict) -> list[Item]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except:
        return []
    selectors = source.get("selectors")
    if selectors and selectors.get("item"):
        return parse_with_selectors(soup, base_url, selectors)
    return parse_heuristic(soup, base_url)


def crawl_source(
    source: dict,
    session: requests.Session,
    robots_cache: dict,
    target_count: int,
    log_func=print,
):
    name = source.get("name", "(không tên)")
    url = source["url"]
    if not can_fetch(url, robots_cache, session):
        return [], f"robots.txt không cho phép crawl {url}"

    log_func(f"Đang quét: {name}...")
    first_html = fetch_url(url, session, log_func)
    if not first_html:
        return [], f"không tải được trang chính {url}"

    feed_url = find_rss_feed(first_html, url)
    if feed_url and HAVE_FEEDPARSER:
        log_func(f"  Nguồn '{name}': dùng RSS feed.")
        items = parse_feed(feed_url, session)
        if items:
            for it in items:
                it.source_name = name
            return items, None

    items = parse_items_from_html(first_html, url, source)
    if not items:
        log_func(f"  Nguồn '{name}': HTML thô rỗng, thử Playwright...")
        js_html = fetch_with_playwright(url, log_func)
        if js_html:
            items = parse_items_from_html(js_html, url, source)
            if not items:
                log_func(
                    f"  Nguồn '{name}': kể cả Playwright không có bài — cần khai báo selectors riêng."
                )

    # Deduplicate ngay từ đầu
    all_items = list({it.link: it for it in items}.values())
    seen_links = {it.link for it in all_items}

    pagination = source.get("pagination")
    if pagination:
        max_pages = int(pagination.get("max_pages", 10))
        step = int(pagination.get("step", 8))
        param = pagination.get("param", "start")
        for i in range(1, max_pages):
            if len(all_items) >= target_count and i >= 2:
                break
            time.sleep(random.uniform(*DELAY_RANGE))
            sep = "&" if "?" in url else "?"
            html = fetch_url(f"{url}{sep}{param}={i * step}", session, log_func)
            if not html:
                continue
            page_items = parse_items_from_html(html, url, source)
            if not page_items:
                log_func(f"  Trang {i + 1} không có bài, dừng phân trang.")
                break
            for it in page_items:
                if it.link not in seen_links:
                    seen_links.add(it.link)
                    all_items.append(it)

    for it in all_items:
        it.source_name = name
    return all_items, None


# ----------------------------------------------------------------------------
# Excerpt & Seen
# ----------------------------------------------------------------------------
def make_excerpt(text: str) -> str:
    try:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return ""
        sentences = re.split(r"(?<=[.!?…])\s+", text)
        out, total = [], 0
        for s in sentences[:3]:
            if total + len(s) > 350:
                rem = 350 - total
                if rem > 30:
                    out.append(s[:rem].rstrip() + "…")
                break
            out.append(s)
            total += len(s) + 1
        return " ".join(out)[:350]
    except Exception:
        return ""


def extract_excerpt(url: str, session: requests.Session) -> str:
    try:
        html = fetch_url(url, session)
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        c = soup.find(["article", "main"]) or soup.body
        return make_excerpt(c.get_text(" ", strip=True)) if c else ""
    except:
        return ""


def hash_link(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]


def load_seen(path: str) -> dict:
    p = Path(path)
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_seen(seen: dict, path: str):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(seen, f, ensure_ascii=False, indent=2)
    except:
        pass


def load_config(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("sources", data if isinstance(data, list) else [])
    except:
        return []


def save_config(sources: list, path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"sources": sources}, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# Main Digest Logic
# ----------------------------------------------------------------------------
def run_digest(
    sources: list,
    count: int,
    mode: str,
    no_excerpt: bool,
    reset_seen: bool,
    seen_path: str,
    log_func=print,
):
    session = make_session()
    robots_cache = {}
    seen = {} if reset_seen else load_seen(seen_path)

    all_data = []
    error_sources = []

    for source in sources:
        try:
            items, err = crawl_source(source, session, robots_cache, count, log_func)
            if err:
                log_func(f"Lỗi nguồn '{source['name']}': {err}")
                error_sources.append((source["name"], err))
                items = []
            elif not items:
                log_func(
                    f"Nguồn '{source['name']}': không tìm thấy bài. Có thể cần khai báo selectors."
                )
            all_data.append({"source": source, "items": items})
        except Exception as e:
            log_func(f"Lỗi không xác định với nguồn '{source['name']}': {e}")
            error_sources.append((source["name"], str(e)))
            all_data.append({"source": source, "items": []})

    log_func("Đang xử lý bài viết (lấy trích đoạn cho bài mới)...")
    for data in all_data:
        for it in data["items"]:
            it.is_new = hash_link(it.link) not in seen
            if it.is_new and not no_excerpt:
                log_func(f"  -> Lấy trích đoạn: {it.title[:50]}...")
                time.sleep(random.uniform(0.5, 1.0))
                it.excerpt = extract_excerpt(it.link, session)

    final_items = []
    for data in all_data:
        items = sorted(
            data["items"],
            key=lambda x: x.date or datetime.min.replace(tzinfo=VN_TZ),
            reverse=True,
        )
        if len(items) < count:
            log_func(
                f"Nguồn '{data['source']['name']}' chỉ có {len(items)} bài (ít hơn {count} yêu cầu)"
            )
        final_items.extend(items[:count])

    if mode == "combined":
        final_items.sort(
            key=lambda x: x.date or datetime.min.replace(tzinfo=VN_TZ), reverse=True
        )
        final_items = final_items[:count]

    now_iso = datetime.now(VN_TZ).isoformat()
    for it in final_items:
        seen[hash_link(it.link)] = now_iso
    save_seen(seen, seen_path)

    log_func("Hoàn tất quét!")
    return final_items, error_sources


def render_report(
    final_items: list,
    count: int,
    mode: str,
    error_sources: list,
    output_path: str = None,
) -> str:
    now_str = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M:%S")
    mode_str = "GỘP TẤT CẢ NGUỒN" if mode == "combined" else "RIÊNG TỪNG NGUỒN"
    lines = [
        f"TOP {count} BÀI MỚI NHẤT — {mode_str}",
        f"Tạo lúc: {now_str} (giờ VN)",
        "=" * 70,
        "",
    ]

    if mode == "combined":
        lines.append(">>> TẤT CẢ NGUỒN\n" + "-" * 70)
        for it in final_items:
            mark = "[MỚI] " if it.is_new else "      "
            lines.append(f"{mark}[{it.source_name}] {it.date_str()} — {it.title}")
            lines.append(f"       {it.link}")
            if it.excerpt:
                lines.append(f"       Trích đoạn: {it.excerpt}")
            lines.append("")
    else:
        curr_source = None
        for it in final_items:
            if it.source_name != curr_source:
                curr_source = it.source_name
                lines.append(f">>> NGUỒN: {curr_source}\n" + "-" * 70)
            mark = "[MỚI] " if it.is_new else "      "
            lines.append(f"{mark}{it.date_str()} — {it.title}")
            lines.append(f"       {it.link}")
            if it.excerpt:
                lines.append(f"       Trích đoạn: {it.excerpt}")
            lines.append("")

    lines.append("=" * 70)
    total_new = sum(1 for i in final_items if i.is_new)
    lines.append(f"TỔNG KẾT: {len(final_items)} bài ({total_new} mới)")
    if error_sources:
        lines.append("\nNguồn lỗi:")
        for n, e in error_sources:
            lines.append(f"  - {n}: {e}")

    text = "\n".join(lines) + "\n"
    if output_path:
        p = Path(output_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            print(f"Lỗi lưu file: {e}")
    return text
