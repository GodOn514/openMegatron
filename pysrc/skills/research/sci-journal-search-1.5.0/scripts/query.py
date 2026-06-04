import re
import json
import argparse
import sys
import time
from urllib.parse import urlparse, urlencode, quote
from datetime import datetime
from html.parser import HTMLParser
from html import unescape
import requests
from bs4 import BeautifulSoup

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False

if sys.platform.startswith("win") and sys.version_info >= (3, 7):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE_URL_XR = "https://www.xr-scholar.com"

ZH_TO_ISSN = {
    "计算机学报": "0254-4164",
    "软件学报": "1000-9825",
    "计算机研究与发展": "1000-1239",
    "中国科学：信息科学": "1674-7267",
    "小型微型计算机系统": "1000-1220",
    "计算机科学": "1002-137X",
    "计算机应用研究": "1001-3695",
    "计算机工程": "1000-3428",
    "计算机应用": "1001-3695",
    "计算机工程与应用": "1002-8331",
    "计算机工程与科学": "1007-130X",
    "计算机工程与设计": "1000-7024",
    "计算机系统应用": "1003-3254",
    "计算机技术与发展": "1673-629X",
    "计算机与现代化": "1006-2475",
    "模式识别与人工智能": "1003-6059",
    "智能系统学报": "1673-4785",
    "人工智能": "2096-5009",
    "中文信息学报": "1003-0077",
    "数据分析与知识发现": "2096-3467",
    "情报学报": "1000-0135",
    "计算机辅助设计与图形学学报": "1003-9775",
    "中国图象图形学报": "1006-8961",
    "软件导刊": "1672-7800",
    "软件工程": "2096-1472",
    "系统仿真学报": "1004-731X",
    "微电子学与计算机": "1000-7180",
    "大数据": "2096-0271",
    "自动化学报": "0254-4156",
    "控制与决策": "1001-0920",
    "控制理论与应用": "1000-8152",
    "信息与控制": "1002-0411",
    "机器人": "1002-0446",
    "计算机集成制造系统": "1006-5911",
    "制造业自动化": "1009-0134",
    "系统工程与电子技术": "1001-506X",
    "电子学报": "0372-2112",
    "通信学报": "1000-436X",
    "电子与信息学报": "1009-5896",
    "信号处理": "1003-0530",
    "数据采集与处理": "1004-9037",
    "电子测量与仪器学报": "1000-7105",
    "仪器仪表学报": "0254-3087",
    "密码学报": "2095-7025",
    "网络与信息安全学报": "2096-109X",
    "信息安全学报": "2096-1146",
    "信息网络安全": "1671-1122",
    "网络空间安全": "2096-2282",
    "保密科学技术": "1674-1102",
    "现代电子技术": "1004-373X",
    "电子技术应用": "0258-7998",
    "微处理机": "1002-2279",
    "清华大学学报（自然科学版）": "1000-0054",
    "浙江大学学报（工学版）": "1008-973X",
    "管理科学学报": "1007-9807",
    "系统工程理论与实践": "1000-6788",
    "运筹与管理": "1007-3221",
    "系统工程学报": "1000-5781",
    "管理工程学报": "1004-6062",
    "工业工程与管理": "1007-5429",
    "工业工程": "1007-7375",
    "中国管理科学": "1003-207X",
    "管理评论": "1003-1952",
    "管理科学": "1672-0334",
    "管理学报": "1672-884X",
    "系统管理学报": "1005-2542",
    "预测": "1003-5192",
    "项目管理技术": "1672-4313",
    "管理现代化": "1003-1154",
    "管理世界": "1002-5502",
    "南开管理评论": "1008-3448",
    "经济研究": "0577-9154",
    "经济管理": "1002-5766",
    "中国工业经济": "1006-480X",
    "数量经济技术经济研究": "1000-3894",
    "公共管理学报": "1672-6162",
    "宏观经济管理": "1004-9070",
    "外国经济与管理": "1001-4950",
    "会计研究": "1003-2886",
    "金融研究": "1002-7246",
    "审计研究": "1002-4239",
    "统计研究": "1002-4565",
    "财贸经济": "1002-8102",
    "经济学（季刊）": "2095-1086",
    "世界经济": "1002-9621",
    "经济学动态": "1002-8390",
    "中国农村经济": "1002-8870",
    "农业经济问题": "1000-6389",
    "中国人口·资源与环境": "1002-2104",
    "改革": "1003-7543",
    "中国图书馆学报": "1001-8867",
    "图书情报工作": "0252-3116",
    "大学图书馆学报": "1002-1027",
    "营销科学学报": "2096-5796",
    "旅游学刊": "1002-5006",
    "科学学研究": "1003-2053",
    "科研管理": "1000-2995",
    "中国软科学": "1002-9753",
    "科学学与科学技术管理": "1002-0241",
    "研究与发展管理": "1004-8308",
    "技术经济": "1002-980X",
    "软科学": "1001-8409",
    "科技进步与对策": "1001-7348",
    "科技管理研究": "1000-7695",
    "物理学报": "1000-3290",
    "机械工程学报": "0577-6686",
    "中国机械工程": "1004-132X",
    "机电工程": "1001-4551",
    "电气工程学报": "2095-9524",
    "电力系统自动化": "1000-1026",
    "电网技术": "1000-3673",
    "电工技术学报": "1000-6753",
    "高电压技术": "1003-6520",
    "中国电机工程学报": "0258-8013",
    "土木工程学报": "1000-131X",
    "建筑结构学报": "1000-6869",
    "建筑经济": "1002-851X",
    "施工技术": "1002-8498",
    "遥感学报": "1007-4619",
    "测绘学报": "1001-1595",
    "生物医学工程学杂志": "1001-5515",
}

def normalize_text(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()

def build_url(url, params=None):
    return f"{url}?{urlencode(params)}" if params else url

class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current_href = None
        self.current_text = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
            return
        if tag == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if tag == "a" and self.current_href:
            self.links.append({
                "href": self.current_href,
                "text": normalize_text(" ".join(self.current_text))
            })
            self.current_href = None
            self.current_text = []

    def handle_data(self, data):
        if not self.skip_depth and self.current_href is not None:
            value = normalize_text(data)
            if value:
                self.current_text.append(value)

class JournalDetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h3_texts = []
        self.capture_h3 = False
        self.current_dt = None
        self.current_dd = None
        self.dl_pairs = []
        self.in_dt = False
        self.in_dd = False
        self.current_table = None
        self.tables = []
        self.current_row = None
        self.current_cell = None
        self.in_script_like = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.in_script_like += 1
            return
        if self.in_script_like:
            return
        if tag == "h3":
            self.capture_h3 = True
            self.h3_texts.append("")
        elif tag == "dt":
            self.in_dt = True
            self.current_dt = ""
        elif tag == "dd":
            self.in_dd = True
            self.current_dd = ""
        elif tag == "table":
            self.current_table = {"rows": []}
        elif tag == "tr" and self.current_table is not None:
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = ""

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            if self.in_script_like > 0:
                self.in_script_like -= 1
            return
        if self.in_script_like:
            return
        if tag == "h3":
            self.capture_h3 = False
        elif tag == "dt":
            self.in_dt = False
        elif tag == "dd":
            self.in_dd = False
            if self.current_dt and self.current_dd:
                self.dl_pairs.append((normalize_text(self.current_dt), normalize_text(self.current_dd)))
            self.current_dt = None
            self.current_dd = None
        elif tag in {"td", "th"} and self.current_cell is not None:
            self.current_row.append(normalize_text(self.current_cell))
            self.current_cell = None
        elif tag == "tr" and self.current_table is not None and self.current_row is not None:
            if any(self.current_row):
                self.current_table["rows"].append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.current_table is not None:
            self.tables.append(self.current_table)
            self.current_table = None

    def handle_data(self, data):
        if self.in_script_like:
            return
        value = normalize_text(data)
        if not value:
            return
        if self.capture_h3:
            self.h3_texts[-1] += " " + value
        if self.in_dt and self.current_dt is not None:
            self.current_dt += " " + value
        if self.in_dd and self.current_dd is not None:
            self.current_dd += " " + value
        if self.current_cell is not None:
            self.current_cell += " " + value

def fetch_html_drission(url, params=None, search_keyword=None, timeout=25, verbose=False):
    if not HAS_DRISSION:
        return {"ok": False, "html": "", "page_text": "", "final_url": url, "status_code": None, "error": "Missing DrissionPage"}
    final_url = build_url(url, params)
    co = ChromiumOptions().headless(True)
    page = None
    try:
        page = ChromiumPage(co)
        page.set_timeout(timeout)
        page.get(final_url)
        for _ in range(20):
            html_content = page.html
            if "Just a moment" in html_content or "cf-browser-verification" in html_content or "Verify you are human" in html_content:
                time.sleep(2)
            else:
                break
        time.sleep(3)
        if search_keyword:
            inputs = page.eles('tag:input')
            for inp in inputs:
                if inp.attr('type') in ['text', 'search', None]:
                    try:
                        inp.clear()
                        inp.input(search_keyword)
                        inp.input('\n')
                        time.sleep(6)
                        break
                    except:
                        continue
        try:
            page.scroll.to_bottom()
        except:
            pass
        time.sleep(3)
        html = page.html
        page_text = html
        final_url_out = page.url
        return {"ok": True, "html": html, "page_text": page_text, "final_url": final_url_out, "status_code": 200, "error": None}
    except Exception as e:
        return {"ok": False, "html": "", "page_text": "", "final_url": final_url, "status_code": None, "error": str(e)}
    finally:
        if page:
            try:
                page.quit()
            except:
                pass

def parse_search_page(html, page_text, final_url, keyword):
    if "/Journals/" in final_url and "/Search" not in final_url:
        redirect_path = urlparse(final_url).path
        if redirect_path.startswith("/Journals/"):
            return {"best_path": redirect_path, "candidates": [{"path": redirect_path, "title": ""}], "warning": None}
    parser = LinkExtractor()
    parser.feed(html or "")
    candidates = []
    seen = set()
    for link in parser.links:
        href = link.get("href") or ""
        path = urlparse(href).path
        title = normalize_text(link.get("text") or "")
        if not path or len(path) <= 1 or "search" in path.lower() or path.startswith("http") or "javascript" in path.lower():
            continue
        seen.add(path)
        candidates.append({"path": path, "title": title})
    raw_paths = re.findall(r'(/[Jj]ournals?/(?!Search|UnderReview|Index|search)[A-Za-z0-9_-]+)', html or "")
    for path in raw_paths:
        if path not in seen:
            seen.add(path)
            candidates.append({"path": path, "title": path})
    if not candidates:
        if keyword.lower() in (page_text or "").lower():
            return {"best_path": None, "candidates": [], "warning": "未提取到跳转链接"}
        else:
            return {"best_path": None, "candidates": [], "warning": "无结果"}
    keyword_lower = keyword.lower().strip()
    for item in candidates:
        slug = [p for p in item["path"].split("/") if p][-1]
        title = item["title"].lower().strip()
        if keyword_lower in (slug.lower(), title):
            return {"best_path": item["path"], "candidates": candidates, "warning": None}
    for item in candidates:
        title = item["title"].lower().strip()
        if title and (keyword_lower in title or title in keyword_lower):
            return {"best_path": item["path"], "candidates": candidates, "warning": None}
    return {"best_path": None, "candidates": candidates, "warning": f"提取到 {len(candidates)} 个链接，全都不匹配"}

def search_journal_xr(keyword, year, verbose=False):
    url = f"{BASE_URL_XR}/Journals/Search"
    result = fetch_html_drission(url, params={"keyword": keyword, "year": year}, search_keyword=keyword, verbose=verbose)
    if not result["ok"]:
        return {"best_path": None, "candidates": [], "warning": result["error"]}
    parsed = parse_search_page(result["html"], result["page_text"], result["final_url"], keyword)
    parsed.update({"status_code": result["status_code"], "final_url": result["final_url"]})
    return parsed

def get_journal_detail_xr(journal_path, verbose=False):
    if not journal_path:
        return None
    result = fetch_html_drission(f"{BASE_URL_XR}{journal_path}", verbose=verbose)
    if not result["ok"]:
        return None
    return parse_journal_detail(result["html"], result["final_url"])

def parse_journal_detail(html, url):
    parser = JournalDetailParser()
    parser.feed(html or "")
    title = next((normalize_text(item) for item in parser.h3_texts if normalize_text(item)), "")
    issn = eissn = publisher = ""
    for dt_text, dd_text in parser.dl_pairs:
        dt_upper = normalize_text(dt_text).upper()
        dd_text = normalize_text(dd_text)
        if "ISSN" in dt_upper and "EISSN" not in dt_upper:
            issn = dd_text
        elif "EISSN" in dt_upper:
            eissn = dd_text
        elif "PUBLISHER" in dt_upper:
            publisher = dd_text
    research_areas, jcr_categories = [], []
    skip_headers = ["英文名", "中文名", "NAME", "学科名", "学科级别", "期刊名称", "收录", "分类", "大类", "小类", "分区"]
    for table in parser.tables:
        rows = table.get("rows", [])
        if not rows:
            continue
        head_text = " ".join(rows[0]).upper() if rows else ""
        is_jcr = "JCR" in head_text or "小类" in head_text
        data_rows = rows[1:] if rows and any(x.upper() in head_text for x in ["NAME", "英文名", "学科名", "分区", "小类"]) else rows
        for cells in data_rows:
            cells = [normalize_text(c) for c in cells if normalize_text(c)]
            if len(cells) < 2 or not cells[0] or any(x.upper() in cells[0].upper() for x in skip_headers):
                continue
            name_en, name_zh_val, partition_vals, is_top = cells[0], "", [], False
            for c in cells[1:]:
                c_clean = normalize_text(c)
                if not c_clean:
                    continue
                if re.search(r"(?i)(?<![a-zA-Z])TOP(?![a-zA-Z])", c_clean):
                    is_top = True
                if re.search(r"([1-4]区|Q[1-4]|核心|CSCD|CSSCI|AMI|引文索引)", c_clean, re.IGNORECASE):
                    clean_part = normalize_text(re.sub(r"(?i)(?<![a-zA-Z])TOP(?![a-zA-Z])\s*(期刊)?", "", c_clean).strip())
                    if clean_part and clean_part not in partition_vals and clean_part != "期刊":
                        partition_vals.append(clean_part)
                elif not name_zh_val and re.search(r"[\u4e00-\u9fa5]", c_clean):
                    name_zh_val = c_clean
            partition_str = " / ".join(partition_vals)
            if not partition_str and len(cells) > 1 and not name_zh_val and len(cells[-1]) < 30:
                partition_str = cells[-1]
            if partition_str or name_zh_val or len(cells) > 1:
                (jcr_categories if is_jcr else research_areas).append({
                    "name_en": name_en, "name_zh": name_zh_val, "partition": partition_str, "is_top": is_top
                })
    return {
        "title": title, "issn": issn, "eissn": eissn, "publisher": publisher,
        "research_areas": research_areas, "jcr_categories": jcr_categories,
        "raw_url": url, "parse_warnings": []
    }

def format_output(detail, source, links=None):
    lines = [f"📰 {detail['title']}"]
    lines.append(f"ISSN: {detail['issn']} | EISSN: {detail['eissn']}")
    if detail.get("publisher"):
        lines.append(f"出版社: {detail['publisher']}")
    metrics = []
    if detail.get("impact_factor") and detail["impact_factor"] != "未公开":
        metrics.append(f"IF: {detail['impact_factor']}")
    if detail.get("jcr_quartile") and detail["jcr_quartile"] != "未公开":
        metrics.append(f"JCR分区: {detail['jcr_quartile']}")
    if detail.get("cas_quartile") and detail["cas_quartile"] != "未公开":
        metrics.append(f"中科院分区: {detail['cas_quartile']}")
    if detail.get("h_index") and detail["h_index"] != "未公开":
        metrics.append(f"H-index: {detail['h_index']}")
    if detail.get("cited_by_count") and detail["cited_by_count"] != "未公开":
        metrics.append(f"被引: {detail['cited_by_count']}")
    if metrics:
        lines.append(" | ".join(metrics))
    if detail.get("research_areas"):
        lines.append("收录/分区:")
        for area in detail["research_areas"]:
            top = "🏆 " if area.get("is_top") else ""
            name = area.get("name_zh") or area.get("name_en", "")
            lines.append(f"  {top}{name}: {area['partition']}")
    if detail.get("jcr_categories"):
        lines.append("JCR类别:")
        for cat in detail["jcr_categories"]:
            name = cat.get("name_zh") or cat.get("name_en", "")
            lines.append(f"  {name}: {cat['partition']}")
    lines.append(f"\n数据来源: {source}")
    if links:
        lines.append("参考链接（本次查询使用的源）:")
        for name, url in links.items():
            lines.append(f"  {name}: {url}")
    return "\n".join(lines)

def crossref_search_by_issn(issn, verbose=False):
    try:
        url = f"https://api.crossref.org/journals/{quote(issn)}"
        headers = {"User-Agent": "JournalFinder/1.0 (mailto:example@example.com)"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        journal = data.get("message", {})
        if not journal:
            return None
        title = journal.get("title", "")
        publisher = journal.get("publisher", "")
        issn_list = journal.get("ISSN", [])
        eissn = ""
        for issn_info in journal.get("issn-type", []):
            if issn_info.get("type") == "electronic":
                eissn = issn_info.get("value", "")
                break
        return {
            "title": title,
            "issn": issn_list[0] if issn_list else issn,
            "eissn": eissn if eissn else (issn_list[0] if issn_list else issn),
            "publisher": publisher,
            "research_areas": [],
            "jcr_categories": []
        }
    except Exception as e:
        if verbose:
            print(f"[crossref ISSN] 抓取失败: {e}", file=sys.stderr)
        return None

def crossref_search_journal(keyword, verbose=False):
    try:
        url = f"https://api.crossref.org/journals?query={quote(keyword)}"
        headers = {"User-Agent": "JournalFinder/1.0 (mailto:example@example.com)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("message", {}).get("items", [])
        if not items:
            return None
        journal = items[0]
        title = journal.get("title", keyword)
        issn_list = journal.get("ISSN", [])
        eissn = ""
        for issn_info in journal.get("issn-type", []):
            if issn_info.get("type") == "electronic":
                eissn = issn_info.get("value", "")
                break
        publisher = journal.get("publisher", "")
        return {
            "title": title,
            "issn": issn_list[0] if issn_list else "",
            "eissn": eissn if eissn else (issn_list[0] if issn_list else ""),
            "publisher": publisher,
            "research_areas": [],
            "jcr_categories": []
        }
    except Exception as e:
        if verbose:
            print(f"[crossref] 抓取失败: {e}", file=sys.stderr)
        return None

def _extract_openalex_fields(source, fallback_title):
    title = source.get("display_name", fallback_title)
    issn_l = source.get("issn_l", "")
    issn_list = source.get("issn", [])
    issn = issn_l if issn_l else (issn_list[0] if issn_list else "")
    publisher = source.get("publisher", "")
    citation_count = source.get("cited_by_count", 0)
    h_index = source.get("h_index", 0)
    summary = source.get("summary_stats") or {}
    impact_factor = summary.get("2yr_mean_citedness", 0)
    if impact_factor:
        impact_factor = round(impact_factor, 3)
    return {
        "title": title,
        "issn": issn,
        "eissn": "",
        "publisher": publisher,
        "impact_factor": str(impact_factor) if impact_factor else "",
        "h_index": str(h_index) if h_index else "",
        "cited_by_count": str(citation_count) if citation_count else "",
        "research_areas": [],
        "jcr_categories": []
    }

def openalex_search_journal(keyword, verbose=False):
    try:
        url = f"https://api.openalex.org/sources?search={quote(keyword)}&per_page=10"
        headers = {"User-Agent": "JournalFinder/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        kw_lower = keyword.lower().strip()
        best = None
        for source in results:
            display = source.get("display_name", "")
            alt_titles = [t.lower() for t in source.get("alternate_titles", [])]
            if kw_lower in display.lower() or any(kw_lower in t for t in alt_titles):
                best = source
                break
        if not best:
            best = results[0]
        return _extract_openalex_fields(best, keyword)
    except Exception as e:
        if verbose:
            print(f"[openalex] 抓取失败: {e}", file=sys.stderr)
        return None

def openalex_search_by_issn(issn, verbose=False):
    try:
        url = f"https://api.openalex.org/sources?filter=issn:{quote(issn)}"
        headers = {"User-Agent": "JournalFinder/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        return _extract_openalex_fields(results[0], "")
    except Exception as e:
        if verbose:
            print(f"[openalex ISSN] 抓取失败: {e}", file=sys.stderr)
        return None

def letpub_search(keyword, issn=None, verbose=False):
    try:
        url = "https://www.letpub.com.cn/index.php"
        data = {
            "page": "journalapp",
            "view": "search",
            "searchname": keyword,
            "searchissn": issn if issn else "",
            "searchfield": "",
            "searchcref": "yes",
            "viewtype": "table"
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://www.letpub.com.cn/index.php?page=journalapp",
            "Origin": "https://www.letpub.com.cn"
        }
        resp = requests.post(url, data=data, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_=re.compile(r"table_(sci|yjfx)"))
        if not table:
            return None
        rows = table.find_all("tr")
        if len(rows) < 2:
            return None
        header_cols = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        data_cols = [c.get_text(strip=True) for c in rows[1].find_all("td")]
        if not data_cols:
            return None
        title_en = data_cols[0] if data_cols else keyword
        issn_val = data_cols[2] if len(data_cols) > 2 else ""
        impact = ""
        cas = ""
        jcr = ""
        for idx, h in enumerate(header_cols):
            h_low = h.lower()
            if idx < len(data_cols):
                val = data_cols[idx].strip()
                if "影响因子" in h or "impact factor" in h_low:
                    impact = val
                elif "中科院" in h or "cas" in h_low:
                    cas = val.replace("查看详情", "").strip()
                elif "jcr" in h_low and "分区" in h:
                    jcr = val.replace("查看详情", "").strip()
        if not impact:
            if len(data_cols) > 3:
                impact = data_cols[3].strip()
        if not cas:
            if len(data_cols) > 4:
                cas = data_cols[4].replace("查看详情", "").strip()
        if not jcr:
            if len(data_cols) > 5:
                jcr = data_cols[5].replace("查看详情", "").strip()
        return {
            "title": title_en,
            "issn": issn_val,
            "impact_factor": impact,
            "cas_quartile": cas,
            "jcr_quartile": jcr,
            "research_areas": [{"name_en": "中科院分区", "name_zh": "中科院分区", "partition": cas, "is_top": "Top" in cas}] if cas else []
        }
    except Exception as e:
        if verbose:
            print(f"[letpub] 抓取失败: {e}", file=sys.stderr)
        return None

def medsci_search(keyword, verbose=False, retries=3):
    attempt = 0
    while attempt < retries:
        try:
            url = "https://www.medsci.cn/sci/json/queryJournalList.do"
            data = {"q": keyword, "page": 1, "rows": 5}
            headers = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
            resp = requests.post(url, data=data, headers=headers, timeout=15)
            resp.raise_for_status()
            try:
                result = resp.json()
            except:
                return None
            rows = result.get("rows", [])
            if not rows:
                return None
            item = rows[0]
            title = item.get("fullname") or item.get("title", "")
            issn = item.get("issn", "")
            impact = item.get("impactFactor") or item.get("impact_factor", "")
            partition = item.get("section", "")
            cas = item.get("cas_quartile", "")
            jcr = item.get("jcr_quartile") or item.get("jcr_partition", "") or partition
            return {
                "title": title,
                "issn": issn,
                "impact_factor": str(impact) if impact else "",
                "cas_quartile": cas,
                "jcr_quartile": jcr,
                "research_areas": [{"name_en": "MedSci", "name_zh": "MedSci分区", "partition": jcr, "is_top": False}] if jcr else []
            }
        except Exception as e:
            attempt += 1
            if verbose:
                print(f"[medsci] 抓取失败: {e}", file=sys.stderr)
            time.sleep(2)
    return None

def cnki_search(keyword, verbose=False):
    try:
        url = "https://navi.cnki.net/knavi/journal/Search"
        params = {"searchType": "0", "searchValue": keyword}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://navi.cnki.net/"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("ul.jour-list li")
        if not items:
            return None
        first = items[0]
        title_tag = first.select_one("a.name")
        if not title_tag:
            return None
        title = title_tag.get_text(strip=True)
        issn_tag = first.select_one("span.issn")
        issn = issn_tag.get_text(strip=True).replace("ISSN：", "") if issn_tag else ""
        pub_tag = first.select_one("span.org")
        publisher = pub_tag.get_text(strip=True) if pub_tag else ""
        return {
            "title": title,
            "issn": issn,
            "eissn": "",
            "publisher": publisher,
            "research_areas": [],
            "jcr_categories": []
        }
    except Exception as e:
        if verbose:
            print(f"[cnki] 抓取失败: {e}", file=sys.stderr)
        return None

def main():
    if not HAS_DRISSION:
        print("DrissionPage未安装，在线搜索将降级为requests方案", file=sys.stderr)
        print("安装命令：pip install DrissionPage", file=sys.stderr)

    parser = argparse.ArgumentParser()
    parser.add_argument("keyword")
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args()

    search_kw = args.keyword.strip()

    final = {
        "title": search_kw,
        "issn": "",
        "eissn": "",
        "publisher": "",
        "impact_factor": "",
        "h_index": "",
        "cited_by_count": "",
        "cas_quartile": "",
        "jcr_quartile": "",
        "research_areas": [],
        "jcr_categories": [],
        "sources_used": []
    }

    used_links = {}
    pretrain_contributed = False

    def merge(source_name, detail, link=None, is_pretrain=False):
        nonlocal pretrain_contributed
        if not detail:
            return
        if not final["title"] or final["title"] == search_kw:
            final["title"] = detail.get("title") or final["title"]
        if not final["issn"]:
            final["issn"] = detail.get("issn", "")
        if not final["eissn"]:
            final["eissn"] = detail.get("eissn", "")
        if not final["publisher"]:
            final["publisher"] = detail.get("publisher", "")
        if not final["impact_factor"] and detail.get("impact_factor"):
            final["impact_factor"] = detail["impact_factor"]
        if not final["h_index"] and detail.get("h_index"):
            final["h_index"] = detail["h_index"]
        if not final["cited_by_count"] and detail.get("cited_by_count"):
            final["cited_by_count"] = detail["cited_by_count"]
        if not final["cas_quartile"] and detail.get("cas_quartile"):
            final["cas_quartile"] = detail["cas_quartile"]
        if not final["jcr_quartile"] and detail.get("jcr_quartile"):
            final["jcr_quartile"] = detail["jcr_quartile"]
        if detail.get("research_areas"):
            final["research_areas"].extend(detail["research_areas"])
        if detail.get("jcr_categories"):
            final["jcr_categories"].extend(detail["jcr_categories"])
        if is_pretrain:
            pretrain_contributed = True
        else:
            if source_name not in final["sources_used"]:
                final["sources_used"].append(source_name)
            if link:
                used_links[source_name] = link

    known_issn = None
    matched_title = None
    if search_kw in ZH_TO_ISSN:
        known_issn = ZH_TO_ISSN[search_kw]
        matched_title = search_kw
    else:
        for name, issn in ZH_TO_ISSN.items():
            if search_kw in name:
                known_issn = issn
                matched_title = name
                break
    if known_issn:
        final["issn"] = known_issn
        if matched_title and matched_title != search_kw:
            final["title"] = matched_title
        merge("预训练 (内置期刊库)", {"title": final["title"], "issn": known_issn}, None, is_pretrain=True)

    if known_issn:
        cr = crossref_search_by_issn(known_issn, args.verbose)
        if cr and cr.get("title"):
            merge("CrossRef", cr, f"https://search.crossref.org/?q={known_issn}")
        oa = openalex_search_by_issn(known_issn, args.verbose)
        if oa:
            merge("OpenAlex", oa, f"https://openalex.org/sources?filter=issn%3A{known_issn}")

    if not final["issn"]:
        oa = openalex_search_journal(search_kw, args.verbose)
        if oa and oa.get("issn"):
            merge("OpenAlex", oa, f"https://openalex.org/sources?search={quote(search_kw)}")
        else:
            cr = crossref_search_journal(search_kw, args.verbose)
            if cr and cr.get("issn"):
                merge("CrossRef", cr, f"https://search.crossref.org/?q={quote(search_kw)}")

    if not final["issn"]:
        cnki = cnki_search(search_kw, args.verbose)
        if cnki and cnki.get("issn"):
            final["issn"] = cnki["issn"]
            cr = crossref_search_by_issn(cnki["issn"], args.verbose)
            if cr and cr.get("title"):
                merge("CrossRef (CNKI→ISSN)", cr, f"https://search.crossref.org/?q={cnki['issn']}")
            else:
                merge("CNKI", cnki, f"https://navi.cnki.net/knavi/journal/Search?searchValue={quote(search_kw)}")

    cur_issn = final["issn"]
    if cur_issn:
        oa_issn = openalex_search_by_issn(cur_issn, args.verbose)
        if oa_issn:
            merge("OpenAlex", oa_issn, f"https://openalex.org/sources?filter=issn%3A{cur_issn}")

    title_for_query = final["title"] if final["title"] != search_kw else search_kw
    if not final["impact_factor"] or not final["jcr_quartile"]:
        lp = None
        if cur_issn:
            lp = letpub_search(title_for_query, issn=cur_issn, verbose=args.verbose)
        if not lp:
            lp = letpub_search(title_for_query, verbose=args.verbose)
        if lp:
            merge("LetPub", lp, f"https://www.letpub.com.cn/index.php?page=journalapp&view=search&searchname={quote(title_for_query)}&searchissn={cur_issn or ''}")

    ms = medsci_search(title_for_query, args.verbose)
    if ms:
        merge("MedSci", ms, f"https://www.medsci.cn/sci/journal.do?issn={cur_issn}" if cur_issn else f"https://www.medsci.cn/sci/json/queryJournalList.do?q={quote(title_for_query)}")

    if not final["issn"] and not final["impact_factor"] and not args.fast:
        xr_res = search_journal_xr(search_kw, args.year, args.verbose)
        xr_path = xr_res.get("best_path") if xr_res else None
        if xr_path:
            xr = get_journal_detail_xr(xr_path, args.verbose)
            if xr:
                merge("XR-Scholar", xr, f"{BASE_URL_XR}{xr_path}")

    if not final["impact_factor"]:
        final["impact_factor"] = "未公开"
    if not final["cited_by_count"]:
        final["cited_by_count"] = "未公开"
    if not final["jcr_quartile"]:
        final["jcr_quartile"] = "未公开"
    if not final["cas_quartile"]:
        final["cas_quartile"] = "未公开"
    if not final["h_index"]:
        final["h_index"] = "未公开"

    if not final["sources_used"] and pretrain_contributed:
        final["sources_used"].append("预训练 (内置期刊库)")

    if not final["sources_used"]:
        if args.json:
            print(json.dumps({"ok": False, "error": "所有在线源均无有效数据"}, ensure_ascii=False, indent=2))
        else:
            print(f"❌ 查询失败：{search_kw}")
            print("⚠️ 所有在线源均未查找到该期刊信息。", file=sys.stderr)
        return 1

    source_str = " + ".join(final["sources_used"]) if final["sources_used"] else search_kw
    if args.json:
        out = {"ok": True, "source": source_str, "data": final, "links": used_links}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_output(final, source_str, used_links))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)