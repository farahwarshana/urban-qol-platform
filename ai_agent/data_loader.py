import os
import sys
from typing import Dict, List, Optional

import geopandas as gpd


def load_grid_features(path: str) -> Optional[gpd.GeoDataFrame]:
    """Load a GeoJSON file containing grid features.

    Args:
        path: Path to the GeoJSON file.

    Returns:
        GeoDataFrame if the file exists and loads successfully, otherwise None.
    """
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        return None

    try:
        gdf = gpd.read_file(path)
        return gdf
    except Exception as exc:
        print(f"ERROR: Failed to read GeoJSON file: {exc}")
        return None


def validate_columns(gdf: gpd.GeoDataFrame) -> List[str]:
    """Validate that required columns exist in the GeoDataFrame.

    Args:
        gdf: Input GeoDataFrame.

    Returns:
        A list of missing column names.
    """
    required_columns = [
        "cell_id",
        "ndvi_mean",
        "lst_mean",
        "built_up_density",
        "road_density",
        "dist_station_m",
        "priority_score",
        "priority_class",
    ]

    missing = [col for col in required_columns if col not in gdf.columns]
    return missing


def _safe_mean(gdf: gpd.GeoDataFrame, column: str) -> Optional[float]:
    if column not in gdf.columns:
        return None
    try:
        return float(gdf[column].mean())
    except Exception:
        return None


def _safe_value(row: gpd.GeoSeries, column: str):
    return row[column] if column in row.index else None


def build_ai_summary(gdf: gpd.GeoDataFrame, top_n: int = 5) -> Dict[str, object]:
    """Build a summary dictionary from grid feature data.

    Args:
        gdf: GeoDataFrame containing grid feature data.
        top_n: Number of top priority cells to include.

    Returns:
        Dictionary with aggregated summary data.
    """
    summary = {
        "total_cells": len(gdf),
        "average_ndvi": _safe_mean(gdf, "ndvi_mean"),
        "average_lst": _safe_mean(gdf, "lst_mean"),
        "average_built_up_density": _safe_mean(gdf, "built_up_density"),
        "average_road_density": _safe_mean(gdf, "road_density"),
        "ndvi_bottom_quartile": None,
        "lst_top_quartile": None,
        "high_priority_count": None,
        "top_priority_cells": [],
    }

    if "ndvi_mean" in gdf.columns:
        try:
            ndvi_values = gdf["ndvi_mean"].dropna().astype(float)
            if not ndvi_values.empty:
                summary["ndvi_bottom_quartile"] = float(ndvi_values.quantile(0.25))
        except Exception:
            summary["ndvi_bottom_quartile"] = None

    if "lst_mean" in gdf.columns:
        try:
            lst_values = gdf["lst_mean"].dropna().astype(float)
            if not lst_values.empty:
                summary["lst_top_quartile"] = float(lst_values.quantile(0.75))
        except Exception:
            summary["lst_top_quartile"] = None

    if "priority_class" in gdf.columns:
        try:
            high_priority = gdf[gdf["priority_class"].astype(str).str.lower() == "high"]
            summary["high_priority_count"] = len(high_priority)
        except Exception:
            summary["high_priority_count"] = None
    else:
        summary["high_priority_count"] = None

    id_column = "cell_id" if "cell_id" in gdf.columns else ("grid_id" if "grid_id" in gdf.columns else None)
    priority_rows = []
    for _, row in gdf.iterrows():
        ndvi = _safe_value(row, "ndvi_mean")
        lst = _safe_value(row, "lst_mean")
        built_up = _safe_value(row, "built_up_density")

        high_heat = False
        low_veg = False
        high_built = False

        if lst is not None and summary["average_lst"] is not None:
            high_heat = lst > summary["average_lst"]
            if summary["lst_top_quartile"] is not None:
                high_heat = high_heat or lst >= summary["lst_top_quartile"]

        if ndvi is not None and summary["average_ndvi"] is not None:
            low_veg = ndvi < summary["average_ndvi"]
            if summary["ndvi_bottom_quartile"] is not None:
                low_veg = low_veg or ndvi <= summary["ndvi_bottom_quartile"]

        if built_up is not None and summary["average_built_up_density"] is not None:
            high_built = built_up > summary["average_built_up_density"]

        combined_score = 0
        if high_heat:
            combined_score += 3
        if low_veg:
            combined_score += 2
        if high_built:
            combined_score += 1

        priority_rows.append({
            "cell_id": _safe_value(row, "cell_id") if id_column == "cell_id" else _safe_value(row, "grid_id"),
            "ndvi_mean": ndvi,
            "lst_mean": lst,
            "built_up_density": built_up,
            "road_density": _safe_value(row, "road_density"),
            "dist_station_m": _safe_value(row, "dist_station_m"),
            "priority_score": _safe_value(row, "priority_score"),
            "priority_class": _safe_value(row, "priority_class"),
            "high_heat": high_heat,
            "low_veg": low_veg,
            "high_built": high_built,
            "relative_priority_score": combined_score,
        })

    priority_rows.sort(key=lambda x: x["relative_priority_score"], reverse=True)
    summary["top_priority_cells"] = priority_rows[:top_n]

    return summary


def main() -> None:
    path = "outputs/features/grid_features.geojson"
    gdf = load_grid_features(path)

    if gdf is None:
        sys.exit(1)

    missing_columns = validate_columns(gdf)
    if missing_columns:
        print("WARNING: Missing columns:")
        for col in missing_columns:
            print(f"  - {col}")
        print()

    summary = build_ai_summary(gdf)
    print("AI SUMMARY:")
    print("-" * 60)
    print(f"Total cells: {summary['total_cells']}")
    print(f"Average NDVI: {summary['average_ndvi']}")
    print(f"Average LST: {summary['average_lst']}")
    print(f"Average built-up density: {summary['average_built_up_density']}")
    print(f"High priority count: {summary['high_priority_count']}")
    print()
    print("Top priority cells:")
    for cell in summary["top_priority_cells"]:
        print(cell)


if __name__ == "__main__":
    main()
