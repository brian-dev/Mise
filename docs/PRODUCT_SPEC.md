# Product Specification: Mise

> *Mise* — from *mise en place* ("everything in its place"). A premium meal planning experience.

> **Status:** Planning Phase  
> **Last Updated:** 2026-06-03  
> **Version:** 0.1 (Pre-development)

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Target Users](#2-target-users)
3. [Core Features](#3-core-features)
4. [Data Model](#4-data-model)
5. [Tech Stack](#5-tech-stack)
6. [Monetization Strategy](#6-monetization-strategy)
7. [Version Roadmap](#7-version-roadmap)
8. [Open Questions & Future Considerations](#8-open-questions--future-considerations)

---

## 1. Product Vision

A cross-platform meal planning application that helps individuals and families plan meals, generate AI-driven recipes, manage grocery shopping within a budget, and track pantry inventory — forming a closed loop from planning to cooking.

**The core loop:**
1. Generate a meal plan for a time period using AI
2. Build a shopping list from the meal plan, adjusted for what's already in the pantry and constrained by a budget
3. Shop and update the pantry
4. Cook meals and automatically (or manually) deplete pantry inventory
5. Feed pantry state back into the next meal plan generation

**Origin / Problem Statement:**  
The app is born from the real experience of shopping for a family — trying to stick to a budget while wanting to cook interesting, varied meals — and the recurring problems of buying duplicate ingredients, forgetting what's on hand, buying ingredients that never get used, and lacking a system to connect planning, shopping, and cooking into one workflow. AI chat interactions naturally surfaced novel recipe ideas and a workflow desire that this app formalizes.

---

## 2. Target Users

### Primary Users
- Individuals cooking for themselves
- Parents cooking for a family
- Anyone cooking at home who wants structure around meal planning and grocery budgeting

### Extended Users (enabled by multi-household feature)
- Parents managing meal plans for children at college
- Caregivers managing meals for elderly parents or relatives
- Anyone managing nutrition/cooking for multiple households

### Platform
- **Web app** and **mobile app** with full feature parity — no features exclusive to either platform.

---

## 3. Core Features

### 3.1 Household & User Management

- A **User** can own or be a member of one or more **Households**
- Each Household represents a physical location (e.g., "Home", "Jake's College Apt")
- Households are independent — each has its own pantry, meal plans, shopping lists, store preferences, and regional pricing
- **Roles within a household:**
  - `owner` — full management, can invite members, manage billing
  - `member` — can interact (mark meals cooked, check off shopping items, view plans)
- Users switch between their households via a selector in the app
- **Dietary preferences** are set at the User level (personal) and optionally overridden at the Household level (e.g., the household is nut-free)
- Multi-household access is a paid tier feature (see Monetization)

---

### 3.2 Meal Planning

- User selects a **date range** and the system generates a complete meal plan using AI
- Meal types supported: breakfast, lunch, dinner, snack
- The AI considers:
  - User/household dietary preferences and restrictions
  - Current pantry inventory (use what you have first)
  - Cuisine preferences or variety targets
  - Number of servings (household size)
- Once generated, the user can **override any individual day or meal**:
  - Change the recipe
  - Change the cuisine
  - Change the meal type or timing within the plan
- **Meal plan statuses:** `draft` → `active` → `closed`
  - Only one active meal plan per household at a time
  - A plan auto-closes after its last day passes, or the user closes it manually
  - Closed plans are retained for history and tracking purposes

---

### 3.3 Recipes

- **AI-generated recipes** are the primary source (LLM-first approach)
- Recipes exist in a **shared pool** (available to all users) or as **user-specific recipes** (created or modified by a user)
- When a user modifies a shared recipe, a copy is created under their ownership
- Each recipe stores the `source_prompt` used to generate it — enabling regeneration, variation, and iteration
- Recipe attributes: title, description, cuisine tags, prep time, cook time, default servings, instructions, ingredients list
- Ingredients in a recipe can be marked as optional

---

### 3.4 Pantry Inventory

- Each household has a pantry tracking ingredient quantities on hand
- **Three ways to add items to the pantry:**
  1. **Manual entry** — user types in item, quantity, unit
  2. **Barcode scanning** — scan a product (via Expo Camera + Open Food Facts API)
  3. **Recipe-driven** — when a shopping list is marked as purchased, those items are added to the pantry automatically
- On first use with no pantry: prompt the user to either create a pantry from their first shopping list or enter items manually
- **Expiry tracking:** not included in v1, planned for a future version
- **Pantry depletion** (removing items as meals are cooked):
  - User chooses their preferred mode per household: `auto` or `manual`
  - **Auto:** when a meal is marked as cooked, ingredients are deducted automatically
  - **Manual:** user explicitly removes items
  - **Partial use handling:** when a recipe uses a partial quantity of an ingredient (e.g., half a can of tomatoes), the system prompts the user at cook time to confirm the quantity used before deducting

**Depletion math:**
```
quantity_deducted = RecipeIngredient.quantity × (Meal.servings ÷ Recipe.default_servings)
```

---

### 3.5 Shopping Lists

- A shopping list is generated from the active meal plan
- Before calculating quantities, the system subtracts what the household already has in the pantry — you only buy what you don't have
- Each item shows:
  - Ingredient name and quantity needed
  - Estimated price
  - Checkbox for in-store use
  - Whether it came from a recipe or was manually added
- **Budget:** the budget covers the entire shopping trip for the meal plan period. The system estimates the total and warns the user if the list exceeds their budget.
- Users can add items to the shopping list manually (beyond what recipes require)
- Shopping list statuses: `draft` → `finalized` → `purchased`
- When marked as `purchased`, pantry inventory is updated accordingly

---

### 3.6 Pricing & Budget Estimation

- **Goal:** estimate shopping trip cost accurate to within 10-15% of actual
- **v1 Approach:**
  1. **USDA food price data** — public dataset, updated regularly, national averages with regional breakdowns. Used as the baseline price per ingredient.
  2. **User price calibration** — on setup, user enters prices for a small set of anchor items (e.g., milk, eggs, bread, chicken breast). This calibrates the USDA baseline to their local reality.
- **Future (v2+):** store API integration (Kroger, HEB, etc.) and/or crowd-sourced pricing from users confirming actual prices post-shop
- **AI-assisted regional estimation:** explore using LLM with store name and region as context to improve price estimates for specific retailers (e.g., HEB in Floresville, TX vs. HEB in Pleasanton, TX)
- Real-time pricing integration is a **nice-to-have**, not a v1 requirement

---

### 3.7 Dietary Preferences & Restrictions

- Set at the User level, applied to all AI meal generation for that user
- Common structured flags: vegetarian, vegan, gluten-free, dairy-free, nut allergy, shellfish allergy, halal, kosher
- Freeform "I don't like / I avoid" text field — passed directly to the LLM in recipe generation prompts
- Household-level dietary overrides (e.g., a household member has a specific allergy that applies to all household meals)
- This is a standard feature, not a primary marketing focus — should be easy to set up and stay out of the way

---

## 4. Data Model

### Entity Relationship Summary

```
Household
  - id
  - name                        -- e.g., "Home", "Jake's College Apt"
  - store_preference            -- preferred grocery store
  - region                      -- for USDA pricing lookup
  - price_calibration (JSONB)   -- anchor item prices user has confirmed
  - pantry_depletion_mode       -- enum: auto | manual

HouseholdMember
  - id
  - household_id (FK → Household)
  - user_id (FK → User)
  - role                        -- enum: owner | member

User
  - id
  - email
  - name
  - dietary_preferences (JSONB) -- structured flags + freeform dislikes
  - active_household_id (FK → Household)

MealPlan
  - id
  - household_id (FK → Household)
  - status                      -- enum: draft | active | closed
  - start_date
  - end_date
  - budget (decimal)
  - created_at
  - closed_at (nullable)

MealPlanDay
  - id
  - meal_plan_id (FK → MealPlan)
  - date

Meal
  - id
  - meal_plan_day_id (FK → MealPlanDay)
  - meal_type                   -- enum: breakfast | lunch | dinner | snack
  - recipe_id (FK → Recipe)
  - servings (int)              -- may differ from recipe default
  - cooked_at (timestamp, nullable)

Recipe
  - id
  - created_by_user_id (nullable) -- null = shared pool; set = user-owned copy
  - title
  - description
  - cuisine_tags (array)
  - prep_time (minutes)
  - cook_time (minutes)
  - default_servings
  - instructions (text)
  - is_ai_generated (bool)
  - source_prompt (text, nullable) -- prompt used to generate, for iteration

RecipeIngredient
  - id
  - recipe_id (FK → Recipe)
  - ingredient_id (FK → Ingredient)
  - quantity (decimal)
  - unit
  - is_optional (bool)

Ingredient
  - id
  - name                        -- canonical name
  - category                    -- produce | dairy | meat | pantry staple | etc.
  - usda_price_per_unit (decimal)
  - usda_unit
  - last_usda_sync (timestamp)

PantryItem
  - id
  - household_id (FK → Household)
  - ingredient_id (FK → Ingredient)
  - quantity (decimal)
  - unit
  - added_at
  - updated_at

ShoppingList
  - id
  - meal_plan_id (FK → MealPlan)
  - store_preference
  - estimated_total (decimal)
  - status                      -- enum: draft | finalized | purchased

ShoppingListItem
  - id
  - shopping_list_id (FK → ShoppingList)
  - ingredient_id (FK → Ingredient)
  - quantity_needed (decimal)   -- after pantry subtraction
  - unit
  - estimated_price (decimal)
  - is_checked (bool)
  - source                      -- enum: recipe | manual
```

---

## 5. Tech Stack

### Frontend — Web
- **Framework:** Next.js (TypeScript)
- **Rationale:** Best-in-class React framework, SSR/SSG support, strong ecosystem, Vercel deployment story

### Frontend — Mobile
- **Framework:** Expo / React Native (TypeScript)
- **Rationale:** Same language as web, large ecosystem, best mobile experience vs. true single-codebase alternatives
- **Barcode scanning:** Expo Camera + Open Food Facts API (free, open source)

### Shared
- TypeScript across web and mobile
- Shared API types/contracts between frontend and backend

### Backend
- **BaaS:** Supabase (PostgreSQL, Auth, Storage, Realtime)
  - Handles auth, database, file storage, real-time subscriptions
  - Fast path to v1 with full control when needed
- **AI Service:** Python + FastAPI
  - Dedicated service for LLM interactions (recipe generation, meal planning, price estimation)
  - Keeps AI logic clean, testable, and portable independent of BaaS

### Database
- **PostgreSQL** (via Supabase)
- JSONB for flexible fields (dietary preferences, price calibration, recipe tags)

### LLM
- **Primary:** Claude API (Anthropic)
  - Strong structured output support
  - Well-suited for recipe generation with constraints (dietary, pantry inventory, budget)
  - Swappable — the FastAPI service abstracts the LLM provider

### Pricing Data
- **USDA Food Price Data** — public dataset for baseline ingredient pricing
- User calibration anchors to localize estimates

### Third-Party APIs
- **Open Food Facts** — barcode lookup for pantry item entry (free, open source)
- **Store APIs (future)** — Kroger, HEB, etc. for real-time pricing (v2+)

---

## 6. Monetization Strategy

All models below are in consideration. Final strategy will be determined as the product takes shape and user behavior becomes clearer.

### 6.1 Subscription Tiers (B2C)

| Tier | Households | Meal Plans | AI Generations | Price |
|---|---|---|---|---|
| **Free** | 1 | 1 active at a time | Limited (~5/month) | $0 |
| **Personal** | 1 | Unlimited history | Unlimited | ~$5–8/mo |
| **Family** | Up to 5 | Unlimited history | Unlimited | ~$12–15/mo |
| **Premium** | Unlimited | Unlimited | Unlimited + priority | ~$20–25/mo |

**Notes:**
- AI generation limits on the free tier are the primary cost-control lever (LLM API calls are the main variable cost)
- Multi-household access is the primary upsell from Personal → Family/Premium
- Annual pricing discounts to be determined

### 6.2 Grocery Delivery Integration
- Partner with Instacart, DoorDash Grocery, or similar
- Referral/affiliate revenue when users order through the app from their shopping list
- Natural fit: user has a shopping list, one tap to send it to delivery

### 6.3 Sponsored Recipe Placement
- Brands (e.g., spice companies, specialty food brands) pay for featured placement in AI-generated recipe suggestions
- Must be clearly labeled as sponsored
- Only viable at meaningful user scale

### 6.4 Anonymized Data Insights
- Opt-in, anonymized meal trend, ingredient, and regional preference data
- Valuable to food brands, grocery retailers, and market research firms
- Strong value prop given the structured, domain-specific data the app accumulates
- Requires careful privacy policy and transparent user consent

### 6.5 White-Label Licensing (B2B)
- License the platform to grocery chains, meal kit companies, corporate wellness programs, or food brands
- They deploy a branded version of the app for their customers
- Flat fee or per-seat pricing
- High-value, high-effort — scale play, not a v1 concern
- The shared recipe pool and household model are particularly attractive for this use case

---

## 7. Version Roadmap

### v1 — Personal Use / Validation
**Goal:** A working product for personal use that validates the core loop.

**In scope:**
- User authentication (Supabase Auth)
- Household setup (single household per user)
- Dietary preferences / profile
- AI meal plan generation (by date range)
- Per-day/meal override (recipe, cuisine, timing)
- Pantry inventory (manual entry + barcode scanning)
- Pantry-aware meal plan generation
- Shopping list generation from meal plan
- Budget estimation (USDA baseline + user calibration anchors)
- Pantry depletion on cook (auto or manual, user's choice)
- Partial-use prompt at cook time
- Meal plan status management (draft → active → closed)
- Web app + mobile app with full feature parity

**Out of scope for v1:**
- Multi-household management
- Real-time store pricing
- Grocery delivery integration
- Expiry date tracking
- Smart home integrations
- Monetization / billing

---

### v2 — Production Grade
**Goal:** Scale to a production-ready, publicly shippable product.

**Additions:**
- Multi-household management (Family/Premium tier)
- Subscription billing (Stripe)
- Household member invites and role management
- Crowd-sourced pricing (users confirm actual prices post-shop)
- Store API integrations where available (Kroger, etc.)
- AI-assisted regional price estimation by store and location
- Recipe rating and feedback loop (improve AI generation quality over time)
- Grocery delivery integration (Instacart affiliate)
- Performance, reliability, and security hardening
- Analytics and observability

---

### v3 — Ecosystem Expansion
**Goal:** Expand surface area and capture broader market share.

**Additions:**
- Smart home integrations (Amazon Alexa, Google Home) — voice-driven pantry updates, meal status
- Sponsored recipe placement
- Anonymized data insights product
- White-label platform
- Nutrition tracking and macro goals
- Meal history and trend insights ("you cook Italian 40% of the time")

---

## 8. Open Questions & Future Considerations

| Topic | Question | Notes |
|---|---|---|
| Recipe ownership | Who owns AI-generated recipes in the shared pool? | IP/licensing consideration; likely app-owned with attribution to generating user |
| LLM cost management | What are acceptable per-user LLM costs at scale? | Need to benchmark generation cost per meal plan to inform tier limits |
| USDA data pipeline | How frequently does USDA data update and how is it synced? | Need to research update cadence and build a sync job |
| Barcode coverage | How complete is Open Food Facts for US grocery items? | May need a fallback (manual entry prompt) for unrecognized barcodes |
| Partial unit tracking | How granular should pantry quantities be? | e.g., "1/2 can of tomatoes" — UX needs to make this easy, not annoying |
| Household dietary conflicts | How does the AI handle a household where one member is vegan and another is not? | Could generate separate meals or flag conflicts |
| Offline support | Should the mobile app work offline (e.g., in-store shopping)? | Shopping list checkout UX strongly benefits from offline support |
| Recipe iteration | How does a user say "make this recipe spicier" or "find me something similar"? | Source prompt + conversation-style iteration is a strong UX opportunity |
| Price calibration UX | What is the right onboarding flow for anchor item pricing? | Should feel lightweight, not like a survey |
