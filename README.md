# Game Census

A local Steam player-statistics application. The first usable version collects real current-player counts, retains its own observations in PostgreSQL, and provides game pages, recorded history, search within enrolled games, methodology, source state and a read API.

This is the first P0–P1 slice of the [product plan](docs/PRD-game-census.md). It collects only when you run a command. Historical coverage starts with your first observation; a displayed peak is a record within this instance. Broader catalog coverage, automatic scheduling, comparisons, reviews, prices, achievements and news remain future phases.

The [direct-source requirement](docs/PRD-game-census.md#1-purpose--vision) requires Valve-operated Steam origins for all external game data. Player counts come from the documented Steam Web API; optional game names come from Steam's own Store appdetails endpoint, which is undocumented. SteamDB supplies no data, history or fallback. Peaks and averages are local calculations over retained Steam observations. The production collector admits only its two fixed Steam HTTPS hosts and does not follow redirects.

## Run it

Prerequisites: Python 3.11 or newer for the standard-library wrapper, Docker Desktop with a running Linux engine, and internet access to the pinned image/package registries and the two Steam source hosts. Application Python and PostgreSQL run in pinned containers; no host PostgreSQL, Node.js or Steam API key is needed.

From this repository:

```powershell
python tools/dev.py doctor
python tools/dev.py quickstart --once --app-id 570
```

The second command prints what it will touch, builds the image, generates configuration and a local database secret, initializes storage, collects one game once and starts the website. The default URL is [localhost:8000](http://127.0.0.1:8000). It never enables a schedule. A partial source result exits nonzero and retains both its successes and failures for inspection.

The default profile requests a current-player count and an optional Store app name. It makes at most two upstream requests with the default settings. Subsequent reads of the website/API use stored data only.

## Daily commands

```powershell
python tools/dev.py app collect --once
python tools/dev.py app report --last-run
python tools/dev.py app apps
python tools/dev.py app history --app-id 570 --hours 24
python tools/dev.py app aggregate rebuild
python tools/dev.py status
python tools/dev.py stop
python tools/dev.py start
```

`stop` retains configuration and the database volume. `start` applies the shipped additive migrations and starts the existing instance without collecting. `aggregate rebuild` replays retained captures, inserts missing projections, and verifies projection contents and capture checksums. It stops on conflicting projections. It is not a database backup/restore command.

Run `python tools/dev.py build` followed by `python tools/dev.py start` after a source change. The first usable version has no delete, purge, volume reset or scheduled collector command.

## Configuration

The generated file is `data/instances/local/config/local.json`. This file contains a local database password and is excluded from Git and exports. Inspect safe effective values or the canonical schema:

```powershell
python tools/dev.py app config describe
python tools/dev.py app config describe --schema
```

`src/game_census/config.py` owns names, defaults and bounds. Edit the generated configuration to change operator values; no rebuild is required. Run `start` to apply web settings and enroll any new `tracking.app_ids`. That list determines future manual collection targets. Previously enrolled games and their retained history remain visible even when removed from the collection list.

For Docker, keep `web.bind` at `0.0.0.0` inside the container; Compose publishes it only on `127.0.0.1` on your computer. Choose `web.port` in configuration, or use `--port` on the first quickstart. An existing profile is preserved; rerunning quickstart with a different `--app-id` or `--port` does not rewrite it. The generated database URL describes the managed local database; changing its password does not automatically change an existing PostgreSQL role.

`--instance NAME` creates an isolated configuration directory, Compose project and database volume. For example, `python tools/dev.py --instance demo quickstart --once --app-id 570 --port 8001`. Choose a free port per simultaneously running instance. Configuration errors name the offending setting; unknown settings and unsafe values fail before collection.

## Read interfaces

| Interface | Purpose |
|---|---|
| `/` | Activity spotlight and search within all enrolled games |
| `/apps/570` | Stored count, source timestamp, recorded peaks, bounded chart and table |
| `/methodology` | Measurement limits, gaps, freshness and averaging definitions |
| `/status` | Observation state and collection outcome |
| `/api/v1/apps` | Enrolled cohort; optional `q` filter |
| `/api/v1/apps/570` and `/api/v1/apps/570/players` | Last valid count and separate last-attempt state |
| `/api/v1/apps/570/history?hours=24` | Half-open UTC window, observations, coverage and gaps |
| `/api/v1/status` | Safe stored-data status |
| `/health/live` and `/health/ready` | Process and database readiness |
| `/openapi.json` | Generated API contract |

Freshness describes the time the page was read. An open page announces changed stored data or freshness without replacing your chart position or keyboard focus. Successful zero, no observations, stale data and failed source attempts are separate states. Windows exceeding configured limits are rejected instead of silently truncated.

## Development and evidence

```powershell
python tools/dev.py test
uv sync --frozen
uv run --frozen playwright install chromium
uv run --frozen python tools/browser_check.py
python tools/sync_toolchain.py --check
python tools/repro_build.py
```

The first command runs unit, HTTP/template and PostgreSQL integration tests in the container. Integration fixtures create uniquely named scratch schemas, retain them for inspection, and make no Steam requests. Browser checks exercise a running local instance and save screenshots under `work/browser-check`. Install the uv version in `build/toolchain.lock.json` for host development commands. The lockfile pins transitive dependencies and hashes. `tools/sync_toolchain.py` regenerates the Python selector and pip requirements from their owners; `--check` detects drift. `tools/repro_build.py` compares two independently built wheel files, including schema, templates and assets. Docker provenance metadata is not the canonical artifact being compared.

See the [completion walkthrough](docs/build-tasks/initial-release/walkthrough.md) for commands and unedited output, acceptance boundaries, file purposes and known limitations. Full-size recovery, performance benchmarks, CI/release hardening and public hosting are future work. The local image currently includes the test toolchain and uses one database role; it is a development deployment.

## Project documents and license

The [PRD](docs/PRD-game-census.md) owns product requirements. The [PRS](docs/PRS-game-census.md) owns technical contracts. The [implementation plan](docs/build-tasks/initial-release/implementation_plan.md) owns delivery sequencing and file/command integration. The [checklist](docs/build-tasks/initial-release/task_checklist.md) owns completion status, and the [execution brief](docs/build-tasks/initial-release/agent_prompt.md) directs the next implementation session. Open decisions remain in the [backlog](docs/BACKLOG.md).

`python tools/export_plan.py --output-dir outputs/snapshot` creates rebuildable documentation and a source repository ZIP, excluding Git metadata, credentials, installed dependencies and database state. Use a new directory when the source changes. `tools/probe_sources.py` is the retained historical planning probe; production manual collection goes through `app collect --once` and its durable request ledger.

The canonical product name is **Game Census**; `game-census` is its filesystem/package slug. Steam's external `appid` maps to internal `app_id`. The application is independent of Valve and SteamDB. Code uses [Apache-2.0](LICENSE), the default proposed in the original plan. Steam data, trademarks and third-party dependencies have their own applicable rights. The source repository is [briandgibby/game-census](https://github.com/briandgibby/game-census). No hosted application deployment has been published.
