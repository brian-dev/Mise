"""Runtime configuration (env-driven).

Secrets and model selection come from the environment / .env. Model defaults
follow docs/AI_LAYER.md §10 (Sonnet for full plans, Haiku for single recipes).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic. `anthropic_api_key` reads ANTHROPIC_API_KEY from the env.
    anthropic_api_key: str = ""

    # Model selection (AI_LAYER §10). Swappable per the architecture's provider abstraction.
    meal_plan_model: str = "claude-sonnet-4-6"
    recipe_model: str = "claude-haiku-4-5"

    # A full 14-day, all-meal plan with inline recipes can be large; stream above ~16k.
    max_output_tokens: int = 32000

    # Bounded validation/repair (AI_LAYER §6): one retry, then fail the job.
    max_repair_attempts: int = 1


settings = Settings()
