#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Novel Bridge Reddit Demand Scraper

Purpose
-------
Find Asian novel/IP titles with:
1) high continuation intent from international readers
2) high access pain around official/raw/translated sources
3) platform friction caused by KR/CN/JP domestic platforms

Output
------
reddit_demand_data.csv

Columns:
- title
- source_type
- origin_market
- continue_intent
- access_pain
- platform_friction
- total_mentions
- total_upvotes
- subreddits_found
- sample_quotes
- opportunity_score
- friction_weighted_score

Setup Reddit API credentials
----------------------------
1. Go to: https://www.reddit.com/prefs/apps
2. Click "create another app" or "create app"
3. Choose app type: "script"
4. Copy:
   - client_id: the short string under the app name
   - client_secret: the secret field
5. Set environment variables on Windows PowerShell:

   setx REDDIT_CLIENT_ID "your_client_id"
   setx REDDIT_CLIENT_SECRET "your_client_secret"
   setx REDDIT_USER_AGENT "NovelBridgeResearch/0.1 by your_reddit_username"

6. Restart your terminal after using setx.
7. Install dependencies:

   pip install praw

8. Run:

   python reddit_scraper.py

Notes
-----
- This is a research pipeline, not a perfect NLP/title extraction engine.
- It prioritizes actionable signals and sample quotes over exhaustive scraping.
- PRAW is preferred. If PRAW is unavailable or credentials are missing, this script
  falls back to Reddit public JSON search endpoints with limited functionality.
"""

from __future__ import annotations

import csv
import html
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


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
        "bookwalker jp",
    ],
}

SEARCH_LIMIT_PER_KEYWORD = 100
COMMENT_LIMIT_PER_POST = 50
OUTPUT_FILENAME = "reddit_demand_data.csv"
TOP_N = 100
SLEEP_BETWEEN_SEARCHES_SECONDS = 1.2
SLEEP_ON_ERROR_SECONDS = 5.0
MAX_RETRIES = 3
OUTPUT_PATH = Path(__file__).resolve().with_name(OUTPUT_FILENAME)

TEXT_NORMALIZATION_REPLACEMENTS = {
    "â€œ": '"',
    "â€\x9d": '"',
    "â€˜": "'",
    "â€™": "'",
    "â€¦": "...",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}

# If title extraction finds these, normalize to canonical names.
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

# Subreddit-level hints. Used only as weak fallback, not as truth.
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


def normalize_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(r"^[\[\(\{<\"']+|[\]\)\}>\"'.,:;!?]+$", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    low = title.lower()
    low = re.sub(r"[^a-z0-9'\-\s:]", "", low).strip()
    low = re.sub(r"\s+", " ", low)

    if low in ALIAS_MAP:
        return ALIAS_MAP[low]

    # Title-case ordinary extracted phrases, but preserve known canonical aliases.
    return smart_title_case(title)


def smart_title_case(text: str) -> str:
    small_words = {"of", "the", "a", "an", "and", "or", "to", "in", "on", "for", "from", "with"}
    words = re.split(r"(\s+)", text.strip())
    out = []
    word_index = 0
    for w in words:
        if w.isspace():
            out.append(w)
            continue
        raw = w
        lower = raw.lower()
        if raw.isupper() and len(raw) <= 5:
            out.append(raw)
        elif word_index > 0 and lower in small_words:
            out.append(lower)
        else:
            out.append(raw[:1].upper() + raw[1:].lower())
        word_index += 1
    return "".join(out).strip()


def is_junk_title(candidate: str) -> bool:
    if not candidate:
        return True

    c = candidate.strip()
    low = c.lower()

    if len(c) < 3 or len(c) > 100:
        return True

    if low in ALIAS_MAP:
        return False

    for pat in GENERIC_JUNK_PATTERNS:
        if re.search(pat, low):
            return True

    tokens = re.findall(r"[a-zA-Z]+", low)
    if not tokens:
        return True

    stop_ratio = sum(1 for t in tokens if t in TITLE_STOPWORDS) / max(len(tokens), 1)
    if stop_ratio >= 0.60:
        return True

    # Too numeric/generic.
    if re.fullmatch(r"(chapter|episode|season|volume)?\s*\d+", low):
        return True

    return False


def pick_most_common(counts: Dict[str, int], default: str = "Unknown") -> str:
    clean_counts = {k: v for k, v in counts.items() if k and k != "Unknown" and v > 0}
    if not clean_counts:
        return default
    return sorted(clean_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


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
    group: [(kw, keyword_regex(kw)) for kw in kws]
    for group, kws in KEYWORD_GROUPS.items()
}


def all_keywords() -> List[str]:
    seen = []
    for kws in KEYWORD_GROUPS.values():
        for kw in kws:
            if kw not in seen:
                seen.append(kw)
    return seen


# =============================================================================
# CLASSIFICATION
# =============================================================================

def classify_intent(text: str) -> Dict[str, int]:
    """
    Return binary counts for each signal group.
    If multiple keywords in the same group match, count the number of matches.
    """
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
    scores = {}
    for market, hints in ORIGIN_MARKET_HINTS.items():
        scores[market] = sum(1 for h in hints if h in low)

    if subreddit_name.lower() in {"manhwa", "webtoons", "sololeveling", "omniscientreader"}:
        scores["KR"] = scores.get("KR", 0) + 1
    if subreddit_name.lower() in {"lightnovels", "manga", "anime"}:
        scores["JP"] = scores.get("JP", 0) + 1
    if subreddit_name.lower() in {"noveltranslations"}:
        scores["CN"] = scores.get("CN", 0) + 1

    best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return best[0] if best[1] > 0 else "Unknown"


def infer_source_type(text: str, subreddit_name: str = "") -> str:
    low = f"{text} {subreddit_name}".lower()
    scores = {}
    for source_type, hints in SOURCE_TYPE_HINTS.items():
        scores[source_type] = sum(1 for h in hints if h in low)

    if subreddit_name.lower() == "manhwa":
        scores["manhwa"] = scores.get("manhwa", 0) + 1
    if subreddit_name.lower() == "manga":
        scores["manga"] = scores.get("manga", 0) + 1
    if subreddit_name.lower() == "lightnovels":
        scores["novel"] = scores.get("novel", 0) + 1

    best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return best[0] if best[1] > 0 else "Unknown"


# =============================================================================
# TITLE EXTRACTION
# =============================================================================

def extract_title(text: str, known_aliases: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Practical, imperfect title extractor.

    Strategy:
    1. Known aliases first.
    2. Quoted/bracketed titles.
    3. Phrases after common intent markers.
    4. Title-case multiword phrases.
    """
    if not text:
        return None

    known_aliases = known_aliases or ALIAS_MAP
    raw_text = clean_text(text)
    low = raw_text.lower()

    # 1. Known aliases first.
    for alias, canonical in sorted(known_aliases.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(alias)}\b", low, flags=re.IGNORECASE):
            return canonical

    candidates: List[str] = []

    # 2. Quoted/bracketed titles.
    quoted_patterns = [
        r"\"([^\"]{3,100})\"",
        r"'([^']{3,100})'",
        r"\[([^\]]{3,100})\]",
        r"\(([A-Z][^)]{3,100})\)",
    ]
    for pat in quoted_patterns:
        candidates.extend(re.findall(pat, raw_text))

    # 3. Phrases after intent markers.
    marker_patterns = [
        r"(?:after|continue after|read after|start after)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})",
        r"(?:where to read|where can i read|where do i read)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})",
        r"(?:raws? for|translation for|novel for)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})",
        r"(?:is|does)\s+([A-Z][A-Za-z0-9:'\-\s]{2,80})\s+(?:have|continue|available)",
    ]
    for pat in marker_patterns:
        candidates.extend(re.findall(pat, raw_text, flags=re.IGNORECASE))

    # 4. Title-case multiword phrases.
    # Examples: "Lord of the Mysteries", "The Beginning After The End"
    title_case = re.findall(
        r"\b(?:[A-Z][A-Za-z0-9'\-]{2,}|[A-Z]{2,5})(?:\s+(?:of|the|a|an|and|or|to|in|on|for|from|with|[A-Z][A-Za-z0-9'\-]{2,}|[A-Z]{2,5})){1,8}\b",
        raw_text,
    )
    candidates.extend(title_case)

    cleaned: List[str] = []
    for c in candidates:
        c = re.split(r"\b(?:where|what|which|chapter|episode|season|volume|anime|manga|manhwa|novel|translation|raw|official)\b", c, flags=re.IGNORECASE)[0]
        c = normalize_title(c)
        if not is_junk_title(c):
            cleaned.append(c)

    if not cleaned:
        return None

    # Prefer longer clean candidates, but not absurdly long.
    cleaned = sorted(set(cleaned), key=lambda x: (-min(len(x), 60), x))
    return cleaned[0]


def extract_title_from_submission(
    subreddit_name: str,
    submission_title: str,
    submission_text: str = "",
) -> Optional[str]:
    combined = f"{submission_title}\n{submission_text}".strip()

    # Specific title community fallback, but only if the post has a matching signal.
    if subreddit_name in SUBREDDIT_TITLE_HINTS:
        signals = classify_intent(combined)
        if sum(signals.values()) > 0:
            return SUBREDDIT_TITLE_HINTS[subreddit_name]

    return extract_title(combined)


# =============================================================================
# REDDIT CLIENTS
# =============================================================================

def get_praw_client() -> Any:
    try:
        import praw  # type: ignore
    except ImportError:
        print("[WARN] PRAW is not installed. Falling back to Reddit JSON endpoints.")
        return None

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "NovelBridgeResearch/0.1")

    if not client_id or not client_secret:
        print("[WARN] Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET.")
        print("[WARN] Falling back to Reddit JSON endpoints.")
        return None

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        check_for_async=False,
    )


def request_json(url: str, user_agent: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise PermissionError(
                "Reddit blocked the public JSON fallback. Set Reddit API credentials to run the scraper reliably."
            ) from exc
        raise
    return json.loads(body)


# =============================================================================
# SCRAPING
# =============================================================================

def scrape_subreddit(subreddit_name: str, keyword_groups: Dict[str, List[str]]) -> List[RawSignal]:
    """
    Scrape one subreddit.
    Uses PRAW if available, otherwise JSON fallback.
    """
    reddit = get_praw_client()
    if reddit is None:
        return scrape_subreddit_json_fallback(subreddit_name, keyword_groups)
    return scrape_subreddit_praw(reddit, subreddit_name, keyword_groups)


def scrape_subreddit_praw(
    reddit: Any,
    subreddit_name: str,
    keyword_groups: Dict[str, List[str]],
) -> List[RawSignal]:
    rows: List[RawSignal] = []
    seen_submission_ids: Set[str] = set()
    subreddit = reddit.subreddit(subreddit_name)
    keywords = all_keywords()

    print(f"\n[SUBREDDIT] r/{subreddit_name}")

    for idx, keyword in enumerate(keywords, start=1):
        print(f"  [{idx}/{len(keywords)}] Searching keyword: {keyword!r}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                submissions = subreddit.search(
                    query=f'"{keyword}"',
                    sort="relevance",
                    time_filter="year",
                    limit=SEARCH_LIMIT_PER_KEYWORD,
                )

                for submission in submissions:
                    if submission.id in seen_submission_ids:
                        continue
                    seen_submission_ids.add(submission.id)

                    rows.extend(process_praw_submission(subreddit_name, submission))

                time.sleep(SLEEP_BETWEEN_SEARCHES_SECONDS)
                break

            except Exception as exc:
                print(f"    [ERROR] r/{subreddit_name} keyword={keyword!r} attempt={attempt}: {exc}")
                if attempt == MAX_RETRIES:
                    traceback.print_exc()
                time.sleep(SLEEP_ON_ERROR_SECONDS * attempt)

    print(f"  [DONE] r/{subreddit_name}: {len(rows)} raw signal rows")
    return rows


def process_praw_submission(subreddit_name: str, submission: Any) -> List[RawSignal]:
    rows: List[RawSignal] = []

    title_text = clean_text(getattr(submission, "title", "") or "")
    self_text = clean_text(getattr(submission, "selftext", "") or "")
    permalink = f"https://www.reddit.com{getattr(submission, 'permalink', '')}"
    upvotes = int(getattr(submission, "score", 0) or 0)
    reddit_id = str(getattr(submission, "id", ""))

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
            )
        )

    # Comments.
    try:
        submission.comments.replace_more(limit=0)
        comments = list(submission.comments[:COMMENT_LIMIT_PER_POST])
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
                reddit_id=str(getattr(comment, "id", "")),
                permalink=permalink,
            )
        )

    return rows


def scrape_subreddit_json_fallback(
    subreddit_name: str,
    keyword_groups: Dict[str, List[str]],
) -> List[RawSignal]:
    """
    Public JSON fallback.

    Limitations:
    - No OAuth.
    - Less reliable.
    - Does not deeply fetch comments.
    - Use this only for smoke tests or when PRAW is unavailable.
    """
    rows: List[RawSignal] = []
    seen_submission_ids: Set[str] = set()
    user_agent = os.getenv("REDDIT_USER_AGENT", "NovelBridgeResearch/0.1")
    keywords = all_keywords()

    print(f"\n[SUBREDDIT JSON FALLBACK] r/{subreddit_name}")

    for idx, keyword in enumerate(keywords, start=1):
        print(f"  [{idx}/{len(keywords)}] Searching keyword: {keyword!r}")
        query = urllib.parse.quote(f'"{keyword}"')
        url = (
            f"https://www.reddit.com/r/{subreddit_name}/search.json"
            f"?q={query}&restrict_sr=1&sort=relevance&t=year&limit={SEARCH_LIMIT_PER_KEYWORD}"
        )

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                payload = request_json(url, user_agent=user_agent)
                children = payload.get("data", {}).get("children", [])

                for child in children:
                    data = child.get("data", {})
                    reddit_id = data.get("id", "")
                    if not reddit_id or reddit_id in seen_submission_ids:
                        continue
                    seen_submission_ids.add(reddit_id)

                    title_text = clean_text(data.get("title", "") or "")
                    self_text = clean_text(data.get("selftext", "") or "")
                    combined = f"{title_text}\n{self_text}".strip()
                    signals = classify_intent(combined)
                    title = extract_title_from_submission(subreddit_name, title_text, self_text)

                    if title and sum(signals.values()) > 0:
                        rows.append(
                            RawSignal(
                                title=title,
                                subreddit=subreddit_name,
                                source_type=infer_source_type(combined, subreddit_name),
                                origin_market=infer_origin_market(combined, subreddit_name),
                                continue_intent=signals["continue_intent"],
                                access_pain=signals["access_pain"],
                                platform_friction=signals["platform_friction"],
                                upvotes=int(data.get("score", 0) or 0),
                                quote=truncate_quote(combined),
                                reddit_id=reddit_id,
                                permalink=f"https://www.reddit.com{data.get('permalink', '')}",
                            )
                        )

                time.sleep(SLEEP_BETWEEN_SEARCHES_SECONDS)
                break

            except PermissionError as exc:
                print(f"    [ERROR] JSON fallback blocked for r/{subreddit_name}: {exc}")
                return rows
            except Exception as exc:
                print(f"    [ERROR] JSON r/{subreddit_name} keyword={keyword!r} attempt={attempt}: {exc}")
                if attempt == MAX_RETRIES:
                    traceback.print_exc()
                time.sleep(SLEEP_ON_ERROR_SECONDS * attempt)

    print(f"  [DONE] r/{subreddit_name}: {len(rows)} raw signal rows")
    return rows


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

        agg = aggregated[title]
        agg.continue_intent += row.continue_intent
        agg.access_pain += row.access_pain
        agg.platform_friction += row.platform_friction
        agg.total_mentions += 1
        agg.total_upvotes += max(0, row.upvotes)
        agg.subreddits_found.add(row.subreddit)
        agg.source_type_counts[row.source_type] += 1
        agg.origin_market_counts[row.origin_market] += 1

        if row.quote and len(agg.sample_quotes) < 5:
            quote = row.quote.replace("\n", " ").strip()
            if quote not in agg.sample_quotes:
                agg.sample_quotes.append(quote)

    return aggregated


def calculate_scores(aggregated: Dict[str, AggregateSignal]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for title, agg in aggregated.items():
        # Keep rows that have at least one meaningful signal.
        if agg.continue_intent == 0 and agg.access_pain == 0 and agg.platform_friction == 0:
            continue

        rows.append(
            {
                "title": title,
                "source_type": agg.source_type,
                "origin_market": agg.origin_market,
                "continue_intent": agg.continue_intent,
                "access_pain": agg.access_pain,
                "platform_friction": agg.platform_friction,
                "total_mentions": agg.total_mentions,
                "total_upvotes": agg.total_upvotes,
                "subreddits_found": "; ".join(sorted(agg.subreddits_found)),
                "sample_quotes": " || ".join(agg.sample_quotes[:5]),
                "opportunity_score": agg.opportunity_score,
                "friction_weighted_score": agg.friction_weighted_score,
            }
        )

    rows.sort(
        key=lambda r: (
            -int(r["friction_weighted_score"]),
            -int(r["opportunity_score"]),
            -int(r["total_mentions"]),
            str(r["title"]).lower(),
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

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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

    for i, subreddit_name in enumerate(SUBREDDITS, start=1):
        print(f"\n[{i}/{len(SUBREDDITS)}] Starting r/{subreddit_name}")
        try:
            rows = scrape_subreddit(subreddit_name, KEYWORD_GROUPS)
            all_raw_rows.extend(rows)
        except KeyboardInterrupt:
            print("\n[STOPPED] KeyboardInterrupt received. Exporting partial results...")
            break
        except Exception as exc:
            print(f"[ERROR] Failed subreddit r/{subreddit_name}: {exc}")
            traceback.print_exc()
            time.sleep(SLEEP_ON_ERROR_SECONDS)

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
