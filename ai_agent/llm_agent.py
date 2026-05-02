import json
import os
import sys

import openai
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from ai_agent.data_loader import load_grid_features, build_ai_summary
    from ai_agent.tools import (
        create_vegetation_zone,
        create_cool_roof_zone,
        create_shading_zone,
    )
except ModuleNotFoundError:
    # When running this script directly from inside ai_agent/, use local imports.
    from data_loader import load_grid_features, build_ai_summary
    from tools import (
        create_vegetation_zone,
        create_cool_roof_zone,
        create_shading_zone,
    )


def build_llm_prompt(summary):
    """Build a clear prompt for an LLM to analyze urban grid data."""
    prompt = (
        "You are analyzing urban grid data for a city. "
        "The data represents individual grid cells in an urban area. "
        "Each cell contains the following values:\n"
        "- lst_mean: land surface temperature\n"
        "- ndvi_mean: vegetation level\n"
        "- built_up_density: urban density\n"
        "- road_density: movement/activity intensity\n"
        "- dist_station_m: distance to monorail station\n"
        "- priority_score: intervention priority\n\n"
        "Based on the summary below, provide only valid JSON in the exact format:\n"
        "{\n"
        "  \"overall_insight\": \"...\",\n"
        "  \"top_issues\": [\"...\", \"...\"],\n"
        "  \"recommendations\": [\n"
        "    {\n"
        "      \"cell_id\": 1,\n"
        "      \"action\": \"vegetation_zone\",\n"
        "      \"reason\": \"...\",\n"
        "      \"confidence\": 0.85\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Allowed actions: vegetation_zone, cool_roofs, shading, no_action.\n"
        "Decision guidance:\n"
        "- high LST + low NDVI + low/medium built-up density = vegetation_zone\n"
        "- high LST + high built-up density = cool_roofs\n"
        "- high LST + high road density or near station = shading\n"
        "- otherwise = no_action\n\n"
        "Use the provided summary data and generate the response strictly in JSON format. "
        "Do not include any explanation outside the JSON object.\n\n"
        "Summary data:\n"
        f"{json.dumps(summary, indent=2)}\n"
    )
    return prompt


def parse_llm_response(response_text):
    """Parse LLM response text into JSON safely."""
    text = response_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
        else:
            text = text.strip("`\n ")

    if text.startswith("`") and text.endswith("`"):
        text = text.strip("`\n ")

    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse LLM response as JSON: {exc}\nCleaned response:\n{text}") from exc


def execute_llm_recommendations(llm_output, grid_path):
    """Execute GIS layer generation from LLM recommendations."""
    created_layers = []

    for recommendation in llm_output.get("recommendations", []):
        cell_id = recommendation.get("cell_id")
        action = recommendation.get("action")

        if cell_id is None:
            print(f"WARNING: Recommendation missing cell_id: {recommendation}. Skipping.")
            continue

        if action == "vegetation_zone":
            output_path = f"ai_agent/outputs/vegetation_cell_{cell_id}.geojson"
            try:
                result = create_vegetation_zone(
                    cell_id=cell_id,
                    grid_path=grid_path,
                    output_path=output_path,
                )
                created_layers.append(result)
            except Exception as exc:
                print(f"WARNING: Could not create vegetation zone for cell {cell_id}: {exc}")
                continue
        elif action == "cool_roofs":
            output_path = f"ai_agent/outputs/cool_roofs_cell_{cell_id}.geojson"
            try:
                result = create_cool_roof_zone(
                    cell_id=cell_id,
                    grid_path=grid_path,
                    output_path=output_path,
                )
                created_layers.append(result)
            except Exception as exc:
                print(f"WARNING: Could not create cool roof zone for cell {cell_id}: {exc}")
                continue
        elif action == "shading":
            output_path = f"ai_agent/outputs/shading_cell_{cell_id}.geojson"
            try:
                result = create_shading_zone(
                    cell_id=cell_id,
                    grid_path=grid_path,
                    output_path=output_path,
                )
                created_layers.append(result)
            except Exception as exc:
                print(f"WARNING: Could not create shading zone for cell {cell_id}: {exc}")
                continue
        elif action == "no_action":
            continue
        else:
            print(f"WARNING: Unknown action '{action}' for cell {cell_id}. Skipping.")
            continue

    return created_layers


def _extract_response_text(response):
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text.strip()

    if hasattr(response, "output") and response.output:
        text_parts = []
        for item in response.output:
            if isinstance(item, dict):
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") == "output_text":
                        text_parts.append(content.get("text", ""))
                    elif isinstance(content, dict) and content.get("type") == "tool":
                        # ignore tool output
                        continue
            else:
                if getattr(item, "type", None) == "output_text":
                    text_parts.append(getattr(item, "text", ""))
                elif hasattr(item, "content"):
                    for content in item.content:
                        if getattr(content, "type", None) == "output_text":
                            text_parts.append(getattr(content, "text", ""))
        result_text = "".join(text_parts).strip()
        if result_text:
            return result_text

    if hasattr(response, "choices") and response.choices:
        text_parts = []
        for choice in response.choices:
            if hasattr(choice, "message") and hasattr(choice.message, "content"):
                if isinstance(choice.message.content, str):
                    text_parts.append(choice.message.content)
                elif isinstance(choice.message.content, dict):
                    text_parts.append(choice.message.content.get("text", ""))
        result_text = "".join(text_parts).strip()
        if result_text:
            return result_text

    raw = str(response)
    if raw.strip():
        return raw.strip()

    return None


def call_llm(prompt):
    """Call the OpenAI API and return the raw model response text."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set. Please set this environment variable.")
        sys.exit(1)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=prompt,
            temperature=0.2,
            max_output_tokens=800,
        )

        response_text = _extract_response_text(response)
        if response_text:
            return response_text

        print("ERROR: OpenAI API returned no text.")
        print("Full response object:")
        print(response)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to call OpenAI API: {exc}")
        sys.exit(1)


def run_llm_agent():
    grid_path = "outputs/features/grid_features.geojson"
    gdf = load_grid_features(grid_path)

    if gdf is None:
        return

    summary = build_ai_summary(gdf)
    prompt = build_llm_prompt(summary)

    print("Sending prompt to LLM...")
    response_text = call_llm(prompt)

    try:
        parsed_response = parse_llm_response(response_text)
    except ValueError as exc:
        print("ERROR: Failed to parse LLM response as JSON.")
        print("Raw response:")
        print(response_text)
        print(str(exc))
        sys.exit(1)

    output_folder = os.path.join("ai_agent", "outputs")
    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, "llm_recommendations.json")

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(parsed_response, fh, indent=2)

    print("LLM analysis completed.")
    print(f"Saved JSON output to: {output_path}")

    layer_results = execute_llm_recommendations(parsed_response, grid_path)
    layer_output_path = os.path.join("ai_agent", "outputs", "generated_layers.json")
    with open(layer_output_path, "w", encoding="utf-8") as fh:
        json.dump(layer_results, fh, indent=2)

    print(f"Saved generated layer results to: {layer_output_path}")
    print()
    print("Generated layer outputs:")
    if layer_results:
        for layer in layer_results:
            print(f"  {layer.get('output_path')} ({layer.get('status')})")
    else:
        print("  No layers were generated.")

    print()
    print("Overall insight:")
    print(parsed_response.get("overall_insight"))
    print()
    print("Recommendations:")
    for rec in parsed_response.get("recommendations", []):
        print(
            f"Cell {rec.get('cell_id')}: {rec.get('action')} - {rec.get('reason')} "
            f"(confidence={rec.get('confidence')})"
        )


if __name__ == "__main__":
    run_llm_agent()
