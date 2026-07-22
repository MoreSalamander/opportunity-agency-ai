# Opportunity [Agency AI]

**An agent organization of agent organizations.** Where a single Hunter AI (like
[Crypto Hunter AI](https://github.com/MoreSalamander/crypto-hunter)) is a multi-agent
organization that hunts opportunity in one domain, Opportunity [Agency AI] is the layer
above them: it reads across every independent Hunter engine and decides how *this
user's* finite time and money should actually be spent today, across every domain at once.

Built on [Veritas](https://github.com/MoreSalamander/veritas) — the deterministic-scaffold
framework every Hunter engine and Opportunity itself are made of. Veritas is the tool
stack, not a product; Hunter engines and Opportunity are what get built with it.

## Constitution

1. **Never holds keys. Never signs, executes, or submits anything on the user's behalf.**
   Every layer, every engine, every level — information system only.
2. **The trust boundary is deterministic, at every level.** Inside a Hunter engine, one
   fail-closed gate decides what's verified. At the Opportunity level, one deterministic
   allocation decision decides what reaches the user — arbitration, not another opinion.
3. **Every trusted claim carries provenance**, traceable all the way down to the Hunter
   engine and gate check that produced it.
4. **Presents intelligence, not advice.** Opportunity ranks and arbitrates what's real;
   the user decides what to act on. This holds harder here than in any single engine,
   since the domains span financial, legal, and personal-risk territory at once.

## Architecture

**Three layers:**
- **Veritas** — the deterministic-scaffold framework (org registry, hub, propose → gate →
  debate mechanics). Infrastructure, not a product.
- **Hunter engines** — independent org instances built on Veritas, one per domain
  (Crypto Hunter AI, Collectible Hunter AI, Free Money Hunter AI, ...). Each owns its own
  scouts (unconstrained proposal zone), its own deterministic gate, its own debate layer,
  and its own DataHub.
- **Opportunity** — reads every Hunter engine's verified queue through read-only bridges
  (the same external-org pattern Veritas already uses), and runs its own gather → weigh →
  learn agents on top: gathering verified opportunities across domains, weighing them
  against the user's real budget of time, money, risk tolerance, and observed tendencies,
  and learning from outcomes over time. Has its own DataHub, keyed to its own record type
  (an allocation/decision record referencing opportunities across engines) — same
  discipline as every Hunter engine, one level up.

**Two governing principles, true at every layer:**
- **The arc is the validation, not every step.** Scouts and debaters operate unconstrained;
  the gate fires at discrete points (once on filing, again only if new evidence appears),
  not continuously. This holds inside a Hunter engine and at the Opportunity level.
- **What's gate-hard vs. debate-argued is decided per domain**, by how deterministically
  checkable a given risk actually is. Crypto's scam-safety is gate-hard (domain age, scam
  lists, contract checks). Collectibles' arbitrage math is gate-hard; its authenticity risk
  is debate-argued. Every new engine makes this call for its own domain — there is no
  universal split.

**Two kinds of debate:**
- **Within an engine** — Advocate/Skeptic/Strategist contest one opportunity's own merit.
  Never changes the verdict; only new evidence can trigger a re-gate.
- **Across engines, at the Opportunity level** — not a debate about truth (each engine's
  gate already settled that); a debate about *priority*. Independently-legitimate
  opportunities from different domains compete for the same finite user time and money.

## Hunter engines

| Engine | Status |
|---|---|
| Crypto Hunter AI | Shipped — the reference implementation |
| Collectible Hunter AI | Building |
| Free Money / Unclaimed-Benefits Hunter AI | Building |
| Grant Hunter AI, Scholarship Hunter AI | Planned — cheap to add once Opportunity exists |
| Vehicle, Developer/Bounty, Government Opportunity Hunter AI | Planned |
| Stock Hunter AI | Planned — advice-liability posture needs its own care |
| Property Hunter AI (foreclosures) | Flagship vision, deliberately deferred — real data-access headwinds (MLS licensing, county-level fragmentation) |
| Startup/Equity Hunter AI | Under consideration — risk too high-variance to gate meaningfully as designed today |

## Status

Proof-of-concept phase: Collectible Hunter AI and Free Money Hunter AI are being built
first as maximally-different inputs (comp-arbitrage gate vs. registry-lookup gate), then
Opportunity's gather/weigh/learn layer gets built as its own dedicated phase against all
three engines (crypto + the two new ones). Remaining Hunter engines are added after —
they're cheap once the pattern's proven twice more.

---

Built by MoreSalamander — "built by the engineer learning how to build it."
