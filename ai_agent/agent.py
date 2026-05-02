from data_loader import load_grid_features, build_ai_summary
from tools import create_vegetation_zone, create_cool_roof_zone, create_shading_zone


def simple_ai_agent(summary):
    """Generate simple action recommendations from a summary dictionary."""
    recommendations = []

    avg_lst = summary.get("average_lst")
    avg_ndvi = summary.get("average_ndvi")
    avg_built = summary.get("average_built_up_density")
    avg_road_density = summary.get("average_road_density")
    lst_top_quartile = summary.get("lst_top_quartile")
    ndvi_bottom_quartile = summary.get("ndvi_bottom_quartile")

    for cell in summary.get("top_priority_cells", []):
        lst_mean = cell.get("lst_mean")
        ndvi_mean = cell.get("ndvi_mean")
        built_up_density = cell.get("built_up_density")
        road_density = cell.get("road_density")
        dist_station_m = cell.get("dist_station_m")
        relative_score = cell.get("relative_priority_score", 0)
        cell_id = cell.get("cell_id")

        action = "no_action"
        reason = "No urgent intervention required."

        high_heat = False
        low_veg = False
        high_built = False
        road_issue = False

        if lst_mean is not None and avg_lst is not None:
            high_heat = lst_mean > avg_lst
            if lst_top_quartile is not None:
                high_heat = high_heat or lst_mean >= lst_top_quartile

        if ndvi_mean is not None and avg_ndvi is not None:
            low_veg = ndvi_mean < avg_ndvi
            if ndvi_bottom_quartile is not None:
                low_veg = low_veg or ndvi_mean <= ndvi_bottom_quartile

        if built_up_density is not None and avg_built is not None:
            high_built = built_up_density > avg_built

        if road_density is not None and avg_road_density is not None:
            road_issue = road_density > avg_road_density
        if dist_station_m is not None:
            road_issue = road_issue or dist_station_m < 300

        if high_built and low_veg:
            action = "cool_roofs"
            reason = (
                f"Cell {cell_id} has high built-up density ({built_up_density:.2f}) and lower-than-average NDVI ({ndvi_mean:.2f}), "
                "so cool roofs are the stronger intervention."
            )
        elif low_veg and (not high_built or high_built is False):
            action = "vegetation_zone"
            reason = (
                f"Cell {cell_id} has low vegetation ({ndvi_mean:.2f}) compared to the AOI average ({avg_ndvi:.2f}) "
                f"and built-up density is {built_up_density:.2f}, making vegetation the preferred intervention."
            )
        elif road_issue:
            action = "shading"
            reason = (
                f"Cell {cell_id} has elevated movement conditions with road density {road_density:.2f} "
                f"and distance to station {dist_station_m} m, so shading is more suitable."
            )
        elif high_heat and low_veg:
            action = "vegetation_zone"
            reason = (
                f"Cell {cell_id} shows higher-than-average heat ({lst_mean:.1f}) and low vegetation ({ndvi_mean:.2f}), "
                "so vegetation is recommended."
            )
        else:
            if lst_mean is not None and ndvi_mean is not None and built_up_density is not None:
                reason = (
                    f"Cell {cell_id} has moderate conditions with LST {lst_mean:.1f}, NDVI {ndvi_mean:.2f}, "
                    f"and built-up density {built_up_density:.2f}, so no urgent action is required."
                )

        recommendations.append({
            "cell_id": cell_id,
            "action": action,
            "reason": reason,
            "confidence": 0.8,
            "relative_priority_score": relative_score,
        })

    recommendations.sort(
        key=lambda rec: (
            0 if rec["action"] == "no_action" else 1,
            rec["relative_priority_score"],
        ),
        reverse=True,
    )

    actionable = [rec for rec in recommendations if rec["action"] != "no_action"]
    if len(actionable) >= 3:
        recommendations = actionable[:5]
    else:
        required = max(3, len(actionable))
        fallback = [rec for rec in recommendations if rec["action"] == "no_action"]
        recommendations = actionable + fallback[: max(0, required - len(actionable))]

    return {
        "summary": "AI analysis completed.",
        "recommendations": recommendations,
    }


def execute_recommendations(ai_output, grid_path):
    created_layers = []

    for rec in ai_output.get("recommendations", []):
        cell_id = rec.get("cell_id")
        action = rec.get("action")

        if action == "vegetation_zone":
            output_path = f"ai_agent/outputs/vegetation_cell_{cell_id}.geojson"
            result = create_vegetation_zone(cell_id, grid_path, output_path)
            created_layers.append(result)
        elif action == "cool_roofs":
            output_path = f"ai_agent/outputs/cool_roofs_cell_{cell_id}.geojson"
            result = create_cool_roof_zone(cell_id, grid_path, output_path)
            created_layers.append(result)
        elif action == "shading":
            output_path = f"ai_agent/outputs/shading_cell_{cell_id}.geojson"
            result = create_shading_zone(cell_id, grid_path, output_path)
            created_layers.append(result)
        else:
            continue

    return created_layers


def main():
    grid_path = "outputs/features/grid_features.geojson"
    gdf = load_grid_features(grid_path)

    if gdf is None:
        return

    summary = build_ai_summary(gdf)
    ai_output = simple_ai_agent(summary)
    layer_results = execute_recommendations(ai_output, grid_path)

    print("AI AGENT RESULTS:")
    print("-" * 60)
    print(ai_output["summary"])
    print()
    print("Recommendations:")
    for rec in ai_output["recommendations"]:
        print(f"Cell {rec['cell_id']}: {rec['action']} ({rec['reason']}) [confidence={rec['confidence']}]")

    print()
    print("Created layer outputs:")
    if not layer_results:
        print("  No layers were created.")
    for layer in layer_results:
        print(f"  {layer['output_path']} ({layer['status']})")


if __name__ == "__main__":
    main()
