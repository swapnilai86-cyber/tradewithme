#!/bin/bash
export ENV_STAGE=dev
export LIVE_MODE=false
uvicorn backend.app.main:app --reload
