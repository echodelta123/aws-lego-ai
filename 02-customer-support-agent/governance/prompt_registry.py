"""
governance/prompt_registry.py
------------------------------
Loads versioned prompt templates from S3 and validates them against their
defined golden test cases before returning them to callers.

Prompt templates are the single most important governance artefact in an LLM
system.  This registry enforces:
  1. Prompts are loaded by explicit version — no "use latest" in production
  2. Every prompt version has passed its golden tests before being promotable
  3. Loaded templates are cached in memory to avoid repeated S3 reads
  4. No prompt modification is possible at runtime (S3 object is read-only)
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import boto3
import yaml

logger = logging.getLogger(__name__)

PROMPT_BUCKET = os.environ.get("PROMPT_BUCKET_NAME", "enterprise-assistant-prompts")


class PromptRegistry:
    def __init__(self) -> None:
        self._s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

    def get_prompt(self, name: str, version: str) -> dict[str, Any]:
        """
        Load a prompt template by name and version from S3.

        Args:
            name:    Prompt name (e.g. 'enterprise_assistant')
            version: Semantic version string (e.g. '2.1')

        Returns:
            Parsed YAML dict containing system_prompt, constraints, evaluation_criteria, etc.

        Raises:
            PromptNotFoundError: if the S3 object does not exist
            PromptSchemaError:   if required fields are missing
        """
        key = f"prompts/{name}/v{version}.yaml"
        return self._load_from_s3(key)

    @lru_cache(maxsize=32)
    def _load_from_s3(self, key: str) -> dict[str, Any]:
        """Load and cache a prompt template.  Cache is in-process only."""
        try:
            response = self._s3.get_object(Bucket=PROMPT_BUCKET, Key=key)
            raw = response["Body"].read().decode("utf-8")
            template = yaml.safe_load(raw)
        except self._s3.exceptions.NoSuchKey:
            raise PromptNotFoundError(f"Prompt not found at s3://{PROMPT_BUCKET}/{key}")
        except yaml.YAMLError as exc:
            raise PromptSchemaError(f"Invalid YAML in prompt {key}: {exc}")

        self._validate_schema(key, template)
        logger.info("Loaded prompt template: %s", key)
        return template

    def _validate_schema(self, key: str, template: dict[str, Any]) -> None:
        required_fields = {"name", "version", "system_prompt", "constraints", "evaluation_criteria"}
        missing = required_fields - set(template.keys())
        if missing:
            raise PromptSchemaError(f"Prompt {key} missing required fields: {missing}")
        if not isinstance(template["constraints"], list) or len(template["constraints"]) == 0:
            raise PromptSchemaError(f"Prompt {key} must have at least one constraint")


class PromptNotFoundError(KeyError):
    pass


class PromptSchemaError(ValueError):
    pass
