# UX Design: Mise

> Information architecture, navigation, and **low-fi wireframes** for the product
> (web + Android). Structure first — **deliberately no visual styling here**;
> palette/type/components come in the design-system pass. The decision that
> shapes the build: a **shared design-token package** consumed by web (Tailwind)
> and mobile (NativeWind), so both platforms render the same system.
>
> Status: design, for review. Supersedes the current single-page dev harness.

## Table of Contents
1. [Principles](#1-principles)
2. [Information Architecture](#2-information-architecture)
3. [Navigation Model](#3-navigation-model)
4. [Screens & Wireframes](#4-screens--wireframes)
5. [Cross-cutting UX Conventions](#5-cross-cutting-ux-conventions)
6. [Component Inventory (for the kit)](#6-component-inventory-for-the-kit)
7. [Build Plan](#7-build-plan)
8. [Theming & Recipe Images](#8-theming--recipe-images)

---

## 1. Principles

- **The dashboard is the home.** An at-a-glance, **action-oriented** overview of
  the account state — tonight's meal, week progress, shopping status, budget, and
  ingredient alerts — every card answers a question *and* offers the next step.
  The full plan is one tap away.
- **Every async action shows its state.** Loading, empty, and error are designed,
  not afterthoughts. No raw error dumps (the harness's failing).
- **One primary action per screen.** The user always knows the next step.
- **Fast feedback.** Optimistic updates for cheap actions (check off, cook);
  progress for slow ones (generation, via Realtime).
- **Same system on web + mobile.** Layout adapts; the design language doesn't.

---

## 2. Information Architecture

Five top-level surfaces. (v1 is single-household; the household switcher is built
into the structure but hidden until multi-household.)

```
Mise
├── Dashboard       ← HOME: tonight's meal, week summary, shopping status, budget, alerts, quick actions
├── Plan            ← the full active week; generate/regenerate; per-meal actions
│   └── Recipe      ← full recipe detail (ingredients, steps, swap/modify/cook)
├── Shopping        ← the active plan's list: items, prices vs budget, check off, purchase
├── Pantry          ← inventory: add (manual / barcode), edit, what's running low
├── Settings        ← (in header) household, dietary prefs, store/region, pricing tier, account
│   └── Onboarding  ← first-run: create household → dietary → optional pantry seed
└── Recipes         ← (v1.5) saved / past recipes, search  [deferred — see Build Plan]
```

The four primary surfaces are **Dashboard · Plan · Shopping · Pantry**. **Settings**
and the household switcher live in the header (not a tab). Auth sits outside the shell.

---

## 3. Navigation Model

- **Mobile:** bottom tab bar — **Home · Plan · Shopping · Pantry** (4 tabs; the
  practical max). Recipe detail and the Generate sheet push/modal over the stack.
- **Web:** the same four as a persistent left sidebar (collapses to a top bar on
  narrow widths). Content area on the right.
- **Settings** is reached from the **account/avatar menu in the header**, not a
  tab — it's infrequent. The **household chip** (top header) shows the current
  household and becomes a switcher in multi-household (v2).
- **State badges** in nav: Shopping shows an item count; Pantry can show a
  "running low" dot.

```
WEB SHELL                                   MOBILE SHELL
┌────────────┬───────────────────────────┐  ┌───────────────────────────┐
│ ◆ Mise     │  [household ▾]    [account ▾]  │ Home      [household][◉] │
│            │                           │  │                           │
│ ▸ Home     │                           │  │   (screen content)        │
│ ▸ Plan     │      (screen content)     │  │                           │
│ ▸ Shopping⁵│                           │  │                           │
│ ▸ Pantry • │                           │  ├───────────────────────────┤
│            │      account ▾ → Settings │  │ Home  Plan  Shop⁵  Pantry•│
└────────────┴───────────────────────────┘  └───────────────────────────┘
```
(`[◉]` = account/avatar → Settings.)

---

## 4. Screens & Wireframes

Low-fi: boxes and labels only. `[Button]`, `( )` field, `▾` menu, `□` checkbox.

### 4.1 Auth

```
┌──────────────────────────────┐
│            Mise              │
│   Plan. Shop. Cook. Repeat.  │
│                              │
│  Email   (______________)    │
│  Password(______________)    │
│         [ Sign in ]          │
│   New here?  [ Create account ]
└──────────────────────────────┘
```
- Sign-up and sign-in on one screen (local stack auto-confirms; prod adds verify).
- Errors inline above the fields.

### 4.2 Onboarding (first run, no household yet)

```
Step 1 of 3 ─ Your kitchen
┌───────────────────────────────────────┐
│  Name this household                   │
│  ( Home________________ )              │
│                          [ Continue ]  │
└───────────────────────────────────────┘
Step 2 ─ Dietary  → flags (chips: veg, vegan, GF, dairy-free, nut allergy…)
                    + "Anything you avoid?" (free text)
Step 3 ─ Pantry (optional)  → "Add a few staples, or skip"  [ Skip ] [ Add ]
                    → lands on Plan (empty state)
```
- Captures the dietary prefs the generator needs **before** the first plan, so the
  first result is already on-target. Skippable but encouraged.

### 4.3 Dashboard — HOME (overview)

Action-oriented cards. Each states the answer and offers the next step.

```
┌──────────────────────────────────────────────────────────┐
│  Good evening, Brian                   [household ▾] [◉]  │
│                                                          │
│  ┌─ Tonight ────────────────┐ ┌─ This week ────────────┐ │
│  │ 🍛 Chana Masala          │ │ Jun 10–16              │ │
│  │ Dinner · 2 servings      │ │ 5 dinners · 3 cooked   │ │
│  │ [ Cook ]   [ View ]      │ │ [ View plan → ]        │ │
│  └──────────────────────────┘ └────────────────────────┘ │
│  ┌─ Shopping ───────────────┐ ┌─ Budget ───────────────┐ │
│  │ Ready · 12 items · $48   │ │ $48 of $60             │ │
│  │ not purchased            │ │ ▓▓▓▓▓▓▓▓░░  ✓ under     │ │
│  │ [ View list → ]          │ └────────────────────────┘ │
│  └──────────────────────────┘                            │
│  ┌─ Heads up ───────────────────────────────────────────┐│
│  │ ⚠ Low: rice, yellow onion                            ││
│  │ ⚠ Fri's Tacos needs avocado — not in your pantry     ││
│  │ ⏳ Use soon (est.): spinach, mozzarella               ││
│  │ [ Add to pantry ]  [ Build shopping list ]           ││
│  └──────────────────────────────────────────────────────┘│
│  Quick: [ + Generate plan ]  [ + Pantry ]  [ Shopping ]  │
└──────────────────────────────────────────────────────────┘
```

Cards (v1): **Tonight/Up-next** (today's meals + one-tap Cook), **This week**
(plan summary + cook progress), **Shopping** (status → list or "build one"),
**Budget** (est vs budget meter), **Heads up** (ingredient alerts, below), and
**Quick actions**. Possible later cards: "recently cooked", a "try this"
suggestion. **Empty state** (new user, no plan): a prominent "Generate your first
plan" with a nudge to finish pantry/dietary setup.

**Ingredient alerts** (the "Heads up" card) — three kinds, by data availability:
- **Running low** — pantry items below a small threshold quantity. *(Have the data.)*
- **Needed, not stocked** — ingredients the upcoming meals require that aren't in
  the pantry. Ties the surfaces together; drives the shopping list. *(Have the data.)*
- **Use soon (estimated)** — a *rough* shelf-life estimate, **not a real expiry**.
  No external API gives reliable expiry (Open Food Facts / Open Prices / Spoonacular
  don't carry shelf life). We approximate from the ingredient **category** +
  `pantry_items.added_at` using a small shelf-life table (seedable from USDA
  FoodKeeper category defaults), assuming default storage. Always labeled "est."
  A precise version (storage location, user-set dates, real best-before) is a later,
  optional enhancement — see §5/Build Plan. *(Lightweight; can ship in v1.)*

### 4.4 Plan — empty state (reached via the Plan tab; dashboard is home)

```
┌───────────────────────────────────────────────────────┐
│  This week                                  [household ▾]│
│                                                         │
│        🍽  No plan yet                                  │
│        Generate a meal plan to get started.            │
│                                                         │
│                 [  Generate a plan  ]                   │
└───────────────────────────────────────────────────────┘
```
- One obvious primary action. (Replaces the harness's bare "— select —".)

### 4.5 Generate (sheet / modal over Plan)

```
┌──────────────  New plan  ──────────────┐
│  Dates    ( Jun 10 ) → ( Jun 16 )       │
│  Meals     □ Breakfast □ Lunch ■ Dinner □ Snack
│  Servings  ( 2 )                        │
│  Budget    ( $60 )                      │
│  Dietary   [veg ✕] [+ add]   Avoid (___)│  ← prefilled from Settings
│                                         │
│                  [ Generate ]           │
└─────────────────────────────────────────┘
        ↓ (Realtime progress)
┌─────────────────────────────────────────┐
│   ⏳ Generating your plan…  (Running)    │
│   ▓▓▓▓▓▓▓░░░  day 2 of 3                  │  (progress from job status)
└─────────────────────────────────────────┘
```
- Dietary pre-filled from Settings; editable per-plan.
- Non-blocking: the sheet shows live progress, then dismisses to the filled Plan.

### 4.6 Plan — filled (the full week)

```
┌───────────────────────────────────────────────────────┐
│  This week · Jun 10–16            [⟳ Regenerate] [household ▾]
│  Budget $60 · est. $48  ✓ under                         │
│                                                         │
│  WED 10 ───────────────────────────────────────────────│
│   🍝 Dinner · Creamy Tomato Pasta · 2 servings          │
│      [ Cook ] [ Swap ] [ Modify ]            (tap → detail)
│  THU 11 ───────────────────────────────────────────────│
│   🌮 Dinner · Black Bean Tacos · ✓ cooked               │
│  FRI 12 ───────────────────────────────────────────────│
│   🍛 Dinner · Chana Masala · 2 servings                 │
│      [ Cook ] [ Swap ] [ Modify ]                       │
│                                                         │
│              [ Build shopping list → ]                  │
└───────────────────────────────────────────────────────┘
```
- Day-grouped cards (web can widen to a 7-col week grid on large screens; mobile
  stays a vertical list — same data, responsive layout).
- Per-meal actions inline; whole card taps into the recipe.
- Budget line is always visible with an over/under indicator.
- Cooked meals show a clear done state (and the pantry quietly updates).

### 4.7 Recipe detail

```
┌───────────────────────────────────────────────────────┐
│  ‹ Back                                                 │
│  Chana Masala                          [Italian][vegan] │
│  Prep 10m · Cook 30m · Serves 2                         │
│  (image placeholder — see design-system pass)           │
│                                                         │
│  Ingredients                Steps                       │
│  • 2 lb yellow onion        1. Sauté onion & garlic…    │
│  • 2 can chickpeas          2. Add spices, simmer…      │
│  • …                        3. …                        │
│                                                         │
│  [ Cook ]   [ Swap ]   [ Modify… ]                      │
└───────────────────────────────────────────────────────┘
```
- "Modify…" opens a small prompt ("spicier", "make it vegan") → iterate.
- "Swap" replaces with a different dish for the slot.

### 4.8 Shopping

```
┌───────────────────────────────────────────────────────┐
│  Shopping · Jun 10–16                  status: draft    │
│  Est. total $48 · Budget $60   ✓ under                  │
│  [ Estimate remaining prices ]   (shown if any unpriced)│
│                                                         │
│  Produce ───────────────────────────────────────────── │
│   □ Yellow onion        3 lb            $2.70           │
│   □ Garlic              3 clove         $0.20           │
│  Pantry ───────────────────────────────────────────────│
│   □ Rice                2 lb            — (no price)    │
│  …                                                      │
│                                                         │
│              [ Mark purchased → restock pantry ]        │
└───────────────────────────────────────────────────────┘
```
- Items **grouped by aisle/category** (we already store `category`).
- Per-item checkbox for in-store use; price shown, "—" when unpriced.
- "Mark purchased" confirms, then restocks the pantry and shows a success toast.

### 4.9 Pantry

```
┌───────────────────────────────────────────────────────┐
│  Pantry                                                 │
│  Add: ( ingredient______ ) ( qty ) ( unit ▾ ) [ Add ]  │
│       or  [ 📷 Scan barcode ]  ( 30176… ) [ Add ]       │
│                                                         │
│   3 lb   Yellow onion                         [ edit ]  │
│   2 lb   Rice                                 [ edit ]  │
│   1 unit Nutella                              [ edit ]  │
│   (running low items flagged)                           │
└───────────────────────────────────────────────────────┘
```
- Manual add + barcode (camera on mobile; typed code on web).
- Inline quantity edit; "running low" affordance feeds future shopping nudges.

### 4.10 Settings (from the header account menu)

```
┌───────────────────────────────────────────────────────┐
│  Settings                                               │
│  Theme       ( Warm Editorial ▾ )   ○ Light  ● …        │  ← theme switcher
│  Household   ( Home________ )                           │
│  Dietary     [veg ✕] [+ add]    Avoid (no mushrooms___) │
│  Store       ( HEB____ )   Region ( Texas )             │
│  Pricing     Free (USDA + AI)        [ Upgrade ]        │  ← tier surface
│  Account     brian@…             [ Sign out ]           │
└───────────────────────────────────────────────────────┘
```
- **Theme switcher** (see §8) — default Warm Editorial; users pick others.
- Dietary lives here (defaults every generation) and is overridable per-plan.
- Store/region feed pricing; the pricing tier is surfaced for the eventual upgrade.

---

## 5. Cross-cutting UX Conventions

Codified once, applied everywhere (this is the "ease of use is structural" part):

- **States:** every list/screen defines **loading** (skeleton), **empty** (icon +
  one-line explainer + primary action), and **error** (friendly message + retry) —
  never a raw exception string.
- **Feedback:** optimistic updates for check-off / cook; a **toast** for completed
  mutations (purchased, added, swapped); inline validation on forms.
- **Slow work:** generation is non-blocking with live progress (Realtime) and is
  cancelable; the UI never just "hangs."
- **Destructive / irreversible:** confirm before purchase and before regenerate
  (which discards the current plan).
- **Navigation:** back always works; the active tab is obvious; deep links resolve
  (a recipe URL opens the recipe).
- **Accessibility:** labeled controls, visible focus, sufficient contrast, hit
  targets ≥ 44px on mobile, respects reduced-motion.
- **Responsive:** web is usable 360px→wide; the plan view reflows list↔grid.
- **Empty-but-blocked:** if dietary/household isn't set, guide to set it rather
  than failing a generation.

---

## 6. Component Inventory (for the kit)

The shared kit we'll build to the tokens (web first, mirrored on mobile):

- **Primitives:** Button (primary/secondary/ghost/destructive), IconButton, Input,
  Select, Checkbox, Chip/Tag, Badge, Card, ListRow, Divider, Avatar.
- **Feedback:** Spinner, Skeleton, Toast, InlineError, EmptyState, ProgressBar.
- **Layout:** AppShell (sidebar/tabbar), Header, Sheet/Modal, Section.
- **Domain:** MealCard, RecipeHeader, IngredientList, ShoppingRow, PantryRow,
  BudgetMeter, CuisineTag, GenerateForm.

---

## 7. Build Plan

Design-led, incremental, each step verifiable:

1. ✅ **IA + wireframes** approved (this doc).
2. ✅ **Visual direction chosen:** **Warm Editorial (A)** as the default, with
   user-selectable **themes** enabled from the start; recipe **images via Pexels**
   (see §8). Mockups in `docs/mockups/`.
3. **Design tokens** package, **theme-aware** (`packages/design` or under
   `@mise/shared`): color, type, spacing, radius, shadow, motion — defined per
   theme, consumed by web (Tailwind/CSS vars) + mobile (NativeWind). Ship
   **Warm Editorial** as the default theme.
4. **Component kit** on web, built to tokens (theme-agnostic).
5. **Rebuild web screens** on the kit, screen by screen (Dashboard → Plan →
   Shopping → Pantry → Settings → Recipe), replacing the harness. Keep the test
   hooks + `data-testid`. Add the **theme switcher** + **recipe images**.
6. **Android (Expo)** starts on the same tokens/kit via NativeWind — on-brand from
   the first screen, not catching up.

Dashboard alerts in v1: **running low** + **needed-not-stocked** (have the data) and
a **lightweight "use soon" estimate** (category shelf-life + `added_at`; needs a small
seedable shelf-life table — bounded). Deferred: **Recipes** browse/search (v1.5),
**precise expiry** (storage location, user-set/scanned best-before dates),
multi-household switcher (v2), AI-generated exact recipe images (paid upgrade).

---

## 8. Theming & Recipe Images

### Theming (decided)
- **Default:** **Warm Editorial** (direction A — cream, Fraunces serif, terracotta).
- **User-selectable themes** from day one: tokens are defined **per theme**;
  switching themes swaps the active token set (a `data-theme` attribute / context
  on web, the same tokens via NativeWind on mobile) — **no component changes**.
  Likely starter set: Warm Editorial (default), a **Dark** theme (direction C —
  charcoal + gold), and **Modern Fresh** (direction B). Light/dark are just themes.
- **Where it lives:** a theme switcher in **Settings**; the choice persists on the
  user profile. Build the token layer theme-aware up front so themes aren't a
  retrofit.

### Recipe images (decided — cheapest good source)
- **Source: Pexels API** (free, generous quota, no attribution requirement) — the
  cheapest path that still looks premium. Search by recipe **title** → fall back to
  **cuisine** → fall back to a tasteful category placeholder.
- **Representative, not exact:** a stock photo of *the kind of dish*, not a render
  of our specific recipe. Acceptable for the cheapest tier; exact **AI-generated**
  images are a paid upgrade later.
- **Persisted:** store the chosen URL on the recipe (small `recipes.image_url`
  migration) so it's stable and we don't re-query Pexels each view.
- **Needs** a free `PEXELS_API_KEY` (like the other integrations); degrades to the
  placeholder when absent or no good match.
