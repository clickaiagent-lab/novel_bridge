# Novel Bridge Reddit Demand Scraper

This project is a Reddit research pipeline for Novel Bridge.

Novel Bridge helps international readers discover and legally read Asian web novels and related source works from Korea, China, and Japan. This scraper focuses on titles that show strong continuation demand together with high access friction.

The script writes a ranked CSV file named `reddit_demand_data.csv`.

## Modes

### Default mode: RSS/API-free

By default, the scraper runs without Reddit API credentials.

- Source: Reddit RSS search
- Credentials required: none
- Best for: immediate MVP runs in GitHub Actions and local smoke tests

The scraper uses RSS URLs in this shape:

`https://www.reddit.com/r/{subreddit}/search.rss?q={query}&restrict_sr=on&sort=relevance&t=year`

### Optional mode: Reddit API via PRAW

If these environment variables exist, the scraper switches to API mode automatically:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

In API mode, the scraper uses PRAW as the primary source and can inspect top-level comments in addition to post content.

## Signals tracked

The scraper looks for three signal families:

- Continuation intent
- Access pain
- Platform friction

It then ranks titles using:

- `opportunity_score = continue_intent * access_pain`
- `friction_weighted_score = continue_intent * (access_pain + platform_friction)`

Results are sorted by:

1. `friction_weighted_score` descending
2. `opportunity_score` descending
3. `total_mentions` descending

## Output columns

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

For permanent variables on Windows:

```powershell
setx REDDIT_CLIENT_ID "your_client_id"
setx REDDIT_CLIENT_SECRET "your_client_secret"
setx REDDIT_USER_AGENT "NovelBridgeResearch/0.1 by your_reddit_username"
```

Then restart the terminal before running the scraper again.

## Add GitHub secrets later

GitHub Secrets are optional. The workflow runs in RSS mode when they are missing.

If you want API mode later, add these repository secrets:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

Path in GitHub:

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

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
5. Uploads `reddit_demand_data.csv` as the `reddit-demand-data` artifact

## How to manually run the workflow

1. Open the repository on GitHub
2. Click `Actions`
3. Select `Novel Bridge Reddit Scraper`
4. Click `Run workflow`
5. Open the completed run
6. Download the `reddit-demand-data` artifact

## RSS mode limitations

- RSS mode does not fetch Reddit comments
- RSS mode does not provide reliable upvote counts, so `total_upvotes` stays `0`
- RSS results can be less complete than API results
- RSS search quality can vary by subreddit and keyword

## API mode benefits

- PRAW mode can inspect post bodies and top-level comments
- PRAW mode can capture Reddit scores
- PRAW mode is more flexible for future enrichment and filtering

## Reddit API credentials

To prepare for API mode:

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Click `create app` or `create another app`
3. Choose the app type `script`
4. Use a redirect URI such as `http://localhost:8080`
5. Save the app
6. Copy:
   - `client_id`
   - `client_secret`
   - a user agent string such as `NovelBridgeResearch/0.1 by your_reddit_username`

## Notes

- The scraper uses lightweight heuristics for title extraction.
- The pipeline is intended for market research rather than production warehousing.
- The script always writes `reddit_demand_data.csv`, even when no qualifying rows are found.
