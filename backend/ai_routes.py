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
    analysis_context: Optional[Dict[str, Any]] = None


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
        reply = chat_with_hadary(messages, analysis_context=body.analysis_context)
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


# ── Pure data-driven feature selection ────────────────────────────────────────

def _numeric_vals(features: list, prop: str) -> List[float]:
    out = []
    for f in features:
        raw = (f.get("properties") or {}).get(prop)
        try:
            out.append(float(raw))
        except (TypeError, ValueError):
            pass
    return out


def _select_features(features: list, hl: MapHighlight) -> list:
    """
    Select features based on annotation_type + filter.property,
    using real data percentiles — never trusting the LLM's threshold value.

    annotation_type drives the selection intent:
      cluster_hull / gap_zone  → features in the bottom or top quartile
                                  (op direction decides which quartile)
      worst_cells              → bottom top_n by property value
      best_cells               → top top_n by property value
      centroid_label           → all features that match the string op (eq/in),
                                  or top half by value for numeric ops

    For string ops (eq, in) we always try an exact match first.
    """
    prop  = hl.filter.property
    op    = hl.filter.op
    atype = hl.annotation_type
    n     = max(1, hl.top_n)

    # ── String / categorical ops — try exact match, no percentile needed ──────
    if op in ("eq", "in"):
        val = hl.filter.value
        candidates = []
        for f in features:
            raw = (f.get("properties") or {}).get(prop)
            if raw is None:
                continue
            if op == "eq" and str(raw) == str(val):
                candidates.append(f)
            elif op == "in" and isinstance(val, list) and str(raw) in [str(v) for v in val]:
                candidates.append(f)
        if candidates:
            return candidates
        # Fallback: most common value for that property
        from collections import Counter
        all_vals = [(f.get("properties") or {}).get(prop) for f in features]
        all_vals = [v for v in all_vals if v is not None]
        if all_vals:
            most_common = Counter(all_vals).most_common(1)[0][0]
            return [f for f in features if (f.get("properties") or {}).get(prop) == most_common]
        return []

    # ── Numeric ops — ignore LLM threshold, use real percentiles ─────────────
    vals = _numeric_vals(features, prop)
    if not vals:
        return []

    arr   = np.array(vals)
    total = len(features)

    # For worst/best: sort and take top-n directly
    if atype == "worst_cells":
        paired = sorted(
            [(float((f.get("properties") or {}).get(prop, np.nan)), f)
             for f in features if (f.get("properties") or {}).get(prop) is not None],
            key=lambda x: x[0]
        )
        return [f for _, f in paired[:n]]

    if atype == "best_cells":
        paired = sorted(
            [(float((f.get("properties") or {}).get(prop, np.nan)), f)
             for f in features if (f.get("properties") or {}).get(prop) is not None],
            key=lambda x: x[0], reverse=True
        )
        return [f for _, f in paired[:n]]

    # For hull/bbox/centroid: use quartile splits based on op direction
    # High values (gt/gte) → top quartile; Low values (lt/lte) → bottom quartile
    if op in ("gt", "gte"):
        threshold = float(np.percentile(arr, 75))
        return [f for f in features
                if (f.get("properties") or {}).get(prop) is not None
                and float((f.get("properties") or {}).get(prop)) >= threshold]
    else:  # lt / lte
        threshold = float(np.percentile(arr, 25))
        return [f for f in features
                if (f.get("properties") or {}).get(prop) is not None
                and float((f.get("properties") or {}).get(prop)) <= threshold]


# ── Geometry builders ─────────────────────────────────────────────────────────

def _geom(feat: dict):
    try:
        from shapely.geometry import shape
        g = feat.get("geometry")
        return shape(g) if g else None
    except Exception:
        return None


def _make_point(coords, props: dict) -> dict:
    return {"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(coords[0], 6), round(coords[1], 6)]},
            "properties": props}


def _make_poly(geom, props: dict) -> dict:
    from shapely.geometry import mapping
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


def _base_props(hl: MapHighlight) -> dict:
    return {"ai_label": hl.label, "ai_color": hl.color,
            "ai_description": hl.description, "ai_group": hl.id}


def _hull(geoms, hl: MapHighlight) -> Optional[dict]:
    from shapely.ops import unary_union
    try:
        hull = unary_union(geoms).convex_hull
        if hull.is_empty or hull.geom_type == "Point":
            return None
        return _make_poly(hull.buffer(0.0002), {**_base_props(hl), "ai_type": "cluster_hull"})
    except Exception:
        return None


def _bbox(geoms, hl: MapHighlight) -> Optional[dict]:
    from shapely.geometry import box
    from shapely.ops import unary_union
    try:
        minx, miny, maxx, maxy = unary_union(geoms).bounds
        return _make_poly(box(minx, miny, maxx, maxy).buffer(0.0004),
                          {**_base_props(hl), "ai_type": "gap_zone"})
    except Exception:
        return None


def _centroid(geoms, hl: MapHighlight) -> Optional[dict]:
    from shapely.ops import unary_union
    try:
        c = unary_union(geoms).centroid
        return _make_point((c.x, c.y), {**_base_props(hl), "ai_type": "centroid_label"})
    except Exception:
        return None


def _ranked_markers(sel_feats, sel_geoms, hl: MapHighlight, descending: bool) -> List[dict]:
    prop = hl.filter.property
    results = []
    for rank, (feat, geom) in enumerate(zip(sel_feats, sel_geoms), 1):
        try:
            c = geom.centroid
        except Exception:
            continue
        p      = feat.get("properties") or {}
        raw    = p.get(prop)
        # Carry area name if present
        name_k = next((k for k in p if k.lower() in
                       ("name","nbhd_name","admin_name","district","governorate",
                        "region","area_name","neighbourhood","city")), None)
        props = {**_base_props(hl),
                 "ai_type":  "best_cells" if descending else "worst_cells",
                 "ai_rank":  rank}
        if name_k and p.get(name_k):
            props["area_name"] = str(p[name_k])
        if raw is not None:
            try:
                props[prop] = round(float(raw), 3)
            except (TypeError, ValueError):
                props[prop] = raw
        results.append(_make_point((round(c.x, 6), round(c.y, 6)), props))
    return results


# ── Main annotate endpoint ────────────────────────────────────────────────────

@router.post("/annotate")
def annotate_endpoint(body: AnnotateRequest = Body(...)):
    """
    Produces NEW annotation geometries (hulls, boxes, ranked markers) derived
    entirely from the actual data distribution — LLM threshold guesses are ignored
    and replaced by real percentile-based splits.
    """
    try:
        features = body.geojson.get("features", [])
        if not features:
            raise HTTPException(status_code=422, detail="GeoJSON has no features.")

        print(f"[AI ANNOTATE] {len(features)} features, "
              f"{len(body.highlights)} highlights, service={body.service}")

        annotation_features: List[dict] = []

        for hl in body.highlights:
            sel = _select_features(features, hl)
            geoms = [g for f in sel if (g := _geom(f)) is not None]

            atype = hl.annotation_type
            print(f"[AI ANNOTATE]   '{hl.label}' ({atype}): {len(sel)} selected / "
                  f"{len(geoms)} with geometry")

            if not geoms:
                continue

            if atype == "cluster_hull":
                feat = _hull(geoms, hl)
                if feat:
                    annotation_features.append(feat)

            elif atype == "gap_zone":
                feat = _bbox(geoms, hl)
                if feat:
                    annotation_features.append(feat)

            elif atype == "worst_cells":
                annotation_features.extend(_ranked_markers(sel, geoms, hl, descending=False))

            elif atype == "best_cells":
                annotation_features.extend(_ranked_markers(sel, geoms, hl, descending=True))

            elif atype == "centroid_label":
                feat = _centroid(geoms, hl)
                if feat:
                    annotation_features.append(feat)

            else:
                # Unknown type — default to hull for polygon data, markers for points
                first_geom_type = geoms[0].geom_type if geoms else ""
                if "Point" in first_geom_type:
                    annotation_features.extend(_ranked_markers(sel, geoms, hl, descending=False))
                else:
                    feat = _hull(geoms, hl)
                    if feat:
                        annotation_features.append(feat)

        print(f"[AI ANNOTATE] → {len(annotation_features)} annotations produced")

        return JSONResponse(content={
            "type":                "FeatureCollection",
            "features":            annotation_features,
            "ai_service":          body.service,
            "ai_annotation_count": len(annotation_features),
        })

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        print(f"[AI ANNOTATE] Error: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Annotation failed: {exc}")
