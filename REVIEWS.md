# Review of Uncommitted Changes

Reviewed 2026-10-30 against `14550e1` (`main`). Scope: the three modified files and all readable untracked files. No code under `backend/` has changed; this is a documentation and tooling change set.

**Verdict:** the planning docs are strong, and most of their claims about the code hold up. Fix H1 before committing the plugin. Fix H2 to H4 before anyone builds from these docs.

| Severity | Count |
|---|---|
| High | 4 |
| Medium | 6 |
| Low | 5 |

## High

### H1. The review hook is not read-only and can reach secrets
**File:** `independent-reviewer/hooks/hooks.json:8`

The hook runs `claude -p` with `"Bash(git *)" Read Grep Glob Write` pre-approved. `Bash(git *)` covers `git push`, `git commit`, `git reset --hard` and `git clean`. `Read` can open `.env`, and the output file `REVIEWS.md` is not gitignored, so anything quoted from `.env` could be committed.

The repo's own `change-reviewer` agent forbids editing, committing and reading `.env`, but the hook does not use that agent, so none of those rules apply.

**Fix:** have the hook run `change-reviewer`, or narrow the tools to `Bash(git diff *)` and `Bash(git status *)`, deny reads of `.env`, and add `REVIEWS.md` to `.gitignore`.

### H2. The proposed Massive fallback can leave a Basic key with no prices for an hour
**File:** `planning/MARKET_INTERFACE.md:172-193`, section "Massive Implementation"

`_poll_snapshots` sets `self._interval = 3600` before `_poll_closes` runs. If `_poll_closes` then fails, `_poll_once` logs the error and `_poll_loop` (`massive_client.py:86`) sleeps the full hour. `latest_closes` re-raises anything that is not `NOT_AUTHORIZED`, so a `429`, a `5xx` or a network error all end this way.

This is likely in development: each start uses 1 snapshot call plus up to 4 daily calls against a limit of 5 requests/min, so two quick restarts can hit a `429`. The `.env` key is Basic, so this is the path this project would actually take. Found by reading the code; not run.

**Fix:** switch to the hourly interval only after a poll has written prices, and keep retrying at 15 seconds until then.

### H3. Buying an untracked ticker is undefined and differs by data source
**Files:** `planning/PLAN.md` sections 6 and 8; `planning/MARKET_INTERFACE.md`, sections "Tracked Tickers" and "Reading Prices"

Section 6 says buying a ticker starts tracking it. Section 8 rejects a trade with `400` if the ticker has no cached price. Neither document gives the order:

- **Check the price first:** a ticker that is not tracked never gets a price, so it can never be bought.
- **Call `add_ticker` first:** the simulator prices it at once, but Massive paid plans only price it on the next poll, so the buy fails and the ticker stays tracked with no watchlist entry or position. Any buy rejected for insufficient cash leaks tracking the same way.

This also affects AI chat, which runs trades through the same path.

**Fix:** state the order in `PLAN.md`. Suggested: call `add_ticker`, then read the price. On any rejection, call `remove_ticker` unless the ticker is on the watchlist or held. Add a test for this on both sources.

### H4. New status text and the contract docs contradict the findings
**Files:** `README.md` section "Status"; `planning/PLAN.md` section 6; `planning/MARKET_DATA_SUMMARY.md:3`

`MARKET_INTERFACE.md:5` says the Massive path writes no prices on any plan. The code confirms it: `massive_client.py:103` reads `last_trade.timestamp`, which the docs say does not exist, and line 126 passes the enum. Yet:

- The `README.md` rewrite in this change set says the subsystem, including the "Massive client", is complete.
- `PLAN.md` section 6 still has the three statements that `MARKET_INTERFACE.md:318-326` lists as wrong, including "works on all tiers" and "poll every 15 seconds". `PLAN.md` is the shared contract, and it is also the file that agents load automatically.
- `MARKET_DATA_SUMMARY.md` and the root `CLAUDE.md` still say complete.

**Fix:** apply the three corrections to `PLAN.md`, and change `README.md` and `MARKET_DATA_SUMMARY.md` to say the simulator works and the Massive client is broken pending the listed fixes.

## Medium

### M1. The README test commands will not install pytest
**File:** `README.md` section "Backend Development"

The README says `uv sync --dev`, but `dev` is declared under `[project.optional-dependencies]`, and `pyproject.toml` has no `[dependency-groups]`. `--dev` only selects the dependency group, so `pytest` is not installed and `uv run pytest` should fail. `backend/CLAUDE.md` has the right command. `backend/README.md:25,48` has the same mistake. Not confirmed by running it (see "Not Verified").

**Fix:** use `uv sync --extra dev` and `uv run --extra dev pytest` in both READMEs.

### M2. The hook runs a full review after every turn
**File:** `independent-reviewer/hooks/hooks.json`

There is no condition on the Stop hook, so even a one-line answer with no file changes starts a separate Claude session. It costs tokens each time, delays the end of each turn, and overwrites `REVIEWS.md`, losing earlier reviews.

**Fix:** skip when nothing changed since the last review, or make this a command run on request.

### M3. The hook feeds its Stop payload into the review prompt
**File:** `independent-reviewer/hooks/hooks.json:8`

Claude Code passes the hook's JSON on stdin, and `claude -p` reads it as part of the prompt. This was observed directly: this review's prompt ended with the payload, including the session ID, transcript path and the previous assistant message. The reviewer therefore starts from the main session's conclusions, which undermines an independent review.

**Fix:** add `< /dev/null` to the `claude` command.

### M4. The plugin may not resolve on a fresh clone
**File:** `.claude/settings.json`

`independent-reviewer@finally` is enabled, but the file does not register the `finally` marketplace (no `extraKnownMarketplaces`). It likely depends on a local `/plugin marketplace add`. Not tested on a clean clone.

**Fix:** add the marketplace to `extraKnownMarketplaces`, or leave the plugin out of shared settings.

### M5. The seed price decision invalidates the simulator's own tables
**File:** `planning/MARKET_SIMULATOR.md:82-111`

The doc decides to move seeds to current closes, but the "Avg move per tick" and "Flat ticks" figures were measured on the old seeds. NFLX is the worst case: at $62.05 instead of $600 its typical tick is about $0.006, so by my estimate roughly half its ticks would be flat, against the 6% shown. NVDA also goes quieter, falling from $800 to $213.66. This works against the doc's "look alive" goal.

**Fix:** re-measure after the seed change, and consider raising the volatility for low-priced tickers.

### M6. `.gitignore` does not cover the database
**File:** `.gitignore:61-62`

`PLAN.md` section 4 says `finally.db` is gitignored, but only `db.sqlite3` is. `git check-ignore db/finally.db` matches nothing. Running the backend locally would leave the database committable. The `db/` directory and its `.gitkeep` do not exist yet either.

**Fix:** add `db/*.db`, and create `db/.gitkeep`.

## Low

- **L1. `planning/MARKET_SIMULATOR.md:65`:** "TSLA sits in the tech group" is wrong. `CORRELATION_GROUPS["tech"]` in `seed_prices.py:39` does not include TSLA. The same mistake is in the comment at `simulator.py:188`.
- **L2. `planning/MARKET_INTERFACE.md:107`:** `session_change_percent` being "Always 0" on Basic only holds within one session. A process running across two sessions keeps its first close as the open, so the value becomes non-zero.
- **L3. `planning/MARKET_INTERFACE.md:220`:** the stated worst case of 1 + 4 calls is not the maximum. If the previous day's data is not ready yet, which the docs say has no published time, the same holiday week needs 1 + 5 calls, over the 5/min limit.
- **L4. `planning/MARKET_INTERFACE.md` "Required Changes":** the list omits three follow-ups: the `PriceUpdate` fields in `backend/CLAUDE.md`, the free-tier text in the `massive_client.py:23-25` docstring, and the status in `MARKET_DATA_SUMMARY.md`.
- **L5. Tidying:** `planning/PLAN.md` gains a stray blank line at the end; `independent-reviewer/.claude-plugin/plugin.json` has no trailing newline; the plugin version is declared in both `plugin.json` and `marketplace.json`, so they can drift apart.

## Checked With No Issues

- **Secrets:** none found in the diff, `.env.example` or the new docs. `.env` is ignored and was not read.
- **Doc claims confirmed against the code:** 73 tests; `massive` locked at 2.2.0; `SnapshotMarketType.STOCKS` passed at `massive_client.py:126`; `remove()` does not bump `version`; `python-dotenv` is not a dependency; `SimulatorDataSource` does not pass `dt`; seed prices are written on start and on add; `retry: 1000` is sent; tests read `SEED_PRICES` rather than literal seeds.
- **Arithmetic:** `dt`, the 0.64 bp tick, 47 shocks per 6.5 hours, the 25% and 1.4% swings, the 3% downward pull, 2,880 snapshots/day, and the worked examples in `PLAN.md` sections 6 and 8 all compute correctly. The `1793304000000` sample timestamp is 2026-10-29 20:00 UTC, as stated.
- **`PLAN.md` edits:** apart from H3 and H4, the new sections are consistent with each other. This covers the schema changes, response shapes, LLM failure handling and mock rules.
- **`README.md`:** dropping the `docker run` steps is correct, since no Dockerfile exists yet.
- **`.claude/agents/change-reviewer.md`, `.claude/commands/doc-review.md`, `.env.example`:** no issues. `.env.example` matches `PLAN.md` section 5.

## Not Verified

Network access to PyPI, OpenRouter and nodejs.org was denied in this environment, so these checks could not be done:

- **Tests were not run**, so M1 comes from reading `pyproject.toml` and `uv.lock`. The 72-of-74 result in `MARKET_INTERFACE.md` could not be reproduced.
- **`massive` client claims**, such as the URL built from the enum, exception behaviour and retries, could not be checked because the package could not be installed. Plan prices and limits were not checked either.
- **`LLM_MODEL` default:** whether `openrouter/nvidia/nemotron-3.5-super-vl:free` still exists and supports structured outputs is unconfirmed.
- **Node 24 as "current LTS":** Node's LTS changes hands around October, so confirm this in `PLAN.md` section 11 before writing the Dockerfile.

Not reviewed: 18 untracked paths in `git status`, such as `.bashrc`, `.mcp.json`, `.gitmodules`, `.vscode`, `.idea` and `.claude/hooks`. The ones sampled are empty character devices, which are sandbox placeholders rather than project files. Do not stage them; avoid `git add -A` while they are present.
