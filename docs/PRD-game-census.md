# Game Census — Product Requirements Document

> Status: DRAFT · Owner: project maintainer, not yet assigned by name · Created: 2026-09-04
>
> This document defines the complete proposed product. No section has owner ratification. The first usable P0–P1 local slice is implemented and locally verified; the checklist owns implementation status. This does not imply completion of the full product or approval for public release.

Canonical technical specification: [PRS-game-census.md](PRS-game-census.md). Delivery work: [implementation plan](build-tasks/initial-release/implementation_plan.md) and [checklist](build-tasks/initial-release/task_checklist.md). Deferred decisions: [BACKLOG.md](BACKLOG.md).

## 1. Purpose & vision

Game Census will provide an open source, self-hostable view of player activity and other public Steam game statistics. A visitor should be able to find a game, inspect its last observed player count, and understand its recorded activity over time.

The operating problem is trust and access. A displayed count can be stale. A historical peak can cover only part of a game's life. A ranking can omit untracked games. Game Census will expose those limits with the data so visitors can assess the result.

The intended product offers SteamDB-like statistical depth through its own collection from Steam. Direct-source independence is a core product requirement: all external game statistics and metadata must originate from Valve-operated Steam sources. SteamDB and other third-party aggregators must never supply observations, historical imports, enrichment, reconciliation values, or fallback data. This requirement applies regardless of a third party's ownership or scraping policy. A failed Steam source remains an explicit failure. Locally calculated metrics must remain traceable to retained Steam observations.

The product starts with current players and recorded history. It later adds review summaries, metadata, prices, achievements, and news through separately enabled Steam sources. Steam-hosted undocumented endpoints must be labeled distinctly from documented Steam APIs. Equivalent historical coverage to an established tracker is not promised.

The first deliverable is one game followed end to end: Steam input, a durable observation, a read API, and a visible game page. Broader coverage follows demonstrated collection and recovery capacity.

## 2. Users & personas

Game Census is a **new standalone information product**. It is not a language-model agent or a component of an existing SignSense product.

| Actor | Need | Authority |
|---|---|---|
| Visitor | Inspect a game's activity and compare it with other tracked games | Read public game pages, charts, methodology, and exposed read API without an account |
| Analyst | Interpret trends without confusing observations with unique users or sales | Read the same data and provenance. Use bounded comparisons and permitted API access |
| Operator | Run an instance, select its coverage, diagnose collection failures, and restore history | Configure and administer the instance through shipped commands. Supply required external credentials |
| Maintainer | Develop, review, and release the open source software | Change source through repository review. Cannot claim a release passed without command evidence |

A community manager uses the Visitor or Analyst role. No additional account type is required. Each installation has its own Operator. Hosted multi-tenant administration is outside this release.

## 3. Value drivers → required capabilities

| Value driver | Required outcome | Capability trace |
|---|---|---|
| Know what a number means | Counts show source, age, availability, and measurement limits | FR-02, FR-03, FR-06 |
| Discover and compare activity | Search finds catalog entries. Rankings and comparisons disclose the tracked cohort and missing data | FR-05, FR-06 |
| Understand context around changes | Optional game information appears with source-specific scope and timestamps | FR-07, FR-08, FR-09 |
| Operate an independent instance | Shipped commands initialize, collect, report failures, and recover acquired history | FR-01, FR-04, FR-10 |
| Keep the project inspectable and maintainable | Inputs, calculations, configuration, and builds have named owners and reproducible evidence | NFR-01, NFR-02, NFR-03, NFR-04 |

The proposed value is supported by the original product request and the documented source limitations. No interviews, adoption baseline, or demand study have been completed. Adoption measures are deferred in GC-B05.

## 4. Capability catalog

### Requirements and capability acceptance

These stable IDs continue the initial development plan. Each row names a behavior and an observable failure condition. Exact calculations and interfaces belong to the PRS.

No governing ADR exists. The behaviors below are draft product requirements. Technical choices in the PRS remain proposals until recorded decisions settle them.

| ID | Capability and actor | Required behavior and intended outcome | Observable acceptance / boundary | Legitimate exception |
|---|---|---|---|---|
| FR-01 | First-run setup — Operator | Generate configuration and initialize an empty installation through shipped commands. Complete one bounded real collection and show its result | A fresh installation reaches a persisted observation and game page without manual files, database inserts, or source-only values. Repeated setup preserves acquired data | The Operator supplies facts the system cannot know, such as an external key. Missing facts stop the dependent capability and name the setting |
| FR-02 | Current player counts — Visitor | Show the latest validated Steam concurrent-player count with source and observation time. Distinguish fresh, stale, unavailable, and unsupported results | A valid zero remains zero. A failed request never becomes zero. A stale value appears as last observed and cannot appear as current | Steam availability can prevent a fresh value. The failure and last valid observation remain visible |
| FR-03 | Player history — Analyst | Show recorded activity, observed peaks, averages, growth, and coverage for the selected window | Charts preserve gaps. Peaks identify their recorded scope. Averages and growth disclose coverage. No data before enrollment is fabricated | New tracking or source outages can leave gaps. The display must expose them |
| FR-04 | Collection scheduling — Operator | Preview collection scope and enforce budgets, pacing, retries, and explicit enablement | A dry-run reports targets and maximum work. A schedule cannot start before an acknowledged watched run of the same collection plan. Restarts do not reset request accounting | Reads and dry-runs have no watched-run requirement. They cannot enable a schedule |
| FR-05 | Catalog and tracking — Visitor, Operator | Search the discovered catalog and distinguish discovery from active tracking. Retain prior app identities through incomplete discovery | Untracked, unknown, and unsupported apps have distinct states. A failed catalog page cannot remove an app or advance a completed scan | Catalog omissions caused by Steam do not establish that an app ceased to exist |
| FR-06 | Exploration and read API — Visitor, Analyst | Provide game pages, tracked-game rankings, comparison, methodology, status, and a versioned read API | A Visitor can navigate search → game → comparison and inspect scope. Keyboard and table alternatives expose chart information. Page views do not trigger Steam collection | Optional panels can be disabled. Their state must be explicit |
| FR-07 | Metadata and prices — Visitor | Show validated metadata and observed price history for a stated country, currency, and product context | Missing prices never become free. Currency changes produce distinct series. Source drift disables the affected capability visibly | Unsupported fields or markets may remain unavailable after validation |
| FR-08 | Review summaries — Analyst | Show source review totals, score descriptions, and net snapshot changes with the query filters that define them | The display distinguishes returned-page size from total matching reviews. Zero totals yield no percentage. No reviewer identities, text, or playtime persist | Source filters can limit the population. Labels must identify that population |
| FR-09 | Achievements and news — Visitor | Show supported achievement percentages and source-linked news. Keep their scope separate from player counts | Unsupported achievements have an explicit state. News markers link to their source. No marker claims a causal effect on activity | A game may lack either source. Its player history remains available independently |
| FR-10 | Operations and recovery — Operator | Report collection outcomes and next actions. Back up and restore acquired observations through shipped commands | Partial runs return a nonzero outcome. Scratch restore verifies contents before destructive work. Recovery demonstrates the targets in section 6 | If storage cannot record a failure, the command must emit structured stderr and exit nonzero |

### Cross-cutting requirements

| ID | Requirement and actor | Required behavior | Observable acceptance / boundary | Legitimate exception |
|---|---|---|---|---|
| NFR-01 | Validated access and configuration — Operator, Maintainer | Read operator values from validated configuration. Bound public inputs. Keep administration and credentials outside public reads | Invalid settings name the offending key. Query and payload limits are enforced. Credential values do not appear in logs, errors, or public responses | Fixed correctness bounds remain in code. External secrets arrive through the configuration surface |
| NFR-02 | Retained history and rebuildable projections — Operator, Maintainer | Keep one canonical owner for each acquired fact. Rebuild derived views from that owner | A replay reproduces the defined projections. Deleting canonical history requires a tested restore path. A rollup alone cannot replace original observations | A derived copy can be removed after its regeneration command succeeds |
| NFR-03 | Freshness and performance — Visitor, Operator | Meet the proposed targets in section 6 at a measured scope. Include missing games and failures in freshness reporting | Reports include dataset, machine, workload, denominator, and source failures. A failing tier cannot disappear from the denominator | Targets can change through explicit review before release. A missed target cannot be relabeled passing |
| NFR-04 | Open source reproducible delivery — Maintainer | Publish source under the selected open source license. Pin release inputs and provide direct component interfaces | Two isolated builds of identical inputs produce the same canonical artifact. A clean installation requires no newer dependency. The release contains install and recovery evidence | Code licensing does not grant new rights to Steam data or third-party assets |

## 5. Phased delivery

Phase names and boundaries continue the initial plan. These are proposed delivery gates, not completed releases. Detailed tasks and estimates belong to the implementation plan.

| Phase | Product scope | Required proof before expansion |
|---|---|---|
| P0: feasibility | Configuration, pinned foundation, one-game live command | A real source response reaches an inspectable command result. Missing prerequisites produce actionable errors |
| P1: vertical slice | Durable count, API, and game page | An empty installation reaches visible real data. Reinitialization preserves that data |
| P2: history and scheduling | Recorded metrics, quota controls, watched enablement, failure reports | Independent metric fixtures pass. Bounded live collection and simulated failure/restart cases meet their requirements |
| P3: public alpha | Catalog, search, rankings, comparison, methodology, and status | The complete player-statistics journey works for an explicit tracked cohort |
| P4: enriched beta | Metadata, one-country prices, reviews, achievements, and news | Every enabled source passes its own capability checks and first watched run |
| P5: operational release | Recovery, measured capacity, reproducible artifacts, and release documentation | Fresh install, upgrade, restore, and release-build evidence support the declared scope. Public distribution decisions are resolved |
| P6: optional research | Official charts, Steam-wide indicators, survey trends, and public app changes | Separate source/rights/access evidence and an approved extension scope precede implementation |

The smallest real slice must remain runnable as later phases add capability. The product must not depend on every enrichment working before it can display player history.

P3 and P4 name capability milestones. They do not authorize publication. Before any public beta, satisfy FR-07 through FR-10 and NFR-01 through NFR-04. Resolve the distribution scope and record full-size scratch-restore evidence. P5 consolidates operational-release evidence after those public-beta prerequisites.

## 6. Success metrics

All numerical targets here are **proposed engineering acceptance targets** from the development plan. They are not measured results or owner-approved service commitments. The implementation plan owns test execution. The PRS owns calculation definitions.

| Measure | Proposed target | Measurement and failure condition |
|---|---|---|
| First-run completeness | One shipped flow from empty local state to one real persisted observation visible in API and page | Run from fresh scratch storage. Any manual state creation or fabricated live value fails |
| Data interpretation | Every count/history/ranking response exposes applicable source, time, availability, and scope | Contract and UI scenarios cover fresh, stale, zero, unavailable, unsupported, and untracked states. A missing label fails |
| Collector freshness | At least 95% of tracked app-time has a valid sample younger than twice its applicable cadence during a 24-hour canary | Use tracking intervals as the denominator. Include apps with no observations, missed jobs, and source failures |
| Summary-read latency | p95 below 300 ms at 20 read requests/second | Benchmark a documented 2-vCPU/4-GiB reference machine with 90 days of the PRS sample workload. Report cold/warm results and errors |
| Bounded-history latency | p95 below 1 second under the same reference workload | Test the configured point/range bounds. Do not generate live Steam load for this test |
| Recovery | Recovery-point objective at most 24 hours. Recovery-time objective at most 4 hours | Restore a representative full-size backup into scratch. Verify content and record elapsed recovery time |
| Reproducibility | Identical canonical artifact hashes from two isolated builds of the same pinned inputs | Differences fail the release check. Signing time and external attestations remain outside the canonical artifact comparison |
| Source failure visibility | Every attempted source operation ends with a reportable outcome and next action on failure | Inject auth, timeout, schema, quota, and storage failures. Silent loss or success-shaped partial failure fails |

No adoption, conversion, satisfaction, or traffic-growth target has a measured baseline. GC-B05 owns those evidence gaps. They do not block the first technical slice.

## 7. Relationship to existing systems

Game Census reads public Steam sources and retains its own dated observations. It coexists with Steam and SteamDB. It replaces no installed application and migrates no existing product data.

The source research dated 2026-09-04 found a documented current-player endpoint and a replacement catalog endpoint requiring a Web API key. Store metadata has a weaker contract. These distinctions govern capability availability. [Player statistics](https://partner.steamgames.com/doc/webapi/ISteamUserStats) · [Catalog](https://partner.steamgames.com/doc/webapi/IStoreService)

The planning probe made three public GET requests for one app. Its output records current players, basic metadata, and a review summary. It does not establish authenticated access, long-term availability, or collection capacity. [Probe evidence](build-tasks/initial-release/evidence/source-probes.json)

SteamDB is only a reference for the type of information users want. The direct-source requirement in section 1 is the reason Game Census collects from Steam. Changes to SteamDB's access rules, ownership or availability do not change that requirement.

The software's open source license and the rights to distribute Steam data are separate. Public hosting and API distribution must resolve the applicable terms before release. [Steam Web API terms](https://steamcommunity.com/dev/apiterms)

This PRD becomes the canonical product document. The [PRS](PRS-game-census.md) owns technical contracts, sources, configuration, and calculations. The old build-packet PRD path becomes a navigation pointer. The existing implementation plan retains work sequencing and verification commands.

## 8. Risks & open questions

### Risks & mitigations

| Risk | Product consequence | Mitigation and trace |
|---|---|---|
| Requested polling scope exceeds source or instance capacity | Displayed activity becomes stale or collection exceeds its budget | Admit an explicit cohort through a capacity dry-run. Expose actual freshness. FR-04, FR-05, NFR-03 |
| Observed history is mistaken for full Steam history | Visitors draw incorrect peak or growth conclusions | Show tracking start, gaps, metric scope, and the comparison population. FR-02, FR-03, FR-06 |
| An enrichment endpoint changes or denies access | A panel produces misleading or missing values | Validate each source separately. Disable and report the failed capability. FR-07, FR-08, FR-09 |
| A review filter or currency changes unnoticed | Visitors compare different populations or monetary units | Preserve filter/country/currency identities and split affected series. FR-07, FR-08 |
| Acquired history is lost | The instance cannot recreate past observations from a current-count endpoint | Retain canonical captures and prove restore before pruning. FR-10, NFR-02 |
| Public distribution exceeds applicable rights | A planned deployment cannot launch in its intended form | Resolve the concrete distribution scope before public release. NFR-04, GC-B02 |
| Activity includes idling or automated play | Visitors interpret raw activity as verified human engagement | Describe Steam-reported concurrent activity. Do not claim bot removal or unique humans. FR-02, FR-03 |
| Draft targets exceed measured hardware capacity | The release overstates freshness or speed | Measure the declared workload. Reduce scope or explicitly revise the target before release. NFR-03 |

### Open questions

Every unresolved decision has a named disposition in [BACKLOG.md](BACKLOG.md). No unresolved item is disguised as an accepted ADR.

| Backlog item | Decision / evidence gap | Must resolve by |
|---|---|---|
| GC-B01 | Named product owner, name clearance, and final code license | Before public source release |
| GC-B02 | Hosting target, domain, privacy disclosures, operating budget, and Steam-data distribution scope | Before a public deployment or public bulk/API distribution |
| GC-B03 | Exact tested runtime, dependency, asset, container, and build-tool versions | P0, before the first reproducible implementation artifact |
| GC-B04 | Authenticated catalog/schema access and candidate enrichment field/query validation | Before enabling each dependent capability in P3/P4 |
| GC-B05 | P6 extensions and product adoption baselines | Before committing an extension or claiming a business outcome |

These decisions do not block delivery of this draft. They block only the dependent implementation or release step.

## 9. Out of scope

The P0-P5 product excludes:

- Importing or scraping SteamDB history and claiming equivalent historical coverage.
- Frequent collection of every Steam app without a demonstrated feasible budget.
- Exact sales, owners, revenue, DAU, MAU, demographics, geography, or unique-user retention.
- User profile/library harvesting, personal accounts, Steam login, or multi-tenant administration.
- Bot detection, anti-cheat decisions, and verified-human activity estimates.
- Private branches, depot contents, game downloads, license acquisition, and credential collection.
- Desktop/mobile applications, outbound alerts, paid subscriptions, and monetization workflows.
- A language model as the connection between components.
- P6 sources without their own validated source contract and extension scope.

This authoring task delivers the PRD/PRS pair and reconciles the planning references. It does not authorize implementation, commits, publication, or scheduled collection.
