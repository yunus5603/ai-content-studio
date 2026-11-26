"""Copilot: turns a goal ("a 8s teaser for our coffee brand") into a costed plan of
generation steps, and runs the plan once the user approves it.

- schema.py: plan and step shapes, API models
- planner.py: picks models and settings (LLM planner with a rules fallback)
- executor.py: submits steps as jobs and chains outputs into the next step
"""
