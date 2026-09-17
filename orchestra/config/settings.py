"""Centralized runtime configuration (single source of truth).

Operational constants (paths, timeouts, execution limits, retry/healing budgets)
are declared once here and consumed by the adapters and kernel. Environment
variables override the defaults for environment-dependent values (always
preferring env-provided credentials over any hardcoded default).

This module is the framework's configuration root: prefer importing from here
instead of scattering literals across adapters.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Repository layout -----------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(os.environ.get("QA_RESULTS_DIR", "results/run"))
ALLURE_DIR = Path(os.environ.get("QA_ALLURE_DIR", "results/run/allure-results"))
TEST_SUITE = "tests"

# --- Execution engine ------------------------------------------------------
# Time spent waiting for a Robot Framework run (seconds).
ROBOT_TIMEOUT_SECONDS = int(os.environ.get("QA_ROBOT_TIMEOUT", "600"))
# Time spent waiting for an agent subprocess (seconds).
AGENT_TIMEOUT_SECONDS = int(os.environ.get("QA_AGENT_TIMEOUT", "900"))
# Time spent waiting for a Docker build+run unit (seconds).
DOCKER_TIMEOUT_SECONDS = int(os.environ.get("QA_DOCKER_TIMEOUT", "1200"))

# --- Self-healing policy ---------------------------------------------------
# Hard cap on autonomous repair attempts (contract: at most 3).
MAX_HEALING_ATTEMPTS = int(os.environ.get("QA_MAX_HEALING", "3"))
# A healing fix must never modify these protected paths.
HEALING_PROTECTED_PATHS = (
    "Jenkinsfile",
    "Dockerfile",
    "tests/",
    "resources/",
    "pages/",
)

# --- Resume/loop guard -----------------------------------------------------
# At most one resumable execution per run id.
MAX_RESUMES = 1

# --- Agent dispatch --------------------------------------------------------
# Maximum depth of nested agent dispatch (guards against recursive agent loops).
MAX_AGENT_DEPTH = int(os.environ.get("QA_MAX_AGENT_DEPTH", "1"))

# --- Regression scope policy ------------------------------------------------
# Any change touching these shared surface areas forces a full regression.
SHARED_CORE_COMPONENT_CHANGED = True

# --- Git delivery / CI contract ---------------------------------------------
# Jenkins job triggered exclusively by the GitHub webhook for a pushed feature/fix
# branch. Autonomous remote-trigger tokens and "Build Now" are prohibited (AGENTS.md).
JENKINS_JOB_NAME = os.environ.get("QA_JENKINS_JOB", "Robot-Playwright-Sanity")
JENKINS_BASE_URL = os.environ.get("QA_JENKINS_BASE_URL", "")
# Remote name used for push verification (always the tracked GitHub remote).
GIT_REMOTE = os.environ.get("QA_GIT_REMOTE", "origin")

# --- Execution environment contract ------------------------------------------
# True when the automation target is a PUBLIC / shared DEMO environment (e.g. the
# public OrangeHRM 5.9 demo). Public demos are periodically unavailable, rate-limited
# or unresponsive. When True, an environment marker (page not rendered, /auth/validate
# hang, network timeout, server unresponsive) is classified as ENVIRONMENT_FAILURE on
# first occurrence and is NEVER healable and NEVER a reason to modify working
# automation. Override with QA_PUBLIC_DEMO_ENVIRONMENT=false for a controlled,
# self-hosted certification environment.
PUBLIC_DEMO_ENVIRONMENT = os.environ.get(
    "QA_PUBLIC_DEMO_ENVIRONMENT", "true"
).lower() in ("1", "true", "yes")
