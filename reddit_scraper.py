#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Novel Bridge Reddit Demand Scraper

Default mode:
- RSS/API-free mode using Reddit search RSS feeds

Optional mode:
- Reddit API mode using PRAW when REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET exist

Output:
- reddit_demand_data.csv
"""

from __future__ import annotations

import csv
import html
import os
from pathlib import Path
import re
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

import feedparser
import requests
from bs4 import BeautifulSoup


# =============================================================================
# CONFIG
# =============================================================================

SUBREDDITS = [
    "manga",
    "manhwa",
    "LightNovels",
    "noveltranslations",
    "SoloLeveling",
    "OmniscientReader",
    "ProgressionFantasy",
    "anime",
    "webtoons",
    "LightNovelPub",
]

KEYWORD_GROUPS = {
    "continue_intent": [
        "where to continue",
        "what chapter after anime",
        "continue after anime",
        "continue after manga",
        "where to start novel",
        "what volume after anime",
        "what chapter after season",
        "read the original novel",
        "novel ahead of anime",
    ],
    "access_pain": [
        "no english translation",
        "where to read",
        "can't find raw",
        "cant find raw",
        "cannot find raw",
        "only in korean",
        "only in japanese",
        "only in chinese",
        "no official release",
        "licensed nowhere",
        "unavailable",
        "unreadable mtl",
        "only available on",
    ],
    "platform_friction": [
        "naver series",
        "kakao page",
        "kakaopage",
        "ridibooks",
        "ridi",
        "syosetu",
        "shousetsuka ni narou",
        "kakuyomu",
        "pixiv novel",
        "jjwxc",
        "qidian",
        "bilibili comics",
        "bookwalker",
    ],
}

SEARCH_LIMIT_PER_KEYWORD = 100
COMMENT_LIMIT_PER_POST = 50
OUTPUT_FILENAME = "reddit_demand_data.csv"
TOP_N = 100
SLEEP_BETWEEN_REQUESTS_SECONDS = 0.5
SLEEP_ON_ERROR_SECONDS = 2.0
MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 30
OUTPUT_PATH = Path(__file__).resolve().with_name(OUTPUT_FILENAME)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 NovelBridgeResearch/0.1"
)

TEXT_NORMALIZATION_REPLACEMENTS = {
    "Ã¢â‚¬Å“": '"',
    "Ã¢â‚¬\x9d": '"',
    "Ã¢â‚¬Ëœ": "'",
    "Ã¢â‚¬â„¢": "'",
    "Ã¢â‚¬Â¦": "...",
    "â€œ": '"',
    "â€\x9d": '"',
    "â€˜": "'",
    "â€™": "'",
}

ALIAS_MAP = {
    "orv": "Omniscient Reader's Viewpoint",
    "omniscient reader": "Omniscient Reader's Viewpoint",
    "omniscient reader's viewpoint": "Omniscient Reader's Viewpoint",
    "omniscient readers viewpoint": "Omniscient Reader's Viewpoint",
    "solo leveling": "Solo Leveling",
    "tbate": "The Beginning After The End",
    "the beginning after the end": "The Beginning After The End",
    "lotm": "Lord of the Mysteries",
    "lord of mysteries": "Lord of the Mysteries",
    "lord of the mysteries": "Lord of the Mysteries",
    "sss class suicide hunter": "SSS-Class Suicide Hunter",
    "sss-class suicide hunter": "SSS-Class Suicide Hunter",
}

SUBREDDIT_TITLE_HINTS = {
    "SoloLeveling": "Solo Leveling",
    "OmniscientReader": "Omniscient Reader's Viewpoint",
}

GENERIC_JUNK_PATTERNS = [
    r"\bwhere to read\b",
    r"\bwhere can i read\b",
    r"\bwhat chapter\b",
    r"\bwhich chapter\b",
    r"\bchapter\s+\d+\b",
    r"\bepisode\s+\d+\b",
    r"\bseason\s+\d+\b",
    r"\bvolume\s+\d+\b",
    r"\benglish translation\b",
    r"\bofficial translation\b",
    r"\boriginal novel\b",
    r"\blight novel\b",
    r"\bweb novel\b",
    r"\bwebnovel\b",
    r"\bmanhwa\b",
    r"\bmanga\b",
    r"\banime\b",
    r"\bnovel\b",
    r"\braws?\b",
    r"\bmtl\b",
    r"\brecommendations?\b",
    r"\bsuggestions?\b",
    r"\bhelp\b",
    r"\bquestion\b",
    r"\bdiscussion\b",
]

TITLE_STOPWORDS = {
    "where",
    "what",
    "which",
    "when",
    "why",
    "how",
    "read",
    "reading",
    "continue",
    "chapter",
    "season",
    "episode",
    "volume",
    "novel",
    "anime",
    "manga",
    "manhwa",
    "webtoon",
    "translation",
    "official",
    "raw",
    "raws",
    "mtl",
    "english",
    "korean",
    "japanese",
    "chinese",
    "recommend",
    "recommendation",
    "suggest",
    "help",
    "question",
    "discussion",
    "looking",
    "find",
    "available",
    "licensed",
}

ORIGIN_MARKET_HINTS = {
    "KR": [
        "korean",
        "manhwa",
        "webtoon",
        "naver",
        "naver series",
        "kakao",
        "kakao page",
        "kakaopage",
        "ridibooks",
        "ridi",
    ],
    "JP": [
        "japanese",
        "manga",
        "light novel",
        "syosetu",
        "shousetsuka ni narou",
        "kakuyomu",
        "pixiv novel",
        "bookwalker",
    ],
    "CN": [
        "chinese",
        "manhua",
        "qidian",
        "webnovel",
        "jjwxc",
        "bilibili",
    ],
}

SOURCE_TYPE_HINTS = {
    "anime": ["anime", "episode", "season"],
    "manga": ["manga", "chapter"],
    "manhwa": ["manhwa", "webtoon"],
    "web novel": ["web novel", "webnovel", "raw", "mtl", "qidian", "syosetu", "kakuyomu", "jjwxc"],
    "novel": ["novel", "light novel", "volume"],
}


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class RawSignal:
    title: str
    subreddit: str
    source_type: str
    origin_market: str
    continue_intent: int
    access_pain: int
    platform_friction: int
    upvotes: int
    quote: str
    reddit_id: str
    permalink: str
    keyword: str = ""
    published_at: str = ""


@dataclass
class AggregateSignal:
    title: str
    source_type_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    origin_market_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    continue_intent: int = 0
    access_pain: int = 0
    platform_friction: int = 0
    total_mentions: int = 0
    total_upvotes: int = 0
    subreddits_found: Set[str] = field(default_factory=set)
    sample_quotes: List[str] = field(default_factory=list)

    @property
    def source_type(self) -> str:
        return pick_most_common(self.source_type_counts, default="Unknown")

    @property
    def origin_market(self) -> str:
        return pick_most_common(self.origin_market_counts, default="Unknown")

    @property
    def opportunity_score(self) -> int:
        return self.continue_intent * self.access_pain

    @property
    def friction_weighted_score(self) -> int:
        return self.continue_intent * (self.access_pain + self.platform_friction)


@dataclass
class SourceConfig:
    mode: str
    user_agent: str
    reddit: Any = None
    session: Optional[requests.Session] = None


class RSSRateLimitedError(RuntimeError):
    pass


# =============================================================================
# UTILS
# =============================================================================


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    for source, replacement in TEXT_NORMALIZATION_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return clean_text(soup.get_text(" ", strip=True))


def normalize_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"^[\[\(\{<\"']+|[\]\)\}>\"'.,:;!?]+$", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    low = title.lower()
    low = re.sub(r"[^a-z0-9'\-\s:]", "", low).strip()
    low = re.sub(r"\s+", " ", low)

    if low in ALIAS_MAP:
        return ALIAS_MAP[low]

    return smart_title_case(title)


def smart_title_case(text: str) -> str:
    small_words = {"of", "the", "a", "an", "and", "or", "to", "in", "on", "for", "from", "with"}
    words = re.split(r"(\s+)", text.strip())
    out = []
    word_index = 0
    for word in words:
        if word.isspace():
            out.append(word)
            continue
        lower = word.lower()
        if word.isupper() and len(word) <= 5:
            out.append(word)
        elif word_index > 0 and lower in small_words:
            out.append(lower)
        else:
            out.append(word[:1].upper() + word[1:].lower())
        word_index += 1
    return "".join(out).strip()


def is_junk_title(candidate: str) -> bool:
    if not candidate:
        return True

    normalized = candidate.strip()
    low = normalized.lower()

    if len(normalized) < 3 or len(normalized) > 100:
        return True

    if low in ALIAS_MAP:
        return False

    for pattern in GENERIC_JUNK_PATTERNS:
        if re.search(pattern, low):
            return True

    tokens = re.findall(r"[a-zA-Z]+", low)
    if not tokens:
        return True

    stop_ratio = sum(1 for token in tokens if token in TITLE_STOPWORDS) / max(len(tokens), 1)
    if stop_ratio >= 0.60:
        return True

    if re.fullmatch(r"(chapter|episode|season|volume)?\s*\d+", low):
        return True

    return False


def pick_most_common(counts: Dict[str, int], default: str = "Unknown") -> str:
    clean_counts = {key: value for key, value in counts.items() if key and key != "Unknown" and value > 0}
    if not clean_counts:
        return default
    return sorted(clean_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def truncate_quote(text: str, max_len: int = 260) -> str:
    text = normalize_space(clean_text(text))
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def keyword_regex(keyword: str) -> re.Pattern[str]:
    escaped = re.escape(keyword.lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


COMPILED_KEYWORDS = {
    group: [(keyword, keyword_regex(keyword)) for keyword in keywords]
    for group, keywords in KEYWORD_GROUPS.items()
}


def all_keywords() -> List[str]:
    seen: List[str] = []
    for keywords in KEYWORD_GROUPS.values():
        for keyword in keywords:
            if keyword not in seen:
                seen.append(keyword)
    return seen


# =============================================================================
# CLASSIFICATION
# =============================================================================


def classify_intent(text: str) -> Dict[str, int]:
    text = clean_text(text).lower()
    result = {
        "continue_intent": 0,
        "access_pain": 0,
        "platform_friction": 0,
    }
    for group, pairs in COMPILED_KEYWORDS.items():
        for _, pattern in pairs:
            if pattern.search(text):
                result[group] += 1
    return result


def infer_origin_market(text: str, subreddit_name: str = "") -> str:
    low = f"{text} {subreddit_name}".lower()
    scores: Dict[str, int] = {}
    for market, hints in ORIGIN_MARKET_HINTS.items():
        scores[market] = sum(1 for hint in hints if hint in low)

    if subreddit_name.lower() in {"manhwa", "webtoons", "sololeveling", "omniscientreader"}:
        scores["KR"] = scores.get("KR", 0) + 1
    if subreddit_name.lower() in {"lightnovels", "manga", "anime"}:
        scores["JP"] = scores.get("JP", 0) + 1
    if subreddit_name.lower() in {"noveltranslations"}:
        scores["CN"] = scores.get("CN", 0) + 1

    best = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
    return best[0] if best[1] > 0 else "Unknown"


def infer_source_type(text: str, subreddit_name: str = "") -> str:
    low = f"{text} {subreddit_name}".lower()
    scores: Dict[str, int] = {}
    for source_type, hints in SOURCE_TYPE_HINTS.items():
        scores[source_type] = sum(1 for hint in hints if hint in low)

    if subreddit_name.lower() == "manhwa":
        scores["manhwa"] = scores.get("manhwa", 0) + 1
    if subreddit_name.lower() == "manga":
        scores["manga"] = scores.get("manga", 0) + 1
    if subreddit_name.lower() == "lightnovels":
        scores["novel"] = scores.get("novel", 0) + 1

    best = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
    return best[0] if best[1] > 0 else "Unknown"


# =============================================================================
# TITLE EXTRACTION
# =============================================================================


def extract_title(text: str, known_aliases: Optional[Dict[str, str]] = None) -> Optional[str]:
    if not text:
        return None

    known_aliases = known_aliases or ALIAS_MAP
    raw_text = clean_text(text)
    low = raw_text.lower()

    for alias, canonical in sorted(known_aliases.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", low, flags=re.IGNORECASE):
            return canonical

    candidates: List[str] = []

    quoted_patterns = [
        r"\"([^\"]{3,100})\"",
        r"'([^']{3,100})'",
        r"\[([^\]]{3,100})\]",
        r"\(([A-Z][^)]{3,100})\)",
    ]
    for pattern in quoted_patterns:
        candidates.extend(re.findall(pattern, raw_text))

    marker_patterns = [
        r"(?:after|continue after|read after|start after)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})",
        r"(?:where to read|where can i read|where do i read)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})",
        r"(?:raws? for|translation for|novel for)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})",
        r"(?:is|does)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})\s+(?:have|continue|available)",
    ]
    for pattern in marker_patterns:
        candidates.extend(re.findall(pattern, raw_text, flags=re.IGNORECASE))

    title_case = re.findall(
        r"\b(?:[A-Z][A-Za-z0-9'\-]{2,}|[A-Z]{2,5})(?:\s+(?:of|the|a|an|and|or|to|in|on|for|from|with|[A-Z][A-Za-z0-9'\-]{2,}|[A-Z]{2,5})){1,8}\b",
        raw_text,
    )
    candidates.extend(title_case)

    cleaned: List[str] = []
    for candidate in candidates:
        candidate = re.split(
            r"\b(?:where|what|which|chapter|episode|season|volume|anime|manga|manhwa|novel|translation|raw|official)\b",
            candidate,
            flags=re.IGNORECASE,
        )[0]
        candidate = normalize_title(candidate)
        if not is_junk_title(candidate):
            cleaned.append(candidate)

    if not cleaned:
        return None

    cleaned = sorted(set(cleaned), key=lambda value: (-min(len(value), 60), value))
    return cleaned[0]


def extract_title_from_submission(subreddit_name: str, submission_title: str, submission_text: str = "") -> Optional[str]:
    combined = f"{submission_title}\n{submission_text}".strip()
    if subreddit_name in SUBREDDIT_TITLE_HINTS:
        signals = classify_intent(combined)
        if sum(signals.values()) > 0:
            return SUBREDDIT_TITLE_HINTS[subreddit_name]
    return extract_title(combined)


# =============================================================================
# SOURCE SELECTION
# =============================================================================


def create_requests_session(user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
    )
    return session


def select_source() -> SourceConfig:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT") or DEFAULT_USER_AGENT

    if client_id and client_secret:
        try:
            import praw  # type: ignore
        except ImportError:
            print("[WARN] PRAW is unavailable, so the scraper is falling back to RSS mode.")
        else:
            print("[MODE] Using Reddit API mode via PRAW.")
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
                check_for_async=False,
            )
            return SourceConfig(mode="praw", user_agent=user_agent, reddit=reddit)

    print("[MODE] Using RSS mode (API-free fallback).")
    return SourceConfig(mode="rss", user_agent=user_agent, session=create_requests_session(user_agent))


# =============================================================================
# SCRAPING
# =============================================================================


def scrape_subreddit(subreddit_name: str, source: SourceConfig) -> List[RawSignal]:
    if source.mode == "praw":
        return scrape_subreddit_praw(source.reddit, subreddit_name)
    return scrape_subreddit_rss(source.session, subreddit_name)


def scrape_subreddit_praw(reddit: Any, subreddit_name: str) -> List[RawSignal]:
    rows: List[RawSignal] = []
    seen_submission_ids: Set[str] = set()
    subreddit = reddit.subreddit(subreddit_name)
    keywords = all_keywords()

    print(f"\n[SUBREDDIT PRAW] r/{subreddit_name}")

    for index, keyword in enumerate(keywords, start=1):
        print(f"  [{index}/{len(keywords)}] Searching keyword: {keyword!r}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                submissions = subreddit.search(
                    query=f'"{keyword}"',
                    sort="relevance",
                    time_filter="year",
                    limit=SEARCH_LIMIT_PER_KEYWORD,
                )

                for submission in submissions:
                    submission_id = str(getattr(submission, "id", "") or "")
                    if not submission_id or submission_id in seen_submission_ids:
                        continue
                    seen_submission_ids.add(submission_id)
                    rows.extend(process_praw_submission(subreddit_name, submission, keyword))

                time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)
                break
            except Exception as exc:
                print(f"    [ERROR] PRAW r/{subreddit_name} keyword={keyword!r} attempt={attempt}: {exc}")
                if attempt == MAX_RETRIES:
                    traceback.print_exc()
                time.sleep(SLEEP_ON_ERROR_SECONDS * attempt)

    print(f"  [DONE] r/{subreddit_name}: {len(rows)} raw signal rows")
    return rows


def process_praw_submission(subreddit_name: str, submission: Any, keyword: str) -> List[RawSignal]:
    rows: List[RawSignal] = []

    title_text = clean_text(getattr(submission, "title", "") or "")
    self_text = clean_text(getattr(submission, "selftext", "") or "")
    permalink = f"https://www.reddit.com{getattr(submission, 'permalink', '')}"
    upvotes = int(getattr(submission, "score", 0) or 0)
    num_comments = int(getattr(submission, "num_comments", 0) or 0)
    reddit_id = str(getattr(submission, "id", "") or "")
    published_at = str(getattr(submission, "created_utc", "") or "")

    combined_post_text = f"{title_text}\n{self_text}".strip()
    title = extract_title_from_submission(subreddit_name, title_text, self_text)
    post_signals = classify_intent(combined_post_text)

    if title and sum(post_signals.values()) > 0:
        rows.append(
            RawSignal(
                title=title,
                subreddit=subreddit_name,
                source_type=infer_source_type(combined_post_text, subreddit_name),
                origin_market=infer_origin_market(combined_post_text, subreddit_name),
                continue_intent=post_signals["continue_intent"],
                access_pain=post_signals["access_pain"],
                platform_friction=post_signals["platform_friction"],
                upvotes=upvotes,
                quote=truncate_quote(combined_post_text),
                reddit_id=reddit_id,
                permalink=permalink,
                keyword=keyword,
                published_at=published_at,
            )
        )

    try:
        submission.comments.replace_more(limit=0)
        top_level_count = min(COMMENT_LIMIT_PER_POST, max(num_comments, 0))
        comments = list(submission.comments[:top_level_count])
    except Exception:
        comments = []

    for comment in comments:
        body = clean_text(getattr(comment, "body", "") or "")
        if not body:
            continue

        signals = classify_intent(body)
        if sum(signals.values()) == 0:
            continue

        comment_title = extract_title(body) or title
        if not comment_title:
            continue

        rows.append(
            RawSignal(
                title=comment_title,
                subreddit=subreddit_name,
                source_type=infer_source_type(body + " " + combined_post_text, subreddit_name),
                origin_market=infer_origin_market(body + " " + combined_post_text, subreddit_name),
                continue_intent=signals["continue_intent"],
                access_pain=signals["access_pain"],
                platform_friction=signals["platform_friction"],
                upvotes=int(getattr(comment, "score", 0) or 0),
                quote=truncate_quote(body),
                reddit_id=str(getattr(comment, "id", "") or ""),
                permalink=permalink,
                keyword=keyword,
                published_at=published_at,
            )
        )

    return rows


def scrape_subreddit_rss(session: Optional[requests.Session], subreddit_name: str) -> List[RawSignal]:
    if session is None:
        raise RuntimeError("RSS mode requires a requests session.")

    rows: List[RawSignal] = []
    seen_entry_ids: Set[str] = set()
    keywords = all_keywords()

    print(f"\n[SUBREDDIT RSS] r/{subreddit_name}")

    for index, keyword in enumerate(keywords, start=1):
        print(f"  [{index}/{len(keywords)}] Searching keyword: {keyword!r}")
        try:
            feed = fetch_rss_feed(session, subreddit_name, keyword)
        except RSSRateLimitedError as exc:
            print(f"    [WARN] {exc}")
            print(f"    [WARN] Stopping RSS collection early for r/{subreddit_name}.")
            break

        for entry in feed.entries[:SEARCH_LIMIT_PER_KEYWORD]:
            entry_id = clean_text(getattr(entry, "id", "") or getattr(entry, "link", "") or "")
            if not entry_id or entry_id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry_id)

            title_text = clean_text(getattr(entry, "title", "") or "")
            summary_html = get_feed_entry_summary_html(entry)
            summary_text = strip_html(summary_html)
            combined = f"{title_text}\n{summary_text}".strip()
            signals = classify_intent(combined)
            title = extract_title_from_submission(subreddit_name, title_text, summary_text)

            if not title or sum(signals.values()) == 0:
                continue

            rows.append(
                RawSignal(
                    title=title,
                    subreddit=subreddit_name,
                    source_type=infer_source_type(combined, subreddit_name),
                    origin_market=infer_origin_market(combined, subreddit_name),
                    continue_intent=signals["continue_intent"],
                    access_pain=signals["access_pain"],
                    platform_friction=signals["platform_friction"],
                    upvotes=0,
                    quote=truncate_quote(combined),
                    reddit_id=entry_id,
                    permalink=clean_text(getattr(entry, "link", "") or ""),
                    keyword=keyword,
                    published_at=clean_text(getattr(entry, "published", "") or getattr(entry, "updated", "") or ""),
                )
            )

        time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    print(f"  [DONE] r/{subreddit_name}: {len(rows)} raw signal rows")
    return rows


def fetch_rss_feed(session: requests.Session, subreddit_name: str, keyword: str) -> feedparser.FeedParserDict:
    url = f"https://www.reddit.com/r/{subreddit_name}/search.rss"
    params = {
        "q": f'"{keyword}"',
        "restrict_sr": "on",
        "sort": "relevance",
        "t": "year",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return feedparser.parse(response.text)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            print(f"    [ERROR] RSS r/{subreddit_name} keyword={keyword!r} attempt={attempt}: {exc}")
            if status_code == 429 and attempt == MAX_RETRIES:
                raise RSSRateLimitedError(
                    "Reddit RSS returned repeated 429 rate limits. The scraper will export any rows collected so far."
                ) from exc
            if attempt == MAX_RETRIES:
                break
            time.sleep(SLEEP_ON_ERROR_SECONDS * attempt)
        except Exception as exc:
            print(f"    [ERROR] RSS r/{subreddit_name} keyword={keyword!r} attempt={attempt}: {exc}")
            if attempt == MAX_RETRIES:
                break
            time.sleep(SLEEP_ON_ERROR_SECONDS * attempt)

    return feedparser.FeedParserDict(entries=[])


def get_feed_entry_summary_html(entry: Any) -> str:
    content = getattr(entry, "content", None)
    if content:
        first = content[0]
        if isinstance(first, dict):
            return str(first.get("value", "") or "")
        value = getattr(first, "value", "")
        if value:
            return str(value)
    return str(getattr(entry, "summary", "") or "")


# =============================================================================
# AGGREGATION / SCORING / EXPORT
# =============================================================================


def aggregate_by_title(raw_data: Sequence[RawSignal]) -> Dict[str, AggregateSignal]:
    aggregated: Dict[str, AggregateSignal] = {}

    for row in raw_data:
        title = normalize_title(row.title)
        if is_junk_title(title):
            continue

        if title not in aggregated:
            aggregated[title] = AggregateSignal(title=title)

        aggregate = aggregated[title]
        aggregate.continue_intent += row.continue_intent
        aggregate.access_pain += row.access_pain
        aggregate.platform_friction += row.platform_friction
        aggregate.total_mentions += 1
        aggregate.total_upvotes += max(0, row.upvotes)
        aggregate.subreddits_found.add(row.subreddit)
        aggregate.source_type_counts[row.source_type] += 1
        aggregate.origin_market_counts[row.origin_market] += 1

        if row.quote and len(aggregate.sample_quotes) < 5:
            quote = row.quote.replace("\n", " ").strip()
            if quote not in aggregate.sample_quotes:
                aggregate.sample_quotes.append(quote)

    return aggregated


def calculate_scores(aggregated: Dict[str, AggregateSignal]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for title, aggregate in aggregated.items():
        if aggregate.continue_intent == 0 and aggregate.access_pain == 0 and aggregate.platform_friction == 0:
            continue

        rows.append(
            {
                "title": title,
                "source_type": aggregate.source_type,
                "origin_market": aggregate.origin_market,
                "continue_intent": aggregate.continue_intent,
                "access_pain": aggregate.access_pain,
                "platform_friction": aggregate.platform_friction,
                "total_mentions": aggregate.total_mentions,
                "total_upvotes": aggregate.total_upvotes,
                "subreddits_found": "; ".join(sorted(aggregate.subreddits_found)),
                "sample_quotes": " || ".join(aggregate.sample_quotes[:5]),
                "opportunity_score": aggregate.opportunity_score,
                "friction_weighted_score": aggregate.friction_weighted_score,
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row["friction_weighted_score"]),
            -int(row["opportunity_score"]),
            -int(row["total_mentions"]),
            str(row["title"]).lower(),
        )
    )
    return rows[:TOP_N]


def export_csv(data: Sequence[Dict[str, Any]], filename: str) -> None:
    fieldnames = [
        "title",
        "source_type",
        "origin_market",
        "continue_intent",
        "access_pain",
        "platform_friction",
        "total_mentions",
        "total_upvotes",
        "subreddits_found",
        "sample_quotes",
        "opportunity_score",
        "friction_weighted_score",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)

    print(f"\n[EXPORT] Wrote {len(data)} rows to {filename}")


# =============================================================================
# MAIN
# =============================================================================


def main() -> None:
    print("=" * 80)
    print("Novel Bridge Reddit Demand Scraper")
    print("=" * 80)
    print(f"Subreddits: {len(SUBREDDITS)}")
    print(f"Keywords: {len(all_keywords())}")
    print(f"Search limit: {SEARCH_LIMIT_PER_KEYWORD} posts per keyword per subreddit")
    print(f"Comment limit: {COMMENT_LIMIT_PER_POST} top-level comments per post")
    print("=" * 80)

    all_raw_rows: List[RawSignal] = []

    try:
        source = select_source()

        for index, subreddit_name in enumerate(SUBREDDITS, start=1):
            print(f"\n[{index}/{len(SUBREDDITS)}] Starting r/{subreddit_name}")
            try:
                rows = scrape_subreddit(subreddit_name, source)
                all_raw_rows.extend(rows)
            except KeyboardInterrupt:
                print("\n[STOPPED] KeyboardInterrupt received. Exporting partial results...")
                break
            except Exception as exc:
                print(f"[ERROR] Failed subreddit r/{subreddit_name}: {exc}")
                traceback.print_exc()
                time.sleep(SLEEP_ON_ERROR_SECONDS)
    except KeyboardInterrupt:
        print("\n[STOPPED] KeyboardInterrupt received before completion. Exporting partial results...")
    except Exception as exc:
        print(f"[ERROR] Fatal scraper setup failure: {exc}")
        traceback.print_exc()
    finally:
        print("\n" + "=" * 80)
        print(f"Raw signal rows collected: {len(all_raw_rows)}")

        aggregated = aggregate_by_title(all_raw_rows)
        print(f"Aggregated titles: {len(aggregated)}")

        scored = calculate_scores(aggregated)
        print(f"Final top rows: {len(scored)}")

        export_csv(scored, str(OUTPUT_PATH))

        print("\nTop 10 preview:")
        for row in scored[:10]:
            print(
                f"- {row['title']} | "
                f"continue={row['continue_intent']} "
                f"access={row['access_pain']} "
                f"platform={row['platform_friction']} "
                f"score={row['friction_weighted_score']}"
            )

        print("\nDone.")


if __name__ == "__main__":
    main()
