# Novel Bridge Reddit Demand Scraper

This project is a Reddit research pipeline for Novel Bridge.

Novel Bridge helps international readers discover and legally read Asian web novels and related source works from Korea, China, and Japan. This scraper focuses on a specific business question: which titles show strong international continuation demand while also creating friction around official access, raw source access, or available translation.

The script looks for three signal types across selected Reddit communities:

- Continuation intent, such as readers asking where to continue after an anime, manga, or manhwa adaptation.
- Access pain, such as missing official releases, missing translations, or difficulty finding raws.
- Platform friction, such as demand being trapped behind domestic-origin platforms like Naver Series, KakaoPage, Ridibooks, Syosetu, Kakuyomu, JJWXC, Qidian, or BookWalker.

The output is a ranked CSV file named `reddit_demand_data.csv`.

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

## Reddit API credentials

You need Reddit API credentials before running the scraper reliably in GitHub Actions.

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).
2. Click `create app` or `create another app`.
3. Choose the app type `script`.
4. Fill in a name such as `NovelBridgeResearch`.
5. Set the redirect URI to `http://localhost:8080`.
6. Save the app.
7. Copy these values:
   - `client_id`: the short string shown under the app name
   - `client_secret`: the secret value
   - a user agent string such as `NovelBridgeResearch/0.1 by your_reddit_username`

## GitHub Secrets to add

After the repository is on GitHub, add these repository secrets:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USER_AGENT`

Path in GitHub:

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

## Run locally

Create a Python environment if you want one, then install dependencies:

```bash
pip install -r requirements.txt
```

Set the environment variables before running the scraper.

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

Then restart the terminal and run:

```bash
python reddit_scraper.py
```

If the run succeeds, it writes `reddit_demand_data.csv` in the project folder.

## GitHub Actions automation

The workflow file is:

`/.github/workflows/reddit-scraper.yml`

It runs in two ways:

- On a schedule every day at `02:00 UTC`
- Manually through the GitHub Actions tab with `workflow_dispatch`

Each workflow run:

1. Checks out the repository
2. Sets up Python 3.13
3. Installs dependencies from `requirements.txt`
4. Verifies that the required Reddit secrets exist
5. Runs `python reddit_scraper.py`
6. Uploads `reddit_demand_data.csv` as a workflow artifact named `reddit-demand-data`

## Download the CSV artifact

After a workflow run finishes:

1. Open the repository on GitHub
2. Go to `Actions`
3. Open the latest `Novel Bridge Reddit Scraper` run
4. Scroll to `Artifacts`
5. Download `reddit-demand-data`

The downloaded ZIP contains `reddit_demand_data.csv`.

## Notes

- The scraper uses lightweight heuristics for title extraction.
- Reddit search is useful for research, but not exhaustive.
- The pipeline is intended for market research rather than production warehousing.
- If credentials are missing during local runs, the script falls back to Reddit's public JSON search, which may have more limited coverage or be blocked by Reddit.
