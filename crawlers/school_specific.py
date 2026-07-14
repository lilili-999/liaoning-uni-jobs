from .generic_static import crawl_source


def crawl(session, source, max_items=30):
    return crawl_source(session, source, max_items=max_items)
