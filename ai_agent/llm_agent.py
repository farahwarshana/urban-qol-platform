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
            elif hasattr(msg, "role") and hasattr(msg, "content"):
                api_messages.append({"role": msg.role, "content": msg.content})
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


def _build_context_prompt(service, service_label, inputs, full_area, grid):
    """
    Build a rich, service-specific context string to include in the system prompt.
    """
    lines = [f"SERVICE: {service_label} (key: {service})"]

    # ---- Inputs ----
    if inputs:
        lines.append("\nINPUT DATA:")
        for k, v in inputs.items():
            if v is not None and v != "":
                lines.append(f"  {k}: {v}")

    # ---- Full-area results ----
    if full_area:
        lines.append("\nFULL-AREA ANALYSIS RESULTS:")
        for k, v in full_area.items():
            if v is not None and v != "" and not (isinstance(v, float) and v != v):
                lines.append(f"  {k}: {v}")

    # ---- Grid results ----
    if grid:
        lines.append("\nGRID / CELL ANALYSIS RESULTS (200 m cells):")
        for k, v in grid.items():
            if v is not None and v != "" and not (isinstance(v, float) and v != v):
                lines.append(f"  {k}: {v}")

    return "\n".join(lines)


_SERVICE_SYSTEM_PROMPTS = {
    "ndvi": (
        "You are analysing NDVI (Normalized Difference Vegetation Index) results for an urban area. "
        "NDVI ranges from -1 to 1: values < 0 are water/built-up, 0–0.2 are bare soil/stress, "
        "0.2–0.5 moderate vegetation, > 0.5 dense healthy vegetation. "
        "WHO recommends ≥ 9 m² of green space per person and urban greenery ≥ 30% of area. "
        "Identify vegetation stress patterns, highlight areas needing green infrastructure, "
        "and recommend specific interventions (tree planting, green roofs, parks)."
    ),
    "heat-index": (
        "You are analysing urban heat island (LST / heat index) results. "
        "Comfortable urban temperature is < 27 °C; 27–32 °C is caution; 32–38 °C extreme caution; ≥ 38 °C is danger. "
        "Urban heat islands raise mortality, energy use, and inequality. "
        "Recommend cool roofs, tree canopy expansion, permeable paving, and urban water features "
        "as evidence-based heat mitigation strategies."
    ),
    "crime": (
        "You are analysing crime density patterns for an urban area. "
        "Higher crime density means lower safety and lower QoL. "
        "Look for hotspot concentration vs. dispersal, and consider environmental design theory (CPTED): "
        "lighting, surveillance, mixed-use activation, and community programs to reduce crime."
    ),
    "urban-density": (
        "You are analysing urban population density. "
        "The recommended healthy urban density target is approximately 5,000 pop/km². "
        "Very low density (< 500) suggests sprawl; very high density (> 20,000) suggests overcrowding. "
        "Assess whether the area is under- or over-dense, and recommend infill development, "
        "rezoning, or infrastructure investment accordingly."
    ),
    "facility-accessibility": (
        "You are analysing pedestrian accessibility to urban facilities (healthcare, education, parks, etc.). "
        "WHO and urban planning standards typically target ≤ 10-minute walk to essential services. "
        "Identify coverage gaps, underserved cells, and recommend facility placement or transport links."
    ),
    "public-transport": (
        "You are analysing public transport coverage for an urban area. "
        "A ≤ 400–500 m walking buffer (approx. 5 min walk) to transit is the standard benchmark. "
        "Coverage below 70% indicates significant transit deserts. "
        "Recommend new stops, route extensions, feeder services, or multimodal hubs."
    ),
    "vegetation": (
        "You are analysing vegetation density coverage. "
        "The global urban greenery benchmark is ≥ 30% vegetation cover. "
        "Identify how far the area is from the benchmark, which cells fail, "
        "and recommend targeted greening: parks, street trees, green corridors, bioswales."
    ),
    "traffic": (
        "You are analysing road network quality and traffic congestion. "
        "Optimal road density is 2–10 km/km²; connectivity index ≥ 3.5 is well-connected. "
        "High congestion means poor mobility and high emissions. "
        "Recommend road network improvements, traffic demand management, "
        "public transport modal shifts, and pedestrian/cycle infrastructure."
    ),
    "informal-settlement": (
        "You are analysing informal settlement patterns using building footprint irregularity. "
        "Irregularity score: 0–33 = planned, 34–66 = mixed, 67–100 = informal. "
        "High-irregularity areas often lack services, tenure security, and infrastructure. "
        "Recommend targeted upgrading programmes, participatory planning, service delivery prioritisation, "
        "and tenure regularisation where applicable."
    ),
    "air-quality": (
        "You are analysing air quality index (AQI) distribution across an urban area. "
        "AQI categories: Good (0–50), Moderate (51–100), Unhealthy for sensitive groups (101–150), "
        "Unhealthy (151–200), Very Unhealthy (201–300), Hazardous (301+). "
        "Identify pollution hotspots, likely sources, and recommend emission controls, "
        "green buffer zones, and public health advisories."
    ),
}

_GENERIC_SERVICE_PROMPT = (
    "You are analysing urban quality-of-life metrics for an urban area. "
    "Identify key patterns, anomalies, and provide actionable urban planning recommendations."
)

_RESPONSE_FORMAT = """
Respond ONLY with a valid JSON object (no markdown, no commentary outside JSON) in exactly this structure:
{
  "headline": "<one concise sentence summarising the key finding, max 120 chars>",
  "overall_score": <integer 0-100 representing your assessment of this area, or null>,
  "score_label": "<short label for the score, e.g. 'Poor' / 'Moderate' / 'Good' / 'Excellent'>",
  "sections": [
    {
      "type": "finding",
      "title": "Key Findings",
      "items": ["<finding 1>", "<finding 2>", ...]
    },
    {
      "type": "insight",
      "title": "Data Insights",
      "items": ["<insight 1>", "<insight 2>", ...]
    },
    {
      "type": "warning",
      "title": "Risks & Concerns",
      "items": ["<risk 1>", ...]
    },
    {
      "type": "recommendation",
      "title": "Actionable Recommendations",
      "items": ["<recommendation 1>", "<recommendation 2>", ...]
    }
  ],
  "map_highlights": [
    {
      "id": "<unique short id, e.g. 'hotspot_hull', 'gap_zone', 'worst_cell'>",
      "label": "<short map legend label, e.g. 'High-Crime Zone', 'Transit Desert', 'Worst Cell'>",
      "color": "<hex colour, e.g. '#e74c3c'>",
      "description": "<one sentence shown in map popup explaining what this shape represents>",
      "annotation_type": "<one of: cluster_hull | gap_zone | worst_cells | best_cells | centroid_label>",
      "filter": {
        "property": "<property key to select source features>",
        "op": "<one of: gt | lt | gte | lte | eq | in>",
        "value": <threshold number, string, or array>
      },
      "top_n": <optional integer — for worst_cells/best_cells, how many cells to mark (default 5)>
    }
  ]
}

Rules for sections:
- Each section must have 2–5 items.
- Items must be specific to the data provided, not generic.
- Reference actual numbers from the data in findings and insights.
- Recommendations must be concrete, spatially relevant, and feasible.
- overall_score must reflect the quality/health of what was measured (higher = better).
- Omit a section if it truly has nothing to say (minimum 2 sections required).

Rules for map_highlights — IMPORTANT: these produce NEW annotation shapes drawn on top of the analysis:
- annotation_type meanings:
  * cluster_hull   — draws a convex hull polygon enclosing all features that pass the filter. Use for hotspots, dense clusters, risk zones.
  * gap_zone       — draws a bounding-box polygon around features that pass the filter. Use for coverage gaps, underserved areas, low-score zones.
  * worst_cells    — places circle markers at the centroids of the top_n lowest-scoring cells (use with qol_score or value). Use to pinpoint the most critical locations.
  * best_cells     — places circle markers at the centroids of the top_n highest-scoring cells.
  * centroid_label — places a single point marker at the centroid of all filtered features, labelled with the group name.
- Choose annotation_type to best communicate the spatial insight:
  * A zone of danger/concentration → cluster_hull (red/orange)
  * An underserved/missing coverage area → gap_zone (blue/purple)
  * Individual worst or best locations → worst_cells / best_cells (markers)
  * A summary anchor point for a group → centroid_label
- Property keys by service (use these exactly):
  * crime: "crime_density"
  * urban-density: "urban_density"
  * vegetation: "vegetation_pct"
  * traffic grid cells: "congestion" (values: "low","medium","high") or "value" (road density km/km²)
  * traffic network: "hierarchy" (values: "primary","secondary","local")
  * informal-settlement: "irregularity_score" or "classification" (values: "low","medium","high")
  * facility-accessibility: "type" (values: "uncovered") or "value" (walk time minutes)
  * public-transport: "type" (values: "uncovered","covered") or "value" (distance km)
  * ndvi / heat-index / air-quality: "qol_score" (0–100) or "value" (raw metric)
- Provide 2–4 highlights covering distinct spatial patterns (e.g. worst zone + best zone + gap).
- Use distinct contrasting colours: red=#e74c3c, orange=#e67e22, amber=#f39c12, green=#27ae60, blue=#3498db, purple=#9b59b6.
- Omit map_highlights (empty array) only if data truly has no spatial patterns worth annotating.
"""


def generate_recommendations(service, service_label, inputs, full_area, grid):
    """
    Generate structured AI recommendations for a completed analysis.

    Returns a dict compatible with the RecommendationsResponse schema.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMError("OPENAI_API_KEY environment variable is not set.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    service_prompt = _SERVICE_SYSTEM_PROMPTS.get(service, _GENERIC_SERVICE_PROMPT)
    context_block = _build_context_prompt(service, service_label, inputs, full_area, grid)

    system_prompt = (
        "You are Hadary, an expert urban quality of life analyst. "
        + service_prompt
        + "\n\nYour role: given the analysis results below, produce a structured JSON report "
        "with key findings, data insights, risks, and concrete actionable recommendations. "
        "Be specific — cite the actual numbers from the data. "
        "Think like a senior urban planner advising a city authority."
        + _RESPONSE_FORMAT
    )

    user_message = (
        "Here are the analysis results. Please generate a structured recommendations report:\n\n"
        + context_block
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
            max_tokens=1800,
            top_p=0.95,
            response_format={"type": "json_object"},
        )
    except openai.OpenAIError as e:
        raise LLMError(f"OpenAI API error: {e}") from e

    raw = response.choices[0].message.content.strip() if response.choices else ""
    if not raw:
        raise LLMError("OpenAI returned an empty response.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM returned invalid JSON: {e}\nRaw: {raw[:300]}") from e

    # Normalise sections
    sections = []
    for sec in parsed.get("sections", []):
        sections.append({
            "type": sec.get("type", "insight"),
            "title": sec.get("title", ""),
            "items": sec.get("items", []),
        })

    # Normalise map_highlights — validate required keys, drop malformed entries
    map_highlights = []
    for hl in parsed.get("map_highlights", []):
        f = hl.get("filter", {})
        if not f.get("property") or not f.get("op"):
            continue
        map_highlights.append({
            "id":              hl.get("id", "highlight"),
            "label":           hl.get("label", "AI Highlight"),
            "color":           hl.get("color", "#e74c3c"),
            "description":     hl.get("description", ""),
            "annotation_type": hl.get("annotation_type", "cluster_hull"),
            "top_n":           hl.get("top_n", 5),
            "filter": {
                "property": f["property"],
                "op":       f["op"],
                "value":    f.get("value"),
            },
        })

    return {
        "headline":       parsed.get("headline", "Analysis complete."),
        "overall_score":  parsed.get("overall_score"),
        "score_label":    parsed.get("score_label", ""),
        "sections":       sections,
        "map_highlights": map_highlights,
    }


if __name__ == "__main__":
    run_llm_agent()
