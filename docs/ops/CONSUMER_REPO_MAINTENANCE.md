# Consumer Repository Maintenance Guide

This document outlines the process for maintaining workflow system consistency across consumer repositories and debugging issues that may affect multiple repos.

## Verifier canary review recovery

Named review-evidence destinations include both PR body and PR description.
Their editor, field, textarea and preview suffixes use one shared grammar in
channel recognition and destination alternatives: an explicit `or` permits
either channel, while `and` retains both obligations. This does not turn UI
product requirements into reviewer-delivery obligations.
Optional presence predicates use the shared delivery-modality grammar before
checklist fallback, so expanding alternatives cannot revive residual evidence
nouns as mandatory overall evidence. Independent mandatory clauses still gate.
Mandatory checklist noun phrases such as `Test evidence in a PR comment`
retain their destination even without a delivery verb. Optional/prohibited
evidence, product behavior and quoted examples remain subject to the shared
polarity, modality and literal boundary rules.

Reusable Python CI scope includes Python modules at the repository root and
under arbitrary flat-layout package directories, not only `src/`, `scripts/`,
`tools/` and `tests/`. This conservative language-level scope avoids silently
skipping application changes in packages such as `pa_core/` or `dashboard/`;
requirements*.lock inputs also select Python scenarios because lock-only
dependency graph changes are test inputs. Documentation-only and unrelated
JavaScript lock changes still select no Python scenarios.

### Bounded input-limit recovery

After inspecting an actual incomplete verifier report, manual `Agents Verifier`
dispatch may select `evidence_profile=expanded`. Standard remains the default;
this is not an automatic retry or a verdict override. Expanded permits 1,000
retained review records and 1 MiB of combined comment text, with at most ten
collected pages per comment endpoint, plus one bounded re-read of those pages
when pagination was needed. Associated-run discovery follows at most two pages
per exact head/merge SHA, retaining at most 200 distinct runs globally. Artifact
lists follow at most four pages per run, within a global 400-record ceiling.
Later pages, changing/malformed totals, repeated IDs and empty nonterminal pages
cannot establish completeness. A failed later page preserves earlier findings.
Reference-bearing body, comments and linked issues must all be complete before
explicit exact-head references can skip unrelated associated-run discovery.
Missing comment content cannot be replaced by associated jobs.
Paginated comment records require positive stable identities, checked before
body filtering. Each channel tracks its own IDs and observed monotonic direction;
duplicate IDs, direction changes or missing paginated identities keep discovery
unavailable while retaining earlier findings. Both ascending and descending
stable listings are supported because endpoint ordering differs.
Duplicate-free ordering alone cannot detect deletion-induced boundary shifts.
Before declaring a multi-page comment source complete, re-read every collected
page once, including its terminal link boundary, and compare SHA-256 signatures
of ordered identities, bodies, authors, URLs and next-page presence. Changes,
malformed responses and transport failures retain earlier findings but mark
the source unavailable and prevent an incomplete explicit reference union from
suppressing associated-run discovery. This bounded stability observation is not
a transactional API snapshot and performs no retry loop or unbounded recovery.

Archives retain the 4 MiB compressed, 80-entry and 128,000-rendered-character
per-archive bounds. Collection also has global 32 MiB downloaded, 64 MiB extracted
and 4 MiB rendered-text ceilings. Declared sizes are checked before download and
actual buffer sizes afterward; an oversize response fails closed. Extraction
charges raw stdout bytes before UTF-8 decoding or rendering (including invalid
UTF-8), and headings/separators count toward characters.
NDJSON is supported alongside JSONL. Unsupported payloads, expired artifacts,
entry overflow and read/extraction failures remain actionable gaps alongside any
complete siblings. The context records separate page, record, character, archive,
entry, unsupported-payload and provenance counters and failure reasons.

Expanded prompt allocation is 16,384 context, 65,536 diff and 65,536 evidence
estimated tokens (four characters per allocation unit). The existing 8 MiB diff
fetch and 300,000-character context-diff ceiling remain. These allocation units
are **not model token counts**. Only for explicit expanded recovery, before each
evaluation, comparison arm and schema repair generation, the verifier counts the entire native request through the
resolved client's SDK token-count endpoint and reserves its complete configured
output ceiling (including thinking). It requires the source-owned exact-model contract's
positive `max_input_tokens` and output ceiling, and blocks when input plus output
exceeds the input bound. This is conservative even for an input-only bound.
No approximate tokenizer, automatic truncation, stateful unseen context or model
replacement is allowed on capacity failure. Native counter or profile absence is
NON_PASS, including authentication failure while counting; it never authorizes
an alternate judge. Capacity receipts are retained as `verifier-capacity-checks.jsonl`
for both evaluate and compare, including failed generation attempts.
The evaluate receipt upload uses a full action commit pin; its regression rejects
mutable tags without changing upload eligibility or retention.
Receipt open, write or close failures emit a warning without replacing the
preflight result or entering provider authentication fallback. The structured
capacity decision remains in the job log; a failed receipt write means the JSONL
artifact may be absent or incomplete and must not be claimed as retained proof.
A profile's absent output ceiling cannot make an unknown reserve zero.
The selected `VERIFIER_EVIDENCE_PROFILE` is a job-level environment value inherited
by the actual Python processes, not just the allocation and snapshot steps.

Expanded recovery supports `evaluate` and `compare`. The ancillary checkbox CLI
has no native input-count contract here, so expanded compare skips it and expanded
checkbox dispatch rejects before invocation.
Every expanded mode other than exact `evaluate` or `compare` rejects before
profile exports or generation, including empty, mistyped and whitespace modes.
The existing comparison verdict and CI/coverage floors remain authoritative.
No human-only gate is introduced.

SDK-bundled profiles vary by installed version and do not establish the native
counting contract by themselves. Expanded recovery now prepares only
exact `gpt-5.6-terra` as a shallow verifier-local copy with Responses enabled,
retaining the authenticated SDK objects, credentials, endpoint, timeout and retry
settings. An unset Terra output ceiling becomes the documented 128,000; explicit
ceilings are preserved and checked against the model maximum. The source-owned
[Terra facts](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
(owner-fetched 2026-10-10) are context 1,050,000, input 922,000, output 128,000.
The unchanged conservative sum policy requires input + reserved output <= 922,000;
this deliberately leaves more headroom than the shared context requires. It does
not incorrectly describe the input-only bound as a context window.

Exact `claude-sonnet-5-5` retains its Messages adapter and 128,000 configured ceiling.
Each preflight queries the same authenticated SDK's
[Models API](https://platform.claude.com/docs/en/api/models/retrieve), requires an
identical model ID and positive integer `max_input_tokens`/`max_tokens`, and bounds
those values by the [Sonnet nonbatch facts](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
(context 1,000,000, output 128,000; owner-fetched 2026-10-10). Metadata failure is
NON_PASS, never permission to guess a profile. The conservative sum policy applies
to the smaller input/context bound, reserving the complete actual output ceiling.

Both contracts require the exact native adapter/SDK type and official API root;
custom endpoints, counter/client mismatches, query extensions, mismatched payload
models, stateful input, truncation and unsupported input fields fail closed. OpenAI
messages can never be routed to Anthropic's counter. The native counters receive
all supported input fields (including instructions/system, tools, reasoning/thinking
and response formats). The receipt binds provider, exact model, provenance,
endpoint and full generation-request SHA256, and a changed request after counting
blocks generation. Native metadata/count failures and expanded generation failures
cannot trigger alternate-provider resolution. SDK retries keep their existing bound.

Standard remains the default and preserves the original shared builders, request
shape, invocation and schema repair without native capacity claims. No caller client
is mutated. Unknown future models do not inherit these capabilities by prefix.
Retrieval completeness, required evidence and changed-code coverage floors apply
unconditionally in both profiles. Local simulated transport tests establish source
behavior only. Inspect actual new retrieval, authenticated capacity receipts and
both provider verdicts; workflow success alone is not acceptance.
The input snapshot records every bound, and the consumer fingerprint includes the
profile plus `bounded-native-capacity-v3` (standard retains `bounded-native-capacity-v2`), so a previously fingerprinted expanded
evaluation cannot suppress this changed input contract. Existing manifest entries already manage both repaired scripts; no file
addition, rename or delivery scope change requires a new manifest entry.

Workflows#3802's immutable expanded capture reproduces 4/7 complete files and
127,635/257,099 included code characters with the old allocation. The new expanded
allocation represents 7/7 files and all 257,099 characters, while still withholding
PASS for unavailable captured evidence. Proposed retrieval bounds do not prove
that omitted comments, archives or live provider capacity fit. Unsupported archive
entries remain unresolved; no exclusion or batching is introduced. Post-merge
comparison and campaign regeneration remain separate owner work.

For Workflows#3774, the standard report clipped 89,554 changed-code characters
to 63,401 and exceeded the 40,000-character review collection limit. Its reported
CONCERNS remains CONCERNS until a complete expanded evaluation actually passes.
The explicit recovery uses the same merged PR and acceptance criteria, rather
than weakening the obligations or requiring a human reply.

Correct verifier findings in the Workflows source and copy-managed templates,
then regenerate through Maint 68/71. An unsealed staging canary cannot be
promoted merely because a reconciliation run completed successfully.

Unavailable or truncated linked-issue discovery is a required completeness gap
even for a PR not already classified as issue-backed: a failed query does not
prove that its linked acceptance set is empty. A complete, empty query for a
non-issue PR remains non-required; this does not invent an issue or human reply
gate. Retry or repair the discovery source before claiming a complete verdict.

Doc-Lineage#81 also reported that omitted-file diagnostics could exceed the
verifier's diff budget. The source fits text excerpts first, then uses the remaining budget for a
count-only diagnostic, including the separator after a partial line.
Complete omitted paths remain in coverage metadata. Binary descriptors and
diff summaries cannot provide sufficient changed-code coverage. This file is
copy-delivered from `scripts/langchain/pr_verifier.py` to the same consumer path
by the `scripts` entry in `.github/sync-manifest.yml`, which includes Doc-Lineage.

For merged PRs, the context builder retrieves original first-commit metadata
and uses the historical merge parent to anchor the local full diff. An unchanged
rebase uses the original commit count to recover the full range; ambiguous
partial rebases fail closed. The current API `base.sha` may already
contain the head after merging or a later base advance. Missing commit metadata
fails closed instead of replacing the range with an empty or bounded API patch.

Coverage uses Git's `rename to`/`copy to` metadata for destination filenames with
embedded ` b/` tokens. Explicit attach, upload, and include instructions naming
a PR comment require comment evidence. Passive product uploads through a UI or
by an application actor do not require GitHub workflow artifacts; a separate
review-evidence instruction still applies.

Common `submit` and `deliver` evidence verbs normalize through the same
obligation, optionality, negation, literal and destination rules as `record`.
The same shared alias mapping also precedes passive actor binding: supplied,
shared, written, placed, submitted, delivered, pasted and put retain an explicit
reviewer or product actor before or after the complete destination list.
Human AND/OR deliveries and product-component alternatives retain independent
reviewer/artifact obligations and actual missing/unavailable-channel floors;
canonical recorded, optional, prohibited and quoted controls remain unchanged.
Recognized availability relatives also stay attached to bounded product
components while passive actor binding reads the complete destination list.
Moving the qualifier after that list preserves a mandatory bare sibling in
either order and with AND/OR, without turning the component into a delivery.
An independent artifact duty cannot satisfy a missing bare review channel.
Component content relatives use the same bounded presence grammar as bare
channels, but do not create a separate review delivery: their parent governor
and full destination list remain authoritative. Bare-channel relative duties
remain independent. Passive binding reads both attachment kinds before channel
classification, and independent reviewer/artifact clauses remain intact. This
normalization changes only delivery classification, not the original criterion
supplied to the substantive review prompt.
Delivery recognition and product recipients share a bounded modifier grammar
rather than an adjective allowlist. Active human/product past-tense subjects
remain operations; participial evidence adjectives do not become new deliveries.
The product capability `let users post PR comments` uses a bare infinitive
(unlike `allow users to post`) and does not require discussion evidence.
A separate reviewer delivery clause still requires its specified channel;
capability inheritance cannot hide that independent obligation.
Progressive auxiliaries and bounded adverbs (`is currently letting`, `has been
letting`, `supports reliably letting`) obey the same product-only and independent
reviewer boundaries. Qualified delivery actors, including assigned reviewers and
automation agents/runners, retain active past-tense delivery requirements; an
earlier governing display/output operation cannot turn a participle into a delivery.
Actor normalization ignores only the existing list/checklist prefix syntax, without
changing whether the acceptance item is mandatory. Product artifact capabilities
use the shared client/user/consumer recipient grammar rather than a users-only rule.
A single progressive-capability normalizer feeds both comment and artifact
classification; channel-specific copies must not diverge on auxiliary/adverb forms.
Negated capability auxiliaries (`must not`, `does not`, `cannot`) are normalized
only for product recognition. The original criterion and any separate positive
reviewer delivery retain their obligation/negation semantics.
The cross-channel regression matrix combines negated progressive/perfect
auxiliaries, users/clients/consumers, and an optional independent reviewer delivery.
Comment capabilities share quantified and possessive recipients (`all clients`,
`any consumers`, `each user`, `our clients`) with artifact capabilities.
Recognized capability delivery spans are removed before channel classification:
`lets users submit evidence` and `let clients upload validation artifacts` remain
product behavior. Only that operation/object span is excluded; a separate reviewer
delivery is classified from the residual criterion, including its evidence qualifiers.
An object used by an attached mandatory delivery (`artifacts that the reviewer
must upload`, or `artifacts must be uploaded`) remains as that delivery's
antecedent. Before suppressing a capability span, bind its attached mandatory
predicate, original actor, polarity and immediate review destination together.
Common proof objects (test/validation results, logs and outputs, CI/build/execution
logs, artifact-provenance proof delivered to an explicit review destination, screenshots
including before/after screenshots, and recordings) with an explicit review
destination in the same clause normalize into this same evidence grammar before
channel classification. Explicit concrete destination alternatives (a PR comment
or workflow artifact, including `in either`, punctuated OR lists and repeated prepositions) need one present alternative;
`and` and independent clauses still require every obligation. Expansion preserves
the full criterion and its actor, polarity and modality in every alternative,
including overlapping independently required destinations. Mixed conjunctions or
more than 32 combinations retain strict legacy requirements, never a permissive
any-channel shortcut. Only builder-owned present statuses satisfy a branch;
Partially recognized branches retain strict original and recognized requirements,
never disable evidence enforcement. Comma-only lists are not implicit ORs.
absent/unavailable statuses and quoted status-looking content cannot do so.
Artifact provenance is otherwise a property noun: enforcing existing exact-head
or workflow artifact provenance does not demand a new artifact, even in a checked
criterion. A qualified property cannot be its own review destination. Independent
enforcement of provenance within workflow-artifact storage is likewise a property,
not a proof delivery. Independent
actual artifact deliveries remain required; explicit active/passive provenance
delivery uses the same polarity, actor and destination grammar.
Quoted labels/examples cannot supply destinations or clause boundaries, except
exact quoted review-destination names (for example, `workflow artifacts` or
`PR body`) in actual delivery instructions. Parser-operation examples remain
opaque before that narrow destination-name normalization.
Normalization stops at independently governed coordinated actor
clauses, reusing the existing shared actor-role heads (including developers,
testers, auditors, automation agents, runners and bots) and recipient-role heads
rather than maintaining a narrower independent role list. An explicit
pronoun delivery in the next actor clause retains the introduced proof as an
antecedent; an unrelated body update does not canonicalize that proof. Its actor
boundary accepts the shared delivery operations and aliases as finite predicates
and the existing shared delivery-governor grammar for perfect/progressive and
optional/negative actions, not a narrower auxiliary subset. Its destination uses the same shared
preposition grammar (in, into, to, within, for, as, through and via) as ordinary
delivery, including bounded proof qualifiers, rather than a narrower duplicate.
The ordinary classifier still decides actual obligation, negation and product
behavior after normalization. The
antecedent predicate shares the canonical delivery operations and record-alias
map with ordinary delivery; bounded alias-plus-pronoun review destinations
normalize before resolution, retaining governing negation and modality. They
skip shared quoted literal spans before common-proof substitution, not only
before PR-contained comment substitution. The shared independent-predicate
boundary includes negative requirement governors, so an unrelated actor's
optional or excluded PR-body update cannot become the proof's destination.
Explicit next-actor pronoun deliveries retain their introduced proof across
semicolon and sentence boundaries as well as coordination; unrelated updates
and negative or optional deliveries remain nongating. They
canonicalize contracted governors before all normalization while leaving quoted
input intact. Contextual proof binding uses an offset-preserving literal-free
projection, so quoted destinations or actors cannot govern unquoted proof nouns.
Common proof nouns share a bounded object qualifier before explicit delivery
destinations or governors, retaining active qualified-recording body delivery
without converting the progressive recording verb into an object. The qualifier
boundary uses the existing shared delivery governors, negative governors and
destination prepositions; finite operations end the qualifier only when followed
by a bound review destination, so operation-like adjectives remain part of the
object. Neither qualifier repetition nor its final token may consume the actual
governor or operation. Bare participial descriptors retain the ordinary canonical
evidence policy rather than acquiring a new body-specific gate. Direct upload
and pronoun upload use the same PR-body operation grammar; neither may fall back
to generic overall evidence when the body is explicitly required. Body matching
must leave a nounless attached predicate with its antecedent for the shared
attached-delivery pass, preventing an orphaned product object from creating an
extra generic requirement. They
therefore retain negative/optional governors,
quoted-literal and product-capability exclusions, and independent reviewer
obligations; a mandatory PR-body proof cannot bypass the coverage floor when
body retrieval is absent or unavailable.
PR-subject inclusion predicates (`the PR must include/contain/have a comment`)
normalize to PR-comment obligations while preserving their original governor.
A present PR body cannot satisfy that comment channel; negative and optional
inclusion stays nongating. This normalization skips the shared straight/curly
quoted and backtick literal spans before substituting a PR-comment noun, so
parser/documentation examples remain nongating while an independent reviewer
delivery still requires its own channel.
Comment inclusion requires a delivered noun boundary (end/punctuation or an
object qualifier, destination or coordination), not an open-ended feature-noun
blocklist. Compounds such as comment button, form, count, thread and parser are
product features, not delivered comment objects.
Qualified singular `recording of ...` proof nouns use a bounded noun qualifier
ending before the original governor; verbal `is recording evidence` is not a
proof noun. Product link capabilities (`allow users to link`, `let users link`)
share the base operation vocabulary with direct product-owned links.
Bare mandatory `be in` presence shares the same polarity-aware normalized
delivery grammar as `appear` and `be present`, including PR-body destinations.
Product-governed `link` operations use the same UI/API actor classification as
other field operations. A separate reviewer-governed link or comment-delivery
clause remains a real evidence obligation.
Apply this binding before both capability and product-response suppression.
Classify that isolated obligation with the shared destination and channel grammar,
including every declared passive aspect (`be`, `have been`, `have been being`);
bounded predicate/coordination adverbs (`also`, `now`, `still`, ordinary `-ly`
modifiers) cannot break this binding or restore inheritance across a new actor.
An explicit comment/body/artifact destination selects that channel, not an extra
artifact channel merely because the antecedent is an artifact. A generic PR
destination continues to use object-specific classification.
Mandatory evidence that must `appear` or `be present` in a declared review
destination requires that channel; a present body or artifact cannot substitute
for absent or unavailable comments. Optional, prohibited and product capability statements
do not create that obligation.
These presence predicates normalize to the existing passive-record grammar
before polarity and modality classification, only when the mandatory auxiliary
directly governs that predicate. Bare `be in` destinations consume the shared
negative requirement governor.
Presence normalization preserves negative governors for body, comment and
artifact destinations, including `Evidence must not appear as workflow artifacts`.
For negative `No`/`Neither` presence clauses, normalization consumes the full
bounded coordinated destination list (including qualified recipients), not just
its first channel; leftover checklist destinations must not invent an obligation.
The shared destination list stops before a destination-shaped noun governed by
an independent predicate, using the shared mandatory auxiliary vocabulary,
bounded delivery adverbs, and attached `that`/`which` prefixes. Body-subject
delivery predicates recognize the same prefixes rather than losing the channel.
For example, `No evidence is required to appear in a PR comment, and workflow
artifacts must contain command output` still requires the artifacts channel.
Quoted presence text remains literal during normalization. An explicit quote
instruction does not turn its quoted example into an evidence obligation;
independent delivery instructions outside that example retain their channel.
Product capability `permit` shares the bounded `allow`/`enable`/`support`
classification; reviewer `share` and its inflections share the existing record
delivery alias grammar, including negation and independent destinations.
Thus `Command output is not expected to be in a PR comment` and `is not
supposed to be in` impose no comment requirement; a separate affirmative
delivery before or after either clause still selects its destination and floors
PASS when that channel is absent or unavailable.
Preserve
subject-level `No` and coordinated `neither … nor`, exclude collection/product-preview clauses, and normalize
equivalent `comments on/in the PR` destinations before matching presence.
Bare and qualified artifact nouns share that grammar: validation artifacts
required in a PR comment need comment evidence, not merely retrieved artifacts.
The bounded lexical aliases `put` and `place` share the record-delivery
grammar, including negation, body/comment destinations and product storage.
Active-past `placed` with a declared reviewer/author actor is delivery, not an
evidence-object modifier; bare active product persistence remains nongating.
Bounded conjunction/relative clause boundaries isolate the active-past subject
before alias normalization. Perfect product persistence (`has/had placed`,
`has put`, `will have placed`) is also excluded through its immediate
storage destination without discarding a separate reviewer obligation.
Sentence terminators (`.`, `!`, `?`) also isolate that subject. Future
perfect persistence permits negation and the shared delivery adverbs both
before `have` and afterward; those modifiers cannot manufacture a review
evidence obligation from product storage.
Product output exclusions reuse the complete shared response vocabulary,
including `include`, `contain` and `have`; an independent reviewer
delivery remains mandatory after the product clause is excluded.
Thus `not expected`, `not supposed`, `no evidence` and `no longer required`
cannot become affirmative floors.
The same bounded adverbs apply to ordinary coordinated capability actions,
prohibited predicates and modifiers inside perfect passive auxiliaries. Definite
future (`will`) attached delivery retains its obligation. Conditional body records
(`if available`, `when present` and the declared availability conditions) are
optional before channel accumulation; a separate required reviewer clause remains.
This also applies after a structural product component and its coordinated review
destination: leading `either` retains the mandatory alternative, while trailing
`if available`/other declared availability conditions qualify the full list.
Single, body-first and body-last structural destinations share that bounded
availability binding for both product and human deliveries; an independent
reviewer clause retains its own mandatory channels.
Component spans are bounded to one through three same-line words and stop at
shared clause/list/availability boundaries, not an expanding UI noun allowlist.
Declared temporal qualifiers also terminate an already recognized component
(for example, `settings panel before merge` or `field today`). A temporal
qualifier alone after bare `PR description` does not create a product component;
human and independent reviewer deliveries remain mandatory.
Relative markers `that`, `which` and `where` likewise cannot start component
names and terminate an already matched component before its relative clause.
Named checklist shorthand accepts the same declared temporal and relative continuation
after its destination (`Test evidence in a PR comment before merge` remains
mandatory comment evidence). Optional and negative delivery governors keep
their own polarity; an independent artifact cannot replace the named channel.
Postposed `only`/`solely if`/`when` conditions do not become unconditional
checklist deliveries. Postposed negative requirement adjectives reuse the shared
negative-governor vocabulary, retaining their adverb qualifier rather than
turning `currently not required` into a positive imperative.
Qualified checklist continuations use the same independent-actor grammar as
proof-object recognition, including `and`/`or`/`but` forms; a conditional or
negative clause cannot govern a later mandatory reviewer. This normalization
does not rewrite unrelated product clauses, and capability verbs cannot become
recipient adjectives that split repeated product capabilities into deliveries.
Relative optional/prohibited delivery predicates reuse shared adverbs before
their governor as well as the shared governors and delivery operations. Attached simple
copular availability (`that is available`) stays inside the destination branch.
Simple copular qualifiers reuse the shared adverbs before and after `is`/`are`
(`that now is available` and `that is now available` are equivalent).
Both channel classification and destination-OR expansion use that same span.
Body predicates reuse the shared delivery-operation grammar rather than a
separate verb list: linking or generating proof has the same destination and
polarity contract as posting it, and AND still requires both destinations.
This is the canonical operation grammar after context-bound alias normalization,
not the broader alias vocabulary that could mistake an evidence-object word for
another actor. Shared negative adjective governors retain modifiers before the
copula, after it, and after negation (`that is not currently required`), without
turning an optional/prohibited relative checklist into an imperative.
The existing additive contrasts `not only`, `not merely`, and `not just` are
not negative adjective governors, even with supported intervening modifiers;
they cannot erase a mandatory checklist destination.
Product-side generation uses the same governing-actor classification as other
delivery operations. A bounded structural body/description/comment component
remains product-owned for generation, linking, posting and recording, while a
bare explicit review destination and independent reviewer duties stay authoritative.
The shared modifier grammar includes `always`, so `that must always remain available`
stays attached to its existing OR destination rather than becoming a new duty.
Governing product operations reuse the canonical delivery-operation grammar,
including `prove`. Coordinated destinations are classified individually: a
structural comment component cannot consume a bare body/description sibling,
and a structural body component cannot require a bare comment's product channel.
Both orders retain mandatory bare destinations, optional/prohibited governors,
conditional suffixes and independent reviewer artifacts.
OR expansion classifies each bounded structural member with its governing
prefix before trailing independent duties are added. A product-only branch is
not an alternative evidence delivery; an unrelated artifact duty cannot make
that branch satisfy a missing bare review destination.
Both paths also share the independent review-predicate exclusion: an actor
such as `the PR description that must contain command output` is not consumed
as another destination of an earlier prohibited delivery. OR expansion cannot
invent an overall-evidence requirement by splitting that independent actor.
An attached `that`/`which` availability qualifier using `remain`/`stay`/`be`
and `available`/`accessible`/`present` is not a new delivery predicate. It keeps
body/comment OR branches alternative; a relative requirement to contain proof
remains independent and authoritative under the existing shared grammar.
A comma may introduce a declared availability condition. Human body/comment ORs
retain genuine alternatives; a product-only component cannot erase a coordinated
mandatory review delivery, even when an independent artifact keeps every expanded
variant nonempty.
Independent-clause recognition uses those same bounded predicate modifiers, so
availability cannot spill into a later named reviewer obligation. Bind attached
delivery to the noun itself (including a coordinated object), not only an
operation/object pair. Isolated obligations are classified once with rebinding
disabled, preventing recursive re-extraction of passive antecedents.
Punctuated `, which` relative clauses retain the same noun binding. Capability
recombination requires a new recognized evidence object in the incoming fragment;
an explicit reviewer clause using `it`/`them` stays separate for antecedent resolution.
Bounded demonstratives `these`, `those` and `both` share that same resolver.
Bound spans cannot overlap: skip nouns already consumed by an earlier binding,
and do not parse a bare evidence noun qualifier as the attached predicate's actor.
Qualified actor names select the delivery owner, not the evidence object: isolate
the bound object, predicate and destination before classification so an `artifact
reviewer` uploading transcripts to a generic PR retains the overall-evidence floor.
Resolved plural pronoun uploads into the PR body are classified as body delivery,
including bounded coordinated noun lists; attached relative-body uploads remain
owned by the noun binder rather than consumed a second time as body records.
The noun `command outputs` is not command execution behavior when its delivery
has an explicit review destination. Test every declared evidence-object channel
and the absent-evidence coverage floor, not only the original artifact example.
active/passive wording and bare/qualified artifacts must not select different
preposition rules. Missing required evidence still lowers a supplied PASS to CONCERNS.
Coordinated capability actions consume only a complete recognized
preceding object, never an unknown intervening predicate. Recipient modifiers
such as `authenticated users` and `enterprise clients` use one bounded grammar
across channels. Contracted modal negations (`won't`, `couldn't`, `mustn't`) are
canonicalized only for product recognition and cannot erase reviewer requirements.
Attached active reviewer delivery must bind bare `artifacts` as well as
`validation artifacts` to its explicit PR destination. Clause recombination uses
the same evidence/artifact/output/comment object vocabulary as capability-chain
recognition, so changing the final channel cannot change product-only semantics.
Capability recipients reuse the bounded qualifier prefix for supported review
roles too (`assigned reviewers`, `authorized maintainers`). This does not make
review roles product-output destinations. A repeated capability verb after a
recognized object and coordination starts its own bare/`to` complement under
the same product subject; a new human subject or unknown predicate cannot inherit it.

Regression gates: `python3 -m pytest tests/scripts/test_pr_verifier_prompt_coverage.py
tests/scripts/test_pr_verifier_sync_manifest.py -q --no-cov` and
`node --test .github/scripts/__tests__/agents-verifier-context.test.js`.
The latter exercises real merge, squash, and rebase histories with a later base
advance. Keep exact-head canary reviews and seals pending until the source fix
has been merged and delivered; do not manually resolve consumer threads.

## Keepalive authority recovery

Manifest-managed keepalive authority scripts preserve exact-attempt safety across
pre-worker failures. If the summary rewrites `challenge-due` to
`automation-retry` before the failed-run reporter settles the receipt, it keeps
the originating owner attempt and prior generation as non-authorizing recovery
markers. The reporter projects recovery only when those markers match the
authoritative receipt lineage. An available released state rotates when its
boundary fingerprint changes or its due window expires, but retains the settled
receipt and generation lineage so delayed reporters remain safe and idempotent.
Repair this contract in Workflows and distribute it through Maint 68/71; never
patch a generated consumer PR directly.

The manifest-managed runner comment storage queries only GraphQL
`fullDatabaseId` for issue comments. Selecting the legacy 32-bit `databaseId`
in the same query can fail the entire response for current comment IDs, even
when the full-width field is available. It queries `databaseId` only on older
GitHub endpoints that explicitly reject `fullDatabaseId`; keep this repair in
Workflows source and distribute it through Maint 68/71.

---

## Verdict confidence normalization

The manifest-managed `scripts/langchain/verdict_policy.py` treats non-finite
confidence values (NaN and positive/negative infinity, including overflowing
numeric strings) as zero. This applies to markdown parsing and direct policy
calls, including provider rows in JSON output. Verdict text and severity are
preserved: a CONCERNS or FAIL verdict is not converted to PASS. Invalid
confidence cannot manufacture a high-confidence split-verdict hold. Finite
values without a percent sign use fractional form at or below `1` (`0.9` is
90%); values with a percent sign always use percentage points (`0.9%` is 0.9%,
not 90%). Parsing and direct-policy adapters must preserve that unit distinction.
The existing review threshold is unchanged.
Repair this shared policy in Workflows, then deliver it through Maint 68/71;
do not patch generated consumer branches.

## Embedding input alignment

The manifest-managed `tools/embedding_provider.py` preserves one output vector
per input in the same order, including blank and whitespace-only strings.
The local fallback uses its normal 256-dimensional zero vector for blank inputs.
OpenAI requests omit blank strings, then restore their positions with zero
vectors matching the returned dimensionality. An all-blank OpenAI batch makes
no SDK call and needs no credentials: it returns one empty vector per input
with unknown dimensionality. A truly empty batch returns no vectors. Repair
this contract in Workflows and distribute it through Maint 68/71, not by editing
generated consumer PRs.

The manifest-managed `scripts/langchain/semantic_matcher.py` wrapper also keeps
blank positions, including with an injected client: an all-blank request returns
empty vectors without selecting a provider, while a mixed request embeds only
nonblank strings and restores zero vectors in the original positions.

## Inv-Man emitted evidence ownership

`scripts/validate_run_contract.py` is manifest-managed and Workflows-owned.
Inv-Man-Intake keeps its producer-specific local wrapper under
`src/inv_man_intake/emit/validate_evidence.py`; that wrapper preserves local
validation and tests but is not the authoritative reusable conformance gate.
The canonical gate selects `manifest-evidence-closure/v1` from the Workflows
participant registry and validates the downloaded `evidence-*.json` objects,
manifest hashes, and `evidence_refs` closure in the shared validator. Repair
shared behavior here first and distribute the managed validator through the
normal Maint 68 candidate/promotion and Maint 71 reconciliation flow. Never
patch the generated Inv-Man sync PR directly. The policy is valid only for an
`emitting` or `conformant` producer/bridge, so it cannot silently skip closure.

## Registered Consumer Repos

Consumer repositories are synced by the workflow
`.github/workflows/maint-68-sync-consumer-repos.yml`.

The list of registered repos lives in that workflow (env var
`REGISTERED_CONSUMER_REPOS`). Avoid duplicating the list here; it changes over time and
the workflow is the source of truth.

### Drift coverage states

Scheduled Health 68 runs are triggered only after a successful Maint 71 janitor; push and
manual runs are intentionally immediate. It classifies each
consumer as `converged`, `covered`, `blocked`, `untracked_drift`, or `stale`. An open
sync PR covers drift only when it matches the current compiled plan and is within the
36-hour coverage lease. Configured canaries use the stable `sync/workflows-candidate`
branch; promoted non-canaries use the stable `sync/workflows-delivery` branch. Fully covered drift
exits zero and does not append a durable-tracker comment; stale (including expired
coverage), blocked (including global/lookup failures), and untracked states remain
actionable failures.

### Adding a New Consumer Repo

1. Add the repo to `REGISTERED_CONSUMER_REPOS` in `maint-68-sync-consumer-repos.yml`.
2. Run the bootstrap plan, including the load-bearing priority labels:

   ```bash
   python scripts/bootstrap_consumer_settings.py --repo stranske/NEW_REPO --execute
   ```

3. Ensure bot collaborator access (see [Bot Access](#bot-collaborator-access)).
4. Run the sync workflow manually to verify.

#### Priority labels are an opener reachability contract

Every registered consumer must define `priority:high`, `priority:normal`, and
`priority:low` with the colors and descriptions emitted by
`scripts/bootstrap_consumer_settings.py`. The opener uses those labels for
ordering. It still discovers unlabelled delivery issues, but losing the family
makes intended priority unavailable and can indefinitely defer a new
repository behind established labelled queues.

Do not assume a repository created from `stranske/Template` inherits the
Template repository's live labels: GitHub template creation copies repository
content, not repository label metadata. Keep the three labels on Template so it
remains a safe `gh label clone` donor, and run the bootstrap command for every
new consumer. `--labels-only --execute` repairs just this contract without
changing workflow permissions, variables, collaborators, or existing issue
priorities. Existing label metadata is verified and never overwritten
silently.

Audit the current registered fleet without mutating it:

```bash
python scripts/bootstrap_consumer_settings.py --health-check
```

The health report prints one row per registered consumer, including explicit
zeroes. `implementation` counts open non-PR delivery issues independently of
priority, while `priority_labelled` counts those carrying at least one exact
supported priority label and `unprioritized` is the difference. Explicit
durable trackers and narrowly recognized generated dependency/sync bookkeeping
are reported as exclusions; bot authorship alone never hides delivery work.
Missing labels return exit 1. Authentication, rate-limit, malformed-response,
or incomplete-read failures return exit 2 and render affected values as
`UNKNOWN` rather than a false healthy zero.

When cloning labels between repositories, use a donor that has the full
priority family and verify all three definitions afterward. Never infer a
priority for existing issues merely to make counts look healthy.

### Repos with Custom Configurations

`Manager-Database` maintains a custom Gate with `docker compose`,
`pre-commit`, and a custom test setup. It is the manifest's `pr-00-gate.yml`
skip exception. Any custom Gate must include an independent
`generated-delivery-seal` job that invokes the commit-pinned
`stranske/Workflows/.github/actions/generated-delivery-seal` action, and its
aggregate `Gate / gate` must require that job. Invoking the exact-synced
`.github/actions/path-classifier` is not sufficient because a sync PR can
modify that local action. The Workflows-owned action evaluates the event's
exact head and delivery marker outside the mutable consumer checkout and
fails closed until Maint 71 seals that head.

Other scoped consumer exceptions do not imply a custom Gate:

- `Trend_Model_Project` skips the synced `AGENTS.md` file and keeps its local
  `Agents.md` to avoid a case-only path collision on case-insensitive
  filesystems.
- `Orchestrator` skips the synced `AGENTS.md` and `CLAUDE.md` files and keeps
  its local terminal-merge and orchestration safety rules. In particular,
  `AGENTS.md` requires `src/merge_guard.py`; overwriting it failed
  `tests/test_merge_entrypoint_contract.py` on workflow-sync PR #399.
- `trip-planner` skips the synced `.github/scripts/package.json` and vendored
  `.github/scripts/node_modules/` entries so its lockfile-based dependency
  policy remains intact.
- `Fine-Art-Archive` keeps archive-specific reverse-image-search guidance in
  its local `AGENTS.md` and `CLAUDE.md`; both are excluded from overwrite-sync.
  It still receives the managed `.github/renovate.json`; its
  `jsonschema<4.23.0` exception is centralized in `renovate-presets/fleet.json`
  with a repository-scoped package rule.

Other files listed in the sync manifest continue to sync normally; these
root-guidance exceptions are limited to the named repositories and files.

Maint 68 implements these exceptions through each entry's typed manifest
`skip_repos` rules. There is no separate hard-coded custom-Gate list in the
sync script.

### Fleet Renovate intake policy

All registered consumers extend `renovate-presets/fleet.json`. Routine dependency
work is limited to Monday 01:00–05:00 America/Chicago, two commits per hour, and
three concurrent branches/PRs. Routine releases wait three days and for non-pending
update-branch checks; vulnerability alerts bypass each routine delay. Trusted GitHub Actions
digest, pin, minor, and patch updates are grouped for green automerge, while majors
stay visible in the Dependency Dashboard until explicitly approved. Lock-file
maintenance is grouped into the same weekly maintenance window.

---

### Keepalive authority state delivery

The authority challenge helper is source-owned by Workflows and declared in `.github/sync-manifest.yml`. Sync the helper, consumer sweep, Gate Followups, and reporter workflow together through Maint 71 before enabling v2 challenge dispatch in a consumer. The sweep needs `contents: read`; Gate Followups and its reporter need `contents: write` to initialize and conditionally update the `keepalive-authority-state` branch. No operator-created branch or secret is needed beyond `KEEPALIVE_AUTHORITY_SIGNING_KEY`; a missing branch is initialized on the first new challenge. A missing file for a generation already projected in the trusted summary is an error and must be repaired from authoritative evidence, never from the comment alone.

## Bug Triage Process

The shared `tools/ci_failure_triage.py` links to
`docs/CI_FAILURE_PLAYBOOK.md`, delivered by the same sync manifest. Keep
playbook paths and anchors valid in both Workflows and consumer checkouts;
Workflows-only documentation paths are not consumer-local playbook links.

Default deliberate-break pytest commands clear suite-wide `addopts` for the
named head/base test proof. Other repository pytest configuration remains active,
and explicit author-provided commands are unchanged. Full-suite CI retains its
normal coverage and plugin options; this does not weaken that separate gate.

The deliberate-break assertion-tamper check rejects removed assertions,
including an old assertion replaced by a stronger one. The former temporary
Deliverable-Render issue #36 exception is retired now that the stronger
assertion is on the base branch. PR-authored issue markers cannot authorize
assertion removal. The head/base deliberate-break proof must pass separately
before Gate accepts the PR.

Signed keepalive recovery challenges must reserve their current workflow attempt
before starting a runner. Shared `should-dispatch --authority-challenge` verifies
the existing signed envelope and persists primary state before granting dispatch;
denied storage is a failed reservation, not an invisible successful recovery run.

Repository-variable runner storage must surface denied writes: HTTP 401/403
cannot count as a successful reservation or recorded completion. The shared
runner source propagates these errors to its caller, while a missing variable
(PATCH 404) still uses POST creation. Explicit best-effort reads are unchanged.

When a bug is identified in workflow templates:

### Step 1: Classify the Bug

| Category | Scope | Example |
|----------|-------|---------|
| **Template bug** | All repos using template | Logical expression `|| 'true'` always true |
| **Reusable workflow bug** | All repos calling the workflow | Missing output parameter |
| **Consumer-specific** | Single repo | Wrong CI workflow name in verifier |

### Step 2: Assess Impact

```bash
# Check which repos have the affected file
for repo in Template Travel-Plan-Permission trip-planner Manager-Database; do
  echo "=== $repo ==="
  curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/stranske/$repo/contents/.github/workflows/FILENAME" | \
    jq -r '.content' | base64 -d | grep -E "PATTERN" | head -5
done
```

### Step 3: Fix Strategy

| Bug Type | Fix Location | Propagation |
|----------|-------------|-------------|
| Template bug | `templates/consumer-repo/` | Auto-sync to registered repos |
| Reusable workflow | `.github/workflows/reusable-*.yml` | Immediate (all callers) |
| Consumer-specific | Consumer repo directly | Manual PR |

### Step 4: Create Fix Tracking Issue

For bugs affecting multiple repos, create a tracking issue with:
- [ ] Bug description and root cause
- [ ] List of affected repos
- [ ] Fix commits/PRs for each location
- [ ] Verification steps

> Not to be confused with the **transient alert** for actionable consumer-sync
> drift ([#2210](https://github.com/stranske/Workflows/issues/2210)), which
> `Health 68 Consumer Sync Drift` refreshes while the incident persists and
> closes after a clean comparison. See
> [`DURABLE_TRACKING_ISSUES.md`](DURABLE_TRACKING_ISSUES.md).

---

## Common Bug Patterns

### Logical Expression Bugs

**Pattern**: `${{ inputs.flag && 'true' || 'true' }}`  
**Problem**: Always evaluates to 'true', input cannot disable feature  
**Fix**: `${{ inputs.flag && 'true' || 'false' }}`

**Affected files** (historically):
- `agents-orchestrator.yml`: `enable_watchdog`, `enable_keepalive`
- `agents-issue-intake.yml`: `post_agent_comment`

### Missing Event Handlers

**Pattern**: Workflow has trigger but no corresponding job  
**Example**: `workflow_run` trigger without handler job  
**Detection**: Search for trigger in `on:` block, verify matching job exists

### Sparse checkout state leaking into a later checkout

**Pattern**: A job checks out one local action with `sparse-checkout`, then runs a
second `actions/checkout` into the same workspace and expects the complete
repository to be present.

**Problem**: The later checkout can retain the first checkout's sparse worktree
configuration. A subsequent local action then fails before useful work begins
with `Can't find 'action.yml'`, even though the action is present on the
repository's default branch.

**Fix**: Put the preliminary sparse checkout in a dedicated `path:` and invoke
the local action from that path. Reserve the workspace root for the later full
checkout. The auto-label workflows use `eligibility-source/` for this reason.

### Hardcoded Values

**Pattern**: Repository-specific values in templates  
**Examples**:
- `allowed_keepalive_logins: 'stranske'`
- `ci_workflows: '["ci.yml"]'`
- Bot account names in comments

**Fix**: Use variables or empty defaults with clear documentation

### Workflow input typing mismatches

**Pattern**: passing a string into a reusable workflow input declared as `number`.

**Fix**: pass an actual number expression (often via `fromJSON(...)`) so the workflow
template validator and runtime typing agree.

### Action Version Inconsistencies

**Pattern**: Mixed versions of same action across workflows  
**Example**: `actions/github-script@v7` in some files, `@v8` in others  
**Fix**: Standardize on single version, update all files together

---

## Bot Collaborator Access

The `stranske-automation-bot` account needs push access to consumer repos for:
- Autofix commits
- Agent-created PRs

### Checking Access

```bash
curl -s -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/stranske/REPO/collaborators/stranske-automation-bot/permission" | \
  jq '{permission}'
```

### Granting Access

```bash
curl -s -X PUT \
  -H "Authorization: token $TOKEN" \
  "https://api.github.com/repos/stranske/REPO/collaborators/stranske-automation-bot" \
  -d '{"permission": "push"}'
```

**Note**: The bot must accept the invitation. Check pending invitations at:
`https://github.com/notifications`

---

## Sync Workflow Details

### What Gets Synced

Maint 68 is manifest-driven:

- **What** gets synced is declared in `.github/sync-manifest.yml`.
- **Where** files come from is either `templates/consumer-repo/` (most items) or
  repository-level directories like `.github/scripts/` (for shared scripts).
- **Which repos** receive updates are listed in `REGISTERED_CONSUMER_REPOS`.

The fleet-wide docs registry and scorecard settings remain in the Workflows
root `config/source_of_truth_docs.yml`. The manifest resolves the same target
from `templates/consumer-repo/` for consumers, where the file names only the
local README and agent guidance (with case-insensitive `AGENTS.md` discovery).
Do not distribute the fleet registry to consumers or add repo-specific fleet
entries to the consumer template.

#### Manifest Schema and Compiler

`.github/sync-manifest.yml` is parsed by a **typed, deterministic compiler**
(`scripts/sync_manifest_compiler.py`) before any consumer mutation can happen.
The compiler resolves source ownership once, validates every entry, and raises
one aggregated `ManifestCompileError` before sync fan-out so invalid entries
never reach the sync or drift-check loops. It emits the deterministic
`workflows.consumer-sync-plan/v1` JSON consumed by sync, drift, validation, and
template hashing. Its machine-readable schema is
[`consumer-sync-plan-v1.schema.json`](../contracts/schemas/consumer-sync-plan-v1.schema.json).

Validated fields for each sync entry:

| Field | Type | Notes |
|-------|------|-------|
| `source` | safe relative path, required | Resolved once from its declared source tree |
| `source_tree` | `"template"` or `"root"`, optional | Defaults to the section owner; selects exactly one source tree with no fallback |
| `target` | safe relative path, optional | Defaults to `source`; effective targets must be unique |
| `description` | str, required | Included in the plan for operator summaries |
| `sync_mode` | `"create_only"` or absent | `None` = always overwrite |
| `include_repos` | non-empty list of `owner/repo`, optional | Omitted = fleet-wide; limits delivery to named consumers and cannot overlap `skip_repos` |
| `skip_repos` | list of str or `{repo, reason}` dicts | Repo-specific exclusions |
| `overwrite_repos` | list of str | Repos that ignore `create_only` |
| `is_directory` | bool, optional | Defaults to `False` |
| `template_sync` | `"exact"` or absent | Controls template validator |
| `delivery` | `"copy"` or absent | Runtime-fetched files belong under `runtime_fetched`, not a copy section |
| `requires` | list of manifest targets, optional | Transitive co-delivery dependencies for source-delta plans; targets must exist and cycles are rejected |

Removal targets are typed separately and cannot collide with a copy target.
`excluded:` and `runtime_fetched:` remain metadata-only sections.

Each normalized copy record adds its resolved `source_tree`, `resolved_source`,
`content_sha256`, and a stable `effect_fingerprint`; the plan adds
`manifest_sha256` and `plan_id`.
Directory content hashes are computed from a sorted relative-path/content
inventory, so identical inputs produce byte-identical JSON.

`health-69-consumer-sync-shadow-evidence.yml` publishes that plan with a
`workflows.consumer-sync-shadow-handoff/v1` envelope for the existing local
Orchestrator capability `capability:reference-sync-hygiene-test-gate`. The
handoff is explicitly `shadow`, `write_authority=false`, and
`promotion_allowed=false`. The uploaded Workflows runtime report is limited to
local evidence-ingestion state (including an explicit rejected-ingestion state);
it is not the consumer-sync policy classifier. Authoritative classification,
counterexamples, expiry, rollback, and promotion blockers remain owned by
Orchestrator's `consumer_sync_shadow.py` dashboard.

The same workflow also records typed completion evidence through
`scripts/orchestrator_runtime/completion_event_adapter.py`. The uploaded bundle
includes `completion-evidence.json` (`workflows.runner-completion-evidence/v1`)
plus mutable runtime state files `capabilities-state.json` and
`evidence-ledger.json`. Accepted evidence attaches only to capabilities present
in `config/orchestrator_runtime/capabilities.json`; duplicate replays return
`status=duplicate` without mutating ledger or capability state.

#### Canary-Gated Fan-out

Maint 68 separates a sync plan into `preview`, `canary`, and `promote` phases.
An ordinary scheduled or manual no-filter run defaults to `canary` (release
publication deliberately does not start a second sync cycle):
it can open sync PRs only for the three representative repositories declared in
`config/consumer_sync_canaries.json`. Those canaries span runtime/build shapes
and the fleet's automated-review profiles; at least one must exercise the Codex
review profile before promotion. The selection artifact records the exact
compiled `plan_id`, desired hash, and prospective affected paths for every
registered repository before any consumer write.

Maint 68 supports two immutable plan scopes. `full` compiles every manifest
entry and is the scheduled drift-reconciliation default. `source-delta`
compiles the same typed manifest, then selects only entries whose resolved
source changed in an exact Workflows commit range. This lets a dependency-only
source repair reach consumers without absorbing unrelated, unpromoted workflow
drift. Directory entries match changed descendants. Dependencies are declared
by a selected entry's typed `requires` field and expanded transitively. The
path-classifier action therefore carries its lease-contract bootstrap dependency, so a
consumer whose base predates that contract can still evaluate its initial
staged delivery safely. Manifest changes fail closed and require `full`;
historical removal declarations are never replayed by a source delta. The
uploaded `sync-plan-scope.json` records both plan IDs, the exact base/head,
changed paths, selected targets, dependency targets, and ignored paths.
If no manifest-managed source matches the range, Maint 68 records the empty
scope and skips the consumer fan-out entirely.
Changes to the status-ignore reconciler, its consumer copy, or the consumer
`.gitignore` template require `full` scope because that managed block is applied
only by plan-wide reconciliation; the scope selector fails closed if such a
range is requested as `source-delta`.

Start a bounded source-delta candidate with the source repair's exact first
parent and merged head:

```bash
gh workflow run maint-68-sync-consumer-repos.yml \
  --repo stranske/Workflows \
  --ref main \
  -f phase=canary \
  -f delivery_scope=source-delta \
  -f scope_base_sha=<repair-first-parent> \
  -f scope_head_sha=<repair-merge-commit>
```

Maint 71 writes that same scope, source commit, and immutable range into every
canary evidence row. Every `phase=promote` run recovers the exact source commit
from the evidence; a source-delta promotion also recovers its exact base. The
workflow checks out that historical source head and recompiles the same plan.
A later commit on `main` therefore cannot silently join an authorized delivery,
including a full-plan promotion. Do not substitute a moving branch name for
either source-delta SHA.
Before any checked-out source script runs, Maint 68 requires the resolved source
commit to be an ancestor of the workflow dispatch ref and the scope base to be
an ancestor of that source. New source-delta delivery commits also bind the full
plan ID, scope, range, and source commit into their immutable GitHub-signed
commit message; Maint 71 rejects canary evidence when PR-body metadata does not
match that commit and the validated delivery record.

An explicit `repos` input may narrow a canary run to a subset of those configured
canaries, but it cannot expand a canary run into non-canary repositories. The
selector fails closed with `canary_selection_contains_non_canary` if an operator
tries. Canary corrections refresh the stable `sync/workflows-candidate` branch
and its existing PR instead of opening another hash-named PR for every candidate
plan. Promotion likewise refreshes one stable `sync/workflows-delivery` PR per
non-canary; immutable plan and desired-tree identity live in the delivery
record instead of the branch name.

Do not wait for consumer CI in that workflow. Run Maint 71 later with
`active_sync_hash=candidate` to publish `sync-canary-evidence.json`, then invoke
Maint 68 with `phase=promote` and that artifact's JSON as
`canary_evidence_json`. Promotion rejects absent, stale or
mixed-plan evidence, failed required checks, and active non-outdated review
threads. A successful promotion targets all registered non-canary repositories
once every configured canary has current, green, review-clear evidence for the
same plan.

The normal chain is automatic: Maint 68 dispatches the candidate selector after
writing canary PRs; Maint 71 dispatches `phase=promote` only after the persisted
evidence is complete and every candidate exact head is prepared or safely
recovered. Candidate PRs stay open. A successful promotion dispatches the
`campaign` selector, which prepares the stable candidate and delivery PRs for
the same plan across the entire registered non-admin fleet. Maint 71 emits a
commit authorization only when every repository is exact-head ready or proven
unchanged, then rechecks the authorized heads and merges the batch. Generated-branch Gate
completions provide event-driven wakeups through the synced Gate-followups hub.
Maint 68 binds that handoff to the exact plan ID, plan scope, source range, and
source commit. A canary that already matches the plan contributes explicit
`no-change-canary` evidence containing its observed default-branch SHA; Maint 71
accepts it only while that SHA is still the live default-branch head and its
active-ruleset required checks are green. Recovery
from a previously merged candidate is likewise restricted to the dispatching
plan and source commit. Thus a no-diff run cannot silently recycle an older
merged candidate and promote stale content. If no open candidate, current
no-change evidence, or same-plan merged candidate exists, the evidence pass
fails closed. The remediation is to rerun Maint 68 for the intended immutable
full plan or source range, never to reuse an older evidence artifact. These
rules are enforced by `sync_run_contract.js`, `maint71_merge_sync_prs.js`, and
`sync_pr_merge_contract.js`, with the workflow carrying the immutable fields
between those boundaries.
Maint 82 matches configured review-bot identities case-insensitively after
removing an optional terminal `[bot]` suffix from both the configured identity
and the observed login. This reconciles REST and GraphQL representations without
expanding the configured reviewer allowlist; original author logins remain in
finding evidence. Resolved, outdated and ignored-path threads remain excluded.
An empty discovered queue is not completion evidence when discovery is incomplete.

Maint 82 retains every transient Maint 71 handoff with an immutable plan binding,
idempotency key, and due time and supplies a ten-minute fallback for
candidate/campaign evidence holds, delivery-review startup,
pending checks, changed heads, review windows, reviewer settlement, sealed Gate
checks, and stable candidate base refreshes, so an absent event cannot strand
the lifecycle. It does not retry actionable CI failures, unresolved review
findings, or a dry-run-only sealed-head mismatch as if they were timer states.
Successful Maint 71 stale closures publish terminal handoffs from the closed
PR's own head, generation, and plan identity; a dry-run closure does not.
If the close response has a different head or branch from the selected PR,
Maint 71 records the closure without that selected identity and emits no
terminal handoff for the superseded head.
Maint 82 also checks retained nonterminal handoffs against the live PR. A
confirmed closed PR on the retained branch retires that PR's old queue item.
If its head changed, the old immutable head stays intact, the observed closed
head is recorded separately, and the disposition is only `closed`, never a
claim that the old head merged. Open PRs, changed branches, and API failures
remain unresolved; no record borrows evidence from a replacement delivery.
Delayed older handoffs cannot revive a terminal record or retire a later
reopened record for the same immutable delivery. A later observed Maint 71
handoff can revive it if the PR is reopened without changing head or
generation. Maint 82 verifies every incoming nonterminal handoff against the
currently open PR's branch and head before planning it, including when the
previous record was also nonterminal. A newer report timestamp alone is not
open-PR proof. Verification errors are recorded as warning evidence and
exclude the affected PR from that run's continuation selector.
Malformed incoming handoffs are rejected before their PR keys can suppress
live reconciliation of retained records; identifiable keys are blocked from
continuation for that run.
Stale-close handoffs are also checked against the currently closed PR before
acceptance; an old close report cannot retire a PR reopened on a new head or
generation. Source observation times are ordered across the whole PR, not
only within one generation.
A retained nonterminal record whose live open PR moved to a new head is also
withheld from continuation until its owner publishes a matching handoff.
`campaign_prepared` delivery records are stored as terminal evidence but
schedule campaign authorization; Maint 82 therefore verifies their live open
PR and reconciles closure before scheduling that continuation.
Scheduled Maint 82 continuations exclude the manual Collab-Admin exception.
Its `delivery` selector targets only registered `sync/workflows-delivery`
handoffs with the selected immutable plan, scope, base and source; candidate-only
repositories are not sent to that lane as false `target_missing` failures.
Maint 68 and Maint 71 share one repository-scoped GitHub Actions concurrency
group for every stable-PR writer run. The boundary starts before either workflow
reads consumer PR state and remains held through branch publication, review
request reconciliation, lifecycle body replacement, merge, and cleanup. The
group is intentionally not partitioned by workflow, selector, phase, plan,
generation, head, or ref: candidate and campaign selectors can target the same
stable PR, and Maint 68 can refresh that PR while Maint 71 advances its review
lifecycle. The group admits only one running writer, so a writer paused after
its final identity read cannot race another writer into a whole-body PATCH.
GitHub retains at most one pending run in a concurrency group and a newer
arrival can replace that pending run; this is mutual exclusion, not a lossless
queue. Maint 82 replays persisted transient handoffs from their immutable
bindings. If a request was displaced before its handoff was persisted, rerun
the original normal selector with the same immutable inputs. After any failed
or cancelled writer, the next holder re-reads the durable
plan/generation/head record and reconciles any partial comment, body, branch,
or label state.

The `campaign` selector retains the non-manual fleet scope needed for exact-head
authorization.
Promoted delivery commits carry their exact canary evidence in the verified
commit message so Maint 71 can replay the same promotion if a consumer base
advances during review; editable PR body fields never authorize that replay.

Maint 71 persists and validates the `sync-canary-evidence-premerge` artifact
before promotion is allowed to run. A GitHub pre-job approval hold, a cancelled
evidence step, or an artifact-upload failure therefore leaves the
candidate PRs open and recoverable. If an older operator merged the stable
candidate PRs before evidence was durable, Maint 71 may reconstruct evidence
only from the latest trusted, actually merged `sync/workflows-candidate` PR in
each configured canary, rechecking that exact head's required checks and live
review threads. Maint 68 still rejects a stale or mixed recovered plan.
Candidate mode derives its repository scope from
`config/consumer_sync_canaries.json`; non-canary delivery branches are excluded
and cannot create false `target_missing` failures.
Maint 71 reads required contexts from legacy branch protection when available,
then from active repository and inherited organization rulesets. It fails
closed if neither protection surface is visible. A successful ruleset query
that returns no required checks is authoritative for ordinary repository-local
contexts. Generated sync deliveries additionally require `Gate / gate`, even
when the consumer ruleset is empty, and Maint 71 rechecks that context on the
exact head immediately before every merge attempt. Cancelled informational
jobs therefore do not become invented required failures, while the shared
delivery contract cannot merge around a failed or missing Gate.
Review-thread and final exact-head GraphQL reads use a separate read-only
token-aware path, selecting the service-bot quota by its GraphQL (not REST-core)
budget when it is eligible and rotating away from an exhausted identity.
Response/error rate headers update the resource they identify, and headerless
GraphQL calls decrement the GraphQL budget rather than the REST-core budget;
rotation therefore cannot reselect a token whose GraphQL quota just reached zero.
A partial response that explicitly reports zero remaining is authoritative even
without a limit header; other incomplete snapshots use a one-call estimate.
Reviewer-response and proof-bound thread reads use the same path; incomplete
reviewer evidence cannot satisfy the settlement window. Cross-repository
PR mutations remain pinned to `OWNER_PR_PAT`; a missing, partial, denied,
paginated, or rate-limited review response is unknown and blocks sealing or
merge. The final merge request also supplies the expected head SHA.

Maint 68 creates stable deliveries ready for review with
`sync:delivery-staging` and disables auto-merge before every real head update.
If a later run computes the same base and desired tree, it preserves the PR's
current review/seal state; metadata-only refreshes therefore cannot restart
review forever.

Before a source-delta run rotates an open stable PR, Maint 68 clones the
consumer with complete commit history but omits historical blobs from the
initial transfer. A depth-1 clone followed by unshallowing failed on some
existing stable branches with Git's `shallow file has changed` error. Maint 68
fetches the stable head and uses the full PR merge-base to compare unmerged
file changes with the paths actually staged for the new plan and current
consumer base. Manifest targets skipped for this consumer, including existing
`create_only` files, do not count as staged. If an omitted file is not already
present on that base with the same Git tree entry (mode, type, and content),
it fails closed with
`source_delta_drops_unmerged_targets`; rerun
a full-scope canary instead. A narrow refresh must not silently discard schema
or other prerequisites staged by an earlier, still-unmerged plan.

Created and refreshed deliveries also carry the `sync`, `automated`, and
`workflow:source-sync` labels plus the `workflow-source:sync_campaign` marker.
For compatibility, consumer event handlers accept the underscore sync alias
(`workflow_source_sync`) and the colon or underscore maintenance variants
(`workflow:source-maintenance` or `workflow_source_maintenance`) as the same
controlled source label. Generated sync provenance is authoritative over
issue-like text in a file summary only when one of those controlled source
labels appears with both `sync` and `automated`, the stable
`sync/workflows-candidate` or `sync/workflows-delivery` branch, the canonical
Workflows producer, and a complete immutable consumer-sync marker. Removing
any binding restores ordinary explicit-issue precedence.

Every real head update is fail-closed on commit identity. Maint 68 mints a
repository-scoped Workflows GitHub App installation token, uploads the staged
blobs/tree through GitHub's Git database API, and creates the commit without
custom author, committer, or signature fields. GitHub therefore signs the App
commit. The same repository-scoped App token verifies both an existing stable
head and the newly published head, so an exhausted owner PAT cannot interrupt
signed-delivery proof. Maint 68 compares the returned tree to `git write-tree`,
requires a `verified=true` / `reason=valid` signature, and only then atomically
publishes the stable branch with `--force-with-lease`. An existing exact-tree delivery
with an unsigned head is replaced rather than treated as a no-op. Maint 71
independently requires a valid cryptographic signature on the exact workflow-
sync PR head before merge. This accepts GitHub App, GPG, SSH, and S/MIME
signatures that GitHub validates while still rejecting unsigned generated
heads. The sibling dev-tool sync lane is excluded until its producer gains the
same signed-commit contract. This prevents synced workflow files from reaching
consumer `main` through an unsigned automation commit and avoids GitHub's
subsequent workflow trust approval hold.

Maint 71 starts bounded reviewer settlement while the PR remains ready. Before
starting its clock it posts the review request configured in
`config/consumer_sync_review_policy.json` (currently `@codex review`) on the
exact generated head. A plan/generation/head marker makes retries reuse only
a request bearing the configured command from the authenticated owner-token
writer; a generic Actions bot comment is not sufficient. Formal reviews and
inline replies count only when their commit matches the requested head, while
ordinary PR comments must name that full head. The initial reviewing transition
revalidates the PR after the request is posted and preserves the latest observed
delivery body or fails closed on drift. An old `reviewing` record without a
request is repaired and cannot time out into sealing. Dry-run,
evidence-only, and resolution-only passes inspect an existing request and
reviewer evidence, report missing requests or clock repairs, and preview seal
readiness without posting comments or changing PR bodies.
Already-sealed open deliveries also require a durable exact-head request whose
timestamp is no later than the settlement clock. A legacy timeout seal without
that request is preserved in the reconciliation report and restaged by Maint 71;
it cannot authorize canary promotion or merge. Fresh review then starts through
the normal source-owned request and seal sequence. Restaging checks the
current head and plan/generation before any hold mutation and again before
rewriting a mutable delivery, so a concurrent Maint 68 rotation observed at
either read fails closed instead of
being restaged using an older seal.
An already-sealed delivery found draft or with auto-merge enabled is restaged
through the same guarded owner path, which restores ready state and disables
auto-merge before another review attempt. The request lookup re-reads the PR
after scanning request comments so readiness changes during pagination are
included in that decision; an identity change fails closed.
These reads do not make GitHub's PR-body update conditionally atomic, so the
shared Maint 68/Maint 71 writer group covers the final-read-to-PATCH window.
Exact-head plan, seal, and Gate guards still deny authorization when drift is
observed, including work replayed after a pending run was replaced.
Dry-run reports count an unrequested legacy seal explicitly without mutating it.
The policy requires one response, not all configured reviewers, after a
seven-minute quiet period. If every reviewer
reports capacity unavailability, settlement degrades after the quiet period;
if nobody responds, it degrades after fifteen minutes. Active non-outdated
review threads are never waived by either fallback. Reviewer statuses and
comments that explicitly say a review was skipped, excluded, review-disabled,
or not performed are unavailable signals and cannot satisfy the one-response
quorum. A completed negative verdict with substantive review output still
counts as a response; settlement is evidence of reviewer participation, not
approval.
Maint 71 then seals the
exact head and applies `sync:delivery-ready`, which triggers a fresh Gate. The
Gate summary rejects an unsealed stable delivery, while the shared merge guard
rejects `sync:delivery-staging` for every merger except Maint 71's verified
sealed path. The staging hold remains until the merge succeeds.

For workflow syncs, a sealed candidate is not merged immediately: it remains
the stable delivery PR while promotion prepares the non-canaries. Only the
campaign-wide exact-head authorization releases the candidate and delivery PRs
for Maint 71's final per-PR merge gate. This preserves one update-in-place
review surface without letting ordinary PR minimization merge it before fleet
delivery is complete.

When a consumer still has an open legacy generation-named
`sync/workflows-*` pull request, Maint 68 holds the stable candidate/delivery
branch rather than creating a parallel replacement. The legacy attempt must
reach terminal disposition before the stable branch becomes its successor; a
release source commit is not authority to replace an in-flight review surface.

The standard Gate's generated-delivery job invokes the Workflows-owned
`generated-delivery-seal` action directly. It does not execute seal policy from
the consumer pull request checkout, so a candidate that changes the local path
classifier or lease-contract copy cannot redefine its own acceptance rule. The
local classifier retains its trusted-base and add-only bootstrap checks as
defense in depth, but it is not the authoritative seal boundary. Maint 71
remains the final boundary and independently requires the exact generated head
to carry a valid GitHub-recognized signature before merge.

Generated `sync/workflows-*` PRs are excluded from both the basic and agent
autofix lanes. Their intentional pre-seal Gate failure is a delivery hold, not
a request for a consumer-branch repair commit; Maint 71 advances the record and
shared defects return to Workflows source before the stable PR is refreshed.
Maint 68 also writes `autofix: false` into every generated PR body. The shared
reusable autofix workflow independently rejects `sync/workflows-*` heads, so an
older consumer caller cannot mutate the transition PR while the updated local
caller is still waiting to land. The body directive protects the agent lane;
the synced caller branch exclusion becomes the durable local guard after the
generated PR lands.

Maint 71 also enforces the seven-minute exact-head post-push window and performs a final
head plus active-review-thread query immediately before each generated merge.
If repository policy disables the first merge method, Maint 71 tries the remaining
GitHub-supported methods in order and repeats that exact-head/review-thread gate before
each fallback. Other merge failures remain terminal and are not retried as policy drift.
Maint 68 records the exact head and its post-publication observation time in the
delivery record. That SHA-bound observation anchors the window; PR body edits,
labels, comments, and review-thread resolution do not restart it, while a
mismatched or missing observation fails back to the conservative PR timestamp.
Workflow-call, manual, and repository-dispatch candidate selectors normalize to
the same gate. The executor requires same-job campaign authorization bound to
every PR number, delivery generation, branch, and head SHA, so scheduled or
malformed paths cannot merge a candidate implicitly.

Campaign hold states have explicit recovery paths. For
`campaign_authorization_required`, rerun the prepare pass for the same immutable
plan and source commit, then authorize the exact prepared heads. A
`campaign_prepared` row is intentionally waiting for that authorization and
must not be merged by an unscoped pass. A `campaign_no_change_verified` row is
already terminal evidence and needs no PR mutation. Promotion-produced
`no-change-delivery` evidence carries an explicit exact-tree validation marker;
Maint 71 rechecks its immutable plan/source binding and recorded default-branch
head, then treats it as terminal without dispatching a redundant Gate for an
unchanged repository. Canary no-change evidence retains the live required-check
revalidation that authorized promotion. For `target_missing` with
reason `campaign_pr_and_no_change_evidence_missing`, regenerate the stable
delivery for the same plan; if a partial commit pass already merged it, resume
the prepare pass so Maint 71 rebuilds authorization from trusted closed merged
history. `stranske/Collab-Admin` is excluded from campaign authorization because
it is the generated fleet dashboard/control repository, not a reviewed consumer
delivery target. A narrow operational recovery remains available for an
already-generated administration-surface delivery: manually dispatch
`maint-71-merge-sync-prs.yml` with exactly
`repos=stranske/Collab-Admin` and `active_sync_hash=delivery`. The exception is
accepted only for `workflow_dispatch` with that one normalized repository; it
does not add Collab-Admin to the registry, candidate or campaign evidence, or
scheduled, repository-dispatch, workflow-call, mixed-repository, unscoped, or
other selector runs. Maint 71 still applies the normal exact-head, review,
required-check, seal, and signature gates before any merge.

A plan-bound retry leaves a stable PR carrying a different plan untouched. A
plan ID mismatch establishes lack of ownership, not supersession: Maint 71 reports
`delivery_plan_handoff` with the expected and observed plan IDs and persists a
transient Maint 82 continuation bound to the owning plan, source, scope and head. Stale-PR cleanup is likewise restricted to the selected plan.
This prevents a delayed prior campaign from closing a newer candidate or delivery.

Active non-outdated review threads remain merge blockers. When a shared source
repair proves a finding obsolete on the current generated head, an authenticated
operator may pass `review_resolution_json` to Maint 71.
Bot authorship and a manifest-synced path alone never authorize Maint 71 to
auto-resolve a finding. A bot finding on generated content stays blocked for
Workflows-source repair, regeneration and originating-reviewer disposition
or the explicitly enabled independent finding-verification fallback below;
sealing or a passing Gate is not evidence of reviewer satisfaction.

Each `workflows-sync-review-resolution/v1` proof names one thread, PR, exact head,
Workflows source-fix SHA, evidence URL, originating reviewer ID, exact in-thread
reviewer acceptance URL, and reason. The originating reviewer's comment must
be on that thread and exact commit and contain
`<!-- sync-review-accepted:<full-head-sha> -->`; Maint 71 verifies the reviewer
identity, comment, and contained source fix before resolving. Proof-bound
resolution may also clear an outdated
thread that branch protection still treats as unresolved; that path does not
waive the zero active non-outdated thread requirement for ordinary merge
eligibility. A source fix without this exact proof, a later candidate plan, or a
passing Gate never resolves the current PR's review debt.

### Known issue sources and verifier discovery

An explicitly declared non-issue source (marker, source block, checked source
choice, or recognized source label) takes precedence over coordination relations
and incidental title references in both body synchronization and verifier source
resolution. Those relations must not import an unrelated campaign contract.
Explicit closing keywords or `meta:issue` can still select an issue contract;
inferred non-issue provenance alone does not suppress a genuine issue source.

An issue-backed PR may use a non-closing relationship such as `Related to #123`
or a source marker. The verifier retrieves the known same-repository source issue
identified by `resolvePrSourceContext`, even when GitHub's
`closingIssuesReferences` is empty. A successfully retrieved source contract is
included in the acceptance plan and issue-number outputs, without converting the
relationship into a closing keyword. Already retrieved closing issues are
deduplicated; an unrelated closing issue cannot substitute for the known source.
An explicit closing title such as `Fixes #123` retains closing provenance when
body sync generates its issue preamble, including after an earlier same-issue
relation preamble. Incidental title mentions remain non-closing. Multiple closing
title targets are ambiguous. An unambiguous closing title takes precedence over
incidental non-closing body mentions, even when they name other issues; genuinely
conflicting closing targets across title and body are ambiguous. Explicit
`meta:issue` source metadata pins synchronized body text, including incidental
closing references copied from the source issue. A different explicit closing
target in the PR title conflicts with that metadata: the resolver selects neither
issue and verifier acceptance discovery remains required and unavailable. Matching
title/metadata targets and titles without closing intent retain the metadata
binding. Negated title phrases such as `Does not fix #123` do not express closing
intent or create a conflict; negation cannot suppress a later affirmative
directive or cross a line boundary. For a mention/title-derived PR without explicit closing intent in its
title, one generated
`meta:related-issue` binding precedes incidental synchronized body references,
including closing keywords embedded in that issue text. Duplicate identical
markers are idempotent; distinct related markers remain ambiguous. The binding
retains mention provenance and does not manufacture a closing relationship.
Explicit closing-title/body conflicts still fail closed.
Repeated source/template body syncs preserve
this distinction.

This extra lookup does not conceal unavailable or truncated closing discovery.
A failed or malformed source lookup (including a pull-request response or a
different issue number) keeps required discovery unavailable. Incomplete discovery
continues to withhold PASS. Source and consumer-template builders share the same
retrieval behavior and regression controls.

### Independent automated finding-verification fallback

After one targeted reassessment completes without explicit finding disposition,
do not turn repeated generic reviews into a two-hour wait loop. An authorized
source owner may obtain a separate, read-only finding assessment through the
shared model-allocation ledger and publish its completed result on the delivery
record's durable Workflows issue. This is an owner attestation of an independent
assessment, not an originating-bot response; its authority comes from the explicit
fallback policy. A human reply in a consumer review thread is not required.

The owner must read the actual assessor result, confirm complete current-head
evidence and finding-specific PASS, retain the receipt/result and their SHA-256,
and preserve regression command results plus deliberate pre-fix failure proof.
UNKNOWN, interrupted, partial, generic clean reviews, source-wide CI alone,
or an assessment of a different head may never be published as acceptance.
Publish one result per finding with a single hidden
`maint71-finding-verification:v1` JSON marker whose schema is
`workflows-sync-finding-verification/v1`. It binds repository, numeric PR,
head, thread, original finding-body SHA-256, plan, generation, delivery source,
contained source fix, merged source evidence URL and originating reviewer.
It records `verdict=PASS`, `status=completed`, `coverage=complete`,
`verifier_profile`, `assessment_id`, `result_sha256`, `completed_at`,
a substantive rationale, the existing targeted request URL and originating
completion URL, and nonempty `validation` entries containing command,
`exit_code=0` and `negative_control=failed-before-fix`.

Pass the normal resolution proof with
`acceptance_mode=independent-verification` and
`reviewer_acceptance_url=<durable-issue>#issuecomment-<id>`. Maint 71 fetches
that actual comment; it checks the configured trusted publisher and verifier
profile, exact complete binding, request and same-head originating completion,
chronological order and a 24-hour freshness limit. Both review-thread connections
and each thread's comments are cursor-paginated to completion. Stock top-level
completion comments are collected through the paginated issue-comment API; their
short reviewed-commit references must resolve through GitHub to the exact full
head, rather than merely matching its prefix. Missing, duplicate, forged,
stale, incomplete or non-PASS results fail closed. New originating feedback after
the assessment invalidates it. Immediately before resolution Maint 71 re-reads
the PR head, lease, source/plan and complete thread inventory, fetches the current
attestation again (including publisher withdrawal or deletion), and validates again.
Only Maint 71 resolves generated threads. Successful resolution still cannot
waive exact-head checks, the seven-minute review floor, canary staging, sealing,
promotion or full-fleet/Health 83 evidence.

The operator continues through those owning stages in the same run when evidence
becomes ready; the recurring two-hour schedule is recovery, not the normal
continuation mechanism. A failed assessment causes a concrete repair or explicit
UNKNOWN checkpoint, never a fabricated acceptance or another generic review loop.

Verifier file summaries retain human-readable add/delete labels and an exact JSON
destination in a `verifier-file-path:v1` marker. Coverage consumes that destination,
so literal filenames ending in ` (added)` or ` (deleted)` and containing ` -> `
cannot be mistaken for generated status or rename metadata. Display labels escape
line breaks, marker metadata escapes HTML delimiters and Unicode line separators,
and the final JSON-string marker is authoritative. Malformed marker metadata makes
coverage UNKNOWN and withholds PASS, never silently removing a file. Legacy summaries retain
their existing parser for compatibility; generated contexts always emit the marker.

Patch normalization removes only Git's terminal LF, never content carriage
returns or filename-significant spaces in final rename/copy metadata. Summary parsing,
formatted diff text and changed-code inventory share these canonical bytes and
character offsets; whitespace-only input remains unavailable. Real-Git rename
regressions cover trailing spaces, with/without a final newline, and exact
included/truncated inventory boundaries. Each public path normalizes the original
patch exactly once, including binary patches with two terminal LFs; binary code
remains unavailable even when its character inventory is exact.

Verifier acceptance classification distinguishes product output and product fields from
review deliverables: a command that must output a transcript, response evidence links or
records, and endpoint/service/CLI/renderer PR-comment fields do not require reviewing-PR
evidence. Reports and exports use the same product-operation vocabulary. A separate
required delivery clause remains authoritative.
Explicit `comment on/in the PR` destinations normalize to the PR-comment channel;
evidence required `as an artifact` keeps the artifact channel, using the shared
mandatory auxiliary vocabulary (`must`, `shall`, `need to`, `required to`, `have to`)
for passive upload destinations. Ordinary, perfect, and progressive passive
aspects use the same prefix in positive obligations and prohibitions, so adding
`have been` cannot restore a negated obligation. Present evidence in
another channel cannot satisfy either requirement, and optional/negated forms
retain their existing exemption.
Product fields also preserve reversed noun order (`links to evidence`, `records of
evidence`): the exemption applies only to the immediate object of the response
operation, never a later reviewer linking/recording predicate. Mixed-order and
comma-separated field lists use one bounded object classifier; reports and exports
share the same subject vocabulary during clause coalescing and classification.
Bare `records`/`links` are nouns only at a field-list boundary, not before a finite
evidence-recording or linking destination.
Comment operations are classified by their subject head: an API reviewer or reviewer of an endpoint remains
a review actor, while an endpoint used by reviewers remains a product actor. Actor
classification alone cannot exempt real comment delivery: posting, adding or leaving
comments by a service, endpoint, CLI or renderer retains the evidence floor unless
the object is a product field/destination or nested user capability. Each comment
uses its own destination; a later response field cannot exempt an earlier delivery.
Coordinated or temporal clauses with their own review actor and delivery predicate
cannot inherit an earlier product capability exemption.
After a complete comment object, only recognized shared infinitive coordination
retains that exemption; unknown attachments fail closed rather than relying on a
connector whitelist. Negative `can't`/`cannot` forms do not require a delivery.
Capability exemption validates every link: the initial supported actor-to-base-verb
infinitive and subsequent optional-comma `and`/`or` base verbs, `to` base verbs, or
supported actor-to-base-verb infinitives. Supported actors are users, clients,
reviewers, maintainers, authors and operators, optionally determined and API/UI
qualified. Arbitrary modifiers or finite predicates are not accepted as actors.
An unknown link declines exemption immediately and no later recognized link can
restore it. Clause splitting preserves bare shared verbs only after positive chain
recognition; semicolon-separated deliveries stay independent. Negated outer
allow/enable/support capability is operation-local and cannot erase another delivery.
Qualified
product subjects have no arbitrary word-count ceiling. An embedded product description
cannot veto an independently mandatory comment; unresolved subject attachment retains
the evidence floor. Initial human subject heads remain authoritative across unlisted
modifiers, and negative contractions are normalized before obligation classification.
Fronted adjunct extraction is a partial recognizer: the entire discarded span must
match a supported complete construction before choosing the governing subject.
Unsupported or ambiguous introductions retain the evidence floor and cannot fall
through to a last-product-noun exemption, including unlisted human subject roles.
Reviewer modal verify/check/assert predicates use their nested operation's subject
with or without an explicit `that`/`whether`; infinitive check qualifiers cannot
replace the reviewer actor, and a nested human delivery still requires comments.
Negated delivery never removes a separate mandatory clause. Diff hunk contents cannot
replace path metadata. Instructions to add
or leave a PR comment, including passive command-output requirements in that comment,
require comment evidence and cannot pass when it is absent or unavailable. Git diff
parse failures use a non-filename state; every valid filename, including
`__invalid_git_path__`, remains eligible for complete coverage.

When verifier runs collect acceptance evidence, empty or whitespace-only review bodies
must not count as PR-comment evidence. Single-provider non-PASS text/file output
must carry the post-processed `Verdict: CONCERNS` or `Verdict: FAIL` line so the
downstream artifact parser retains a terminal outcome rather than a partial run.
Overall retrieval availability includes the independently bounded PR body,
comments and artifacts. A present body can supply generic retrieval availability
when other channels are completely inspected and absent, not unavailable.
Availability alone does not identify or satisfy the required evidence. Complete, provenance-validated
explicit workflow-run references in typed evidence inputs or locally labelled
evidence/validation/artifact/test-result lines define the artifact retrieval set when both
reference-bearing body and comment channels were fully inspected. Unrelated
associated head/merge jobs and incidental status URLs cannot exhaust that set's
run budget. Select the deduplicated union of typed and labelled explicit IDs
before budget accounting and provenance validation. Without complete
explicit references, bounded associated-run discovery remains fail-closed.
Incidental body/comment URLs, including status-table `View run` links, do not
select an exclusive evidence set: when no explicit set exists, continue exact-head associated-run discovery
so an unrelated no-artifact status job cannot hide the actual validation artifact.
Production PR and linked-issue bodies are reference-bearing prose, not typed
evidence inputs. Keep them in their own source channels; a duplicate body passed
through the legacy evidence input must not promote incidental URLs to explicit
scope. Labelled evidence in those sources still participates in scope selection.
Generated status rows ending in a result column and `View run` link are excluded before
keyword labelling, even when the workflow name contains `Validation` or
`Artifact` or includes unescaped pipe separators. When no explicit set exists, their URLs receive provenance inspection
and do not suppress associated-run discovery. With an explicit set, incidental
URLs are outside the selected scope. A completely inspected explicit set with
zero artifacts remains absent; do not search unrelated runs for substitute proof.
Wrong-head selected references, excess selected runs, incomplete reference-bearing
sources, partial artifact pages, expired
archives and truncated contents still make artifacts unavailable; scope selection
does not prove that any particular acceptance criterion was satisfied.
Any unavailable eligible channel keeps destination-free aggregate retrieval
unavailable, even if another channel is present: availability alone does not
identify the required evidence, and a requirement-only body cannot mask an
uninspected comment/artifact channel. Channel-specific obligations still use
their own statuses without an unrelated-channel veto. Acceptance-list splitting accepts
`-`, `*`, `+`, and numbered `1.` / `1)` markers, including checkboxes, so an
optional item cannot swallow the next independent required item.
This availability record is not proof of criterion
satisfaction. Channel-specific comment/artifact requirements still use their
own retrieval statuses and cannot be satisfied by body presence.
PR-body evidence has its own builder-owned `PR body` retrieval channel. An
affirmative body-delivery obligation is required, not merely a mention of the
body. Negative obligations and product UI body-editor output do not create a
review-evidence requirement; equivalent passive/existential obligations do,
and a later independent reviewer delivery retains its own destination floor.
Body obligations are classified as bounded occurrences, sharing polarity and
aspect handling across active, passive, existential, body-subject and adjectival
forms. They share bounded evidence-object modifiers with delivery aliases.
Qualified objects such
as `validation evidence`, `test transcript` and `validation command output`
retain the explicit body destination: present comments or artifacts cannot
satisfy a missing required body. Optional/prohibited deliveries and recognized
product UI body-editor capabilities retain their existing exemptions.
Each recognized occurrence contributes its own required destinations and
consumes only its matched span; residual clauses still undergo ordinary evidence
classification. Product-editor output is exempt only for a recognized product
actor and the immediate body-editor destination. Actual delivery into the PR body,
human actors, negative merge prerequisites and independent comment/artifact
obligations retain their evidence floors. Unrecognized wording is not exempted.
The product-editor exemption applies only to that destination, not coordinated
actual PR comments or workflow artifacts; both destination orders are retained.
Recognized comma/and/or lists keep the shared delivery predicate across all
listed destinations before clause splitting. Bare body mentions such as summary
or formatting requirements do not become review-evidence obligations.
Repeated destination prepositions retain the same list binding. Explicit exclusion
verbs are prohibitions (their negated forms preserve the positive floor), and
nested allow/enable/support product capabilities recognize show/contain consistently.
An optional artifact suffix does not erase a recognized mandatory body obligation.
A fully retrieved bounded body is fenced as untrusted material, an empty body is absent,
and missing/invalid/oversized bodies are unavailable. Body presence cannot satisfy
a required PR comment or artifact. Generic comment/artifact retrieval status does
not veto a complete specifically required body; `VERIFIER_EVIDENCE_BODY_CHARS`
bounds this channel without broadening the other evidence caps. Existential
requirements such as `There must be a PR comment` retain the comment floor.
Application recording/capture/attachment/generation into database or audit-log
storage is product behavior; separate reviewer deliveries remain mandatory.
Product `links to the evidence` noun fields stay product fields.
Body requirements emitted by `docs_drift_fix_agent.py` retain their producer
wording: `record the before/after evidence in the pull request body` is a body
delivery obligation. Determiners and the before/after modifier are independent;
integration tests call that producer and verify present/absent/unavailable body
floors with other evidence channels absent, instead of testing a simplified phrase.
The same modifier grammar preserves `no before/after evidence` prohibitions;
separate reviewer-comment deliveries remain required.
Paste/write delivery verbs are canonicalized once before obligation, negation,
destination and product-boundary classification, so those grammar surfaces cannot
silently recognize different aliases. Product-provided command output and bounded
supporting/execution/validation evidence-link modifiers remain product behavior.
Preposed destinations such as `Evidence in the PR body is required` consume the
whole predicate; they do not leave a second generic comment/artifact requirement.
Negated optionality (`not`, `never`, or `no longer optional`) is mandatory, not
prohibited. Canonical record/write/paste output to explicit product recipients
(clients, users or consumers) remains product behavior; PR destinations and
independent reviewer deliveries do not inherit that exemption.
An explicit mandatory PR-comment destination also takes precedence in reverse
word order (`Command output must be provided in a PR comment by the service`);
the later product actor cannot erase that required evidence channel.
Product-operation shortcuts cannot erase an immediate positive artifact or
generic-evidence delivery into PR content. Destination binding excludes later
prohibited pronoun clauses; product-only UI artifact display remains exempt.
Non-modal prohibitions (`Evidence is not written`, `Never write evidence`) retain
their polarity after alias normalization. Reverse product-output matching binds
record/write/paste to the recipient after the verb, not a second object noun.
Body delivery uses the same response-operation vocabulary as product delivery:
return/display/emit/render/expose evidence in the PR body is a body obligation.
Forward and reverse product delivery share recipient grammar, including determined
recipients such as `the clients`, `its users`, and `all its consumers`; an
independent reviewer-comment obligation remains required.
Passive PR deliveries share the mandatory auxiliary and passive-prefix grammar,
including `needs to be`, `has to be`, and `is required to be`; a later product
actor cannot erase those review obligations.
Alias normalization is limited to evidence-object or destination-bearing delivery
uses, preserving command names such as `write` and `paste`. Immediate workflow-
artifact delivery shares explicit review-destination binding with PR delivery;
product-only rendering of an artifact is not itself a delivery requirement.
Quoted literals and qualified command-name spans are preserved before alias
normalization. Product recipients and explicit review destinations share a bounded
destination-list grammar across body recognition and product exemptions. A
recipient does not erase coordinated PR/body/comment/workflow-artifact delivery;
independent or negated predicates are not absorbed into that list. Product body
editors remain product surfaces while coordinated artifact/comment deliveries
retain their own channels.
Shared destination spans survive clause splitting unless a destination starts a
new independent predicate (for example, `the PR body must describe the change`).
Participial modifiers such as `written evidence` under a product display verb do
not become an independent record operation. The outer requirement gate shares
passive obligation auxiliaries with destination recognition; negated `does not
have to be` clauses remain non-obligations. CI, GitHub Actions and workflow
artifact destinations use the same recognition and channel vocabulary.
Named workflow/CI/GitHub Actions artifacts directly provided as delivery objects
remain review artifacts even when the actor is a product service. Past-participle
aliases canonicalize only after a governing obligation or passive auxiliary, not
by enumerating all possible verbs before adjectival `written`/`pasted` evidence.
Explicit evidence-object-to-comment bindings commit the comment channel for the
shared response operations; bare product-comment storage remains exempt. Modal
`must not be optional` uses the same mandatory-auxiliary grammar as preposed body
requirements. Destination-bound object modifiers are bounded tokens that exclude
new predicates and conjunctions, not an independently growing adjective list.
Perfect/modal passive prohibitions retain polarity after alias normalization,
including intervening adverbs admitted by the alias grammar.
Active perfect delivery negation (`has/have/had not`, contracted forms and
`will not have`) uses shared delivery operations/adverbs across body, comments
and artifacts, including intervening `yet`. Product-storage objects reuse the
same bounded evidence modifiers as delivery objects rather than bare nouns only.
Negated active-perfect operations are removed before body occurrences are classified. Independent required
delivery clauses remain affirmative; negative merge gates still retain their
existing required-evidence contract.
Product storage also retains straight/curly contracted future-perfect auxiliaries
(`won't have` / `won’t have`), including those shared adverbs, without erasing
an independent reviewer delivery clause.
An `and`-coordinated bare evidence object with a bounded review destination
inherits the previous delivery predicate (including negation); independent
finite predicates and semicolon-separated clauses do not inherit it.
Alias destination normalization accepts the same `both` prefix as coordinated
destination recognition. Optional delivery modals (`may`, `can`, `could`,
`would`, `should`) share one vocabulary across body, residual, product and
coordinated-storage classification and do not become hard evidence obligations
after alias normalization. Straight and curly `couldn't`/`wouldn't` contractions
normalize before classification just like the other supported auxiliaries;
independent required clauses retain their own channels.
Negated optional modals use that same optional-delivery grammar. Hyphenated
evidence-object qualifiers such as `optional-case` do not make their governing
delivery optional. Product storage and client delivery bind the bounded actor,
perfect/progressive/passive aspect, evidence object and destination together;
passive forms require the explicit product actor. A coordinated second review
destination retains its shared governing verb rather than being consumed with
the product destination. Independent reviewer clauses remain required.
The fallback storage path applies the same coordination guard. Product database
storage followed by a shared review destination retains the governing predicate
before body/comment/artifact classification, with an explicit or inherited
destination preposition. Passive put/place aliases normalize only through their
bounded explicit-actor storage/client destination, rather than requiring a
following evidence object that is already the passive subject.
Finite passive auxiliaries (`is`, `are`, `was`, `were`) share the same alias
normalization and bounded adverb/polarity vocabulary. Negated finite progressive
and passive delivery is removed before both body and residual channel
classification; an independent affirmative reviewer clause retains its channel.
Straight and curly contracted finite auxiliaries retain passive alias identity
before clause-level contraction normalization.
Non-clausal subject parentheticals of up to twelve words retain the actor
before active-past alias classification. Governing auxiliaries, explicit
obligation/polarity terms, merge-gate conditions, actual evidence-delivery
predicates, and review destinations prevent stripping a parenthetical that
could contain a separate requirement. Evidence nouns in non-clausal validation
qualifiers retain the outer actor; complete-word matching bounds the scan
without repeatedly partitioning a rejected word into smaller matches.
Review-related nouns inside validation qualifiers do not erase the outer
actor. A comma-led shared destination is protected at the start of an aside
(including its conjunction), while actual evidence-delivery predicates and
governing terms remain protected throughout its bounded word sequence.
An explicit new governor after an elided-subject coordination starts an
independent delivery predicate. The shared finite auxiliary vocabulary bounds
that reset before optionality/polarity classification; a broad body match
cannot hide it, and shared noun-only object inheritance cannot prepend a
previous predicate to it. Bare product-field nouns such as `records` do not
become independent predicates through this governor-only boundary.
Named actors after a conjunction use the same complete governor, aspect and
operation grammar as elided actors. The boundary and broad-destination span
guards must agree: an optional reviewer delivery cannot absorb a separate
maintainer's mandatory, perfect or progressive delivery. Regression controls
cover qualified actors, all three destination channels and genuine prohibitions.
Sentence-ending period, exclamation and question marks share that boundary.
Bare active-past delivery predicates also reset the actor rather than inheriting
a preceding optional modal. The shared operation grammar retains `prove`;
`supply`, `supplies`, `supplied` and `supplying` normalize to the same
record grammar in active/passive, polarity and product-recipient paths.
The bare active-past branch requires a recognized qualified actor and shares
the bounded adverb grammar. Participial evidence modifiers such as
`previously published evidence` do not introduce an independent actor.
Supply aliases require a verbal governor, qualified actor or list-normalized
imperative; object nouns such as `power supply evidence` are not deliveries.
The actor alternative starts at the clause subject and permits only bounded
role qualifiers (assigned, responsible, authorized, experienced, designated,
senior, lead, primary, current, CI or API), not an arbitrary preceding predicate.
Thus `the reviewer checks the service supply evidence` cannot turn an object
compound into an independent service delivery.
The same bounded subject guard applies to active-past placed/submitted/delivered/
supplied aliases. Independent finite-present delivery predicates share that actor
and operation grammar across conjunctions and sentence endings; they cannot inherit
a preceding actor's optional modal.
Base supply/supplies after bare has/have/had possession is not a verbal alias;
progressive supplying retains be-family governors, while supplied retains perfect
governors. Bounded optional inspect/review/check-whether clauses about product
possession of supply evidence are nongating across review destinations and checklist
markers, including shared bounded adverbs before and after has/have/had;
bounded possession modifiers also retain not/never/no-longer polarity there;
independently required reviewer deliveries remain authoritative.
Elided active-perfect review deliveries admit the shared bounded adverbs before
and after have, retaining the same actor/governor inheritance as passive actions.
Active-past and finite-present aliases share the qualified actor vocabulary:
assigned/responsible/authorized/experienced/designated/senior/lead/primary/current,
CI/API, and release/security/compliance/quality/platform/infrastructure/deployment/
operations/finance/data/privacy/audit/risk/project/independent. Up to three such
modifiers may qualify the existing role heads; this is finite compound-role support,
not arbitrary English parsing. Full-prefix subject matching rejects inspection
predicates such as audits/observes/tests before object service/API actors.
Delivery prohibitions reuse the shared governor and operation vocabulary,
including do/does/did and prove, with not/never/no-longer polarity. A required
delivery in another independent clause remains authoritative. Supply alias
classification inspects contracted negative governors before clause expansion;
bare never/no-longer delivery predicates remain negative in either clause order.
Contrastive not-only/not-merely/not-just deliveries are additive, not prohibitions,
using the same bounded delivery operation/aspect grammar and preserving quoted
literal bytes. A negative
governor cannot be discarded by matching an embedded need-to/has-to substring.
These guards share the passive aspect vocabulary, including residual been/being
after a finite has/had/is governor and the same governed aspect in immediate
review-destination recognition. A short negative requirement match consumes
its complete optional passive or active-perfect action instead of leaving
to-be-recorded or to-have-supplied text behind as a new delivery. Body predicates,
negative action removal, and elided-passive inheritance share the complete
negative requirement governor vocabulary. A coordinated elided passive
review delivery inherits only the preceding evidence object and governor;
optional/negative governors remain optional/negative, and a new actor or product
storage predicate cannot supply that inheritance.
An explicit contrastive but boundary retains the inherited modality but does not
copy its negation to the contrasting delivery; and/or retain the negative governor.
Checklist syntax cannot reclassify object nouns left by a recognized negative
delivery as mandatory evidence. Explicit independent positive predicates and
required body records remain authoritative, including their real evidence floor.
An immediate single-line checklist continuation retains its delivery context;
a blank paragraph ends that context. Bare allowed/permitted evidence-presence
clauses remain nongating. Optional or negative presence alternatives also retain
their governor when `either` precedes the destination preposition, including
PR description components and independently required deliveries.
Checklist shorthand uses the same `-`, `*`, `+`, and numbered `1.` / `1)`
markers as criterion parsing. A terminal component noun after body/description
is product-owned only when its governing subject and operation establish that
ownership; an unlisted UI noun is not automatically an evidence destination.
Human deliveries, prepositional continuations, and independent positive clauses
remain authoritative.
When a product-owned body component is followed by coordinated destinations,
the shared governor remains authoritative: optional UI behavior cannot create a
mandatory comment/artifact obligation. Structural component nouns consume the
same coordinated destination grammar as named components; a separate mandatory
reviewer delivery remains required.
Active-perfect elided deliveries retain their bounded actor and complete governor,
including optional/negative and contrastive paths, through the same splitting and
inheritance predicate as passive delivery. Their explicit evidence objects are
not mistaken for passive subjects or ungoverned checklist deliverables.
Comment presence/containment predicates share the complete mandatory auxiliary
grammar, including `has/have to`, with existing polarity controls.
Do-supported product storage (`do`, `does`, `did`) shares the finite auxiliary
grammar and does not create a review obligation. Comma-separated and conjunctive
shared storage/review destinations reuse the delivery-list separator grammar,
including inherited prepositions and channel-symmetric active/passive forms.
The shared literal grammar recognizes
single-quote delimiters only outside words, retains apostrophes inside quoted
contractions, and cannot swallow an independent mandatory delivery between two
ordinary contractions. Parser examples and quoted inputs remain protected.
Repeated active internal-storage predicates inherit their explicit product actor
and complete governing modality/aspect/polarity before clause splitting. The
bounded normalizer preserves each evidence object and its shared review
destinations; an explicit new governor or independent reviewer clause ends
inheritance. It protects parser examples and literals rather than deleting
unrecognized text. Internal `and`/`or` storage chains are supported; alternative
review-destination semantics and nested/passive coordination are not inferred.
An explicit new mandatory governor also ends optionality after a single storage
predicate, without requiring an intervening inherited storage member.
Definite-future `will` uses that same reset; active-past reviewer subjects retain
up to three shared delivery adverbs before alias classification.
Single explicit-actor passive storage/client clauses retain shared review
destinations, including inherited prepositions. The reverse product shortcut
cannot consume a predicate with a following review destination; passive-perfect
body classification retains the shared aspect and polarity grammar.
Regression controls independently cover negation, optional versus mandatory
delivery, three storage predicates, governor resets, and all review channels.
Explicit passive delivery agents are normalized before both destination and
alternative classification. The same finite actor, operation, aspect, polarity,
and destination grammar stops at unquoted list-item and paragraph boundaries.
Soft wraps within one criterion and quoted multiline examples remain intact;
criterion splitting protects complete quoted literals before recognizing list
items or blank paragraphs. Embedded apparent duties cannot create an evidence
requirement, while independent delivery clauses outside the literal still apply.
bare list markers are not evidence-object adjectives. An adjective such as
`optional` inside an explicitly mandatory delivery object does not change its
governor, while optional modals and post-object availability conditions remain
authoritative. The component start and terminal guards share the full
destination-preposition vocabulary, so `via automation` is a qualifier of a
bare review destination, not a component name. A real named product component
can terminate before the same qualifier without inventing a review obligation.
The component start and terminal guards also share the finite content-predicate
vocabulary: containing, including, showing, displaying, summarizing, presenting,
listing and describing. Such a predicate qualifies the destination's content,
not its component name. Bare mandatory destinations retain their evidence duty;
a real named component before the predicate remains product functionality.
Polarity, passive agents and independent artifact duties retain their own scope.
Both classifiers normalize the same bounded, literal-safe content-object spans
before proof-alias and alternative expansion, so a qualifier cannot invent an
additional overall obligation or hide a following destination alternative.
Conditional and relative boundaries remain outside the content-object span.
Content-object adjectives reuse the shared negative-modality grammar: `not
expected`, `not supposed`, and `no longer required` describe that object, not
the mandatory delivery governor. Passive agents after such content do not
create an additional overall evidence obligation. Literal, conditional, and
independently governed delivery boundaries remain authoritative.
The same finite actor, operation, aspect, polarity,
and destination grammar applies whether `by the reviewer` or `by the UI` occurs
before or after the destination. Agent text cannot become a component name or
detach a bare sibling review obligation. A bare explicit `in a PR comment`
delivery remains review evidence even for a product linking operation; a named
PR-comment settings panel remains product functionality. Regression cases cover
ordinary, perfect, and progressive passive forms and the actual evidence floors.
The explicit delivery guard requires a named evidence object after the operation:
product functionality that merely links to PR comments remains nongating.
Shared delivery operations include their ordinary progressive inflections,
including dropped-e forms such as generating, providing and storing. Perfect
aspect `have` is not a second product operation; possession of an evidence
object remains distinct. An explicit body/description relative predicate with
its own governor is classified independently of an enclosing optional or
prohibited delivery, retaining its own polarity rather than inheriting the
parent's. Product alternatives, bare sibling duties and independent artifacts
are validated across ordinary, perfect, progressive and passive forms.
The supported irregular `leave`/`left` operation shares those same guards.
Active-perfect coordinated deliveries reuse the same supported participle guard,
including irregular `left`, when inheriting a bounded actor and governor. A
repeated operation does not reset product ownership: coordinated body/comment
components retain their product actor and polarity, while bare review siblings
and independently governed artifact duties remain distinct. Alternative review
deliveries are not converted into conjunctive obligations by that inheritance.
This bounded restoration also retains qualified product actors, repeated
perfect/progressive aspects, and repeated capability predicates with qualified
recipients. An explicit repeated aspect replaces only the inherited aspect,
never its actor, modality, or negation. Tests reuse one coverage-fixture module
and exercise the actual floor; caching does not remove destination assertions.
Storage, qualified product recipients and named components use that same product
actor grammar. A repeated explicit governor replaces the inherited governor but
does not invent a new actor; bare destinations still require their own evidence.
Chains of three or more operations carry forward the latest explicit governor
and aspect, not the original head's stale state. A mandatory middle predicate
cannot be made optional by an earlier `may`, nor can an optional middle
predicate borrow an earlier `must` for a later bare review destination.
Product-only AND/OR members preserve that state without inventing proof
alternatives. Once a bare review destination participates, genuine destination
OR still permits either channel; it is not converted to mandatory AND.
Shared negative-governor controls include `not expected`, `not supposed`, and
`no longer required`, alongside optional and direct prohibited deliveries.
Product storage and qualified client/user destinations reuse the canonical
delivery operations and passive agent binding in either position. They do not
invent a generic overall-evidence duty; independently governed artifact and
bare-comment deliveries remain required even when overall retrieval is absent
or unavailable. Reviewer actors are not reclassified as product actors.
Passive destination lists accept the shared `both` and `either` quantifiers
on either side of their leading preposition before actor binding; a product
component cannot erase a mandatory bare sibling.
Bare body, description and comment relative presence duties are separated from
their enclosing delivery before channel and alternative classification. Their
independent governor retains polarity, while the parent's genuine AND/OR list
retains its own semantics. Availability relatives and named product components
are not independent presence deliveries; quoted parser examples stay opaque.
Relative normalization stops at a blank paragraph, including CRLF and
whitespace-only blank lines. Soft single-line wrapping remains supported and
quoted examples spanning paragraphs remain opaque; a later paragraph cannot
become a relative delivery or disappear as an earlier component property.
First-member relative qualifiers preserve the complete bounded parent
destination tail, including repeated prepositions, before independent presence
duties are separated. Recognized attached availability is kept with that whole
AND/OR list rather than hiding its following members. Availability metadata is
removed only from delivery classification, never relocated across a trailing
parent condition. A condition after the complete parent list stays on that
delivery; it cannot migrate to an independently mandatory bare-channel relative
predicate. A condition immediately attached to that relative retains its own
scope. When availability metadata ends the destination list, its trailing
condition remains on the parent delivery instead of disappearing with that
nongating metadata. Both attachment positions
are covered for nominal evidence, reviewer and product actors, channel aliases,
independent artifact duties and actual missing-channel satisfaction.
The same shared `if`/`when` evidence-condition vocabulary stays attached to a
relative presence predicate before its parent destination tail is restored;
comma-delimited conditions cannot sever or make optional a parent's sibling.
Comma-delimited relative clauses use that same attachment path, including their
closing comma before a following destination. Existing `only if`/`solely when`
condition prefixes remain attached to the relative duty rather than consuming
the parent's list. Both first/final positions retain actual AND/OR floors.
Negated obligations use the same delivery-operation grammar as positive
delivery. An explicitly excluded PR-comment destination (`outside`, `rather
than`, `instead of`) is not a required comment channel; generic evidence and
independent positive deliveries still retain their coverage floors.
The four fresh canary findings are tested through the actual coverage floor with
present, absent and unavailable evidence plus independent reviewer-delivery controls.

Non-PASS CLI and file text includes the final verdict, summary, structured concerns and
distinct raw model detail, so concise summaries do not discard actionable gaps.
Embedded structured PASS objects, including prose/code-fence wrappers after a
failed schema repair, are removed from non-PASS diagnostic detail by exact object
span; surrounding actionable prose is retained even for incidental schema examples.
These rules are source-owned and regression-tested before consumer regeneration.
Product UI criteria that allow/enable/support users to upload artifacts likewise
do not require workflow artifacts; separate PR-comment evidence remains required.
Mode-only diffs must preserve identical filenames containing embedded ` b/`
tokens even when Git supplies no rename or `+++` destination metadata.

For a dev-tool delivery or stable workflow-sync candidate and delivery whose
owner has fixed a review finding but whose originating reviewer has not
reassessed it, send the Maint 71
`maint71-review-reassessment` repository-dispatch event with a
`client_payload.review_reassessment_json` string. The versioned JSON object must contain
`schema=maint71-review-reassessment/v1`, `repository`, numeric `pr`, exact
`head_sha`, active `thread_id`, `plan_id`, `generation`, `source_commit`, and
`originating_reviewer` (the configured reviewer ID, such as `codex`). Maint 71
checks the registered repository, trusted generated branch and author, current
delivery lease and immutable bindings, complete review-thread inventory and
originating reviewer, then posts the policy-configured review command once.
Workflow-sync reassessment is restricted to the stable
`sync/workflows-candidate` and `sync/workflows-delivery` branches; another
`sync/workflows-*` branch fails closed.
After the general exact-head review, reassessment posts the configured targeted
command as a reply in the original review thread, including the finding, source
commit, exact generated head, acceptance marker, and prohibition on unrelated
edits or merge actions. A general top-level review request is not an in-thread
disposition task and cannot suppress this targeted request.
The request comment records a plan/generation/head/thread marker and URL; a
repeat dispatch reuses that evidence. An ambiguous POST must be inspected by
marker before retry. This dispatch runs a separate request-only job: it never
resolves a thread, seals, merges, closes, or otherwise reconciles the PR. The
ordinary Maint 71 run later rechecks the same head, reviewer disposition,
checks, and merge gates. A reviewer request is not itself thread acceptance.

If the originating provider reports a terminal failure instead of completing
the targeted request, the same binding may use `request_stage=retry` once.
The source-owned request-only job requires exactly one trusted original request
and one fully discovered originating-provider activity summary with a single
configured failure row. Its failure time must follow the request, its reported
commit must resolve through GitHub to the exact full head, and the summary's
update time must corroborate that failure. Pending/completed activity, mixed
activity rows, ambiguous summaries, forged authors and old heads fail closed.
All sibling-thread comment inventories must also be complete. Explicit
originating replies that start with ACCEPT/REJECT suppress retry just as stock completion does;
quoted instructions or statements such as "I cannot ACCEPT or REJECT yet" do not.
neither is treated as acceptance by the request-only job. Re-read the delivery,
lease, active thread and original request after summary/commit discovery and
before posting; a newly appeared retry marker aborts the POST for recovery.
Repaginate provider conversation comments after the fresh binding read too:
an edited failure summary aborts retry, and a newly posted completion suppresses it.
Revalidate bindings again after that pagination; do not authorize from a stale snapshot.
The canonical `maint71-review-retry:v1` marker makes repeated dispatches reuse
one request rather than creating a retry loop. Retry grants no reviewer
acceptance, resolution, sealing or merge authority; an automated reply remains
sufficient under the existing acceptance contract, without a human-reply gate.

If that exact request completes with a same-head Codex stock no-major-issues
reply but leaves the finding active, send the same binding with optional
`request_stage=disposition`. Maint 71 requires the trusted original request and
the subsequent originating-reviewer completion on that exact head, using a
complete inventory even when the reviewer posts its summary in a sibling
thread. The disposition task itself still replies in the original thread. It then
also recognizes a trusted top-level completion from a fully paginated PR-comment
inventory, but only after resolving its reported commit ID through GitHub to the
exact requested full head; an ambiguous or different commit fails closed. It
posts one separately idempotent `@codex address that feedback` disposition-only
task, requesting an explicit accept/reject and exact-head acceptance marker in
the existing thread. It cannot run while the first review is pending, on a
changed head, or as a duplicate stage. This grants no resolution or merge
authority and imposes no mandatory human reply.

An inline mention is not proof that a disposition cloud task executed. When
the originating provider returns another stock summary, its configured
`disposition_task_transport=pr-conversation` bridges the existing authenticated
in-thread request to one top-level task mention. The bridge binds the same
repository, PR, head, thread, plan, generation, source and reviewer plus the
verified inline request ID and URL.
The canonical binding is SHA-256 hashed in a `maint71-disposition-task:v1`
marker. The policy task command is `@codex answer this specific finding` and
points to the existing inline acceptance instructions rather than repeating
review-command/schema text in the cloud entry. A live top-level diagnostic
question executed as a cloud task while an address-that-feedback request
returned a stock summary; the connector routing internals remain unknown.
Actual originating in-thread output is still required, regardless of command.
A repeated disposition dispatch recovers that request without reposting it
and reuses one trusted bridge after fully
paginating PR comments. Changed bindings, duplicate trusted bridges, incomplete
inventories and uncertain POST outcomes fail closed. The task must answer in
the original thread; top-level answers, generic summaries and task completion
alone cannot satisfy acceptance or authorize resolution. The supported
top-level task entry is documented, but successful in-thread output remains
unqualified until actual originating-reviewer evidence demonstrates it.
This source-owned request-only transport grants no generated mutation authority
beyond posting the bound request and never introduces a mandatory human reply.

A non-empty workflow-sync selector applies only to the `sync/workflows-*` lane.
An open sibling `deps/sync-dev-versions-*` delivery is therefore ignored for
the selector's expected-branch check instead of producing a false
`target_missing` system failure; an unscoped Maint 71 pass reconciles the
dev-tool lane independently.

When open sync PRs exist but none matches the selected branch, Maint 71 reports
`no_active_sync_pr` in its decision log and the JSON row's `delivery_reason`,
alongside `expected_branch` and `active_sync_hash`; the status remains
`target_missing`. `missing_delivery_record` means a selected PR exists but its
body lacks a delivery record. An empty selector still selects the newest
candidate; it does not itself imply either error. The final exact-head seal
check also retains `missing_delivery_record` when an existing PR loses its record.

Use `preview` to produce the plan/evidence artifact without a write matrix.
There is no direct-repository promotion bypass. Security and production-break
fixes may use an expedited canary run, but still require exact-plan evidence
before `phase=promote` can write to non-canaries.

To validate the manifest locally:

```bash
python scripts/sync_manifest_compiler.py \
  --manifest .github/sync-manifest.yml \
  --output-json /tmp/consumer-sync-plan.json
```

This is also run automatically as the first step of both `maint-68-sync-consumer-repos.yml`
(before any PR creation) and `health-70-validate-sync-manifest.yml` (on every PR
that touches the manifest).

Custom Gate repos are a special-case skip: their `pr-00-gate.yml` stays local,
but their Gate must retain the exact-synced path classifier or an equivalent
exact-head delivery-seal check.

The `Template` repository is the canonical source for new consumer repos, so it
must not preserve stale copies of files that are `create_only` for real
consumers. Manifest entries can set `overwrite_repos: [stranske/Template]` to
keep those files aligned in Template while still preserving customizations in
production consumers.

### Reusable Workflow Versioning

First-party consumer repos currently call reusable workflows via `@main`.
That is the active standard reflected in the consumer templates and integration
guide. For repos that need extra stability, pin to a specific commit SHA instead
of following the first-party default.

If a reusable workflow fix must ship immediately, trigger:
- `Maint 68 Sync Consumer Repos` only if template files changed

### Sync PR Branch Cleanup

`maint-71-merge-sync-prs.yml` owns routine cleanup for `sync/workflows-*`
branches. In addition to closing stale duplicate sync PRs and merging the active
passing sync PR, it deletes same-repo sync branches that are connected to closed
or merged sync PRs and no longer have an open PR. Use the `cleanup_branches`
manual input to disable that cleanup only for diagnostics.

### Autofix Tool Version Ownership

Workflows owns shared autofix/dev-tool pins in
`.github/workflows/autofix-versions.env`. Treat that file as the source of truth
for `ruff`, `black`, `mypy`, `pytest`, `coverage`, `isort`, and `docformatter`.
The matching `pyproject.toml`, consumer template, integration template, and
direct `requirements.lock` pins must move in the same Workflows PR. Maint 52
also updates managed `.pre-commit-config.yaml` hook revisions and direct tool pins in a consumer's `requirements-dev.lock` when that
additional generated lockfile exists.

Direct pin replacement is not lock regeneration. Maint 52 applies
`sync_dev_dependencies.py --apply --pre-commit --resolve-locks` before publishing
a changed dependency tree. For generated uv requirements locks, this replays the
recorded repository-local compile inputs and supported extras/platform options
as an argument vector (never a shell command), permitting upgrades of managed
tools and resolving their changed transitive requirements. Existing unrelated
output pins remain resolver preferences. Unsupported provenance or a solver
failure stops publication with a concrete error; it must not leave a knowingly
unsatisfiable generated delivery marked ready to merge. Manually authored
`requirements-dev.txt` without uv provenance remains a direct-pin surface.
Repository-local baseline `.txt` inputs and uv's plural `--constraints` and
`--overrides` options retain their scope. Hashed requirement continuations still
receive canonical tool constraints; previously recorded managed upgrade options
are replaced by the current canonical version. Escaped input/output destinations
fail closed. A successful unchanged lock is a no-op, not an update receipt.
Implicit group inputs use the local `pyproject.toml`; an explicit group path
must validate its own existing repository-local project, not an unrelated root
file. Before any direct apply write, validate all potential output destinations
against repository containment, including resolved symlink targets. Canonical
pyproject updates keep dependency extras before the version and preserve markers.
Inline dependency arrays recognize quoted extras brackets as requirement content,
not the end of the array, and are tested through the full pyproject update path.
Repeated marker-qualified entries are evaluated together: a canonical last entry
must not hide an earlier stale version or non-exact operator. Update every
matching occurrence while preserving its extras and environment marker; a second
apply must be a no-op.
Both apply branches derive publication readiness from the final tree diff; dry
runs perform the same resolution in the disposable checkout without publishing.
The final apply output, rather than the preliminary direct-pin check, supplies
the preview and PR change summary for transitive-only updates.
The propagation-script digest participates in the wave hash, so this repair
produces a replacement wave even when the canonical tool versions are unchanged.

Consumer repos receive those pins through `maint-52-sync-dev-versions.yml`, not
the general `maint-68-sync-consumer-repos.yml` template sync. Keep
`.github/workflows/autofix-versions.env` out of `.github/sync-manifest.yml` so a
workflow-template sync PR cannot update the env file without the matching
`pyproject.toml`, managed `.pre-commit-config.yaml` hook revisions, `requirements.lock`, and supported `requirements-dev.lock`
changes.

If a leased dev-tool PR falls behind its consumer default branch, Maint 71
reports `dev_tool_base_refresh_required` in either a dev-tool or unscoped pass
and dispatches one scoped Maint 52 producer run. If another Maint 52 run is
active, Maint 71 records the exact-head handoff in Maint 82's durable campaign
queue; its ten-minute scheduled continuation retries the dispatch after the
producer finishes. Failure to submit that handoff makes this reconciliation
fail visibly instead of silently losing the request. It must not call GitHub's
branch-update endpoint on that generated PR: a merge commit changes the whole
tree without reminting the recorded `desired_tree_hash`. Maint 52 regenerates
the delivery against the current base and records a fresh lease; then Maint 71
rechecks the new exact head, required checks, review threads, mergeability, and
seven-minute review window. An active producer run or missing API evidence is a
held handoff, not permission to overwrite the lease or merge the stale head.

For a tool-only `pyproject.toml` with no package declaration (as in Orchestrator),
Maint 52 leaves the file's tool configuration alone instead of adding
`[project.optional-dependencies]`. It still synchronizes any supported direct
requirements lockfile and managed pre-commit hooks that exist in that repo.
Package-shaped projects without `[project]`, including legacy `setup.py` or
`setup.cfg` consumers, remain an error requiring explicit integration rather
than a synthetic package declaration.

Managed pre-commit revisions are an explicit Maint 52 propagation surface. The
workflow passes `sync_dev_dependencies.py --pre-commit`; the script's default
check intentionally omits that surface so a Maint 68 workflow-template candidate
does not fail while the separate canonical dependency wave is still pending.

Dependabot should not be merged when it only bumps one of those shared tool pins
in `pyproject.toml`; route that change through the Workflows source pin update
path instead. Runtime dependency bumps remain normal Dependabot work.

Consumer alignment must not wait for unrelated PyPI freshness. The
`maint-52-sync-dev-versions.yml` workflow reports whether newer PyPI versions
exist, but continues syncing the canonical pins from Workflows. The
`maint-auto-update-pypi-versions.yml` workflow is the sole source-proposal lane:
it batches routine updates into one Monday UTC PR and accepts a reviewed manual
security override when needed. Its source proposal requires a classic
`OWNER_PR_PAT` with `repo` and `workflow` scopes to update
`.github/workflows/autofix-versions.env`; the default Actions token cannot push
that workflow-owned file. The workflow checks the token scope before editing
pins and fails closed if it is absent. Maint 50 reports freshness but never creates a
competing issue or proposal. Each consumer wave records the settled Workflows
source commit so propagation can be traced back to the validated source change.

### Renovate vs Maint 68 Path Ownership

Maint 68 overwrites every manifest-managed path in a consumer on each sync. If
that consumer's own Renovate opens a PR touching one of those paths, the change
is discarded on the next sync — consumer Renovate PRs against
`.github/workflows/agents-guard.yml` and
`.github/workflows/maint-76-claude-code-review.yml` (Inv-Man-Intake#838,
Manager-Database#1347) were both closed unmerged for exactly this reason.
The `anthropics/claude-code-action` digest in `maint-76-claude-code-review.yml`
is therefore updated in the Workflows consumer template, then delivered through
Maint 68 and Maint 71; a Renovate PR against a consumer copy is not the source
of that update. The pinned `v1` digest was refreshed to the tag's v1.0.233
commit in September 2026.

`renovate-presets/consumer-managed-paths.json` encodes the boundary. It is
**generated** from `.github/sync-manifest.yml` and the registered consumer list,
and `renovate-presets/fleet.json` extends it, so every consumer inherits it
without a re-sync. Ownership follows the same rules Maint 68 applies:

| Manifest state | Owner | Renovate |
| --- | --- | --- |
| No `sync_mode` (overwrite-managed) | Workflows | disabled in consumers |
| `sync_mode: create_only` | consumer, after first seed | enabled |
| `sync_mode: create_only` + repo in `overwrite_repos` | Workflows | disabled in that repo |
| Repo omitted by non-empty `include_repos` | consumer | enabled in that repo |
| Repo listed in `skip_repos` | consumer | enabled in that repo |

`include_repos` is a non-empty, validated owner/repo allowlist for one manifest
entry; omission means fleet-wide delivery. It may not contain duplicates or
overlap `skip_repos`. Maint 68 excludes ineligible targets from copying,
`sync_targets.txt` staging, and per-repository preview paths; plan/effect
fingerprints include the list. The compiler rejects a `requires` edge when its
required target is not delivered to every repository eligible for the dependent
entry, including future consumers of a fleet-wide entry. Before a plan can be
published, Maint 68 validates every `include_repos` value in the full compiled
plan against the registered consumer fleet, before source-delta filtering; phase
selection also checks the selected plan. The v1 plan schema retains optional
`include_repos` for compatibility with already published plans.

The preset matches consumer repositories only. `stranske/Workflows` is the sync
source, so its canonical files stay fully Renovate-managed and dependency bumps
still land here first, then reach consumers through Maint 68.

Note that `.github/workflows/autofix.yml` has no `sync_mode`, which makes it
overwrite-managed and therefore disabled for consumer Renovate. `ci.yml` and
`pr-00-gate.yml` are `create_only` and stay consumer-owned.

Regenerate after any manifest change:

```bash
python scripts/generate_consumer_renovate_ownership.py          # rewrite the preset
python scripts/generate_consumer_renovate_ownership.py --check  # fail on drift
```

`scripts/dev_check.sh` runs `--check` (and regenerates under `--fix`), and
`tests/scripts/test_generate_consumer_renovate_ownership.py` fails when a new
overwrite-managed path becomes visible to consumer Renovate.

### Monorepo Package Dependencies (`app-baseline-kit`)

Shared packages that live in this repo under `packages/` (currently
`app-baseline-kit`, which ships the `baseline_kit` import) are consumed by
other repos via an **unpinned** git URL in `pyproject.toml`:

```toml
"app-baseline-kit @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit"
```

That URL resolves to **Workflows `main` HEAD** at install time, which is the
intended `@main` consumer default. The hazard is the compiled lockfile: by
default `uv pip compile` freezes that dependency to whatever commit `main`
pointed at when the lock was generated, e.g.

```
app-baseline-kit @ git+https://github.com/stranske/Workflows.git@<sha>#subdirectory=packages/app-baseline-kit
```

CI installs the lock **and** the editable project together
(`uv pip install -r requirements.lock -e .[app,dev]`), so the same package is
declared twice — pinned (lock) and unpinned (project). They agree only while
`main` stays at `<sha>`. The next Workflows `main` advance makes the unpinned
URL resolve to a different commit, and uv aborts the install:

```
Requirements contain conflicting URLs for package `app-baseline-kit`
```

This silently breaks every downstream consumer's CI on an unrelated Workflows
merge (it broke trip-planner CI after the `py.typed` PR #2204). Refreshing the
lock fixes it only until the next advance, so it is not a stable answer.

**Convention: exclude monorepo `@main` packages from the lock.** In each
consuming repo's `pyproject.toml`, add:

```toml
[tool.uv.pip]
no-emit-package = ["app-baseline-kit"]
```

Then regenerate the lock with the repo's documented `uv pip compile` command.
The dependency drops out of `requirements.lock` (every other, versioned package
stays pinned), the editable project install resolves it from `@main`, and there
is no frozen SHA to keep refreshed — the conflict class is gone permanently. uv
reads `[tool.uv.pip]` from `pyproject.toml`, so the lock regen, the
`dependency-refresh.yml` automation, and the lockfile-freshness check all honor
it consistently with no extra wiring.

If the repo has a dependency-alignment test (`tests/test_dependency_version_alignment.py`,
which asserts every `pyproject.toml` dependency is pinned in `requirements.lock`),
make it read the same `no-emit-package` list and subtract those names from the
expected set — otherwise it fails on the now-absent package. Drive it from the
config, not a hardcoded name, so the two never drift:

```python
no_emit = {
    n.split(" @ ")[0].split("[")[0].strip().lower()
    for n in pyproject.get("tool", {}).get("uv", {}).get("pip", {}).get("no-emit-package", [])
}
declared -= no_emit
```

Applied to `trip-planner` and `Counter_Risk`; apply the same `pyproject.toml`,
lock-regen, and alignment-test changes whenever a new repo adopts
`app-baseline-kit` (or any future `packages/` member referenced by an unpinned
`@main` URL). These are per-repo `pyproject.toml`/`requirements.lock`/test
changes, not synced template files.

### Manual Sync Trigger

```bash
gh workflow run "Maint 68 Sync Consumer Repos" \
  --repo stranske/Workflows \
  -f phase=preview \
  -f repos="stranske/Travel-Plan-Permission" \
  -f dry_run=true
```

Omit `repos` for the normal configured canary run. A write run targeting any
non-canary must use `phase=promote` with Maint 71's exact-plan
`canary_evidence_json`; `phase=canary -f repos=<fleet>` is rejected. Reconcile
promoted PRs with Maint 71 using `active_sync_hash=delivery`.

### Drift Detection

Workflows runs **Health 68 Consumer Sync Drift Check** to detect divergence between
templates/manifest entries and the registered consumer repos. It runs daily and
after template/manifest/script changes.

Actionable `stale`, `blocked`, or `untracked_drift` states create or refresh one
transient alert. `converged` and `covered` states exit cleanly; the clean run
closes any open alert so a recovered incident cannot remain as a stale red issue.

- Files marked with `sync_mode: create_only` are excluded, except for repos
  listed in the entry's `overwrite_repos` override.
- The uploaded `consumer-sync-drift-report` artifact uses
  `workflows-consumer-sync-drift/v1` and includes safe
  `token_diagnostics` (`workflows-drift-token-selection/v1`) so permission or
  rate-limit failures are distinguishable from real file drift.
- **Workflows-Integration-Tests** is **not** a consumer repo and is validated by
  [Health 67 Integration Sync Check](../../.github/workflows/health-67-integration-sync-check.yml).

---

## Verification Checklist

After fixing a template bug:

- [ ] Fix applied to `templates/consumer-repo/`
- [ ] Fix applied to reusable workflow (if applicable)
- [ ] Sync workflow triggered or PR created for registered repos
- [ ] Unregistered repos identified and PRs created
- [ ] Bot review comments addressed in PRs
- [ ] CI passing in all affected repos

### Keepalive reservation credential recovery

The managed Agents 81 debounce step uses `SERVICE_BOT_PAT` before the default
workflow token because an empty authoritative PR-comment store requires one
fail-closed read of the legacy repository Actions variable. Verify the PAT's
identity and repository access without printing the token. It must be able to
read Actions variables and read/write PR comments as a trusted marker author.
If a run reports `authoritative-storage-unavailable` with HTTP 401/403, repair
that credential boundary and rerun the exact-head Gate followup. Do not treat
the denied legacy lookup as an empty record, delete state, or force-dispatch a
worker. A healthy retry either reserves the primary comment store or returns a
non-storage debounce reason.

---

## Version History

| Date | Change |
|------|--------|
| 2025-12-27 | Initial document based on trip-planner/Manager-Database setup learnings |

## Generated delivery ownership

For dependency and consumer-sync delivery, the campaign issue is durable and
each generated PR is a leased attempt. Maint 71 alone decides merge or close
disposition for `sync/workflows-*` and `deps/sync-dev-versions-*`; operators
and local watchers must consume its recorded owner/next-command handoff rather
than reimplementing that policy. See
[`SYNC_DEPENDENCY_CAMPAIGN.md`](SYNC_DEPENDENCY_CAMPAIGN.md).

## Vendored JavaScript security updates

The shared script dependency tree remains vendored: minimatch is a
`file:node_modules/minimatch` dependency, not a registry-install migration.
Use the upstream stable release version in vendored package and lock metadata;
adding `-vendored` changes semantic version ordering and can falsely retain a
patched-release advisory. Strip upstream development/lifecycle scripts, preserve
runtime exports and licenses, and update the source and consumer template trees
together before Maint 68/71 delivery. The current patched chain is minimatch
10.2.6, brace-expansion 5.0.12 and balanced-match 4.0.4. Brace-expansion requires
Node 20 or >=22; the current Actions runtime supports that floor, not Node 18.
