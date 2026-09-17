#!/bin/bash

# Start a MuJoCo viewer that replays live quad144w/Y20W hardware LCM feedback.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

XML_PATH="${PROJECT_ROOT}/resources/robots/quad144w/scene_terrain.xml"

LCM_URL="udpm://239.255.76.67:7667?ttl=255"
VIEWER_HZ="60"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --xml)
            XML_PATH="$2"
            shift 2
            ;;
        --lcm-url)
            LCM_URL="$2"
            shift 2
            ;;
        --viewer-hz)
            VIEWER_HZ="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--xml FILE] [--lcm-url URL] [--viewer-hz HZ]"
            echo ""
            echo "Defaults:"
            echo "  --xml       ${XML_PATH}"
            echo "  --lcm-url   ${LCM_URL}"
            echo "  --viewer-hz ${VIEWER_HZ}"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use $0 --help for usage."
            exit 1
            ;;
    esac
done

cd "${PROJECT_ROOT}" || exit 1
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/lcm-types/python:${PYTHONPATH}"

python3 "${PROJECT_ROOT}/scripts/hardware_mujoco_viewer.py" \
    --xml "${XML_PATH}" \
    --lcm-url "${LCM_URL}" \
    --viewer-hz "${VIEWER_HZ}"
