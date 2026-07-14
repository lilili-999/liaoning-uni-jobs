import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "LiaoningUniversityJobs/1.0 (+public recruitment information aggregator)"
DATE_PATTERN = re.compile(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})日?")


def build_session():
    session = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch(session, url):
    response = session.get(url, timeout=(8, 20))
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    time.sleep(1)
    return response.text


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def extract_date(text):
    match = DATE_PATTERN.search(text or "")
    if not match:
        compact = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", text or "")
        if not compact:
            return None
        parts = compact.groups()
    else:
        parts = match.groups()
    year, month, day = map(int, parts)
    if 1 <= month <= 12 and 1 <= day <= 31:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def parse_list(html, source):
    soup = BeautifulSoup(html, "lxml")
    start_year = int(source["start_year"])
    records = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        title = clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "").strip()
        if len(title) < 6 or href.startswith(("javascript:", "mailto:", "#")):
            continue
        context = clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else title)
        post_date = extract_date(context) or extract_date(title)
        combined = f"{title} {context}"
        if not post_date and not any(word in combined for word in ("招聘", "人才", "岗位", "聘用", "招录", "辅导员")):
            continue
        if post_date and int(post_date[:4]) < start_year:
            continue
        detail_url = urljoin(source["list_url"], href)
        if detail_url in seen:
            continue
        seen.add(detail_url)
        records.append({"title": title, "post_date": post_date, "detail_url": detail_url})
    return records


def parse_detail(html, item, source):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = clean_text(soup.get_text(" ", strip=True))
    attachments = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        label = clean_text(anchor.get_text(" ", strip=True))
        if re.search(r"\.(pdf|docx?|xlsx?|zip|rar)(?:$|\?)", href, re.I) or "附件" in label:
            attachments.append(urljoin(item["detail_url"], href))
    return {
        **item,
        "source_id": source["source_id"],
        "city": source["city"],
        "school": source["school"],
        "list_url": source["list_url"],
        "content": text,
        "attachment_urls": "|".join(dict.fromkeys(attachments)),
    }
