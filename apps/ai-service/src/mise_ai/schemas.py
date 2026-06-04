"""Pydantic models for the meal-plan generation contract (docs/AI_LAYER.md §4).

Two halves:
  * Request models — the structured context the service builds a prompt from.
  * Output models — what Claude emits via the `emit_meal_plan` tool, validated
    here before canonicalization/persistence.

The output models mirror the JSON Schema in `tools.py` exactly. The enums are
the Python-side mirror of supabase/migrations/0001_schema.sql and
packages/shared/src/enums.ts — keep all three in lockstep.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MealType(StrEnum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"


class Unit(StrEnum):
    # mass
    g = "g"
    kg = "kg"
    oz = "oz"
    lb = "lb"
    # volume
    ml = "ml"
    liter = "l"
    tsp = "tsp"
    tbsp = "tbsp"
    cup = "cup"
    fl_oz = "fl_oz"
    # count
    unit = "unit"
    clove = "clove"
    slice = "slice"
    can = "can"
    bunch = "bunch"
    pinch = "pinch"


# --------------------------------------------------------------------------- #
# Request context (AI_LAYER §3 — the dynamic user message block)
# --------------------------------------------------------------------------- #
class PantryItem(BaseModel):
    name: str
    quantity: float
    unit: Unit


class Dietary(BaseModel):
    """Structured flags become hard constraints; avoid_text is a soft preference."""

    flags: list[str] = Field(default_factory=list)
    avoid_text: str | None = None


class MealPlanRequest(BaseModel):
    household_id: UUID
    start_date: date
    end_date: date
    household_size: int = Field(ge=1, description="Default servings per meal.")
    meal_types: list[MealType] = Field(min_length=1)
    dietary: Dietary = Field(default_factory=Dietary)
    pantry: list[PantryItem] = Field(default_factory=list)
    budget: float | None = None
    region: str | None = None
    store_preference: str | None = None
    variety_target: str | None = "Avoid repeating the same cuisine two days in a row."


# --------------------------------------------------------------------------- #
# Tool output (AI_LAYER §4 — what `emit_meal_plan` returns)
# --------------------------------------------------------------------------- #
class GeneratedIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: str | None = None
    quantity: float = Field(gt=0)
    unit: Unit
    is_optional: bool = False


class GeneratedRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str | None = None
    cuisine_tags: list[str] = Field(default_factory=list)
    prep_time: int | None = Field(default=None, ge=0)
    cook_time: int | None = Field(default=None, ge=0)
    default_servings: int = Field(ge=1)
    instructions: str
    ingredients: list[GeneratedIngredient] = Field(min_length=1)


class GeneratedMeal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meal_type: MealType
    servings: int | None = Field(default=None, ge=1)
    recipe: GeneratedRecipe


class GeneratedDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    meals: list[GeneratedMeal] = Field(min_length=1)


class GeneratedMealPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[GeneratedDay] = Field(min_length=1)
