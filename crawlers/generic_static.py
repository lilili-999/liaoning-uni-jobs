from .base import fetch, parse_detail, parse_list


def crawl_source(session, source, max_items=30):
    list_html = fetch(session, source["list_url"])
    items = parse_list(list_html, source)[:max_items]
    records = []
    for item in items:
        try:
            detail_html = fetch(session, item["detail_url"])
            records.append(parse_detail(detail_html, item, source))
        except Exception as exc:
            records.append({
                **item,
                "source_id": source["source_id"],
                "city": source["city"],
                "school": source["school"],
                "list_url": source["list_url"],
                "content": item["title"],
                "attachment_urls": "",
                "detail_error": str(exc),
            })
    return records
