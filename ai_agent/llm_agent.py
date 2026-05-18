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
        raise ValueError("OPENAI_API_KEY is not set. Please set this environment variable.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=800,
        )

        response_text = response.choices[0].message.content.strip()
        if response_text:
            return response_text

        raise ValueError("OpenAI API returned no text.")
    except Exception as exc:
        raise ValueError(f"Failed to call OpenAI API: {exc}") from exc


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


# ── LLM Exception and Chat Functions ──────────────────────────────────────────

class LLMError(Exception):
    """Custom exception for LLM-related errors."""
    pass


def chat_with_hadary(messages):
    """
    Main chat function for the urban QoL assistant "Hadary".
    
    Args:
        messages (list): List of message dicts with 'role' and 'content' keys
                        (e.g., [{"role": "user", "content": "..."}, ...])
    
    Returns:
        str: The assistant's response text
    
    Raises:
        LLMError: If the API call fails or response is invalid
    """
    try:
        # Build the system prompt for the urban planning assistant
        system_prompt = (
            "You are Hadary, an expert urban quality of life assistant. "
            "You help cities analyze and improve urban sustainability, livability, and equity. "
            "Provide concise, actionable insights based on urban data and best practices. "
            "Focus on practical recommendations for: vegetation coverage, heat mitigation, "
            "public transport accessibility, traffic patterns, air quality, and informal settlement analysis. "
            "Always cite relevant benchmarks and standards (e.g., 30% urban greenery, 5,000 pop/km² density). "
            "Be clear about uncertainty and limitations in the data."
        )
        
        # Prepare API request with system prompt
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("OPENAI_API_KEY environment variable is not set.")
        
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        client = OpenAI(api_key=api_key)
        
        # Convert user message format to OpenAI format if needed
        api_messages = []
        for msg in messages:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                api_messages.append(msg)
            else:
                raise LLMError(f"Invalid message format: {msg}")
        
        # Call the API
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                *api_messages
            ],
            temperature=0.7,
            max_tokens=1024,
            top_p=0.95,
        )
        
        # Extract and return response
        if response.choices and len(response.choices) > 0:
            reply = response.choices[0].message.content.strip()
            if reply:
                return reply
        
        raise LLMError("OpenAI API returned empty response.")
    
    except openai.OpenAIError as e:
        raise LLMError(f"OpenAI API error: {e}") from e
    except Exception as e:
        raise LLMError(f"Unexpected error in chat_with_hadary: {e}") from e


if __name__ == "__main__":
    run_llm_agent()
