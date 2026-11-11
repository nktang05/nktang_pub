# News desk

A health news page built from 25 sources. GitHub collects the news every hour and publishes the page at a web address. Nothing runs on your computer.

## What's in this folder

| File | What it does |
|---|---|
| `newsdesk.py` | Collects the stories and builds the page |
| `template.html` | The page's layout and features |
| `sources.json` | The news sources to read |
| `settings.json` | How long stories are kept and how gently sites are read |
| `requirements.txt` | Python packages the script needs |
| `.github/workflows/update-news.yml` | Tells GitHub to run the script every hour and publish the page |
| `data/` | The story archive, saved back to GitHub after each run |

## Set up on GitHub (one time)

1. **Create a repository.** On github.com, click **New repository**. Give it a name such as `news-desk` and click **Create repository**.
2. **Upload the files.** On the new repository's page, click **uploading an existing file**. Drag in everything from this folder, including the `.github` and `data` folders, then click **Commit changes**.
   - The `.github` folder may be hidden on your computer. If you use the zip file, unzip it first and drag the folder's contents.
3. **Allow the workflow to save the archive.** Go to **Settings > Actions > General**. Under **Workflow permissions**, choose **Read and write permissions** and click **Save**.
4. **Turn on the web page.** Go to **Settings > Pages**. Under **Build and deployment > Source**, choose **GitHub Actions**.
5. **Run the first update.** Go to the **Actions** tab, click **Update news** on the left, then **Run workflow**, then the green **Run workflow** button. It takes a few minutes.
6. **Open your page.** When the run shows a green check, your page is at `https://<your-username>.github.io/<repository-name>/`. The address also appears under **Settings > Pages**.

If this folder sits inside a larger site repository instead of being the repository root, the page will be served under the folder path, such as `https://<your-username>.github.io/<site-repo>/newsdesk-python/`.

### Keep your current stories (optional)

To carry over the stories from the PowerShell version, upload your old `archive.json` into the `data` folder on GitHub before the first run. Both versions use the same format.

## Using the page

- The page updates every hour by itself. When newer stories are ready, a **Show new stories** button appears.
- **Update now** opens GitHub's workflow page. Click **Run workflow**, then **Run workflow** again, and the page offers the new stories a few minutes later.
- **My topics, Mute words, Saved and New since your last visit** are stored in your browser. They follow you on the same computer and browser, not across devices.
- **Source status** at the bottom of the sidebar shows which sources worked on the last update.

## Changing things

Edit a file on GitHub (open it and click the pencil icon), then **Commit changes**. The page rebuilds automatically.

- **Add or remove a source:** edit `sources.json`. The options are listed at the top of `newsdesk.py`.
- **Update more or less often:** change the `cron` line in `.github/workflows/update-news.yml`. For example, `"17 */2 * * *"` runs every 2 hours. Also set `autoUpdateMinutes` in `settings.json` to match, so the page shows the right "Next update" time.
- **Keep stories longer:** change `keepDays` in `settings.json`.
- **A site keeps blocking:** raise `politeSeconds` in `settings.json` to read it more slowly.

## Running it on your own computer (optional)

With Python 3.10 or newer:

```
pip install -r requirements.txt
python newsdesk.py --open
```

This builds `docs/index.html` and opens it. The Update now button only works on the published page.

## Things to know

- **The page is public.** GitHub Pages sites can be opened by anyone with the address, even from a private repository on most plans. The page holds only public news, but check with TCC IT before sharing it more widely.
- **Some sites may block GitHub.** Sites sometimes refuse requests from cloud servers that they accepted from your computer. Source status will show any that fail.
- **Scheduled updates can pause.** GitHub may run hourly updates a few minutes late. In public repositories it can pause scheduled workflows after 60 days with no activity; if that happens, the Actions tab shows a button to turn them back on.
- **Logs:** each run's output is on the Actions tab. Click a run, then **update**, then **Collect the news**.
