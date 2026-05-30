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


def _build_chat_context_block(analysis_context: dict) -> str:
    """Format analysis context into a readable block for the system prompt."""
    ctx = analysis_context
    service = ctx.get("service", "unknown")
    service_label = ctx.get("service_label", service)

    service_guidance = _SERVICE_SYSTEM_PROMPTS.get(service, _GENERIC_SERVICE_PROMPT)

    lines = [
        "CURRENT ANALYSIS CONTEXT",
        "=" * 40,
        f"Service: {service_label}",
    ]

    inputs = ctx.get("inputs") or {}
    if inputs:
        lines.append("\nUser Inputs:")
        for k, v in inputs.items():
            if v is not None and v != "":
                lines.append(f"  {k}: {v}")

    full_area = ctx.get("full_area") or {}
    if full_area:
        lines.append("\nFull-Area Analysis Results:")
        for k, v in full_area.items():
            if v is not None and v != "" and not (isinstance(v, float) and v != v):
                lines.append(f"  {k}: {v}")

    grid = ctx.get("grid") or {}
    if grid:
        lines.append("\nGrid / Cell Analysis Results (200 m cells):")
        for k, v in grid.items():
            if v is not None and v != "" and not (isinstance(v, float) and v != v):
                lines.append(f"  {k}: {v}")

    lines.append("=" * 40)
    lines.append(
        "\nYou are having a conversation grounded in the analysis data above. "
        "Answer questions specifically about this analysis — use the actual numbers, "
        "compare them against known urban benchmarks, infer the likely city/region "
        "from any available clues, and give locally relevant targeted advice. "
        "Do not give generic advice unrelated to the data shown."
    )
    lines.append(f"\nDomain context: {service_guidance}")

    return "\n".join(lines)


def chat_with_hadary(messages, analysis_context: dict = None):
    """
    Main chat function for the urban QoL assistant "Hadary".

    Args:
        messages (list): List of message dicts with 'role' and 'content' keys
        analysis_context (dict, optional): Current analysis context from the dashboard

    Returns:
        str: The assistant's response text

    Raises:
        LLMError: If the API call fails or response is invalid
    """
    try:
        base_prompt = (
            "You are Hadary, an expert urban quality of life assistant. You help planners and "
            "city authorities anywhere in the world analyse and improve urban sustainability, "
            "livability, safety, and equity.\n\n"
            "Core behaviour:\n"
            "  - Infer the likely city/region from any clues in the conversation or analysis data "
            "(place names, coordinates, file names, statistical patterns). State the inference.\n"
            "  - Compare measured values to WHO, UN-Habitat, and ITDP international benchmarks. "
            "State explicitly whether results meet, fall short of, or exceed each standard.\n"
            "  - Apply the relevant historical, cultural, climate, and governance context for the "
            "inferred region. Explain why patterns exist locally, not just what the numbers show.\n"
            "  - Reference real local programmes, laws, and precedents where known.\n"
            "  - Cite actual numbers from the data in every substantive answer.\n"
            "  - Be concise and direct. When uncertain about location or causation, say so.\n"
            "  - Tailor recommendations to what is locally feasible and culturally appropriate.\n\n"
            + _GLOBAL_STANDARDS
            + _REGIONAL_CONTEXT_INSTRUCTION
        )

        if analysis_context:
            context_block = _build_chat_context_block(analysis_context)
            system_prompt = f"{base_prompt}\n\n{context_block}"
        else:
            system_prompt = (
                base_prompt
                + "\n\nNo specific analysis is loaded. Answer general urban planning questions, "
                "applying international benchmarks and inferring local context from any location "
                "clues the user provides. Cover: vegetation, heat, transport, air quality, density, "
                "informal settlements, crime, and facility accessibility."
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
            max_tokens=1600,
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


# ── Shared knowledge base injected into every prompt ─────────────────────────

_GLOBAL_STANDARDS = """
INTERNATIONAL BENCHMARKS & STANDARDS
======================================
Apply these to the analysis data. For every measured value, explicitly state whether it meets,
exceeds, or falls below the relevant benchmark and by how much.

Vegetation / Green Space:
- WHO: >= 9 m2 of accessible green space per capita; <= 300 m walk to nearest green space.
- UN-Habitat: Urban greenery target >= 30% of city area. < 10% is critically deficient.
- NDVI scale: < 0 water/built-up; 0-0.1 bare/rock; 0.1-0.2 sparse/stressed; 0.2-0.5 moderate; > 0.5 dense healthy.
- Urban NDVI mean >= 0.3 = internationally 'green'; < 0.15 = critically deficient.

Heat / Thermal Comfort:
- ASHRAE 55: operative temperature 20-26 degC at 50% RH for comfort.
- WHO: LST > 35 degC constitutes heat-health risk in temperate climates; threshold lower in humid cities.
- Urban Heat Island (UHI) intensity > 3 degC above rural baseline = public health concern.
- Physiological Equivalent Temperature (PET): < 18 degC comfortable; 18-29 degC warm; > 35 degC very hot.

Air Quality (US EPA / WHO 2021):
- AQI: Good 0-50; Moderate 51-100; Unhealthy for Sensitive 101-150; Unhealthy 151-200;
  Very Unhealthy 201-300; Hazardous 301+.
- WHO 2021 PM2.5 annual guideline: <= 5 ug/m3 (strict); interim target: <= 15 ug/m3.
- WHO PM10 annual guideline: <= 15 ug/m3; interim: <= 45 ug/m3.
- NO2 annual guideline: <= 10 ug/m3.

Public Transport:
- ITDP: <= 500 m walk to BRT/rail; <= 300 m to frequent bus = 'excellent' transit access.
- UN-Habitat: >= 80% of population within 500 m of frequent public transit.
- Coverage < 50% = transit desert condition.

Urban Density:
- UN-Habitat compact city: 150-200 persons/ha (15,000-20,000 pop/km2).
- < 50 persons/ha (5,000 pop/km2): low density / suburban sprawl risk.
- > 400 persons/ha (40,000 pop/km2): overcrowding with service degradation risk.
- Healthy walkable range: ~5,000-15,000 pop/km2 with adequate services.

Road Network & Traffic:
- SUMP (Sustainable Urban Mobility Plans): road density 2-12 km/km2; intersection density >= 100/km2.
- Connectivity index >= 3.5 = well-connected.
- WHO road safety target: < 10 road deaths per 100,000 population per year.

Informal Settlements:
- UN-Habitat slum definition: lacks durable housing, sufficient living area, improved water/sanitation,
  or security of tenure.
- CPTED (Crime Prevention Through Environmental Design): formal streets, active frontages, lighting
  reduce crime 20-40%.
- Evidence from Medellin, Mumbai, Rio, Bangkok: on-site upgrading preserves social capital better
  than relocation; forced relocation typically increases poverty.

Crime:
- UN-Habitat Safe Cities: <= 1 homicide/100,000 = very safe; 1-5 = moderate; > 10 = high risk.
- Official crime data is often underreported globally; use density as a relative indicator.

Facility Accessibility:
- WHO: primary healthcare <= 1 km; secondary hospital <= 5 km.
- UNESCO: primary school <= 1 km; secondary school <= 3 km.
- UN-Habitat: <= 10-minute walk (~800 m) to essential daily services.
- UNICEF: safe water <= 500 m; sanitation <= 100 m.
"""

_REGIONAL_CONTEXT_INSTRUCTION = """
REGIONAL & CULTURAL CONTEXT — INFER FROM AVAILABLE DATA
=========================================================
The user could be working in ANY city worldwide. You must:

1. INFER THE LIKELY REGION from clues in the analysis data:
   - Place names, boundary file names, or input file names (e.g. "Cairo", "Lagos", "Jakarta")
   - Coordinate ranges: lat 20-32 N + lon 25-40 E = Egypt/MENA; lat -35 to 5 S = sub-Saharan Africa;
     lat 0-25 N + lon 60-110 E = South/Southeast Asia; lat 35-70 N + lon -10 to 40 E = Europe; etc.
   - Statistical patterns: NDVI < 0.1 + LST > 38 degC suggests arid/semi-arid; high density > 30,000
     pop/km2 suggests South/Southeast Asian mega-city context; very low density < 500 pop/km2
     with high car ownership patterns suggests North American sprawl.
   - If the region cannot be inferred, state this and apply universal standards only.

2. ONCE THE REGION IS INFERRED, apply relevant historical, cultural, climate, and governance context:

   MENA / North Africa (Egypt, Morocco, Algeria, Jordan, Lebanon, Iraq, Gulf):
   - Hot arid/semi-arid climate; water scarcity constrains greenery; recommend drought-tolerant species.
   - Informal settlements (ashwa'iyyat, bidonvilles, gecekondu) are widespread; distinguish old
     consolidated informal vs. new peripheral squatter areas.
   - Historical urban fabric (medina, hara, souq, waqf land) shapes land use and street networks.
   - Centralised governance (Egypt: GOPP; Morocco: Agence Urbaine; Jordan: GAM) limits local agency.
   - Gender dimensions: public space safety affects women's mobility disproportionately.

   Sub-Saharan Africa (Nigeria, Kenya, Ethiopia, Ghana, South Africa, DRC):
   - Rapid urbanisation (fastest globally); peri-urban informal growth outpaces planning.
   - Colonial street grid legacy in city cores; organic growth on periphery.
   - Climate ranges from arid Sahel to humid equatorial; tailor heat/vegetation advice accordingly.
   - Customary land tenure coexists with formal title; complicates upgrading and redevelopment.
   - Transit systems vary: matatus (Kenya), danfos (Nigeria), minibus taxis (SA) fill formal gaps.

   South & Southeast Asia (India, Bangladesh, Pakistan, Indonesia, Philippines, Vietnam):
   - Extreme density in mega-cities (Mumbai, Dhaka, Jakarta, Manila often > 30,000 pop/km2).
   - Monsoon climate critical for flood risk, vegetation seasonality, and AQI (haze season).
   - Slum upgrading has global precedents: Dharavi (Mumbai), Kampung Improvement (Indonesia).
   - Rickshaw/motorbike/informal transit dominant; pedestrian safety a key concern.
   - Air quality often driven by vehicle emissions, industrial zones, and biomass burning.

   Latin America (Brazil, Colombia, Mexico, Peru, Argentina, Chile):
   - Favela/villa miseria/poblacion upgrading has the world's most studied precedents (Medellin,
     Complexo do Alemao, Villa El Salvador).
   - Social urbanism model: cable cars, escalators, libraries as equity infrastructure.
   - Climate varies: tropical Amazon basin vs. arid Andes vs. temperate Southern Cone.
   - High inequality (Gini > 0.5 in many cities) means QoL gaps are spatially extreme.
   - Public transport: BRT gold standard (Transmilenio, BRTS); Metro expanding in major cities.

   Europe (Western, Central, Eastern):
   - Strong planning regulation; informal settlements rare except in post-Soviet peripheries and
     Roma settlements.
   - High baseline transit coverage; focus is on first/last-mile gaps and equity across districts.
   - Climate change adaptation: heat waves (2003, 2019, 2022) reveal UHI vulnerability in dense cores.
   - Green infrastructure: EU Biodiversity Strategy targets 30% protected; Urban Greening Plans mandatory.
   - Cycling infrastructure well-developed in NW Europe; less so in Eastern/Southern Europe.

   North America (USA, Canada):
   - Low-density sprawl dominant outside city cores; transit deserts in most mid-size cities.
   - Car dependency creates high road-death rates and emissions despite wealth.
   - Redlining legacy: race and income strongly predict green space access and pollution exposure.
   - Heat vulnerability in cities without air conditioning (homeless, elderly, low-income).
   - Transit-oriented development (TOD) is the primary policy lever for density + transit co-location.

   East Asia (China, Japan, South Korea, Taiwan):
   - High-density, well-planned cities; transit coverage typically excellent (Tokyo, Seoul, Shanghai).
   - Air quality: major industrial pollution in Chinese cities; Japan/Korea improving.
   - Aging population driving accessibility design for elderly mobility.
   - Earthquake/typhoon risk shapes building codes and urban form.

3. APPLY CONTEXT TO RECOMMENDATIONS:
   - Tailor interventions to what is locally feasible, culturally appropriate, and
     consistent with the local governance and fiscal capacity.
   - Reference relevant local programmes, laws, or precedents when known
     (e.g. India's JNNURM/PMAY, Colombia's POT, Brazil's City Statute, EU Urban Agenda).
   - Note where the user's data contradicts typical patterns for the inferred region —
     this is often the most valuable insight.
   - If the region is unclear, give recommendations that are valid universally and
     note which aspects depend on local context the user should verify.
"""

_ANALYSIS_INSTRUCTIONS = """
INSTRUCTIONS FOR ANALYSIS
==========================
1. INFER LOCATION: Use all available clues (file names, coordinates, place names, statistical
   patterns) to infer the likely city/region before analysing. State your inference briefly.

2. COMPARE TO STANDARDS: For every metric, state whether it meets the WHO/UN-Habitat/ITDP
   benchmark, and by what margin. Quote both the measured value and the benchmark.

3. APPLY LOCAL CONTEXT: Based on the inferred region, apply relevant climate, cultural,
   historical, and governance context. Explain WHY patterns likely exist locally.

4. IDENTIFY ROOT CAUSES: Go beyond describing numbers. For example: "The low NDVI likely
   reflects arid climate and irrigation scarcity" or "High congestion near the central node
   suggests a radial street network from the colonial period."

5. PRIORITISE COMPOUNDED VULNERABILITY: Where multiple indicators are poor in the same area
   (e.g. high heat + no transit + informal housing), flag this as a compound risk requiring
   integrated intervention.

6. FEASIBLE RECOMMENDATIONS: Recommend interventions appropriate to the local context and
   capacity. Avoid solutions that are culturally inappropriate, fiscally unrealistic, or
   ignore the city's governance structure.

7. CITE NUMBERS: Every finding must reference the actual measured value, the benchmark, and
   the gap. Example: "Vegetation coverage of 8% is 22 percentage points below the WHO/UN-Habitat
   30% benchmark."
"""

_SERVICE_SYSTEM_PROMPTS = {
    "ndvi": (
        "You are analysing NDVI (Normalized Difference Vegetation Index) results for an urban area.\n"
        "NDVI scale: < 0 water/built-up; 0-0.1 bare soil; 0.1-0.2 sparse/stressed; "
        "0.2-0.5 moderate; > 0.5 dense healthy vegetation.\n"
        "Key benchmarks: WHO >= 9 m2 green space per capita; UN-Habitat >= 30% urban area as vegetation; "
        "urban NDVI mean >= 0.3 = 'green city'; < 0.15 = critically deficient.\n"
        "Seasonal variation: NDVI values in arid/semi-arid cities are naturally lower in dry season "
        "and should be interpreted against the local climate baseline, not temperate-city norms.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "heat-index": (
        "You are analysing urban heat island (UHI) and land surface temperature (LST) results.\n"
        "Thresholds: < 27 degC LST comfortable; 27-32 degC caution; 32-38 degC extreme caution; "
        ">= 38 degC danger. UHI > 3 degC above rural baseline = public health concern.\n"
        "ASHRAE 55: 20-26 degC operative temperature at 50% RH.\n"
        "Key interventions (universal): cool/reflective roofs, tree canopy, permeable paving, "
        "water features, urban ventilation corridors. Weight these based on the local climate.\n"
        "In arid cities, shading is higher priority than evapotranspiration. "
        "In humid tropical cities, ventilation and albedo matter more than additional moisture.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "crime": (
        "You are analysing crime density patterns for an urban area.\n"
        "UN-Habitat Safe Cities: <= 1 homicide/100,000 = very safe; 1-5 moderate; > 10 high risk.\n"
        "CPTED principles (universally applicable): natural surveillance, territorial reinforcement, "
        "activity support, access control, lighting, mixed-use activation — reduce crime 20-40%.\n"
        "Note: official crime statistics are underreported in most countries; use density as a "
        "relative spatial indicator. Community-based approaches consistently outperform surveillance-only.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "urban-density": (
        "You are analysing urban population density.\n"
        "UN-Habitat: 150-200 persons/ha (15,000-20,000 pop/km2) = compact city; "
        "< 50 persons/ha = sprawl risk; > 400 persons/ha = overcrowding risk.\n"
        "Healthy walkable range: ~5,000-15,000 pop/km2 with adequate services.\n"
        "Note: vertical density (apartments) vs. horizontal density (low-rise) have different "
        "service and infrastructure implications. Population data quality varies greatly by region.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "facility-accessibility": (
        "You are analysing pedestrian accessibility to urban facilities (healthcare, education, parks, etc.).\n"
        "WHO: primary healthcare <= 1 km; secondary hospital <= 5 km.\n"
        "UNESCO: primary school <= 1 km; secondary <= 3 km.\n"
        "UN-Habitat: <= 10-minute walk (~800 m) to essential daily services.\n"
        "Note: nominal proximity may be misleading if facilities are overcrowded, of poor quality, "
        "or inaccessible due to safety, cost, or physical barriers. Always flag quality alongside distance.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "public-transport": (
        "You are analysing public transport coverage for an urban area.\n"
        "ITDP: <= 500 m to BRT/rail; <= 300 m to frequent bus = 'excellent' access.\n"
        "UN-Habitat: >= 80% of residents within 500 m of frequent transit.\n"
        "Coverage < 50% = transit desert.\n"
        "Note: informal transit networks (minibuses, shared taxis, auto-rickshaws) often fill "
        "formal gaps in Global South cities — acknowledge these where evident and recommend "
        "formalisation rather than replacement where they function.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "vegetation": (
        "You are analysing vegetation density coverage across an urban area.\n"
        "WHO: >= 9 m2 green space per capita; <= 300 m to nearest park.\n"
        "UN-Habitat: >= 30% vegetation cover. < 10% = critically deficient.\n"
        "Note: greening strategies must match the local climate. In water-scarce regions, "
        "recommend drought-tolerant native species and grey-water reuse. In humid regions, "
        "focus on biodiversity corridors and flood-buffering wetlands.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "traffic": (
        "You are analysing road network quality and traffic congestion.\n"
        "SUMP: road density 2-12 km/km2; intersection density >= 100/km2 for walkable grids.\n"
        "Connectivity index >= 3.5 = well-connected. WHO road safety: < 10 deaths/100,000/year.\n"
        "High congestion = mobility poverty, productivity loss, emissions, and road deaths.\n"
        "Note: transport mode mix varies enormously by region — weight recommendations accordingly "
        "(cycling in NW Europe; BRT in Latin America; informal transit formalisation in Africa/MENA/Asia).\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "informal-settlement": (
        "You are analysing informal settlement patterns using building footprint irregularity.\n"
        "Irregularity score: 0-33 = planned/formal; 34-66 = transitional/mixed; 67-100 = informal.\n"
        "UN-Habitat slum definition: lacks durable housing, sufficient space, improved water/sanitation, "
        "or security of tenure.\n"
        "CPTED: formal street grid, active frontages, lighting reduce crime 20-40%.\n"
        "Global upgrading evidence: on-site upgrading (Medellin, Dharavi, Cairo, Bangkok, Rio) "
        "preserves social capital better than relocation. Forced relocation typically worsens poverty.\n"
        "Key universal interventions: tenure regularisation, participatory mapping, infrastructure-first "
        "upgrading, incremental housing improvement support.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
    "air-quality": (
        "You are analysing air quality index (AQI) distribution across an urban area.\n"
        "AQI: Good 0-50; Moderate 51-100; Unhealthy for Sensitive 101-150; "
        "Unhealthy 151-200; Very Unhealthy 201-300; Hazardous 301+.\n"
        "WHO 2021: PM2.5 annual <= 5 ug/m3; interim target <= 15 ug/m3.\n"
        "Common urban AQI sources by region: traffic exhaust (universal); industrial zones; "
        "biomass/crop burning (South/Southeast Asia, sub-Saharan Africa, MENA); "
        "dust storms (arid regions); waste burning (low-income areas globally); "
        "coal heating (Eastern Europe, Central Asia, parts of China).\n"
        "Identify the likely dominant source type from spatial patterns and recommend accordingly.\n"
        + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
    ),
}

_SERVICE_SYSTEM_PROMPTS["expansion"] = (
    "You are analysing multi-criteria urban expansion suitability results.\n"
    "The composite score (0-100) represents a weighted combination of several QoL analysis layers "
    "(e.g. transit coverage, vegetation, crime, air quality, facility accessibility). "
    "Higher scores indicate areas better suited for future urban expansion or development investment.\n"
    "Key considerations:\n"
    "- Top expansion zones are spatial clusters of high-composite-score cells, ranked best to least.\n"
    "- Per-layer scores within each zone reveal which dimensions drive or limit suitability.\n"
    "- Score standard deviation: high stdev = uneven spatial distribution; low stdev = homogeneous area.\n"
    "- Recommend which zone is most suitable and why, referencing per-layer scores.\n"
    "- Warn where a zone scores well overall but has a critical weakness (e.g. low transit coverage).\n"
    "- Relate findings to urban growth policy: greenfield vs. brownfield, TOD principles, "
    "informal settlement risk, infrastructure readiness, and equity of distribution.\n"
    "For map_highlights, use property 'qol_score' on the weighted grid cells. "
    "Best expansion cells: annotation_type='best_cells', op='gt'. "
    "Low-suitability gaps: annotation_type='gap_zone', op='lt'.\n"
    + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
)

_GENERIC_SERVICE_PROMPT = (
    "You are analysing urban quality-of-life metrics for an urban area anywhere in the world.\n"
    "Infer the likely region from available data clues, apply relevant local context, "
    "and compare all metrics to WHO, UN-Habitat, and ITDP international benchmarks.\n"
    + _GLOBAL_STANDARDS + _REGIONAL_CONTEXT_INSTRUCTION + _ANALYSIS_INSTRUCTIONS
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
  * cluster_hull   — convex hull polygon enclosing the top-quartile (high-value) features. Use for hotspots, risk zones, high-concentration areas.
  * gap_zone       — bounding-box rectangle around the bottom-quartile (low-value) features. Use for underserved, sparse, or low-score areas.
  * worst_cells    — numbered circle markers at the top_n lowest-value feature centroids. Pinpoints individual problem locations.
  * best_cells     — numbered circle markers at the top_n highest-value feature centroids. Highlights best performers.
  * centroid_label — single point marker at the centroid of all filtered features.
- The system ignores filter.value and computes real thresholds from the actual data percentiles.
  Your filter.value only sets the direction — set it to the p75 value (for gt) or p25 value (for lt)
  from the data stats provided above. For eq/in provide the exact string.
- Choose annotation_type:
  * High-value concentration → cluster_hull, op="gt"
  * Low-value / sparse area → gap_zone, op="lt"
  * Individual worst locations → worst_cells, op="lt", top_n=5
  * Individual best locations → best_cells, op="gt", top_n=5
- Property keys — use EXACTLY these names:
  * crime: "crime_density"
  * urban-density: "urban_density"
  * vegetation: "vegetation_pct"
  * traffic: "congestion" (op="eq", value="high") or "local_density"
  * informal-settlement: "irregularity_score" or "classification" (op="eq", value="high")
  * facility-accessibility: "time_min" or "type" (op="eq", value="uncovered")
  * public-transport: "type" (op="eq", value="uncovered")
  * ndvi / heat-index / air-quality: "qol_score"
- Provide 2–4 highlights covering distinct spatial patterns (e.g. hotspot hull + worst markers + best markers).
- Use distinct contrasting colours: red=#e74c3c, orange=#e67e22, amber=#f39c12, green=#27ae60, blue=#3498db, purple=#9b59b6.
- label and description MUST reference actual numbers from the data stats provided (e.g. real min/max/percentile values).
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
        "You are Hadary, an expert urban quality of life analyst. You work with cities anywhere "
        "in the world.\n"
        + service_prompt
        + "\n\nYour role: given the analysis results below, produce a structured JSON report. "
        "You MUST:\n"
        "  1. Infer the likely city/region from any clues in the data (place names, file names, "
        "coordinates, statistical patterns). State your inference in the headline or first finding.\n"
        "  2. Compare every measured value against the WHO, UN-Habitat, and ITDP benchmarks — "
        "state explicitly whether results meet, exceed, or fall below each, and by how much.\n"
        "  3. Apply the historical, cultural, climate, and governance context relevant to the "
        "inferred region to explain WHY patterns exist and what interventions are appropriate locally.\n"
        "  4. Reference real local programmes, laws, or precedents where known and relevant.\n"
        "  5. Cite actual numbers from the data in every finding — never give generic statements.\n"
        "  6. Think like a senior urban planner advising the local city authority, balancing "
        "technical standards with local feasibility and capacity.\n"
        + _RESPONSE_FORMAT
    )

    user_message = (
        "Here are the analysis results. Generate a structured recommendations report. "
        "First infer the likely region from any available clues, then benchmark all results "
        "against international standards and interpret them through relevant local context:\n\n"
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
            max_tokens=2400,
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
