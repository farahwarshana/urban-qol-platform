/* ============================================================
   details-map.js
   Shared map controls for vector_details.html and raster-details.html:
   basemap switcher, measure tool, annotate tool, export, scale bar,
   coordinates bar — identical to dashboard.js behaviour.

   Expects: `map` (Leaflet map instance) defined before this script runs.
   Call initDetailsMapControls(map) after the map is created.
   ============================================================ */

/* ── State ─────────────────────────────────────────────────── */
let _detailsCurrentBasemap = null;

const measureState = {
  active: false,
  sessionPoints: [],
  totalDistance: 0,
  markers: [],
  lines: [],
  labels: [],
  previewLine: null
};

const annotateState = {
  active: false,
  drawing: false,
  color: '#e74c3c',
  eraser: false,
  brushSize: 4,
  eraserSize: 18
};

let _annotateCanvas = null;
let _annotateCtx    = null;
let _annotateOverlay = null;
let _measureOverlay  = null;
let _measureIgnoreNextClick = false;
let _detailsMap = null; // set by initDetailsMapControls

/* ── Entry point ───────────────────────────────────────────── */
function initDetailsMapControls(mapInstance) {
  _detailsMap = mapInstance;
  _initHud();
  _initBasemapCloseOnOutsideClick();
  _initExportMenuCloseOnOutsideClick();
}

/* ============================================================
   HUD: scale bar + coordinates
   ============================================================ */
function _initHud() {
  const coordsEl = document.getElementById('mapCoords');
  const lineEl   = document.getElementById('mapScaleLine');
  const labelEl  = document.getElementById('mapScaleLabel');
  if (!coordsEl || !lineEl || !labelEl) return;

  const NICE = [1,2,5,10,20,50,100,200,500,1000,2000,5000,10000,20000,50000,100000,200000,500000,1000000];
  const TARGET_PX = 80;

  function updateScale() {
    const center = _detailsMap.getCenter();
    const zoom   = _detailsMap.getZoom();
    const mPerPx = (156543.03392 * Math.cos(center.lat * Math.PI / 180)) / Math.pow(2, zoom);
    const target = mPerPx * TARGET_PX;
    let best = NICE[0];
    for (const d of NICE) { if (Math.abs(d - target) < Math.abs(best - target)) best = d; }
    lineEl.style.width = (best / mPerPx) + 'px';
    labelEl.textContent = best >= 1000 ? (best / 1000) + ' km' : best + ' m';
  }

  _detailsMap.on('mousemove', function(e) {
    coordsEl.textContent = e.latlng.lat.toFixed(5) + ', ' + e.latlng.lng.toFixed(5);
  });
  _detailsMap.on('mouseout', function() { coordsEl.textContent = '— , —'; });
  _detailsMap.on('zoomend moveend', updateScale);
  updateScale();
}

/* ============================================================
   BASEMAP
   ============================================================ */
function toggleBasemapMenu() {
  document.getElementById('basemapMenu').classList.toggle('open');
}

function changeBasemap(name) {
  if (_detailsCurrentBasemap) _detailsMap.removeLayer(_detailsCurrentBasemap);
  const urls = {
    dark:    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    voyager: 'https://tiledbasemaps.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    light:   'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_labels_under/{z}/{x}/{y}{r}.png',
  };
  const attrs = {
    dark:    '© CARTO © OpenStreetMap',
    voyager: '© Esri © OpenStreetMap',
    light:   '© CARTO © OpenStreetMap',
  };
  _detailsCurrentBasemap = L.tileLayer(urls[name] || urls.light, { attribution: attrs[name] || attrs.light });
  _detailsCurrentBasemap.addTo(_detailsMap);
  _detailsCurrentBasemap.setZIndex(0);
  document.getElementById('basemapMenu').classList.remove('open');
}

function _initBasemapCloseOnOutsideClick() {
  document.addEventListener('click', function(e) {
    const menu = document.getElementById('basemapMenu');
    if (menu && !menu.contains(e.target)) menu.classList.remove('open');
  });
}

/* ============================================================
   MEASURE
   ============================================================ */
function haversineMeters(a, b) {
  const R = 6371000;
  const φ1 = a.lat * Math.PI / 180, φ2 = b.lat * Math.PI / 180;
  const Δφ = (b.lat - a.lat) * Math.PI / 180, Δλ = (b.lng - a.lng) * Math.PI / 180;
  const s = Math.sin(Δφ/2)**2 + Math.cos(φ1)*Math.cos(φ2)*Math.sin(Δλ/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1-s));
}
function formatDist(m) { return m >= 1000 ? (m/1000).toFixed(2)+' km' : Math.round(m)+' m'; }
function measureMidpoint(a, b) { return L.latLng((a.lat+b.lat)/2,(a.lng+b.lng)/2); }

function measureDistLabel(mid, text) {
  return L.marker(mid, {
    icon: L.divIcon({ className:'', html:`<div class="measure-label">${text}</div>`, iconAnchor:[0,0] }),
    interactive: false, zIndexOffset: 500
  }).addTo(_detailsMap);
}

function measureDrawSegment(a, b) {
  const line = L.polyline([a,b],{color:'#4cc2ff',weight:2,dashArray:'6 5',opacity:0.7,interactive:false}).addTo(_detailsMap);
  const dist = haversineMeters(a, b);
  const label = measureDistLabel(measureMidpoint(a,b), formatDist(dist));
  measureState.lines.push(line);
  measureState.labels.push(label);
  return dist;
}

function measureGetOverlay() {
  if (_measureOverlay) return _measureOverlay;
  _measureOverlay = document.createElement('div');
  _measureOverlay.style.cssText = 'position:absolute;inset:0;z-index:650;cursor:crosshair;display:none;';
  _detailsMap.getContainer().appendChild(_measureOverlay);
  return _measureOverlay;
}

function measureOnOverlayClick(e) {
  if (_measureIgnoreNextClick) { _measureIgnoreNextClick = false; return; }
  const rect = _detailsMap.getContainer().getBoundingClientRect();
  const latlng = _detailsMap.containerPointToLatLng(L.point(e.clientX-rect.left, e.clientY-rect.top));
  const pts = measureState.sessionPoints;
  const marker = L.circleMarker(latlng,{radius:5,color:'#4cc2ff',fillColor:'#ffffff',fillOpacity:1,weight:2,interactive:false}).addTo(_detailsMap);
  measureState.markers.push(marker);
  if (pts.length > 0) {
    const segDist = measureDrawSegment(pts[pts.length-1], latlng);
    measureState.totalDistance += segDist;
  }
  pts.push(latlng);
  measureUpdateTotal();
}

function measureOnOverlayDblClick() {
  _measureIgnoreNextClick = true;
  measureDeactivate();
}

function measureOnOverlayMouseMove(e) {
  if (!measureState.sessionPoints.length) return;
  const rect = _detailsMap.getContainer().getBoundingClientRect();
  const latlng = _detailsMap.containerPointToLatLng(L.point(e.clientX-rect.left, e.clientY-rect.top));
  const last = measureState.sessionPoints[measureState.sessionPoints.length-1];
  if (measureState.previewLine) measureState.previewLine.setLatLngs([last,latlng]);
  else measureState.previewLine = L.polyline([last,latlng],{color:'#4cc2ff',weight:1.5,dashArray:'4 6',opacity:0.45,interactive:false}).addTo(_detailsMap);
}

function measureClearAll() {
  measureState.markers.forEach(m => _detailsMap.removeLayer(m));
  measureState.lines.forEach(l => _detailsMap.removeLayer(l));
  measureState.labels.forEach(l => _detailsMap.removeLayer(l));
  if (measureState.previewLine) _detailsMap.removeLayer(measureState.previewLine);
  Object.assign(measureState,{sessionPoints:[],totalDistance:0,markers:[],lines:[],labels:[],previewLine:null});
  const el = document.getElementById('measureTotal');
  el.style.display = 'none'; el.innerHTML = '';
}

function measureUpdateTotal() {
  const el = document.getElementById('measureTotal');
  if (!measureState.totalDistance && measureState.sessionPoints.length < 2) { el.style.display='none'; return; }
  el.innerHTML = 'Total: ' + formatDist(measureState.totalDistance);
  el.style.display = 'flex';
}

function measureDeactivate() {
  measureState.active = false;
  measureState.sessionPoints = [];
  const btn = document.getElementById('measureBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/ruler--v1.png" alt="ruler--v1"/>Measure';
  btn.classList.remove('btn-active');
  const overlay = measureGetOverlay();
  overlay.style.display = 'none';
  overlay.removeEventListener('click', measureOnOverlayClick);
  overlay.removeEventListener('dblclick', measureOnOverlayDblClick);
  overlay.removeEventListener('mousemove', measureOnOverlayMouseMove);
  if (measureState.previewLine) { _detailsMap.removeLayer(measureState.previewLine); measureState.previewLine = null; }
  if (measureState.totalDistance > 0) {
    const el = document.getElementById('measureTotal');
    el.innerHTML = `Total: ${formatDist(measureState.totalDistance)} <button class="measure-clear-btn" onclick="measureClearAll()">Clear</button>`;
    el.style.display = 'flex';
  }
}

function toggleMeasure() {
  if (measureState.active) { measureDeactivate(); return; }
  measureState.sessionPoints = [];
  measureState.active = true;
  const btn = document.getElementById('measureBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/ruler--v1.png" alt="ruler--v1"/>Cancel';
  btn.classList.add('btn-active');
  const overlay = measureGetOverlay();
  overlay.style.display = 'block';
  overlay.addEventListener('click', measureOnOverlayClick);
  overlay.addEventListener('dblclick', measureOnOverlayDblClick);
  overlay.addEventListener('mousemove', measureOnOverlayMouseMove);
}

/* ============================================================
   ANNOTATE
   ============================================================ */
function annotateGetCanvas() {
  if (_annotateCanvas) return _annotateCanvas;
  const container = _detailsMap.getContainer();
  _annotateCanvas = document.createElement('canvas');
  _annotateCanvas.style.cssText = 'position:absolute;inset:0;z-index:640;pointer-events:none;';
  _annotateCanvas.width = container.offsetWidth;
  _annotateCanvas.height = container.offsetHeight;
  container.appendChild(_annotateCanvas);
  _annotateCtx = _annotateCanvas.getContext('2d');
  new ResizeObserver(() => {
    const img = _annotateCtx.getImageData(0,0,_annotateCanvas.width,_annotateCanvas.height);
    _annotateCanvas.width = container.offsetWidth;
    _annotateCanvas.height = container.offsetHeight;
    _annotateCtx.putImageData(img, 0, 0);
  }).observe(container);
  return _annotateCanvas;
}

function annotateGetOverlay() {
  if (_annotateOverlay) return _annotateOverlay;
  _annotateOverlay = document.createElement('div');
  _annotateOverlay.style.cssText = 'position:absolute;inset:0;z-index:645;cursor:crosshair;display:none;';
  _detailsMap.getContainer().appendChild(_annotateOverlay);
  return _annotateOverlay;
}

function annotatePos(e) {
  const rect = _detailsMap.getContainer().getBoundingClientRect();
  const src = e.touches ? e.touches[0] : e;
  return { x: src.clientX - rect.left, y: src.clientY - rect.top };
}

function annotateOnPointerDown(e) {
  annotateState.drawing = true;
  const { x, y } = annotatePos(e);
  _annotateCtx.beginPath(); _annotateCtx.moveTo(x, y);
  if (annotateState.eraser) {
    _annotateCtx.globalCompositeOperation = 'destination-out';
    _annotateCtx.lineWidth = annotateState.eraserSize;
  } else {
    _annotateCtx.globalCompositeOperation = 'source-over';
    _annotateCtx.strokeStyle = annotateState.color;
    _annotateCtx.lineWidth = annotateState.brushSize;
  }
  _annotateCtx.lineCap = 'round'; _annotateCtx.lineJoin = 'round';
}
function annotateOnPointerMove(e) {
  if (!annotateState.drawing) return;
  const { x, y } = annotatePos(e);
  _annotateCtx.lineTo(x, y); _annotateCtx.stroke();
}
function annotateOnPointerUp() {
  if (!annotateState.drawing) return;
  annotateState.drawing = false; _annotateCtx.closePath();
}

function annotateClearAll() {
  if (_annotateCtx && _annotateCanvas) _annotateCtx.clearRect(0,0,_annotateCanvas.width,_annotateCanvas.height);
}

function annotateSelectTool(type, color, btnEl) {
  document.querySelectorAll('.annotate-color-btn').forEach(b => b.classList.remove('selected'));
  document.getElementById('annotateEraserBtn').classList.remove('selected');
  if (type === 'eraser') { annotateState.eraser = true; }
  else { annotateState.eraser = false; annotateState.color = color; }
  btnEl.classList.add('selected');
}

function annotateDeactivate() {
  annotateState.active = false; annotateState.drawing = false;
  const btn = document.getElementById('annotateBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/windows/32/FFFFFF/sign-up.png" alt="sign-up"/>Annotate';
  btn.classList.remove('btn-active');
  document.getElementById('annotateToolbar').classList.remove('visible');
  _detailsMap.dragging.enable(); _detailsMap.doubleClickZoom.enable();
  const overlay = annotateGetOverlay();
  overlay.style.display = 'none';
  overlay.removeEventListener('mousedown', annotateOnPointerDown);
  overlay.removeEventListener('mousemove', annotateOnPointerMove);
  overlay.removeEventListener('mouseup', annotateOnPointerUp);
  overlay.removeEventListener('mouseleave', annotateOnPointerUp);
  if (_annotateCanvas) _annotateCanvas.style.pointerEvents = 'none';
}

function toggleAnnotate() {
  if (annotateState.active) { annotateDeactivate(); return; }
  annotateState.active = true;
  annotateGetCanvas();
  const btn = document.getElementById('annotateBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/windows/32/FFFFFF/sign-up.png" alt="sign-up"/>Cancel';
  btn.classList.add('btn-active');
  document.getElementById('annotateToolbar').classList.add('visible');
  _detailsMap.dragging.disable(); _detailsMap.doubleClickZoom.disable();
  const overlay = annotateGetOverlay();
  overlay.style.display = 'block';
  overlay.addEventListener('mousedown', annotateOnPointerDown);
  overlay.addEventListener('mousemove', annotateOnPointerMove);
  overlay.addEventListener('mouseup', annotateOnPointerUp);
  overlay.addEventListener('mouseleave', annotateOnPointerUp);
}

/* ============================================================
   EXPORT
   ============================================================ */
function toggleExportMenu() {
  const menu = document.getElementById('exportMenu');
  if (!menu) return;
  const isOpen = menu.classList.toggle('open');
  if (isOpen) {
    const close = function(e) {
      if (!menu.contains(e.target)) { menu.classList.remove('open'); document.removeEventListener('click', close); }
    };
    setTimeout(() => document.addEventListener('click', close), 10);
  }
}

function _initExportMenuCloseOnOutsideClick() {
  // handled inside toggleExportMenu
}

function exportMap(format) {
  format = format.toLowerCase();
  const supported = ['png','jpg','jpeg','tiff'];
  if (!supported.includes(format)) { alert('Unsupported format: ' + format); return; }

  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) { exportBtn.disabled = true; exportBtn.innerHTML = '⏳ Exporting…'; }

  setTimeout(() => {
    try {
      _buildCompositeCanvas(function(canvas) {
        if (exportBtn) {
          exportBtn.disabled = false;
          exportBtn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/ios-filled/50/FFFFFF/download--v1.png" alt="download--v1"/>Export';
        }
        if (!canvas) { alert('Export failed — could not read map canvas.'); return; }
        _encodeAndDownload(canvas, format);
      });
    } catch(err) {
      console.error('[exportMap]', err);
      if (exportBtn) {
        exportBtn.disabled = false;
        exportBtn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/ios-filled/50/FFFFFF/download--v1.png" alt="download--v1"/>Export';
      }
    }
  }, 250);
}

function _getElementOffsetInContainer(el, containerRect) {
  const rect = el.getBoundingClientRect();
  let x = rect.left - containerRect.left, y = rect.top - containerRect.top;
  const t = window.getComputedStyle(el).transform;
  if (t && t !== 'none') {
    const m = t.match(/matrix\(([^)]+)\)/);
    if (m) { const p = m[1].split(','); x += parseFloat(p[4])||0; y += parseFloat(p[5])||0; }
  }
  return { x, y };
}

function _drawTilesOntoCanvas(mapContainer, containerRect, ctx, done) {
  const tiles = Array.from(mapContainer.querySelectorAll('.leaflet-tile-pane img.leaflet-tile'))
    .filter(img => img.complete);
  if (!tiles.length) { done(false); return; }
  let pending = tiles.length, anyDrawn = false;
  tiles.forEach(function(src) {
    const r = src.getBoundingClientRect();
    const dx = r.left - containerRect.left, dy = r.top - containerRect.top;
    const dw = r.width||256, dh = r.height||256;
    const img = new Image(); img.crossOrigin = 'anonymous';
    img.onload = function() {
      try { ctx.drawImage(img, dx, dy, dw, dh); anyDrawn = true; } catch(e) {}
      if (!--pending) done(anyDrawn);
    };
    img.onerror = function() {
      try { ctx.drawImage(src, dx, dy, dw, dh); anyDrawn = true; } catch(e) {}
      if (!--pending) done(anyDrawn);
    };
    img.src = src.src;
  });
}

function _buildCompositeCanvas(callback) {
  const mc = document.querySelector('.leaflet-container');
  if (!mc) { callback(null); return; }
  const w = mc.offsetWidth, h = mc.offsetHeight;
  const exportCanvas = document.createElement('canvas');
  exportCanvas.width = w; exportCanvas.height = h;
  const ctx = exportCanvas.getContext('2d');
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, w, h);
  ctx.save(); ctx.beginPath(); ctx.rect(0, 0, w, h); ctx.clip();
  const cr = mc.getBoundingClientRect();

  _drawTilesOntoCanvas(mc, cr, ctx, function() {
    // Canvas layers (georaster)
    mc.querySelectorAll('canvas').forEach(function(src) {
      if (src === _annotateCanvas || !src.width || !src.height) return;
      try { const off = _getElementOffsetInContainer(src, cr); ctx.drawImage(src, off.x, off.y); } catch(e) {}
    });
    // SVG vector layers
    mc.querySelectorAll('.leaflet-overlay-pane svg').forEach(function(svg) {
      const s = new XMLSerializer().serializeToString(svg);
      const blob = new Blob([s], { type:'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const img = new Image();
      const off = _getElementOffsetInContainer(svg, cr);
      img.onload = function() {
        try { ctx.drawImage(img, off.x, off.y); } catch(e) {}
        URL.revokeObjectURL(url);
      };
      img.onerror = () => URL.revokeObjectURL(url);
      img.src = url;
    });
    // Annotation canvas on top
    if (_annotateCanvas && _annotateCanvas.width) {
      try { ctx.drawImage(_annotateCanvas, 0, 0); } catch(e) {}
    }
    ctx.restore();
    setTimeout(() => callback(exportCanvas), 300);
  });
}

function _encodeAndDownload(canvas, format) {
  const mimeMap = { png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg', tiff:'image/tiff' };
  const mime = mimeMap[format] || 'image/png';
  const quality = (format === 'jpg' || format === 'jpeg') ? 0.92 : undefined;
  const dataUrl = canvas.toDataURL(mime, quality);
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = 'map-export.' + format;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}
