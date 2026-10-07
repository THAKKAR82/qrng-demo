# Deploying the phone site

The phone site is the only part of this project on the public internet (SPEC.md, Section 9.7). It is the static folder `ui/dist-web/`, built by `rebuild` (or `npm run build:web`), and hosted on **Cloudflare Pages** at the project's default address, `https://<project>.pages.dev/`.

You run every step here yourself. Claude never deploys, logs in to Cloudflare, or runs `check-site` against the live site.

**What goes up:** `index.html`, the JavaScript and CSS bundle, the fonts, `favicon.svg`, `404.html`, and `_headers` (the security headers, which Pages reads and doesn't serve). The bundle holds the two phone games and the run's data from `demo.json` (bits, statistics, and the run's metadata, including the backend name and job ID, which are public facts about the run and never shown on screen).

**What never goes up:** the presenter deck, slides, notes, live-run code, source maps, the notebook, the repo, and anything from `~/.qiskit`. The site has no server code, cookies, browser storage, forms, analytics, or third-party requests.

The commands below use `npx wrangler@4.148.0`, Cloudflare's command-line tool, fetched by `npx` on first use and not added to the project. Run them from the repo root.

## 1. The account (once)

1. Create a free Cloudflare account, or use the one you have. If you deploy from the enterprise Mac, check first that company policy allows a personal cloud account there; otherwise deploy from the home Mac.
2. **Turn on two-factor authentication:** dashboard → your profile (top right) → **Authentication** → **Two-Factor Authentication**. Use an authenticator app or a security key, and save the backup codes somewhere that isn't this laptop.
3. **No payment method is needed.** Static sites on Pages' Free plan have no charge for requests or bandwidth, and this site has no Functions (the only part of Pages that counts invocations). Don't add a card. If any screen in these steps asks for payment details, stop: something other than a plain Pages project is being set up.
4. Don't turn on **Web Analytics** for the project; the app collects nothing, and it should stay that way.
5. Log in from the terminal, and turn off wrangler's own usage telemetry:

   ```sh
   npx wrangler@4.148.0 login                 # opens the browser to authorise
   npx wrangler@4.148.0 telemetry disable
   ```

## 2. Choose the project name, before building

The QR code is baked into the builds, so the address must be known before you build.

1. Pick a neutral name: lowercase letters, digits, and hyphens, such as `qrng-talk-oct26`. It is public and appears under the QR code, so don't use a personal or company name.
2. Create the project. This is a **direct upload** project: Cloudflare never gets access to the GitHub repo. Don't click "Connect to Git" in the dashboard, now or later.

   ```sh
   npx wrangler@4.148.0 pages project create qrng-talk-oct26 --production-branch=main
   ```

3. Note the address it prints. It is `https://qrng-talk-oct26.pages.dev/` unless the name was taken, in which case Pages adds a few random characters to the subdomain. Use exactly what it prints.
4. Put the name and the address, with the trailing slash, into `site.json`:

   ```json
   {
     "host": "cloudflare-pages",
     "project": "qrng-talk-oct26",
     "url": "https://qrng-talk-oct26.pages.dev/"
   }
   ```

   Keep the `_comment` line if you like. Commit `site.json` and push, so both Macs build the same QR code.

## 3. Build

```sh
source .venv/bin/activate
python -m pipeline.tasks rebuild
```

It exports `demo.json` from the latest committed run, re-runs the notebook, and builds the presenter app (`ui/dist/`), the single-file fallback (`demo/index.html`), and the phone site (`ui/dist-web/`), all with `site.json`'s address as the QR code. It prints the address and the short text shown under the code, and it checks that every build carries it and that the phone site has no source maps. Commit `ui/src/data/demo.json` and `demo/index.html` if they changed beyond the export time.

## 4. Deploy

```sh
npx wrangler@4.148.0 pages deploy ui/dist-web \
  --project-name=qrng-talk-oct26 --branch=main --commit-message="phone site"
```

`--branch=main` makes it the production deployment at the project's address. `--commit-message` stops wrangler sending your latest git commit message as deployment metadata.

## 5. Check the live site

```sh
python -m pipeline.tasks check-site
```

It fetches only the address in `site.json`, and checks:

- HTTPS answers `200` with the page itself, and plain HTTP redirects to HTTPS (if it doesn't, it prints a note rather than failing: every `.dev` address is on browsers' HSTS preload list, so browsers never use plain HTTP);
- every header in `ui/web/public/_headers` arrives exactly as written (the Content-Security-Policy, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Strict-Transport-Security`, and the rest), and Pages' default `Access-Control-Allow-Origin` is gone;
- the deployed `index.html` is byte-for-byte your local `ui/dist-web/index.html`, so what's live is what you built and verified;
- nothing it loads holds presenter content, notes, slide titles, or live-run code, and no source map is served;
- paths outside the build (such as `/demo/index.html`) are not served: the host answers `404` (or a redirect), never the app;
- the QR codes in `ui/dist/` and `demo/index.html` point to exactly this address.

Then scan the QR code on slide 1 with your own phone.

## 6. After a new run

Collect (README, "Real collection"), then repeat steps 3 to 5: `rebuild`, deploy, `check-site`. The address doesn't change.

## Logs and privacy

The app itself collects nothing: no cookies, no storage, no analytics, and no request after the page's own files have loaded. The host still sees every request. Cloudflare processes standard request data (IP addresses, user agents, times, and the paths requested) to serve the site and protect it, and keeps it under its own policies; you can't turn that off. Don't promise the audience more than "the app collects nothing". The site is marked `noindex`, so search engines shouldn't list it.

## Taking the site down after the talk

Do this the same day.

1. **Replace the games with an "ended" page first.** This keeps the project, and so the name, yours. If you delete the project straight away, anyone can create a new project with the same name, and every QR code already out there (in photos of the slides, or in old copies of `demo/index.html`) would point to whatever they put there.

   ```sh
   npx wrangler@4.148.0 pages deploy deploy/ended \
     --project-name=qrng-talk-oct26 --branch=main --commit-message="ended"
   ```

   Open the address to confirm it now says "This demo has ended".

2. **Delete the old deployments.** Every deployment also has its own permanent address (`https://<id>.qrng-talk-oct26.pages.dev/`) that keeps serving the games. List them and delete every one except the "ended" deployment:

   ```sh
   npx wrangler@4.148.0 pages deployment list --project-name=qrng-talk-oct26
   npx wrangler@4.148.0 pages deployment delete <deployment-id> --project-name=qrng-talk-oct26
   ```

3. **Later, if you want the project gone entirely** (once nobody is likely to scan an old code), delete it. This removes every deployment and frees the name:

   ```sh
   npx wrangler@4.148.0 pages project delete qrng-talk-oct26
   ```

4. Put `site.json` back to the placeholder (`"project": "CHOOSE-A-NAME"`, `"url": "https://CHOOSE-A-NAME.pages.dev/"`), run `rebuild` so `demo/index.html` carries no QR code to a site you no longer control, and commit.
