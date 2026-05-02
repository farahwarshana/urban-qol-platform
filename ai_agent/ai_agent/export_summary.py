import json
import os

LLM_FILE = "ai_agent/outputs/llm_recommendations.json"
LAYERS_FILE = "ai_agent/outputs/generated_layers.json"
OUTPUT_FILE = "ai_agent/outputs/ai_summary.json"


def export_summary():
    if not os.path.exists(LLM_FILE):
        print("LLM recommendations file not found.")
        return

    with open(LLM_FILE, "r") as f:
        llm_data = json.load(f)

    recommendations = llm_data.get("recommendations", [])

    summary = {
        "overall_insight": llm_data.get("overall_insight", ""),
        "total_recommendations": len(recommendations),
        "action_counts": {},
        "top_cells": [],
        "generated_layers": []
    }

    for rec in recommendations:
        action = rec.get("action", "unknown")

        # Count actions
        summary["action_counts"][action] = summary["action_counts"].get(action, 0) + 1

        # Collect top cells
        summary["top_cells"].append({
            "cell_id": rec.get("cell_id"),
            "action": action,
            "confidence": rec.get("confidence")
        })

    # Add generated layers if exists
    if os.path.exists(LAYERS_FILE):
        with open(LAYERS_FILE, "r") as f:
            layers = json.load(f)
            summary["generated_layers"] = layers

    # Save summary
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary, f, indent=4)

    print("AI summary created:")
    print(OUTPUT_FILE)


if __name__ == "__main__":
    export_summary()