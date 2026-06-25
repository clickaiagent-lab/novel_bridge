# Novel Bridge Opportunity Engine Phase 1

This repository is the Phase 1 Reddit intake pipeline for Novel Bridge.

Novel Bridge helps international readers discover and legally read Asian web novels and related source works from Korea, China, and Japan. In Phase 1, the goal is to collect raw Reddit discussions first, preserve them in Google Sheets, and only then review and classify them with AI or manual analysis.

## Phase 1 architecture

Phase 1 now produces two CSV outputs:

1. `raw_discussions.csv`
2. `reddit_demand_data.csv`

`raw_discussions.csv` is the main output and the source of truth.

`reddit_demand_data.csv` is a backward-compatible aggregate view derived from the raw discussion rows when possible.

## Google Sheet structure

Spreadsheet:

- Name: `Novel Bridge Reddit Demand`
- Spreadsheet ID: `1HHejoNqiAbhiamU9aUn1smWx86okO09D5K7KdEy9200`

Phase 1 tabs:

- `Raw_Discussions`: append-only raw intake from each scraper run
- `AI_Review`: manual or ChatGPT-assisted review and classification
- `Title_Opportunities`: final opportunity decisions

Legacy aggregate tabs still supported:

- `Latest`: latest aggregate CSV snapshot
- `History`: append-only historical aggregate rows
- `Dashboard`
- `Settings`

## Modes

### Default mode: RSS/API-free

By default, the scraper runs without Reddit API credentials.

- Source: Reddit RSS search
- Credentials required: none
- Output: one raw row per RSS result

RSS mode captures:

- subreddit
- query
- post title
- summary/body
- URL
- matched keywords
- fetch mode

RSS mode does not reliably expose Reddit score or comment count, so those fields are written as `0`.

### Optional mode: Reddit API via PRAW

If these environment variables exist, the scraper switches to API mode automatically:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

PRAW mode captures:

- post rows
- top-level comment rows where available
- Reddit score data
- comment text

## Raw output columns

`raw_discussions.csv` contains:

- `run_date`
- `source`
- `subreddit`
- `query`
- `post_title`
- `post_body_or_summary`
- `comment_text`
- `url`
- `score`
- `num_comments`
- `created_at`
- `matched_keywords`
- `fetch_mode`
- `raw_id`
- `needs_ai_review`
- `notes`

## Aggregate output columns

`reddit_demand_data.csv` contains:

- `title`
- `source_type`
- `origin_market`
- `continue_intent`
- `access_pain`
- `platform_friction`
- `total_mentions`
- `total_upvotes`
- `subreddits_found`
- `sample_quotes`
- `opportunity_score`
- `friction_weighted_score`

## Repository structure

```text
.
|-- .github/
|   `-- workflows/
|       `-- reddit-scraper.yml
|-- README.md
|-- reddit_scraper.py
|-- upload_to_google_sheets.py
`-- requirements.txt
```

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run locally

### RSS mode

No credentials are required:

```bash
python reddit_scraper.py
python upload_to_google_sheets.py
```

### PRAW mode

Set these environment variables first.

PowerShell:

```powershell
$env:REDDIT_CLIENT_ID="your_client_id"
$env:REDDIT_CLIENT_SECRET="your_client_secret"
$env:REDDIT_USER_AGENT="NovelBridgeResearch/0.1 by your_reddit_username"
python reddit_scraper.py
```

Command Prompt:

```cmd
set REDDIT_CLIENT_ID=your_client_id
set REDDIT_CLIENT_SECRET=your_client_secret
set REDDIT_USER_AGENT=NovelBridgeResearch/0.1 by your_reddit_username
python reddit_scraper.py
```

## GitHub secrets

GitHub Actions supports both Reddit credentials and Google Sheets upload.

Optional Reddit API secrets:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

Required Google Sheets secrets:

- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

No secrets are hardcoded in the repository.

## GitHub Actions automation

The workflow file is:

`/.github/workflows/reddit-scraper.yml`

It runs in two ways:

- Automatically every day at `02:00 UTC`
- Manually from the `Actions` tab with `workflow_dispatch`

Each workflow run:

1. Checks out the repository
2. Sets up Python 3.13
3. Installs dependencies
4. Runs `python reddit_scraper.py`
5. Runs `python upload_to_google_sheets.py`
6. Uploads `raw_discussions.csv` as a GitHub artifact
7. Uploads `reddit_demand_data.csv` as a GitHub artifact when present

## How the Google Sheets upload works

`upload_to_google_sheets.py` does the following:

- appends `raw_discussions.csv` rows into `Raw_Discussions`
- refreshes `Latest` with `reddit_demand_data.csv` when that file exists
- appends aggregate rows into `History` when that file exists

The raw discussion upload is append-only so Phase 1 history is preserved.

## How to manually run the workflow

1. Open the repository on GitHub
2. Click `Actions`
3. Select `Novel Bridge Reddit Scraper`
4. Click `Run workflow`
5. Open the completed run
6. Check the workflow logs for:
   - total raw discussions collected
   - rows appended to `Raw_Discussions`
   - whether aggregate CSV was produced
7. Download the artifacts:
   - `raw-discussions-data`
   - `reddit-demand-data` when available

## RSS mode limitations

- RSS mode does not fetch Reddit comments
- RSS mode does not provide reliable upvote counts
- RSS search quality can vary by subreddit and keyword
- RSS mode is best treated as a broad raw intake layer

## API mode benefits

- PRAW mode includes top-level comments
- PRAW mode captures Reddit scores
- PRAW mode provides richer raw intake for AI review

## Notes

- `Raw_Discussions` is the source of truth for Phase 1.
- `AI_Review` is intended for manual or ChatGPT-assisted classification.
- `Title_Opportunities` is intended for final opportunity decisions.
- The aggregate CSV remains useful, but it is now downstream of raw intake rather than the primary dataset.
