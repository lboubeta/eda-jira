#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_TAG="${1:-redhat-iberia-eda-de:latest}"
DEFINITION="${DEFINITION:-${SCRIPT_DIR}/execution-environment.yml}"

if ! command -v ansible-builder >/dev/null 2>&1; then
  echo "ansible-builder is required. Install it with: pip install ansible-builder" >&2
  exit 1
fi

ansible-builder build \
  -f "${DEFINITION}" \
  -c "${REPO_ROOT}" \
  -t "${IMAGE_TAG}"

echo "Built decision environment image: ${IMAGE_TAG}"
