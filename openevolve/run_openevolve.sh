#!/usr/bin/env bash

export OPENAI_API_KEY="<your-api-key>"
openevolve-run \
  run_benchmarks_3all.sh \
  evaluator.py \
  --config openevolve/config.yaml \
  --output openevolve/output