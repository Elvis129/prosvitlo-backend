#!/bin/bash
cd /Users/user/my_pet_project/prosvitlo-backend
export PYTHONPATH=/Users/user/my_pet_project/prosvitlo-backend
/Users/user/my_pet_project/prosvitlo-backend/.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
