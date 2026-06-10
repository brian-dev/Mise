"""Runtime configuration (env-driven).

Secrets and model selection come from the environment / .env. Model defaults
follow docs/AI_LAYER.md §10 (Sonnet for full plans, Haiku for single recipes).
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic. `anthropic_api_key` reads ANTHROPIC_API_KEY from the env.
    anthropic_api_key: str = ""

    # Model selection (AI_LAYER §10). Swappable per the architecture's provider abstraction.
    meal_plan_model: str = "claude-sonnet-4-6"
    recipe_model: str = "claude-haiku-4-5"

    # Privileged Postgres connection (ARCHITECTURE §6 — the AI service uses a
    # service-role/superuser connection and does its own authz). Defaults to the
    # local Supabase stack.
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

    # Ingredient canonicalization fuzzy-match cutoff (AI_LAYER §5).
    ingredient_match_threshold: float = 0.6

    # CORS allow-list for the local web harness (comma-separated origins).
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Supabase auth (ARCHITECTURE §4). Default is the local-stack JWT secret.
    # require_auth enforces a verified JWT + household membership on every
    # household-scoped endpoint (on now that the web client signs in and sends
    # tokens). Set REQUIRE_AUTH=false for unauthenticated local poking via curl.
    # Supabase signs user access tokens with an asymmetric key (ES256) published
    # at the JWKS endpoint; the HS256 shared secret remains valid for legacy
    # tokens and tests. The verifier (auth.py) handles both.
    supabase_jwt_secret: str = "super-secret-jwt-token-with-at-least-32-characters-long"
    supabase_jwks_url: str = "http://127.0.0.1:54321/auth/v1/.well-known/jwks.json"
    supabase_jwt_aud: str = "authenticated"
    require_auth: bool = True

    # A full 14-day, all-meal plan with inline recipes can be large; stream above ~16k.
    max_output_tokens: int = 32000

    # Bounded validation/repair (AI_LAYER §6): one retry, then fail the job.
    max_repair_attempts: int = 1

    # Test mode (MISE_TEST_MODE=true) mounts /v1/test/* helper endpoints used by
    # E2E tests to reach app states fast and deterministically WITHOUT calling
    # Claude. Never enable in production.
    test_mode: bool = Field(default=False, validation_alias="MISE_TEST_MODE")


settings = Settings()
