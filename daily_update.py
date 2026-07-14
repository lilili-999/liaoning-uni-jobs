import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

from crawlers.base import build_session, clean_text, extract_date
from crawlers.generic_static import crawl_source
from db import connect, init_db

BASE_DIR = Path(__file__).resolve().parent
SOURCES_PATH = BASE_DIR / "config" / "sources.csv"
DATA_PATH = BASE_DIR / "data" / "latest_jobs.csv"
LOG_DIR = BASE_DIR / "logs"
EXPORT_DIR = BASE_DIR / "exports" / "daily"

ADMIN_WORDS = ("管理岗", "行政", "辅导员", "组织员", "党政", "办公室", "学生工作", "管理人员")
SUPPORT_WORDS = ("实验技术", "图书", "档案", "财务", "审计", "网络", "信息化", "教辅")
NOTICE_WORDS = ("资格审查", "面试", "体检", "考察", "拟聘", "公示", "递补")
EXCLUDED_WORDS = ("专任教师", "博士后", "高层次人才", "教学科研")


def load_sources():
    with SOURCES_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row["enabled"].lower() == "true"]


def infer_category(title, content):
    title_text = title
    body_text = content[:1200]
    if "辅导员" in title_text:
        return "辅导员"
    if "组织员" in title_text:
        return "组织员"
    if any(word in title_text for word in NOTICE_WORDS):
        return "招聘后续通知"
    if any(word in title_text for word in EXCLUDED_WORDS):
        return "其他招聘"
    if any(word in title_text for word in ADMIN_WORDS):
        return "行政管理"
    if any(word in title_text for word in SUPPORT_WORDS):
        return "教辅/实验技术"
    if any(word in body_text for word in ADMIN_WORDS):
        return "行政管理"
    if any(word in body_text for word in SUPPORT_WORDS):
        return "教辅/实验技术"
    return "待人工复核"


def infer_degree(text):
    for degree in ("博士", "硕士", "本科"):
        if degree in text:
            return degree
    return "不限/未明确"


def infer_deadline(text):
    patterns = (
        r"(?:报名|申报|截止)[^。；]{0,30}?(20\d{2}[-年./]\d{1,2}[-月./]\d{1,2}日?)",
        r"(20\d{2}[-年./]\d{1,2}[-月./]\d{1,2}日?)[^。；]{0,10}?(?:截止|前)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return extract_date(match.group(1))
    return None


def normalize(record):
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    content = clean_text(record.get("content", ""))
    title = clean_text(record["title"])
    post_date = record.get("post_date") or extract_date(content[:500])
    category = infer_category(title, content)
    matching_words = [word for word in ADMIN_WORDS + SUPPORT_WORDS if word in f"{title} {content[:1200]}"]
    hash_input = clean_text(f"{title} {content}")
    deadline = infer_deadline(content)
    status = "有效"
    if deadline and deadline < date.today().isoformat():
        status = "已截止"
    return {
        "source_id": record["source_id"],
        "city": record["city"],
        "school": record["school"],
        "title": title,
        "post_date": post_date,
        "year": int(post_date[:4]) if post_date else None,
        "job_category": category,
        "position_keywords": "|".join(dict.fromkeys(matching_words)),
        "degree_requirement": infer_degree(content),
        "major_requirement": "详见官方公告",
        "political_requirement": "是" if "中共党员" in content or "中国共产党党员" in content else "未明确",
        "fresh_graduate": "是" if "应届" in content else "未明确",
        "deadline": deadline,
        "summary": content[:240],
        "list_url": record["list_url"],
        "detail_url": record["detail_url"],
        "attachment_urls": record.get("attachment_urls", ""),
        "content_hash": hashlib.sha256(hash_input.encode("utf-8")).hexdigest(),
        "first_seen_at": now,
        "last_seen_at": now,
        "status": status,
        "is_new_today": 1,
    }


def upsert_job(connection, job):
    existing = connection.execute(
        "SELECT id, content_hash FROM jobs WHERE detail_url = ?", (job["detail_url"],)
    ).fetchone()
    if not existing:
        columns = ", ".join(job)
        placeholders = ", ".join("?" for _ in job)
        connection.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})", tuple(job.values())
        )
        return "new"
    if existing["content_hash"] != job["content_hash"]:
        connection.execute(
            """UPDATE jobs SET title=?, post_date=?, year=?, job_category=?, position_keywords=?,
            degree_requirement=?, major_requirement=?, political_requirement=?, fresh_graduate=?,
            deadline=?, summary=?, attachment_urls=?, content_hash=?, last_seen_at=?, status=?
            WHERE id=?""",
            (
                job["title"], job["post_date"], job["year"], job["job_category"],
                job["position_keywords"], job["degree_requirement"], job["major_requirement"],
                job["political_requirement"], job["fresh_graduate"], job["deadline"],
                job["summary"], job["attachment_urls"], job["content_hash"],
                job["last_seen_at"], job["status"], existing["id"],
            ),
        )
        connection.execute(
            "INSERT INTO change_log (job_id, change_type, old_hash, new_hash, changed_at) VALUES (?, '内容修改', ?, ?, ?)",
            (existing["id"], existing["content_hash"], job["content_hash"], job["last_seen_at"]),
        )
        return "updated"
    connection.execute(
        """UPDATE jobs SET last_seen_at=?, is_new_today=0, job_category=?,
        position_keywords=?, degree_requirement=?, deadline=?, status=? WHERE id=?""",
        (
            job["last_seen_at"], job["job_category"], job["position_keywords"],
            job["degree_requirement"], job["deadline"], job["status"], existing["id"],
        ),
    )
    return "unchanged"


def write_csv(connection):
    rows = connection.execute("SELECT * FROM jobs ORDER BY COALESCE(post_date, '') DESC, id DESC").fetchall()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return 0
    with DATA_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return len(rows)


def export_daily(connection):
    rows = connection.execute(
        "SELECT city, school, title, post_date, job_category, deadline, status, detail_url, first_seen_at FROM jobs WHERE is_new_today=1 ORDER BY id DESC"
    ).fetchall()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = EXPORT_DIR / f"{date.today().isoformat()}_招聘更新汇总.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = rows[0].keys() if rows else ("city", "school", "title", "post_date", "job_category", "deadline", "status", "detail_url", "first_seen_at")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)


def main(max_items=20):
    init_db()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_lines = []
    session = build_session()
    with connect() as connection:
        connection.execute("UPDATE jobs SET is_new_today=0")
        for source in load_sources():
            started_at = datetime.now().replace(microsecond=0).isoformat(sep=" ")
            run_id = connection.execute(
                "INSERT INTO crawl_runs (source_id, started_at, status) VALUES (?, ?, '运行中')",
                (source["source_id"], started_at),
            ).lastrowid
            new_count = updated_count = 0
            try:
                records = crawl_source(session, source, max_items=max_items)
                for record in records:
                    result = upsert_job(connection, normalize(record))
                    new_count += result == "new"
                    updated_count += result == "updated"
                status, error = "成功", None
            except Exception as exc:
                records = []
                status, error = "失败", str(exc)
            finished_at = datetime.now().replace(microsecond=0).isoformat(sep=" ")
            connection.execute(
                "UPDATE crawl_runs SET finished_at=?, status=?, new_count=?, updated_count=?, error_message=? WHERE id=?",
                (finished_at, status, new_count, updated_count, error, run_id),
            )
            connection.commit()
            log_lines.append(json.dumps({
                "source_id": source["source_id"], "status": status,
                "records": len(records), "new": new_count, "updated": updated_count,
                "error": error,
            }, ensure_ascii=False))
        total = write_csv(connection)
        export_daily(connection)
        failed_sources = connection.execute(
            "SELECT COUNT(*) FROM crawl_runs WHERE id > ? AND status = '失败'",
            (run_id - len(load_sources()),),
        ).fetchone()[0]
    finished_at = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    log_path = LOG_DIR / f"{date.today().isoformat()}.log"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    update_status = {
        "last_update": finished_at,
        "total_records": total,
        "source_count": len(log_lines),
        "success_count": len(log_lines) - failed_sources,
        "failed_count": failed_sources,
    }
    (BASE_DIR / "data" / "latest_update.json").write_text(
        json.dumps(update_status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"采集完成：数据库共 {total} 条，日志 {log_path}")


if __name__ == "__main__":
    main()
