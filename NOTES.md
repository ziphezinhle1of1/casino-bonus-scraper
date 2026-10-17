# My Approach

## Approach

My approach was to keep the scraper simple and avoid trying to hard-code every possible bonus format. The parser’s main job is to find each casino on the page and separate its content into individual blocks. I then use an AI model to read the terms for each casino and return the information I need in a structured JSON format.

I also didn't want to blindly trust whatever the AI returned. After the model extracts a value, the scraper checks it against the original source text. If it cannot find enough evidence for a value, it doesn't try to guess. Instead, it leaves the value empty or marks the offer as needing review. I saw this happen with Coral and Ladbrokes, where the offer mentioned spending £10 but never actually stated a minimum deposit. Rather than assuming the minimum deposit was £10, the scraper correctly displayed it as "not stated."

## What's missing

At the moment, the scraper mainly relies on one source. Other gambling.com country pages can work, but completely different websites would need their own small parser to identify where each casino listing starts and ends.

Anything marked as "needs review" is currently shown with a warning instead of being automatically corrected. I did this deliberately because I would rather flag uncertain information than silently publish a value that may be wrong.

The current version also doesn't keep historical data, so a new run replaces the previous results. In a production version, I would store daily snapshots so changes to offers could be tracked over time.

I have also included a daily GitHub Actions workflow, but it is not currently enabled because the API key still needs to be added securely as a repository secret.

## Production plan

If I had to run this for around 200 casinos every day, I would keep the infrastructure fairly small because the workload doesn't justify something complicated like Kubernetes.

I would run the scraper on a small Linux VPS in Europe using Docker. A server with around 2 vCPUs and 4 GB of RAM should comfortably handle this workload. The application would be packaged as a Docker image through GitHub Actions, and the server would pull and run that image. This would make deployments repeatable without needing to manually set up the application every time.

For the database, I would use PostgreSQL and keep it on the same server initially. Instead of only storing the latest result, I would keep a daily snapshot of each casino's offer. I would store the original terms, the extracted values, the model used, the validation status and a hash of the terms. This would allow me to see when an offer changed and would also make it easier to notice if the scraper suddenly started producing incorrect results.

I would back up the database every night and store encrypted copies somewhere separate from the server, such as Cloudflare R2 or Backblaze B2. I would keep roughly 30 days of backups and test restoring one of them each month. I think testing the restore is important because having backups doesn't help much if I only discover they don't work after something has gone wrong.

The public website itself doesn't need to run directly from the scraper server. After a successful scrape, I would generate the static page and deploy it to Cloudflare Pages. That means the website can stay online even if the scraper server has a problem. Cloudflare can also handle the DNS and HTTPS certificate.

I would schedule the scraper to run once every morning using a system timer or cron. I would also add monitoring so I know when something goes wrong. For example, Healthchecks.io could alert me if the daily job doesn't finish, while Sentry could capture application errors.

I would monitor the data as well as the application. A scraper can technically finish successfully while still collecting bad information. If the number of casinos suddenly drops compared with the previous day, or too many offers are marked as needing review, I would want an alert.

For scraping, I would keep the requests polite by respecting robots.txt, limiting requests per domain and using a clear User-Agent. I wouldn't use CAPTCHA solving or proxy rotation to force access to a website that is blocking the scraper.

One important cost saving would be checking whether the terms have actually changed before sending them to the AI model. I would compare the current terms hash with the previous day's hash. If nothing changed, there is no reason to pay for another AI request.

Overall, I estimate this could run for roughly €10–15 per month. The VPS would be the main fixed cost, with a small amount for backups, the domain and AI usage. Services such as Cloudflare Pages, DNS, Healthchecks.io, Sentry and GitHub Actions can initially stay within their free tiers.

## Use of AI

I used Claude to help me write parts of the scraper, tests and webpage, but I still reviewed and tested the code myself rather than assuming generated code would work correctly.

One issue I found was that all the tests passed in the AI's Linux environment, but two failed when I ran them on my Windows laptop. Windows was reading the £ symbol incorrectly because the files weren't explicitly being opened as UTF-8. I fixed the file reads and writes to always use UTF-8.

I also ran into problems with model names suggested during development. Some of the models had already been retired or were no longer available by the time I tested them. That taught me not to assume that an AI's knowledge of current APIs or model versions is up to date. I changed the project so the model is configurable through `LLM_MODEL`, which also makes it easier to switch models later.

Another problem appeared when the AI provider itself became unreliable. Gemini returned high-demand errors and timeouts, while the first implementation gave up too quickly. I added retries with increasing wait times and made it possible to switch providers without rewriting the scraper.

Testing also helped me find a case where the README said the `--url` option supported the Irish page, but the scraper returned no casinos because that page structured its links differently. I changed the parser so it didn't depend on the UK page's naming convention and added a test for the problem.

The main lesson for me was that AI was useful for speeding up development, but its output still needed to be tested against the real environment and real data.

## Time spent

I spent approximately 3–4 hours completing the assessment. This included reviewing and testing the code, setting up the required API keys, debugging the issues I found, testing the scraper with real data, publishing the live page and preparing the submission.
