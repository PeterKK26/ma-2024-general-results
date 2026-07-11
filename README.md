# MA 2024 General Election — Precinct-Level Results

Precinct-by-precinct results for every 2024 General Election race in
Massachusetts, pulled from [electionstats.state.ma.us](https://electionstats.state.ma.us/)
(the Secretary of the Commonwealth's official results archive).

## What's here

- `scripts/scrape.py` — the scraper. Walks every office (President down
  through Register of Probate and County Commissioner races), finds every
  district, and downloads the precinct-level CSV for each.
- `data/` — output goes here, organized as `data/<Office>/<District>_<id>.csv`,
  plus a `data/manifest.csv` index of every race and whether it downloaded
  successfully.

## Running it

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python scripts/scrape.py
```

This will take a while — there's a deliberate ~1 second delay between
requests so as not to hammer the state's server, and there are likely
several hundred races. Expect it to run for 15–45+ minutes depending on
exactly how many races 2024 turns out to have.

When it's done, check `data/manifest.csv` — the `status` column will say
`ok` or show an error for any race that failed, so you can spot gaps or
re-run just those.

## A heads-up on the scraper

I couldn't test this script against the live site directly (my sandbox
can't reach `electionstats.state.ma.us`), so it's built defensively:
it tries to walk pagination on the "all offices" search page, and as a
backup also queries the site once per known office category so a single
odd page-size limit can't quietly drop races. If a run comes back with
obviously too few results, the most likely culprit is the HTML parsing
in `extract_races()` not matching the page as actually served — ping me
with a saved copy of one search results page and I'll fix the selectors.

## Pushing to your own GitHub

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```
(Create the empty repo on GitHub first, without a README, so there's no
merge conflict.)
