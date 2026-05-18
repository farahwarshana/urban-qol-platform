from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ai_agent.llm_agent import chat_with_hadary, generate_recommendations, LLMError

router = APIRouter(prefix="/ai", tags=["AI"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: Optional[str] = None
    messages: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    reply: str


class RecommendationsRequest(BaseModel):
    service: str
    service_label: str
    inputs: Optional[Dict[str, Any]] = None
    full_area: Optional[Dict[str, Any]] = None
    grid: Optional[Dict[str, Any]] = None


class RecommendationSection(BaseModel):
    type: str
    title: str
    items: List[str]


class HighlightFilter(BaseModel):
    property: str
    op: str
    value: Any = None


class MapHighlight(BaseModel):
    id: str
    label: str
    color: str
    description: str
    annotation_type: str = "cluster_hull"
    top_n: int = 5
    filter: HighlightFilter


class RecommendationsResponse(BaseModel):
    headline: str
    overall_score: Optional[int] = None
    score_label: Optional[str] = None
    sections: List[RecommendationSection]
    map_highlights: List[MapHighlight] = []


class AnnotateRequest(BaseModel):
    geojson: Dict[str, Any]
    highlights: List[MapHighlight]
    service: str


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(body: ChatRequest = Body(...)):
    if body.messages:
        messages = body.messages
    elif body.message:
        messages = [ChatMessage(role="user", content=body.message)]
    else:
        raise HTTPException(status_code=422, detail="Request must include 'message' or 'messages'.")
    try:
        reply = chat_with_hadary(messages)
        return ChatResponse(reply=reply)
    except LLMError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat backend failed: {exc}")


@router.post("/recommendations", response_model=RecommendationsResponse)
def recommendations_endpoint(body: RecommendationsRequest = Body(...)):
    try:
        result = generate_recommendations(
            service=body.service,
            service_label=body.service_label,
            inputs=body.inputs or {},
            full_area=body.full_area or {},
            grid=body.grid,
        )
        return result
    except LLMError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recommendations backend failed: {exc}")


# ── Data-driven filter helpers ────────────────────────────────────────────────

def _collect_numeric_values(features: list, prop: str) -> List[float]:
    """Collect all non-null numeric values for a property across features."""
    vals = []
    for f in features:
        raw = (f.get("properties") or {}).get(prop)
        if raw is None:
            continue
        try:
            vals.append(float(raw))
        except (TypeError, ValueError):
            pass
    return vals


def _resolve_filter(features: list, hl: MapHighlight) -> list:
    """
    Apply the LLM-specified filter. If it matches fewer than 2 features,
    fall back to a data-driven percentile threshold using the same property and
    operator direction, so annotations always reflect the real data distribution.
    """
    prop = hl.filter.property
    op   = hl.filter.op

    # First try the LLM's exact filter
    matched = [f for f in features if _passes_filter(f.get("properties") or {}, hl.filter)]

    # If it matched a reasonable number, use it as-is
    min_features = max(2, len(features) // 20)  # at least 5% of features
    if len(matched) >= min_features:
        return matched

    # Fall back: compute a percentile-based threshold from the actual values
    vals = _collect_numeric_values(features, prop)
    if not vals:
        return matched  # can't improve — return whatever we got

    arr = np.array(vals)
    # Determine which percentile to use based on operator direction
    if op in ("gt", "gte"):
        # Caller wants high values → use 75th percentile as threshold
        threshold = float(np.percentile(arr, 75))
        fallback_filter = HighlightFilter(property=prop, op="gte", value=threshold)
    elif op in ("lt", "lte"):
        # Caller wants low values → use 25th percentile as threshold
        threshold = float(np.percentile(arr, 25))
        fallback_filter = HighlightFilter(property=prop, op="lte", value=threshold)
    elif op == "eq":
        # String equality — can't compute a percentile; return most frequent value
        str_vals = [(f.get("properties") or {}).get(prop) for f in features]
        str_vals = [v for v in str_vals if v is not None]
        if not str_vals:
            return matched
        from collections import Counter
        most_common = Counter(str_vals).most_common(1)[0][0]
        fallback_filter = HighlightFilter(property=prop, op="eq", value=most_common)
        threshold = most_common
    else:
        return matched

    fallback_matched = [f for f in features if _passes_filter(f.get("properties") or {}, fallback_filter)]
    print(f"[AI ANNOTATE]   filter fallback: '{prop}' {op} {hl.filter.value} → {op} {threshold:.3g} "
          f"({len(matched)} → {len(fallback_matched)} features)")
    return fallback_matched if len(fallback_matched) >= min_features else matched


def _passes_filter(props: dict, f: HighlightFilter) -> bool:
    raw = props.get(f.property)
    if raw is None:
        return False
    val = f.value
    try:
        op = f.op
        if op == "gt":  return float(raw) >  float(val)
        if op == "gte": return float(raw) >= float(val)
        if op == "lt":  return float(raw) <  float(val)
        if op == "lte": return float(raw) <= float(val)
        if op == "eq":  return str(raw) == str(val)
        if op == "in":
            return isinstance(val, list) and str(raw) in [str(v) for v in val]
    except (TypeError, ValueError):
        pass
    return False


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _geom_from_feature(feat: dict):
    try:
        from shapely.geometry import shape
        g = feat.get("geometry")
        return shape(g) if g else None
    except Exception:
        return None


def _centroid_coords(geom) -> tuple:
    c = geom.centroid
    return (round(c.x, 6), round(c.y, 6))


def _make_point_feature(coords, props: dict) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": list(coords)}, "properties": props}


def _make_polygon_feature(geom, props: dict) -> dict:
    from shapely.geometry import mapping
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


def _hull_feature(geoms, hl: MapHighlight) -> Optional[dict]:
    from shapely.ops import unary_union
    try:
        hull = unary_union(geoms).convex_hull
        if hull.is_empty or hull.geom_type == "Point":
            return None
        return _make_polygon_feature(hull.buffer(0.0002), {
            "ai_type": "cluster_hull", "ai_label": hl.label,
            "ai_color": hl.color, "ai_description": hl.description, "ai_group": hl.id,
        })
    except Exception:
        return None


def _bbox_feature(geoms, hl: MapHighlight) -> Optional[dict]:
    from shapely.geometry import box
    from shapely.ops import unary_union
    try:
        minx, miny, maxx, maxy = unary_union(geoms).bounds
        return _make_polygon_feature(box(minx, miny, maxx, maxy).buffer(0.0004), {
            "ai_type": "gap_zone", "ai_label": hl.label,
            "ai_color": hl.color, "ai_description": hl.description, "ai_group": hl.id,
        })
    except Exception:
        return None


def _centroid_marker(geoms, hl: MapHighlight, extra_props: dict = None) -> Optional[dict]:
    from shapely.ops import unary_union
    try:
        c = unary_union(geoms).centroid
        props = {"ai_type": "centroid_label", "ai_label": hl.label,
                 "ai_color": hl.color, "ai_description": hl.description, "ai_group": hl.id}
        if extra_props:
            props.update(extra_props)
        return _make_point_feature((round(c.x, 6), round(c.y, 6)), props)
    except Exception:
        return None


def _top_n_markers(features, geoms, hl: MapHighlight, sort_prop: str,
                   descending: bool, n: int) -> List[dict]:
    try:
        paired = []
        for feat, geom in zip(features, geoms):
            raw = (feat.get("properties") or {}).get(sort_prop)
            if raw is None:
                continue
            try:
                paired.append((float(raw), feat, geom))
            except (TypeError, ValueError):
                pass
        paired.sort(key=lambda x: x[0], reverse=descending)
        result = []
        for rank, (val, feat, geom) in enumerate(paired[:n], 1):
            cx, cy = _centroid_coords(geom)
            # Carry the area name forward if it exists
            feat_props = feat.get("properties") or {}
            name_key   = next((k for k in feat_props if k.lower() in
                               ("name","nbhd_name","admin_name","district","governorate","region","area_name")), None)
            extra = {sort_prop: round(val, 3)}
            if name_key and feat_props.get(name_key):
                extra["area_name"] = str(feat_props[name_key])
            result.append(_make_point_feature((cx, cy), {
                "ai_type": "worst_cells" if not descending else "best_cells",
                "ai_label": hl.label, "ai_color": hl.color,
                "ai_description": hl.description, "ai_group": hl.id,
                "ai_rank": rank, **extra,
            }))
        return result
    except Exception:
        return []


# ── Main annotate endpoint ────────────────────────────────────────────────────

@router.post("/annotate")
def annotate_endpoint(body: AnnotateRequest = Body(...)):
    """
    Derives NEW annotation geometries grounded in the actual data distribution.
    Filters are auto-corrected to percentile thresholds when the LLM's guess
    matches too few features, so annotations always reflect real spatial patterns.
    """
    try:
        features = body.geojson.get("features", [])
        if not features:
            raise HTTPException(status_code=422, detail="GeoJSON has no features.")

        print(f"[AI ANNOTATE] {len(features)} features, "
              f"{len(body.highlights)} highlights, service={body.service}")

        annotation_features = []

        for hl in body.highlights:
            # Use data-driven filter resolution — falls back to percentile if needed
            matched_feats = _resolve_filter(features, hl)
            matched_geoms = [g for f in matched_feats if (g := _geom_from_feature(f)) is not None]

            atype = hl.annotation_type
            print(f"[AI ANNOTATE]   '{hl.label}' ({atype}): {len(matched_feats)} features")

            if not matched_geoms:
                continue

            if atype == "cluster_hull":
                feat = _hull_feature(matched_geoms, hl)
                if feat:
                    annotation_features.append(feat)

            elif atype == "gap_zone":
                feat = _bbox_feature(matched_geoms, hl)
                if feat:
                    annotation_features.append(feat)

            elif atype == "worst_cells":
                markers = _top_n_markers(matched_feats, matched_geoms, hl,
                                         sort_prop=hl.filter.property,
                                         descending=False, n=hl.top_n)
                annotation_features.extend(markers)

            elif atype == "best_cells":
                markers = _top_n_markers(matched_feats, matched_geoms, hl,
                                         sort_prop=hl.filter.property,
                                         descending=True, n=hl.top_n)
                annotation_features.extend(markers)

            elif atype == "centroid_label":
                marker = _centroid_marker(matched_geoms, hl)
                if marker:
                    annotation_features.append(marker)

            else:
                feat = _hull_feature(matched_geoms, hl)
                if feat:
                    annotation_features.append(feat)

        print(f"[AI ANNOTATE] → {len(annotation_features)} annotation features produced")

        return JSONResponse(content={
            "type":                  "FeatureCollection",
            "features":              annotation_features,
            "ai_service":            body.service,
            "ai_annotation_count":   len(annotation_features),
        })

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[AI ANNOTATE] Error: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Annotation failed: {exc}")
