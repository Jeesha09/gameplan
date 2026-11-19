# Migrating from Discourse

How to run the Discourse importer on a local bench. The importer reads a restored
Discourse Postgres database plus its uploads folder and writes Gameplan data into a site.

## What you need

- A Frappe bench (Linux or WSL) with this branch of Gameplan.
- The Discourse backup tarball (`dump.sql.gz` + `uploads/`). It has real user emails:
  never commit it or share rows from it.
- Postgres 15 or newer.
- About 30 GB free disk: ~19 GB for the restored DB, ~4 GB for uploads, 5+ GB for the site.

## 1. Code and Python packages

```bash
cd ~/frappe-bench/apps/gameplan
git checkout forum-features
cd ~/frappe-bench
./env/bin/pip install psycopg2-binary beautifulsoup4 psutil
```

## 2. Restore the dump into Postgres (~45 min)

```bash
sudo -u postgres createuser --superuser $USER   # skip if your role already exists
createdb discourse_db
tar -xOzf /path/to/frappe-forum-*.tar.gz dump.sql.gz | gunzip | psql -d discourse_db -q 2> restore.err
```

This streams straight out of the tarball, so no unzipped copy lands on disk. About 12
errors at the end are expected and harmless: `schema "public" already exists`, the
`halfvec` / `ai_*_embeddings` tables (Discourse AI, needs pgvector) and
`discourse_functions`.

## 3. Extract the uploads (~5 min)

```bash
mkdir -p ~/discourse-migration/logs
tar -xzf /path/to/frappe-forum-*.tar.gz -C ~/discourse-migration --no-same-owner uploads/
```

You should end up with `~/discourse-migration/uploads/default/...`.

## 4. Create a fresh site

```bash
bench new-site discuss.localhost --install-app gameplan
bench build --app gameplan
```

Use a site you can throw away. Don't set `allow_tests` or `enable_ui_tests` on it,
because Cypress wipes whatever site it points at.

## 5. Configure the importer

Add this to `sites/discuss.localhost/site_config.json`:

```json
"discourse_migration": {
  "postgres": {"dbname": "discourse_db"},
  "uploads_folder": "/home/<you>/discourse-migration/uploads",
  "log_folder": "/home/<you>/discourse-migration/logs",
  "lock_trust_levels": true
}
```

- `postgres` is passed to `psycopg2.connect`. `dbname` alone works if your Linux user has
  a Postgres role with the same name; otherwise add `user`, `password` and `host`.
- `uploads_folder` is the folder that contains `default/`, not `default/` itself.

## 6. Dry run

Writes nothing (everything is rolled back) and prints what it would have written.

```bash
bench --site discuss.localhost execute gameplan.migrate_from_discourse.execute --kwargs "{'dry_run': True}"
```

## 7. Real run (a few hours)

```bash
bench --site discuss.localhost execute gameplan.migrate_from_discourse.execute
```

Steps run in this order: `users`, `categories`, `topics`, `messages`, `trust_levels`,
`badges`, `links`, `backlinks`. Activity counts and the search index are rebuilt at the end.

The `badges` step brings over grants of the badges Gameplan ports (`prd/badges.md`), with no
notifications. Turn badges on afterwards in Admin settings > Badges: its first pass is silent and
grants Helper, which Discourse has no badge for, and anything else Discourse missed.

Options, passed through `--kwargs`:

| Option | Example | What it does |
|---|---|---|
| `steps` | `'users,categories'` | Run only some steps |
| `category_ids` | `[5]` | Import only these categories |
| `topic_ids` | `[101, 102]` | Import only these topics |
| `user_ids` | `[1, 2]` | Import only these users |
| `users_from_topics` | `True` | Import only users who posted in the selected topics |
| `batch_size` | `500` | Rows per batch |
| `dry_run` | `True` | Roll back instead of saving |

The same keys can also go in `discourse_migration` in `site_config.json`.

## 8. Check the result

The run prints done / skipped / failed counts per step. Failures are written to
`<log_folder>/<site>-run-<time>.jsonl`. Then open `http://discuss.localhost:<port>/g`
and look around.

Around 15 users currently fail on name clashes (accents and number suffixes) until a
fix to frappe's `append_number_if_name_exists` lands. Their posts go to the
"Deleted user" placeholder.

## Starting over

The importer opens Postgres read-only and only reads from the uploads folder, so the
source data can't be damaged. To retry, drop the site and go back to step 4:

```bash
bench drop-site discuss.localhost
```
