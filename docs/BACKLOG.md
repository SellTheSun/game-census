# Game Census — deferred decisions and research

Status: DRAFT. Owner roles below are proposed responsibilities, not assignments to named people. This is the canonical disposition of open questions in the [PRD](PRD-game-census.md) and [PRS](PRS-game-census.md).

| ID | Item and current proposal | Decision owner | Dependency gate | Evidence required to close |
|---|---|---|---|---|
| GC-B01 | Assign the product owner. Check Game Census naming. Confirm the proposed Apache-2.0 code license | Project maintainer | Before public source release | Named owner and recorded license/name decision. Separate treatment of third-party assets and Steam data |
| GC-B02 | Choose hosting, domain, operating budget, privacy/log policy, and concrete public data/API distribution scope | Operator with project maintainer | Before public hosting, bulk export publication, or public API distribution | Reviewed deployment and data presentation against then-current Steam terms. Configured external facts. Applicable disclosures. No outreach is authorized by this document |
| GC-B03 | Select and pin the proposed Python/PostgreSQL build and runtime inputs | Maintainer | P0 implementation artifact | Exact tested versions, hashes/digests, licenses, clean install and reproducible build output. No floating resolution |
| GC-B04 | Validate eligible user-key access for catalog/schema. Probe candidate metadata and price fields. Confirm review query scope and supported achievement/news behavior | Operator for credentials, Maintainer for source contracts | Before enabling the dependent P3/P4 source | Bounded probe output, authenticated capability result where required, sanitized fixtures, failure behavior and confirmed field/query labels. Credentials remain in configuration |
| GC-B05 | Select any P6 extension. Establish product adoption or satisfaction baselines before proposing related targets | Product owner with Maintainer | Before adding the extension or claiming its outcome | Extension source/access/rights/capacity evidence and scoped requirements. For adoption, actual research or usage baseline with consent and retention decisions |

No item is complete or approved. Closing one requires an explicit recorded decision or the specified evidence. Update the canonical PRD/PRS and affected implementation tasks when that decision changes scope. Create an ADR for a consequential technical commitment during authorized implementation. No ADR has been created by this drafting task.
