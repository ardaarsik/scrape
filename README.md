# Teaching page scraper

Downloads https://ilmargh.com/teaching/ and saves its content as JSON and Markdown.

## Setup on Windows 10

1. Install Python 3.8 or newer from https://www.python.org/downloads/windows/.
   In the installer, tick **"Add Python to PATH"**.
2. Open **Command Prompt** in this folder and install the dependencies:

   ```
   py -m pip install -r requirements.txt
   ```

## Run

Either double-click `run.bat`, or run:

```
py scrape_teaching.py
```

The results are written to the `output` folder:

| File        | Contents                                                        |
| ----------- | --------------------------------------------------------------- |
| `page.html` | The raw downloaded HTML                                         |
| `page.json` | Title, meta tags, navigation, sections (by heading), links, images |
| `page.md`   | A readable Markdown version of the page                         |

## Options

```
py scrape_teaching.py --url https://ilmargh.com/research/   # scrape another page
py scrape_teaching.py --out results                        # choose output folder
py scrape_teaching.py --from-file output\page.html         # re-parse a saved page offline
```

If the download fails (for example, the site blocks scripts), save the page from
your browser with **Ctrl+S → "Webpage, HTML only"** and use `--from-file`.
