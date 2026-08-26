# Flexible Allocation & Reallocation — The Missing Logic

Companion to `allocation-reallocation-flow-design.md`. That doc covers *what* the endpoints are; this one covers the actual redistribution logic — what happens, step by step, when an admin doesn't just want "recalculate everyone proportionally," but wants to steer a budget change to one specific child while protecting the rest.

## 1. The problem, precisely

Today, one rule governs everything: **a child's ₹ = parent's ₹ × child's %.** % is stored; ₹ is derived. That's clean, but it has exactly one behaviour when a parent's ₹ changes: every child's % stays fixed, so every child's ₹ moves in lockstep with the parent, whether anyone wanted that or not.

**What's missing:** the admin should be able to say either of these, and have the system do the math:

- *"Tenant budget went up ₹20,000 — give all of it to Application A. Don't touch B or C's ₹."*
- *"I'm typing in a ₹ amount for this key directly, not a %— work out the % yourself."*
- *"Application A's budget just grew — put the entire increase into Key 1, leave Key 2 exactly where it is."*

Two separate capabilities are tangled up in that ask. Split them apart and the problem becomes tractable.

## 2. The two building blocks

### 2.1 Bidirectional input — edit by % or by ₹, admin's choice

Every place an allocation is set (create, or a row inside a bulk edit) accepts **either** `allocated_percentage` **or** `allocated_budget` — never both unless they already agree. Whichever one is given, the server computes the other against the *current* parent ₹:

```
given allocated_percentage  →  allocated_budget = parent_budget × pct / 100
given allocated_budget      →  allocated_percentage = budget / parent_budget × 100
given both, and they disagree (outside rounding tolerance)  →  422 PERCENTAGE_AMOUNT_MISMATCH
```

This alone solves "adjust the amount directly and have the percentage follow" for any *single* row, any time the parent isn't also changing in the same request.

### 2.2 Redistribution mode — the part that's actually missing

This is the real gap. It only matters at the moment a **parent's own ₹ changes** — because that's the only moment where every *other* child is forced to react one way or the other, whether the admin asked for it or not.

| Mode | Untouched children | When it applies |
|---|---|---|
| **`proportional`** *(default)* | % stays fixed, ₹ moves with the parent — **and this cascades all the way down**, through every level, automatically | The default — "the whole tree scales together," not just the level being edited |
| **`directed`** | ₹ stays fixed (**protected**), % is recomputed to whatever that now implies | New — "everyone I didn't mention keeps their ₹ exactly as it was" |

Explicitly-listed children in the same request always get exactly what's specified — the mode only decides what happens to the ones the admin *didn't* mention. The "cascades all the way down" half of `proportional` is what Section 4 step 3d actually implements, and it's the main thing this section revises from an earlier version of this doc, which stopped the automatic cascade at one level even for the default mode.

## 3. Where the mode applies — exactly one level at a time, never nested

`redistribution_mode` is a field on the two endpoints that change a *parent's* ₹ and therefore force a cascade:

- `PATCH .../budget` (Tenant → Applications) — a Tenant budget change forces every Application to react
- `PUT .../application-allocations` (Application → Keys) — whenever *this call* changes an Application's own ₹ (whether by editing its % directly, or by a Tenant-level cascade landing on it), that Application's Keys must react too

`PUT .../key-allocations` needs **no mode** — Keys have no children, so there's nothing to cascade to.

**Admin control stays one level deep — automatic cascading doesn't.** A Tenant-level call only ever accepts `application_overrides`; it has no way to specify anything about a particular Key, and never will. What happens to a Key is decided by the algorithm (Section 4, step 3d), not by the admin, in two different ways depending on mode:

- **`proportional` (default):** every Application moves with the Tenant, and every Application's own Keys move with it in turn — automatically, through as many levels as exist, in the same call. This is true whether the Tenant total went up or down.
- **`directed`:** only an *overridden* Application's own ₹ actually changes at all — protected ones are untouched, so there's nothing to cascade for them. For the overridden one: a **decrease** still auto-cascades to its Keys (mandatory — Section 5.3, Cases 4/5 — a shrinking Application can never leave its Keys stranded, choice or no choice). An **increase** does *not* auto-cascade — its Keys are left exactly as they were, so a second, separate call to the Application's own key-allocations endpoint is how an admin *directs* that growth to a specific Key (Section 5.2). This is the one place growth and shrinkage genuinely behave differently — see Section 6 for why.

## 4. The algorithm — identical shape at both edges

```
INPUT:  new_parent_amount
        mode              ("proportional" | "directed", default "proportional")
        overrides[]        used only when mode = "directed"
                            each = { child_id, allocated_percentage? | allocated_budget? }

1. LOCK the parent
2. FEASIBILITY — already-spent across the parent > new_parent_amount?  → reject BUDGET_OVERCOMMITTED
3. FOR EACH child under the parent:
     a. IF child is in overrides:
          resolved = convert(override, new_parent_amount)          -- explicit, wins outright
     b. ELIF mode == "proportional":
          resolved.pct = child.allocated_percentage                -- unchanged
          resolved.amt = new_parent_amount × resolved.pct / 100
     c. ELSE  (mode == "directed", not overridden):
          resolved.amt = child.allocated_budget                    -- PROTECTED, unchanged
          resolved.pct = resolved.amt / new_parent_amount × 100    -- recomputed, floats
     d. DECIDE whether to cascade into child's own children (only Applications have any — Keys are leaves):
          cascade = child has children AND ( mode == "proportional" OR resolved.amt < child's PREVIOUS amount )
          -- proportional mode always cascades, whichever direction the parent moved, because the whole
          --   tree is meant to scale together by default (Section 2.2).
          -- directed mode only cascades when resolved.amt is a DECREASE from before — mandatory, for
          --   correctness (Section 6) — never on a directed increase, which is left for a deliberate
          --   follow-up call so the admin can choose where it lands (Section 5.2).
          IF cascade:
              FOR EACH grandchild under child:
                  grandchild.newAmt = resolved.amt × grandchild.allocated_percentage / 100   -- always proportional, no overrides at this depth
                  IF grandchild.newAmt < grandchild's already-spent:
                      → reject ALLOCATION_BELOW_CONSUMED, name the grandchild and child together
                      -- only reachable when resolved.amt < child's previous amount — a cascade triggered
                      --   purely by growth can never fail this, so this path is unreachable on an increase.
              -- all grandchildren fit → they're part of this commit too (step 5), not a separate call
          ELSE:
              FLOOR CHECK: resolved.amt ≥ child's already-spent?  → else reject ALLOCATION_BELOW_CONSUMED, name the child
4. SIBLING CHECK: Σ resolved.amt (all children) ≤ new_parent_amount?  → else reject ALLOCATION_TOTAL_EXCEEDED
5. Commit every row whose resolved value actually changed (version += 1) — including any grandchildren re-fitted in step 3d, in the same transaction; push new ceilings to budget_usage
```

This is the *same* algorithm at Tenant→Application and at Application→Key — just called independently at each edge, per Section 3, **except** that step 3d now pulls the Application→Key cascade in automatically whenever it applies, rather than always deferring it to a second call.

**The algorithm is mostly direction-agnostic — increase and decrease share every step except the inner loop of 3d, which can only ever reject on a decrease.** An increase cascading into grandchildren (which now happens by default in `proportional` mode) can never fail — growing a parent can only ever make more room for its children, never less, so nothing downstream can be stranded by it; the inner floor check is unreachable in that direction. A decrease is the only direction where a parent shrinking can strand what depends on it — which is exactly what step 3d's cascade exists to prevent, automatically, without needing a second call, whether the shrink came from `proportional` or from an override. One behaviour is worth naming explicitly because it only shows up on a decrease:

**Protection is absolute — the system never auto-shrinks a protected child to make the numbers fit.** If cutting the parent's total, directing the whole cut at one child, and protecting everyone else turns out to be infeasible (Section 5.3 shows exactly this), the write is rejected outright. It does **not** fall back to quietly shrinking a protected sibling instead — that would silently violate the one guarantee `directed` mode makes. The admin has to either override more than one child, or use `proportional` mode instead.

## 5. Worked examples

### 5.1 Default proportional increase — cascades all the way to Keys

**Setup:** same as below — Tenant ₹1,00,000 → App A 50% (₹50,000, spent ₹40,000), App B 30%, App C 20%. App A's own Keys: Key 1 60% of A (₹30,000, spent ₹20,000), Key 2 40% of A (₹20,000, spent ₹8,000).

**Ask: raise the Tenant to ₹1,20,000. No overrides, no direction — just the default.**

```
PATCH /auth/tenants/{tenant_id}/budget
{
  "allocated_budget": 120000.00,
  "expected_version": 5
}
```

`redistribution_mode` omitted → defaults to `proportional`. Every Application's % stays fixed, ₹ moves with the parent — and because App A has Keys, step 3d cascades into them too, automatically, in this same call:

| Application | New ₹ | | Key (under App A) | New ₹ |
|---|---|---|---|---|
| A | 60,000 *(was 50,000)* | | 1 | 36,000 *(was 30,000)* |
| B | 36,000 *(was 30,000)* | | 2 | 24,000 *(was 20,000)* |
| C | 24,000 *(was 20,000)* | | | |

Every row committed in one call — App A's Keys never needed a separate request, because nothing here required an admin decision: growing can't strand anyone, so the default just scales the whole tree together. Contrast this with 5.2 below, where `directed` mode is used specifically to *stop* this from happening and put the admin in control instead.

### 5.2 Directed increase — the exact scenario from the brief

**Setup:** Tenant ₹1,00,000 → App A 50% (₹50,000, spent ₹40,000), App B 30% (₹30,000, spent ₹10,000), App C 20% (₹20,000, spent ₹5,000). App A's own keys: Key 1 60% of A (₹30,000, spent ₹20,000), Key 2 40% of A (₹20,000, spent ₹8,000).

**Ask: raise the Tenant to ₹1,20,000, give the entire +₹20,000 to App A only, then give App A's entire increase to Key 1 only.**

**Call 1 — Tenant level, directed at App A:**
```
PATCH /auth/tenants/{tenant_id}/budget
{
  "allocated_budget": 120000.00,
  "redistribution_mode": "directed",
  "application_overrides": [
    { "application_id": "A", "allocated_budget": 70000.00 }
  ],
  "expected_version": 5
}
```

| Application | Rule applied | New ₹ | New % | Floor check |
|---|---|---|---|---|
| A | overridden | 70,000 | 58.33% | 70,000 ≥ 40,000 ✓ |
| B | protected (unlisted, directed mode) | 30,000 *(unchanged)* | 25.00% *(was 30%)* | 30,000 ≥ 10,000 ✓ |
| C | protected (unlisted, directed mode) | 20,000 *(unchanged)* | 16.67% *(was 20%)* | 20,000 ≥ 5,000 ✓ |

Σ = 120,000 ≤ 120,000 ✓. B and C's **₹ never moved** — only their % shifted, purely as a side effect of the pie growing while they were protected. App A's Keys were **not** touched by this call — unlike 5.1, App A got here via an explicit override in `directed` mode, so its Keys are deliberately left alone; they still sum to ₹50,000 under an Application that now holds ₹70,000, and ₹20,000 sits as unallocated headroom on App A until the next call.

**Call 2 — Application level, directed at Key 1:**
```
PUT /auth/applications/{A}/key-allocations
{
  "redistribution_mode": "directed",
  "allocations": [
    { "api_key_id": 1, "allocated_budget": 50000.00 }
  ]
}
```

| Key | Rule applied | New ₹ | New % | Floor check |
|---|---|---|---|---|
| 1 | overridden | 50,000 | 71.43% | 50,000 ≥ 20,000 ✓ |
| 2 | protected (unlisted, directed mode) | 20,000 *(unchanged)* | 28.57% *(was 40%)* | 20,000 ≥ 8,000 ✓ |

Σ = 70,000 ≤ 70,000 (App A's now-larger ceiling) ✓. Key 2 never moved. The entire ₹20,000 increase has now flowed, by explicit direction, all the way from the Tenant down to one Key — in two calls, each individually simple, each individually safe.

### 5.3 Decrease — same mechanism, both outcomes

Starting fresh from the original setup: Tenant ₹1,00,000 → App A 50% (₹50,000, spent ₹40,000), App B 30% (₹30,000, spent ₹10,000), App C 20% (₹20,000, spent ₹5,000).

**Case 1 — feasible: cut the Tenant to ₹90,000, take the entire ₹10,000 cut from App C only.**

```
PATCH /auth/tenants/{tenant_id}/budget
{
  "allocated_budget": 90000.00,
  "redistribution_mode": "directed",
  "application_overrides": [
    { "application_id": "C", "allocated_budget": 10000.00 }
  ],
  "expected_version": 5
}
```

| Application | Rule applied | New ₹ | New % | Floor check |
|---|---|---|---|---|
| A | protected (unlisted, directed mode) | 50,000 *(unchanged)* | 55.56% *(was 50%)* | 50,000 ≥ 40,000 ✓ |
| B | protected (unlisted, directed mode) | 30,000 *(unchanged)* | 33.33% *(was 30%)* | 30,000 ≥ 10,000 ✓ |
| C | overridden | 10,000 | 11.11% | 10,000 ≥ 5,000 ✓ |

Σ = 90,000 ≤ 90,000 ✓. Same four rules as the increase case, same outcome shape: A and B's ₹ never moved, only their % floated because the pie shrank under them. **200 OK.**

**Case 2 — infeasible: cut the Tenant to ₹90,000, but try to take the entire ₹10,000 cut from App C only, when C has only ₹5,000 of headroom above its own spend.**

Same request shape, but App C is asked to absorb more than its floor allows:
```
"application_overrides": [
  { "application_id": "C", "allocated_budget": 8000.00 }   // only ₹12,000 cut from C, not ₹10,000... still fine on its own
]
```
Suppose instead the admin tries `"allocated_budget": 4000.00` for C — below its ₹5,000 already-spent:

| Application | Rule applied | New ₹ | Floor check |
|---|---|---|---|
| C | overridden | 4,000 | 4,000 ≥ 5,000 → **✗ fails** |

**422 `ALLOCATION_BELOW_CONSUMED`**, naming App C, exactly as the companion doc's existing floor check already does — no new error code needed. The write is rejected before A or B are even touched.

**Case 3 — infeasible a different way: protection itself doesn't leave room.** Cut the Tenant all the way to ₹70,000, direct the cut at App C only, protecting A and B:

A protected at 50,000 + B protected at 30,000 = 80,000 already **exceeds** the new Tenant total of 70,000 — before App C's override is even considered. This fails the **sibling check** (Section 4, step 4), not the floor check: `Σ resolved.amt > new_parent_amount`. This is the "protection is absolute" behaviour called out above — the system does not fall back to shrinking A or B to make room; it rejects and tells the admin why (Section 8 below adds a breakdown to this error for exactly this case).

**Case 4 — a cut that reaches App A auto-cascades to its Keys, in the same call.** App A currently has ₹50,000, and its Keys already sum to exactly ₹50,000 (Key 1 60% = ₹30,000, spent ₹20,000; Key 2 40% = ₹20,000, spent ₹8,000 — zero headroom of their own). Cut App A specifically to ₹40,000:

```
PATCH /auth/tenants/{tenant_id}/budget
{
  "allocated_budget": 90000.00,
  "redistribution_mode": "directed",
  "application_overrides": [
    { "application_id": "A", "allocated_budget": 40000.00 }
  ]
}
```

App A is shrinking (₹50,000 → ₹40,000) and has Keys, so step 3d fires automatically — each Key is re-fit proportionally against App A's *new* ₹40,000, using each Key's existing %:

| Key | % of App A (unchanged) | New ₹ | Floor check |
|---|---|---|---|
| 1 | 60% | 24,000 | 24,000 ≥ 20,000 spent ✓ |
| 2 | 40% | 16,000 | 16,000 ≥ 8,000 spent ✓ |

Both pass, Σ = ₹40,000 = App A's new ceiling exactly (proportional scaling always sums to the new total). **200 OK, one call** — App A → ₹40,000, Key 1 → ₹24,000, Key 2 → ₹16,000 all commit together. No second call needed, and no manual bottom-up ordering required — this is the case an earlier version of this doc got wrong by blocking outright instead of attempting the re-fit.

**Case 5 — the same cut, but deep enough that the auto-cascade genuinely can't fit.** Same starting point, but cut App A to ₹30,000 instead:

| Key | % of App A (unchanged) | New ₹ | Floor check |
|---|---|---|---|
| 1 | 60% | 18,000 | 18,000 ≥ 20,000 spent → **✗ fails** |
| 2 | 40% | 12,000 | 12,000 ≥ 8,000 spent ✓ |

Key 1 can't fit at its current 60% share of a ₹30,000 App A. **422 `ALLOCATION_BELOW_CONSUMED`**, naming *Key 1* specifically (not App A) — the message should say what it needs: at least ₹20,000, which at 60% implies App A needs to stay at ₹33,333.33 or above for the auto-cascade to succeed unaided. The admin's options: cut App A less deeply, or explicitly shrink Key 1's own % first (freeing Key 1's share so the remaining proportional split has room) via a separate, `directed` call to `PUT /auth/applications/{A}/key-allocations` — this is the one situation where a second call is still genuinely needed: not because the system defers the cascade, but because the automatic *proportional* re-fit isn't the split the admin actually wants, and only they can say who should absorb the shortfall.

## 6. When does the cascade defer to a second call, and why

The default (`proportional`) never defers, in either direction — Section 5.1 shows an increase committing all the way to Keys in one call, and Section 5.3 Cases 1 and 4 show the same for a decrease. Deferring to a second call only happens inside `directed` mode, and only for one specific combination: **an explicitly overridden Application that's growing.** Everything else — proportional in either direction, and a directed decrease — resolves in a single call. This wasn't always the design: an earlier version of this doc deferred *every* cascade to a second call regardless of mode or direction, which was unnecessary friction for the common case and, on a decrease, actively unsafe. Both are fixed here.

**Why `directed` growth is the one case that still defers.** When an admin explicitly overrides App A to a *larger* value, deferring its Keys is genuinely safe — App A holding ₹70,000 while its Keys still sum to ₹50,000 satisfies `Σ children ≤ parent` (Section 4, step 4), inert headroom, not a violation. Leaving it deferred here is deliberate, not lazy: it's what makes Section 5.2 possible at all — the gap that lets an admin *choose* which Key gets the increase in a follow-up call, rather than the system guessing on their behalf. This is the entire reason `directed` mode exists as distinct from `proportional`: if it auto-cascaded too, there would be no way to ask for admin-chosen placement at the Key level in the same breath as the Application level, and `directed` would do nothing that `proportional` doesn't already do.

**Why a decrease never defers, directed or not.** A cut that shrinks App A without touching its Keys would leave `Σ children > parent` sitting in the database, not just transiently mid-request — an actual invariant breach, not headroom. There's no admin choice to preserve here the way there is for growth (nobody benefits from being asked "who should get stranded?") — proportional re-fit is the only sane automatic response, so Section 4 step 3d just does it, checks it, and either commits everything together or refuses everything together, regardless of which mode triggered the shrink. See Section 5.3, Case 4 (fits automatically) and Case 5 (doesn't, and why refusing is still the right outcome — an automatic re-fit that silently violates a Key's own spend would be worse than refusing outright).

**The shape of the rule, restated:** deferring is only ever about preserving a *choice* the admin might want to make. Growth via `proportional` has no choice to make (there's only one sane default, and it now runs automatically). Growth via `directed` override has a real choice (which Key gets it), so it waits. Shrinkage never has a choice worth waiting for (something has to give, and proportional re-fit is the least-surprising default) — so it never waits, and fails loudly in one call if it can't be resolved automatically.

A single call still isn't guaranteed to succeed just because it's automatic — Section 5.3's Case 5 is exactly the case where the proportional re-fit itself fails, and a second, `directed` call to the Key level remains the right tool when the admin needs to *choose* who absorbs a shortfall the automatic split can't resolve on its own.

## 7. Rules that don't change

Everything from the companion doc still applies, unmodified, regardless of mode **and regardless of whether the parent's total is going up or down** — Section 5.3 exercises all four against a decrease:

- **Floor check** — no resolved ₹, overridden or protected, can ever fall below what's already spent. For a shrinking Application specifically, this check happens one level lower than usual: instead of comparing the Application's own new ₹ against a number, Section 4 step 3d re-fits its Keys proportionally against that new ₹ and checks *them* against their own spend — so the real constraint is "can the Keys still fit," not "does the Application's own figure look big enough." Protected children (unchanged ₹) never trigger this, since they're not shrinking; only overridden or proportionally-moved children can be.
- **Sibling check** — Σ resolved ₹ ≤ parent ₹, always, checked after resolving every child, not before.
- **Lock** — one lock per parent, held for the full resolve-and-write, exactly as already designed.
- **Version** — every row that actually changes still bumps its `version`; `expected_version` conflicts still surface as `409 VERSION_CONFLICT`.
- **Partial-list semantics still hold in `proportional` mode** — omitting a child there means "leave its % alone," which is exactly what it already meant. `directed` mode is what changes the meaning of "omitted" to "leave its ₹ alone" instead.

## 8. API contract — delta over the companion doc

Two fields added, both optional, both defaulting to today's behaviour so nothing existing breaks:

```json
{
  "allocated_budget": 120000.00,           // number — unchanged from companion doc
  "expected_version": 5,                   // integer — unchanged
  "redistribution_mode": "directed",       // string, optional — "proportional" (default) | "directed" — NEW
  "application_overrides": [               // array, optional, used only when mode = "directed" — NEW
    {
      "application_id": "3fa8b8b0-...",    // string (uuid), required
      "allocated_percentage": 58.33,       // number — exactly one of these two
      "allocated_budget": 70000.00         // number — exactly one of these two
    }
  ]
}
```

Same shape on `PUT .../application-allocations`, with `key_overrides` in place of `application_overrides`, applying to that call's mandatory Application→Key cascade.

**New error:**

| Status | Code | Meaning |
|---|---|---|
| 422 | `PERCENTAGE_AMOUNT_MISMATCH` | both `allocated_percentage` and `allocated_budget` given for the same row, and they don't agree |

**`ALLOCATION_TOTAL_EXCEEDED` gets a breakdown when `redistribution_mode` is `"directed"`** — Section 5.3's Case 3 is otherwise hard to diagnose from a bare "doesn't add up" message, since the shortfall comes from *protected* siblings the admin never mentioned:
```json
{
  "detail": {
    "code": "ALLOCATION_TOTAL_EXCEEDED",
    "message": "Resolved total ₹80,000.00 (protected) already exceeds the new budget of ₹70,000.00, before overrides",
    "timestamp": 1785060000.123,
    "details": "new_parent_amount=70000.00 protected_total=80000.00 protected=[application_id=A amount=50000.00, application_id=B amount=30000.00] overridden=[application_id=C amount=unresolved]"
  }
}
```

## 9. One further option worth naming, not building yet

A **persisted** per-child preference (`pin_mode: "percentage" | "amount"` stored on the row itself) would let an admin mark "always protect this Application's ₹" once, so every *future* Tenant-level change treats it as protected by default without needing `directed` mode and an explicit override every time. Left out of this design because the two-call, per-request approach above already covers everything in the brief — this is a genuine enhancement if "always protect App X" turns out to be a recurring admin request, not a gap in the current ask.
