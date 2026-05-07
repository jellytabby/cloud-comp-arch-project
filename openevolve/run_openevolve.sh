#!/usr/bin/env bash

export OPENAI_API_KEY="<your-api-key>"
openevolve-run \
  openevolve/run_benchmarks_3all.sh \
  openevolve/evaluator.py \
  --config openevolve/config.yaml \
  --output openevolve/output