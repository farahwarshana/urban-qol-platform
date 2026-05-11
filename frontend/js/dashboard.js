/* ============================================================
   dashboard.js
   ------------------------------------------------------------
   All dashboard-specific behavior:
     1. Service selection → shows inputs in the right sidebar
     2. "Run Analysis" → switches the right panel to a
        tabbed Results view (Raw / Full / Grid) + insights
     3. Floating AI chatbot
     4. Placeholder Leaflet map init
   ============================================================ */


/* ============================================================
   1. SERVICE DEFINITIONS
   ------------------------------------------------------------
   Each service describes the inputs it needs. The right-sidebar
   form is generated from this object — so adding a new service
   only requires editing this map.
   ============================================================ */
var API_BASE_URL =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "";

// ------------------saveAnalysisToProfile--------------------

function autoSaveCurrentAnalysis() {
  const username = localStorage.getItem('username') || 'default';
  if (!username) return;

  const serviceNames = {
    'ndvi': 'NDVI Analysis',
    'heat-index': 'Heat Index',
    'crime': 'Crime Density',
    'urban-density': 'Urban Density',
    'public-transport': 'Public Transport Coverage',
    'vegetation': 'Vegetation Density',
    'traffic': 'Traffic Analysis',
    'informal-settlement': 'Informal Settlement',
    'air-quality': 'Air Quality Index',
    'facility-accessibility': 'Facility Accessibility'
  };

  const title = serviceNames[lastResultService] || lastResultService;
  
  const panel = document.getElementById('analysisPanel');
  const scoreEl = panel ? panel.querySelector('.insight-card .value') : null;
  const scoreMatch = scoreEl ? scoreEl.textContent.match(/(\d+)\s*\/\s*100/) : null;
  const score = scoreMatch ? parseInt(scoreMatch[1]) : 50;
  const status = score >= 75 ? 'high' : score >= 40 ? 'mid' : 'low';


  fetch(`${API_BASE_URL}/analyses?username=${username}`, {
  // fetch(`http://localhost:8000/analyses?username=${username}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: lastResultService,
      title: title,
      area: '',
      score: score,
      status: status
    })
  }).catch(e => console.warn('Could not save analysis:', e));
}
// ---------------------------------------------------------------
const SERVICES = {
  "urban-density": {
    title: "Urban Density",
    desc: "Estimate population density across an area.",
    inputs: [
      { type: "file", id: "geoJsonInput", label: "Upload boundary data (GeoJSON)" },
      { type: "text", id: "populationField", label: "Population field name", placeholder: "e.g. population, pop" }
    ],
  },
  "public-transport": {
    title: "Public Transport Coverage",
    desc: "Analyze walking coverage of transit stations within an area of interest.",
    inputs: [
      { type: "file",   id: "stationsInput",    label: "Upload transit stations (GeoJSON points)" },
      { type: "file",   id: "aoiInput",          label: "Upload area of interest (GeoJSON polygon)" },
      { type: "tip",    text: "Recommended urban public transport coverage is within 500–1000 walking metres." },
      { type: "number", id: "walkingDistance",   label: "Walking distance (metres)", value: 1000 },
      { type: "number", id: "populationCount",   label: "Total population in area (optional)", value: "" },
    ],
  },
  "facility_Accessibility_index": {
    title: "Facility Accessibility Index",
    desc: "Compute 5, 10, and 15-minute walking service areas for every facility point in your dataset.",
    inputs: [
      { type: "file",   id: "facilitiesGeojsonInput", label: "Upload facilities layer (GeoJSON)" },
      { type: "number", id: "walkingSpeedInput",       label: "Walking speed (km/h)",            value: 4.5  },
      { type: "number", id: "networkDistInput",        label: "Network download radius (meters)", value: 2000 },
      { type: "tip",    text: "All points in the uploaded file will be analysed. Larger datasets and wider radii take longer." },
    ],
    action: runFacilityAccessibilityAnalysis
  },

  "heat-index": {
    title: "Heat Index",
    desc: "Surface heat analysis from raster data.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "vegetation": {
    title: "Vegetation Density",
    desc: "Analyse how much of your area meets the 30% urban greenery standard.",
    inputs: [
      { type: "file",   id: "tiffInput",    label: "Upload satellite raster (GeoTIFF)" },
      { type: "number", id: "vegThreshold", label: "Vegetation Threshold. Recommended: 0.3", value: 0.3 },
    ],
  },
  "ndvi": {
    title: "NDVI",
    desc: "Normalized Difference Vegetation Index from raster.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "crime": {
    title: "Safety / Crime Density",
    desc: "Hotspot analysis from incident points.",
    inputs: [
      { type: "file", id: "csvInput", label: "Upload crime data (CSV)" },
      { type: "file", id: "geoJsonInput", label: "Upload boundary data (GeoJSON)" },
      { type: "text", id: "latField", label: "Latitude column name", placeholder: "Auto-detected from CSV", autoDetect: true },
      { type: "text", id: "lonField", label: "Longitude column name", placeholder: "Auto-detected from CSV", autoDetect: true },
      { type: "number", id: "crimePopInput", label: "Total population (optional — enables per-capita comparison)" },
    ],
  },
  "traffic": {
    title: "Traffic Analysis",
    desc: "Analyse road density and congestion hotspots within an area of interest.",
    inputs: [
      { type: "file",   id: "roadsInput",  label: "Upload road network (GeoJSON LineStrings)" },
      { type: "file",   id: "aoiInput",    label: "Upload area of interest (GeoJSON polygon)" },
      { type: "number", id: "populationInput", label: "Population (optional — enables traffic pressure)" },
    ],
  },
  "informal-settlement": {
    title: "Informal Settlement Pattern Analysis",
    desc: "Detect informal settlement patterns from satellite/aerial imagery using texture, edge density, and built-up crowding analysis.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload satellite/aerial imagery (GeoTIFF)" },
    ],
  },
  "air-quality": {
    title: "Air Quality Index",
    desc: "Classify PM2.5, PM10, NO2, or AQI raster into 6 AQI categories and map air quality.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload pollutant raster (GeoTIFF — PM2.5, PM10, NO2, or AQI)" },
    ],
  },
  "expansion": {
    title: "Future Expansion Suitability",
    desc: "Combine multiple analyses to score expansion areas.",
    inputs: [
      { type: "text", id: "weights", label: "Analysis weights (comma list, e.g. 0.3,0.5,0.2)" },
    ],
    isExpansion: true,
  },
};


/* ============================================================
   2. SERVICE SELECTION
   ============================================================ */
const serviceList   = document.getElementById("serviceList");
console.log("serviceList =", serviceList);
const analysisPanel = document.getElementById("analysisPanel");



serviceList.addEventListener("click", function (e) {
  const li = e.target.closest("li[data-service]");
  if (!li) return;

  // Highlight the selected service
  serviceList.querySelectorAll("li").forEach(el => el.classList.remove("active"));
  li.classList.add("active");

  const key = li.getAttribute("data-service");
  renderServicePanel(key);
});


/* ---------- Render the right sidebar based on selection ---------- */
function renderServicePanel(key) {
  const service = SERVICES[key];
  if (!service) return;

  clearMap();
  inputLayer = null;
  resultLayer = null;

  // Special case for the "Future Expansion Suitability" flow
  if (service.isExpansion) {
    renderExpansionPanel(service);
    return;
  }

  // Build the input fields HTML from the SERVICES config
  const fieldsHtml = service.inputs.map(field => {
    if (field.type === "file") {
      // TODO: We only want to accept certain file formats so we have to add them per service in the array
      return `
        <div class="form-group">
          <label for="${field.id}">${field.label}</label>
          <input type="file" id="${field.id}" />
        </div>`;
    }
    if (field.type === "number") {
      const labelHtml = field.label.replace(/\(optional\b([^)]*)\)/i, (m, rest) =>
        `(<em style="color:var(--accent);font-style:italic;font-weight:500;">optional</em>${rest})`
      );
      return `
        <div class="form-group">
          <label for="${field.id}">${labelHtml}</label>
          <input type="number" id="${field.id}" value="${field.value ?? ""}" />
        </div>`;
    }
    if (field.type === "select") {
      const optionsHtml = field.options.map(opt =>
        `<option value="${opt.value}" ${opt.selected ? 'selected' : ''}>${opt.label}</option>`
      ).join("");
      return `
        <div class="form-group">
          <label for="${field.id}">${field.label}</label>
          <select id="${field.id}" class="form-select">
            ${optionsHtml}
          </select>
        </div>`;
    }
    if (field.type === "tip") {
      return `<div style="background:rgba(76,194,255,0.10);border-left:3px solid var(--accent);border-radius:4px;padding:7px 10px;margin-bottom:6px;font-size:11.5px;color:var(--text-primary);">💡 ${field.text}</div>`;
    }
    if (field.type === "custom") {
      return field.html;
    }
    // default: text
    return `
      <div class="form-group">
        <label for="${field.id}">${field.label}</label>
        <input type="text" id="${field.id}" placeholder="${field.placeholder || ""}" />
        ${field.id === "populationField" ? `<small id="populationFieldHint" class="text-muted" style="display:none;">Auto-detected — you can edit this.</small>` : ""}
        ${field.autoDetect ? `<small id="${field.id}Hint" class="text-muted" style="display:none;">Auto-detected — you can edit this.</small>` : ""}
      </div>`;
  }).join("");

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">${service.title}</h3>
      <p class="panel-desc">${service.desc}</p>

      <!-- STEP 1 + 2 — required inputs / upload UI -->
      ${fieldsHtml}

      <!-- STEP 3 — Run Analysis button -->
      <button class="btn btn-primary btn-block btn-lg mt-3"
              onclick="runAnalysis('${key}')">
        ▶ Run Analysis
      </button>
    </div>
  `;

  // Attach event listeners after HTML is rendered
  attachFileInputListeners();
}

function clearMap() {
  map.eachLayer(function (layer) {
    console.log("layer:" , layer)
    if (layer !== currentBasemap) {
      map.removeLayer(layer);
    }
  });
  disableNdviProbe();
}
/* ---------- Special panel: Future Expansion Suitability ---------- */
function renderExpansionPanel(service) {
  clearMap();

  // Provide checkboxes for combining multiple previous analyses.
  const otherKeys = Object.keys(SERVICES).filter(k => k !== "expansion");
  const checkboxes = otherKeys.map(k => `
    <div class="form-check" style="margin: 4px 0;">
      <input class="form-check-input" type="checkbox" value="${k}" id="chk-${k}" />
      <label class="form-check-label" for="chk-${k}">${SERVICES[k].title}</label>
    </div>
  `).join("");

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">${service.title}</h3>
      <p class="panel-desc">${service.desc}</p>

      <label class="text-muted" style="font-size:12px; text-transform:uppercase;">
        Combine analyses
      </label>
      <div class="mt-2">${checkboxes}</div>

      <div class="form-group mt-3">
        <label for="weights">Weights (comma list)</label>
        <input type="text" id="weights" placeholder="0.3, 0.5, 0.2" />
      </div>

      <button class="btn btn-primary btn-block btn-lg mt-3"
              onclick="runAnalysis('expansion')">
        ▶ Compute Best Expansion Areas
      </button>
    </div>
  `;

  // Attach event listeners after HTML is rendered
  attachFileInputListeners();
}


/* ============================================================
   3. RUN ANALYSIS — switches the panel to the Results view
   ============================================================ */
// function runAnalysis(key) {
//   const service = SERVICES[key];  ضيفت بدالها السطر الجاي

function runAnalysis(key) {
  document.getElementById('analysisPanel').dataset.saved = '';

  if (key === "facility_Accessibility_index") {
  runFacilityAccessibilityAnalysis();
  return;
}

  if (key === "ndvi") {
    runNDVIAnalysis();
    return;
  }

  if (key === "heat-index") {
  runHeatIndexAnalysis();
  return;
  }

  if (key === "crime") {
    runCrimeAnalysis();
    return;
  }

  if (key === "urban-density") {
    runUrbanDensityAnalysis();
    return;
  }

  if (key === "public-transport") {
    runPublicTransportAnalysis();
    return;
  }

  if (key === "vegetation") {
    runVegetationAnalysis();
    return;
  }

  if (key === "traffic") {
    runTrafficAnalysis();
    return;
  }

  if (key === "informal-settlement") {
    runInformalSettlementAnalysis();
    return;
  }

  if (key === "air-quality") {
    runAirQualityAnalysis();
    return;
  }

  renderResults(service);
}


/* ---------- NDVI Analysis - calls backend API ---------- */
async function runNDVIAnalysis() {
  const tiffInput = document.getElementById("tiffInput");

  if (!tiffInput || !tiffInput.files[0]) {
    alert("Please upload a GeoTIFF file first.");
    return;
  }

  const file = tiffInput.files[0];
  const inputs = { fileName: file.name };

  const formData = new FormData();
  formData.append("geotiff", file);

  // Show loading state
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">NDVI — Processing</h3>
      <p class="panel-desc">Calculating NDVI from uploaded raster...</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
      </div>
    </div>
  `;

  try {
    const response = await fetch(`${API_BASE_URL}/calculate-ndvi`, {
    // const response = await fetch("http://localhost:8000/calculate-ndvi", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    // Get NDVI stats from response headers
    const ndviMin = response.headers.get("X-NDVI-Min");
    const ndviMax = response.headers.get("X-NDVI-Max");
    const ndviMean = response.headers.get("X-NDVI-Mean");
    const validPixels = response.headers.get("X-Valid-Pixels");
    const redBand      = response.headers.get("X-Red-Band");
    const nirBand      = response.headers.get("X-NIR-Band");
    const satellite    = response.headers.get("X-Satellite");
    const ndviStddev   = response.headers.get("X-NDVI-Stddev");
    const imgWidth     = response.headers.get("X-Img-Width");
    const imgHeight    = response.headers.get("X-Img-Height");
    const pixelSizeX   = response.headers.get("X-Pixel-Size-X");
    const pixelSizeY   = response.headers.get("X-Pixel-Size-Y");
    const pixelUnit    = response.headers.get("X-Pixel-Unit") || "";
    const pctNoVeg     = response.headers.get("X-Pct-No-Veg");
    const pctBareSoil  = response.headers.get("X-Pct-Bare-Soil");
    const pctModerate  = response.headers.get("X-Pct-Moderate");
    const pctDense     = response.headers.get("X-Pct-Dense");

    // Convert response to array buffer
    const arrayBuffer = await response.arrayBuffer();
    // Keep a copy for the grid endpoint (slice() creates a detached copy)
    lastResultBlob    = arrayBuffer.slice(0);
    lastResultService = "ndvi";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

    // Render the NDVI result: low NDVI → red, high NDVI → green
    const ndviMinF = parseFloat(ndviMin);
    const ndviMaxF = parseFloat(ndviMax);
    const ndviRange = ndviMaxF - ndviMinF || 1;
    resultLayer = await renderGeoRasterFromArrayBuffer(arrayBuffer, {
      opacity: 0.9,
      resolution: 256,
      colorFn: (values) => {
        const v = values[0];
        if (v === undefined || v === null || isNaN(v) || v < -1.5 || v > 1.5) return null;
        const t = Math.max(0, Math.min(1, (v - ndviMinF) / ndviRange));
        // red (200,20,0) → yellow (220,200,0) → green (0,150,0)
        let r, g, b;
        if (t < 0.5) {
          const s = t / 0.5;
          r = Math.round(200 - s * 20);   // 200 → 180 (stays reddish into yellow)
          g = Math.round(20  + s * 180);  // 20  → 200
          b = 0;
        } else {
          const s = (t - 0.5) / 0.5;
          r = Math.round(180 - s * 180);  // 180 → 0
          g = Math.round(200 - s * 50);   // 200 → 150
          b = 0;
        }
        return `rgba(${r},${g},${b},0.9)`;
      },
    });

    // Enable NDVI pixel probe on the map
    enableNdviProbe(resultLayer);

    // Render results panel with NDVI stats
    renderNDVIResults({
      min: ndviMin,
      max: ndviMax,
      mean: ndviMean,
      valid_pixels: validPixels,
      red_band:     redBand,
      nir_band:     nirBand,
      satellite:    satellite,
      stddev:       ndviStddev,
      img_width:    imgWidth,
      img_height:   imgHeight,
      pixel_size_x: pixelSizeX,
      pixel_size_y: pixelSizeY,
      pixel_unit:   pixelUnit,
      pct_no_veg:   pctNoVeg,
      pct_bare_soil: pctBareSoil,
      pct_moderate: pctModerate,
      pct_dense:    pctDense,
    }, inputs);

  } catch (error) {
    console.error("NDVI calculation error:", error);
    
    // Try to get error details from response
    let errorMessage = error.message;
    
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate NDVI: ${errorMessage}</p>
        <div class="alert alert-warning mt-2">
          <strong>Note:</strong> Make sure you're using the correct satellite type for your GeoTIFF.
          <br>• Landsat: Band 4 (Red), Band 5 (NIR)
          <br>• Sentinel-2: Band 4 (Red), Band 8 (NIR)
        </div>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('ndvi')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}


/* ---------- Crime Analysis - calls backend API ---------- */
async function runCrimeAnalysis() {
  const csvInput = document.getElementById("csvInput");
  const geoJsonInput = document.getElementById("geoJsonInput");
  const latField = document.getElementById("latField");
  const lonField = document.getElementById("lonField");
  
  if (!csvInput || !csvInput.files[0]) {
    alert("Please upload a CSV file with crime data first.");
    return;
  }

  if (!geoJsonInput || !geoJsonInput.files[0]) {
    alert("Please upload a GeoJSON file with boundary data first.");
    return;
  }

  const latFieldValue = latField ? latField.value.trim() : "";
  const lonFieldValue = lonField ? lonField.value.trim() : "";
  const popEl = document.getElementById("crimePopInput");
  const totalPopulation = popEl && popEl.value ? parseInt(popEl.value) : null;

  const csvFile = csvInput.files[0];
  const geoJsonFile = geoJsonInput.files[0];
  const inputs = {
    csvFileName: csvFile.name,
    geoJsonFileName: geoJsonFile.name,
    latField: latFieldValue || "auto-detected",
    lonField: lonFieldValue || "auto-detected",
    totalPopulation,
  };

  // Parse crime type counts directly from the CSV file
  window._crimeTypeCounts = {};
  await new Promise(resolve => {
    const reader = new FileReader();
    reader.onload = function(e) {
      try {
        const lines = e.target.result.trim().split('\n');
        if (lines.length < 2) { resolve(); return; }
        const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
        const _typeRoots = ["offense","crime","incident","violation","charge","category","classification","nature","description","ucr","primary_type","event_type","call_type","report_type"];
        const typeCol = headers.find(h => _typeRoots.some(root => h.toLowerCase().replace(/\s+/g, "_").includes(root)));
        if (typeCol != null) {
          const typeIndex = headers.indexOf(typeCol);
          for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
            if (values[typeIndex]) {
              const t = values[typeIndex];
              window._crimeTypeCounts[t] = (window._crimeTypeCounts[t] || 0) + 1;
            }
          }
        }
      } catch(err) { console.warn("Crime type parsing failed:", err); }
      resolve();
    };
    reader.readAsText(csvFile);
  });

  const formData = new FormData();
  formData.append("csv", csvFile);
  formData.append("geojson", geoJsonFile);

  // Show loading state
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Crime Density — Processing</h3>
      <p class="panel-desc">Calculating crime density from uploaded data...</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
      </div>
    </div>
  `;

  try {
    const params = new URLSearchParams();
    if (latFieldValue) params.set("lat_field", latFieldValue);
    if (lonFieldValue) params.set("lon_field", lonFieldValue);

    const url = `${API_BASE_URL}/calculate-crime-density${params.toString() ? "?" + params.toString() : ""}`;
    // const url = `http://localhost:8000/calculate-crime-density${params.toString() ? "?" + params.toString() : ""}`;
    
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    // Get crime density stats from response headers
    const crimeCount = response.headers.get("X-Crime-Count");
    const areaCount = response.headers.get("X-Area-Count");
    const avgDensity = response.headers.get("X-Avg-Density");
    const maxDensity = response.headers.get("X-Max-Density");

    // Render the crime density result on the map as GeoJSON
    const geojsonData = await response.json();

    // Store for grid analysis
    lastResultBlob    = geojsonData;
    lastResultService = "crime";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

    if (inputLayer) {
      map.removeLayer(inputLayer);
    }
    clearMap();

    resultLayer = L.geoJSON(geojsonData, {
      style: function(feature) {
        const density = feature.properties.crime_density || 0;
        // Color gradient from green (low crime) to red (high crime)
        let color = '#2ecc71'; // green
        if (density > 5) color = '#f1c40f'; // yellow
        if (density > 10) color = '#e67e22'; // orange
        if (density > 15) color = '#e74c3c'; // red
        if (density > 20) color = '#891508'; // dark red
        return {
          fillColor: color,
          fillOpacity: 0.6,
          color: '#333',
          weight: 1
        };
      },
      onEachFeature: function(feature, layer) {
        const props = feature.properties;
        const info = `
          <strong>Area:</strong> ${props.NBHD_NAME || props.name || 'Unknown'}<br>
          <strong>Crime Count:</strong> ${props.crime_count || 0}<br>
          <strong>Crime Density:</strong> ${props.crime_density?.toFixed(2) || 0} /km²
        `;
        layer.bindPopup(info);
      }
    }).addTo(map);

    // Fit bounds
    try {
      const bounds = resultLayer.getBounds();
      if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    } catch (boundsError) {
      console.warn("Could not fit bounds:", boundsError);
    }

    // Render results panel with crime density stats
    renderCrimeResults({
      crime_count: crimeCount,
      area_count: areaCount,
      avg_density: avgDensity,
      max_density: maxDensity,
    }, inputs, geojsonData);

  } catch (error) {
    console.error("Crime density calculation error:", error);
    
    // Try to get error details from response
    let errorMessage = error.message;
    
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate crime density: ${errorMessage}</p>
        <div class="alert alert-warning mt-2">
          <strong>Note:</strong> Make sure your CSV has columns for latitude and longitude, or that they can be auto-detected (e.g. <code>lat</code>, <code>lon</code>, <code>x</code>, <code>y</code>).
          ${latFieldValue ? `<br>• Latitude column used: ${latFieldValue}` : "<br>• Latitude column: auto-detection failed"}
          ${lonFieldValue ? `<br>• Longitude column used: ${lonFieldValue}` : "<br>• Longitude column: auto-detection failed"}
        </div>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('crime')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}


/* ---------- Urban Density Analysis - calls backend API ---------- */
async function runUrbanDensityAnalysis() {
  const geoJsonInput = document.getElementById("geoJsonInput");
  const populationField = document.getElementById("populationField");
  
  if (!geoJsonInput || !geoJsonInput.files[0]) {
    alert("Please upload a GeoJSON file with boundary data first.");
    return;
  }

  const populationFieldValue = populationField ? populationField.value.trim() : "";

  if (!populationFieldValue) {
    alert("Please enter the population field name.");
    return;
  }

  const geoJsonFile = geoJsonInput.files[0];
  const inputs = {
    geoJsonFileName: geoJsonFile.name,
    populationField: populationFieldValue,
  };

  const formData = new FormData();
  formData.append("geojson", geoJsonFile);
  formData.append("population_field", populationFieldValue);

  // Show loading state
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Urban Density — Processing</h3>
      <p class="panel-desc">Calculating urban density from uploaded data...</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
      </div>
    </div>
  `;

  try {
    // const url = `http://localhost:8000/calculate-urban-density?population_field=${encodeURIComponent(populationFieldValue)}`;
    const url = `${API_BASE_URL}/calculate-urban-density?population_field=${encodeURIComponent(populationFieldValue)}`;
    
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    // Get urban density stats from response headers
    const totalPopulation = response.headers.get("X-Total-Population");
    const totalArea = response.headers.get("X-Total-Area");
    const areaCount = response.headers.get("X-Area-Count");
    const avgDensity = response.headers.get("X-Avg-Density");
    const maxDensity = response.headers.get("X-Max-Density");

    // Render the urban density result on the map as GeoJSON
    const geojsonData = await response.json();

    // Detect the name field from the first feature's properties
    const nameFieldPatterns = /\b(name|nombre|nom|bezeichnung|area|region|district|zone|ward|neighborhood|neighbourhood|locality|title|label|admin)\b/i;
    const firstProps = geojsonData.features?.[0]?.properties || {};
    const nameKey = Object.keys(firstProps).find(k => nameFieldPatterns.test(k) && k !== "area_km2") || null;

    // Store for grid analysis
    lastResultBlob    = geojsonData;
    lastResultService = "urban-density";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

    if (inputLayer) {
      map.removeLayer(inputLayer);
    }
    clearMap();

    resultLayer = L.geoJSON(geojsonData, {
      style: function(feature) {
        const density = feature.properties.urban_density || 0;
        // Color gradient from light blue (low density) to dark blue (high density)
        let color = '#add8e6'; // light blue
        if (density > 100) color = '#87ceeb'; // sky blue
        if (density > 500) color = '#4682b4'; // steel blue
        if (density > 1000) color = '#4169e1'; // royal blue
        if (density > 2000) color = '#000080'; // navy
        return {
          fillColor: color,
          fillOpacity: 0.6,
          color: '#333',
          weight: 1
        };
      },
      onEachFeature: function(feature, layer) {
        const props = feature.properties;
        const areaName = (nameKey && props[nameKey]) ? props[nameKey] : 'Unknown';
        const info = `
          <strong>Area:</strong> ${areaName}<br>
          <strong>Population:</strong> ${props[populationFieldValue] || 0}<br>
          <strong>Area (km²):</strong> ${props.area_km2?.toFixed(2) || 0} km²<br>
          <strong>Urban Density:</strong> ${props.urban_density?.toFixed(2) || 0} /km²
        `;
        layer.bindPopup(info);
      }
    }).addTo(map);

    // Fit bounds
    try {
      const bounds = resultLayer.getBounds();
      if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    } catch (boundsError) {
      console.warn("Could not fit bounds:", boundsError);
    }

    // Render results panel with urban density stats
    renderUrbanDensityResults({
      total_population: totalPopulation,
      total_area: totalArea,
      area_count: areaCount,
      avg_density: avgDensity,
      max_density: maxDensity,
    }, inputs, geojsonData, nameKey);

  } catch (error) {
    console.error("Urban density calculation error:", error);
    
    // Try to get error details from response
    let errorMessage = error.message;
    
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate urban density: ${errorMessage}</p>
        <div class="alert alert-warning mt-2">
          <strong>Note:</strong> Make sure your GeoJSON has a column for population.
          <br>• Population column: ${populationFieldValue}
        </div>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('urban-density')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}

/*---------------------facility accessibility-------------------------*/
async function runFacilityAccessibilityAnalysis() {
  const facilitiesInput = document.getElementById("facilitiesGeojsonInput");

  if (!facilitiesInput || !facilitiesInput.files[0]) {
    alert("Please upload a GeoJSON file with facility points.");
    return;
  }

  const facilitiesFile = facilitiesInput.files[0];
  const walkingSpeed   = parseFloat(document.getElementById("walkingSpeedInput")?.value) || 4.5;
  const networkDist    = parseInt(document.getElementById("networkDistInput")?.value)    || 2000;

  const inputs = {
    facilitiesFileName: facilitiesFile.name,
    walkingSpeed,
    networkDist,
  };

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Facility Accessibility — Processing</h3>
      <p class="panel-desc">Downloading walking networks and computing isochrones for every facility point…</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading…</span>
        </div>
      </div>
    </div>
  `;

  try {
    const formData = new FormData();
    formData.append("facilities_geojson", facilitiesFile);

    const url = `${API_BASE_URL}/calculate-facility-accessibility?walking_speed_kmh=${walkingSpeed}&network_dist_m=${networkDist}`;
    // const url = `http://localhost:8000/calculate-facility-accessibility?walking_speed_kmh=${walkingSpeed}&network_dist_m=${networkDist}`;
    const response = await fetch(url, { method: "POST", body: formData });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP error ${response.status}`);
    }

    const totalFacilities     = response.headers.get("X-Total-Facilities");
    const facilitiesProcessed = response.headers.get("X-Facilities-Processed");
    const walkingSpeedHdr     = response.headers.get("X-Walking-Speed-Kmh");
    const networkDistHdr      = response.headers.get("X-Network-Dist-M");
    const pct5min             = response.headers.get("X-Pct-5min");
    const pct10min            = response.headers.get("X-Pct-10min");
    const pct15min            = response.headers.get("X-Pct-15min");

    const geojsonData = await response.json();

    lastResultBlob    = geojsonData;
    lastResultService = "facility-accessibility";

    if (gridLayer)  { map.removeLayer(gridLayer);  gridLayer  = null; }
    if (inputLayer)   map.removeLayer(inputLayer);
    clearMap();

    // Result layer: isochrone zones coloured by walk-time band
    resultLayer = L.geoJSON(geojsonData, {
      style: function(feature) {
        const t = feature.properties.time_min;
        if (t === 5)  return { color: "#198754", fillColor: "#198754", fillOpacity: 0.40, weight: 1.5 };
        if (t === 10) return { color: "#ffc107", fillColor: "#ffc107", fillOpacity: 0.32, weight: 1.5 };
        return              { color: "#dc3545", fillColor: "#dc3545", fillOpacity: 0.24, weight: 1.5 };
      },
      onEachFeature: function(feature, layer) {
        const p = feature.properties;
        layer.bindPopup(
          `<strong>${p.category || ("Within " + p.time_min + " min")}</strong><br>` +
          `Walk time: ${p.time_min} min<br>` +
          `Facilities: ${p.facility_count}`
        );
      }
    }).addTo(map);

    // Input layer: facility point markers (shown in Raw Data tab)
    try {
      const gj = JSON.parse(await facilitiesFile.text());
      inputLayer = L.geoJSON(gj, {
        pointToLayer: function(feature, latlng) {
          return L.circleMarker(latlng, {
            radius: 5, fillColor: "#4cc2ff", color: "#1a8fc1",
            weight: 1.5, opacity: 1, fillOpacity: 0.9,
          });
        },
        onEachFeature: function(feature, layer) {
          const p = feature.properties || {};
          const nameKey = Object.keys(p).find(k => /^name$/i.test(k) || /^title$/i.test(k));
          layer.bindPopup(`<strong>${nameKey ? p[nameKey] : "Facility"}</strong>`);
        }
      });
    } catch(err) { console.warn("Could not build input layer from facilities file:", err); }

    try {
      const bounds = resultLayer.getBounds();
      if (bounds && bounds.isValid()) map.fitBounds(bounds, { padding: [50, 50] });
    } catch(e) { console.warn("Could not fit bounds:", e); }

    renderFacilityAccessibilityResults({
      total_facilities:     totalFacilities,
      facilities_processed: facilitiesProcessed,
      walking_speed_kmh:    walkingSpeedHdr,
      network_dist_m:       networkDistHdr,
      pct_5min:             pct5min,
      pct_10min:            pct10min,
      pct_15min:            pct15min,
    }, inputs, geojsonData);

  } catch (error) {
    console.error("Facility Accessibility error:", error);
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate facility accessibility: ${error.message}</p>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('facility_Accessibility_index')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}
/* ---------- Public Transport Analysis - calls backend API ---------- */
async function runPublicTransportAnalysis() {
  const stationsInput     = document.getElementById("stationsInput");
  const aoiInput          = document.getElementById("aoiInput");
  const walkingDistanceEl = document.getElementById("walkingDistance");
  const populationCountEl = document.getElementById("populationCount");

  if (!stationsInput || !stationsInput.files[0]) {
    alert("Please upload a GeoJSON file with transit stations.");
    return;
  }
  if (!aoiInput || !aoiInput.files[0]) {
    alert("Please upload a GeoJSON file for the area of interest.");
    return;
  }

  const stationsFile   = stationsInput.files[0];
  const aoiFile        = aoiInput.files[0];
  const walkingDistance = walkingDistanceEl ? (parseFloat(walkingDistanceEl.value) || 1000) : 1000;
  const populationCount = populationCountEl && populationCountEl.value ? parseInt(populationCountEl.value) : null;

  const inputs = {
    stationsFileName: stationsFile.name,
    aoiFileName:      aoiFile.name,
    walkingDistance:  walkingDistance,
    populationCount:  populationCount,
  };

  const formData = new FormData();
  formData.append("stations_geojson", stationsFile);
  formData.append("aoi_geojson",      aoiFile);

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Public Transport — Processing</h3>
      <p class="panel-desc">Calculating transit coverage…</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading…</span>
        </div>
      </div>
    </div>
  `;

  try {
    let url = `${API_BASE_URL}/calculate-transit-coverage?walking_distance_m=${walkingDistance}`;
    // let url = `http://localhost:8000/calculate-transit-coverage?walking_distance_m=${walkingDistance}`;
    if (populationCount) url += `&population_count=${populationCount}`;

    const response = await fetch(url, { method: "POST", body: formData });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const coveragePct             = response.headers.get("X-Coverage-Pct");
    const overallScore            = response.headers.get("X-Overall-Score");
    const stationCount            = response.headers.get("X-Station-Count");
    const walkingDistanceM        = response.headers.get("X-Walking-Distance-M");
    const stationDistribution     = response.headers.get("X-Station-Distribution");
    const avgStationDistanceM     = response.headers.get("X-Avg-Station-Distance-M");
    const gapRegionsRaw           = response.headers.get("X-Gap-Regions");
    const gapRegions              = gapRegionsRaw ? JSON.parse(decodeURIComponent(gapRegionsRaw)) : [];
    const populationDensity       = response.headers.get("X-Population-Density");
    const demandPressure          = response.headers.get("X-Demand-Pressure");
    const popAdjustedInsightRaw   = response.headers.get("X-Pop-Adjusted-Insight");
    const popAdjustedInsight      = popAdjustedInsightRaw ? decodeURIComponent(popAdjustedInsightRaw) : null;

    const geojsonData = await response.json();

    lastResultBlob    = geojsonData;
    lastResultService = "public-transport";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

    if (inputLayer) map.removeLayer(inputLayer);
    clearMap();

    // resultLayer: coverage polygons only (Full Area tab)
    resultLayer = L.geoJSON(geojsonData, {
      filter: function(feature) {
        const l = feature.properties.layer;
        return l !== "boundary" && l !== "station";
      },
      style: function(feature) {
        const isCovered = feature.properties.type === "covered";
        return {
          fillColor:   isCovered ? "#4cc2ff" : "#e74c3c",
          fillOpacity: isCovered ? 0.45      : 0.25,
          color:       isCovered ? "#1a8fc1" : "#c0392b",
          weight:      1.5,
          dashArray:   isCovered ? null       : "5, 4",
        };
      },
      onEachFeature: function(feature, layer) {
        const label = feature.properties.type === "covered"
          ? "Within walking distance"
          : "Outside walking distance";
        layer.bindPopup(`<strong>${label}</strong>`);
      }
    }).addTo(map);

    // inputLayer: boundary outline + station dots (Raw Data tab)
    inputLayer = L.geoJSON(geojsonData, {
      filter: function(feature) {
        const l = feature.properties.layer;
        return l === "boundary" || l === "station";
      },
      style: function(feature) {
        if (feature.properties.layer === "station") return {};
        return { fillColor: "transparent", fillOpacity: 0, color: "#f0a500", weight: 2.5, dashArray: "6, 3" };
      },
      pointToLayer: function(feature, latlng) {
        return L.circleMarker(latlng, { radius: 6, fillColor: "#1a8fc1", color: "#0d5f8a", weight: 1.5, fillOpacity: 1 });
      },
      onEachFeature: function(feature, layer) {
        const l = feature.properties.layer;
        if (l === "station") {
          const p = feature.properties || {};
          const nameKey = Object.keys(p).find(k => /^name$/i.test(k) || /^station_name$/i.test(k) || /^stop_name$/i.test(k) || /^title$/i.test(k));
          const label = nameKey ? p[nameKey] : "Transit Station";
          layer.bindPopup(`<strong>${label}</strong>`);
          return;
        }
        if (l === "boundary") { layer.bindPopup("<strong>Area of Interest</strong>"); return; }
      }
    });

    try {
      const bounds = resultLayer.getBounds();
      if (bounds && bounds.isValid()) map.fitBounds(bounds, { padding: [50, 50] });
    } catch (e) { console.warn("Could not fit bounds:", e); }

    renderTransitResults({
      coverage_pct:              coveragePct,
      overall_score:             overallScore,
      station_count:             stationCount,
      walking_distance_m:        walkingDistanceM,
      station_distribution:      stationDistribution,
      avg_station_distance_m:    avgStationDistanceM,
      gap_regions:               gapRegions,
      population_density:        populationDensity,
      demand_pressure:           demandPressure,
      pop_adjusted_insight:      popAdjustedInsight,
    }, inputs, geojsonData);

  } catch (error) {
    console.error("Transit coverage error:", error);
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate transit coverage: ${error.message}</p>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('public-transport')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}


/* ---------- Render Public Transport Results ---------- */
function renderTransitResults(stats, inputs, geojsonData) {
  const covPct   = stats.coverage_pct !== null ? parseFloat(stats.coverage_pct) : null;
  const uncovPct = covPct !== null ? (100 - covPct).toFixed(1) : null;

  const populationCount = inputs && inputs.populationCount;
  const coveredPopHtml = (covPct !== null && populationCount)
    ? `<div class="insight-card">
        <div class="label">Est. Population Covered</div>
        <div class="value">${Math.round(populationCount * covPct / 100).toLocaleString()} / ${parseInt(populationCount).toLocaleString()}</div>
       </div>`
    : "";

  // Raw data tab: input summary + station distribution stats
  const stationDistrib   = stats.station_distribution || "N/A";
  const avgStDist        = stats.avg_station_distance_m && stats.avg_station_distance_m !== ""
    ? parseFloat(stats.avg_station_distance_m).toFixed(0) + " m"
    : "N/A";
  const avgStDistNum     = stats.avg_station_distance_m && stats.avg_station_distance_m !== ""
    ? parseFloat(stats.avg_station_distance_m)
    : null;
  const avgStDistColor   = avgStDistNum !== null
    ? (avgStDistNum <= 1000 ? "#4cc2ff" : "#e74c3c")
    : "#888";

  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">Stations file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.stationsFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Area of interest</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.aoiFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Walking distance</div>
      <div class="value">${inputs.walkingDistance} m</div>
    </div>
    ${populationCount ? `<div class="insight-card">
      <div class="label">Total Population</div>
      <div class="value">${parseInt(populationCount).toLocaleString()}</div>
    </div>` : ""}
    <div class="insight-card">
      <div class="label">Stations Analyzed</div>
      <div class="value">${stats.station_count || "N/A"}</div>
    </div>
    <div class="insight-card">
      <div class="label">Station Distribution</div>
      <div class="value">${stationDistrib}</div>
    </div>
    <div class="insight-card">
      <div class="label">Avg Distance Between Stations <span style="font-size:10px;color:var(--text-muted);">(rec. 500 m)</span></div>
      <div class="value" style="color:${avgStDistColor}">${avgStDist}</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  // Full area tab
  const score     = parseFloat(stats.overall_score);
  const cat       = !isNaN(score) ? perfCategory(score) : null;

  const chartHtml = covPct !== null ? miniBarChart(
    [covPct.toFixed(1), uncovPct],
    2,
    ["#4cc2ff", "#e74c3c"],
    ["Covered", "Uncovered"]
  ) : "";

  const ineqStdDev = covPct !== null ? calcStdDev([covPct, 100 - covPct]) : 0;
  const ineq = inequalityLabel(ineqStdDev);

  const coverageInsight = covPct !== null
    ? covPct >= 70
      ? `Good transit coverage — most of the area is within walking distance of a station.`
      : covPct >= 40
      ? `Moderate coverage — ${uncovPct}% of the area lacks walkable transit access.`
      : `Low coverage — ${uncovPct}% of the area is underserved by transit.`
    : "";

  // Population-adjusted insight block
  const popDensity   = stats.population_density  ? parseFloat(stats.population_density)  : null;
  const demandPressure = stats.demand_pressure || null;
  const pressureColor = { low: "#4cc2ff", medium: "#f0a500", high: "#e74c3c" }[demandPressure] || "#888";
  const popInsightText = stats.pop_adjusted_insight || null;

  const popAdjustedHtml = popDensity !== null ? `
    <div style="border:1px solid var(--border-color);border-radius:6px;padding:10px 12px;margin-top:10px;">
      <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">Population-Adjusted Coverage</div>
      <div class="insight-card" style="margin-bottom:4px;">
        <div class="label">Population Density</div>
        <div class="value">${popDensity.toLocaleString(undefined, {maximumFractionDigits:0})} p/km²</div>
      </div>
      <div class="insight-card" style="margin-bottom:4px;">
        <div class="label">Demand Pressure</div>
        <div class="value" style="color:${pressureColor};text-transform:capitalize;">${demandPressure}</div>
      </div>
      ${popInsightText ? `<div style="background:rgba(240,165,0,0.07);border-left:3px solid ${pressureColor};border-radius:4px;padding:8px 10px;margin-top:6px;font-size:12px;color:var(--text-primary);line-height:1.5;">
        📊 ${popInsightText}
      </div>` : ""}
    </div>` : "";

  // Gap region insight
  const gapRegions = stats.gap_regions || [];
  const gapInsightHtml = gapRegions.length > 0 ? `
    <div style="background:rgba(231,76,60,0.08);border-left:3px solid #e74c3c;border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
      ⚠️ <strong>Key gap insight:</strong> Large uncovered zone${gapRegions.length > 1 ? "s" : ""} detected — ${gapRegions.map(g => `${g.area_pct}% of area near (${g.lat}, ${g.lon})`).join("; ")}.
    </div>` : "";

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Public Transport — Results</h3>
      <p class="panel-desc">Analysis complete.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        <p class="text-muted" style="font-size:11px;">Input data summary. Boundary and stations are shown on the map.</p>
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        <div class="insight-card">
          <div class="label">Area Coverage</div>
          <div class="value">${covPct !== null ? covPct.toFixed(1) + "%" : "N/A"}</div>
        </div>
        ${coveredPopHtml}
        ${cat ? `<div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>` : ""}
        <div class="insight-card">
          <div class="label">Stations Analyzed</div>
          <div class="value">${stats.station_count || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Walking Buffer</div>
          <div class="value">${stats.walking_distance_m || "N/A"} m</div>
        </div>
        ${covPct !== null ? `<div class="insight-card">
          <div class="label">Coverage Balance</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>` : ""}
        ${chartHtml}
        ${coverageInsight ? `<div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${coverageInsight}
        </div>` : ""}
        ${gapInsightHtml}
        ${popAdjustedHtml}
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('public-transport')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ============================================================
   VEGETATION DENSITY — analysis and results
   ============================================================ */

let lastVegResult = null;   // full result GeoJSON for grid + CSV


/* ---------- Vegetation Analysis — calls backend API ---------- */
async function runVegetationAnalysis() {
  const tiffInput = document.getElementById("tiffInput");
  const threshold = parseFloat(document.getElementById("vegThreshold")?.value ?? 0.2);

  if (!tiffInput || !tiffInput.files[0]) {
    alert("Please upload a satellite GeoTIFF file.");
    return;
  }

  const tiffFile = tiffInput.files[0];
  const inputs   = { fileName: tiffFile.name, threshold, aoiDesc: "Full raster extent" };

  const formData = new FormData();
  formData.append("geotiff", tiffFile);

  // const url = `http://localhost:8000/calculate-vegetation-density?ndvi_threshold=${threshold}`;
  const url = `${API_BASE_URL}/calculate-vegetation-density?ndvi_threshold=${threshold}`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Vegetation Density — Processing</h3>
      <p class="panel-desc">Classifying vegetated pixels and building cell grid…</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading…</span>
        </div>
      </div>
    </div>`;

  try {
    const response = await fetch(url, { method: "POST", body: formData });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const vegetationPct   = parseFloat(response.headers.get("X-Vegetation-Pct") || "0");
    const benchmarkGap    = parseFloat(response.headers.get("X-Benchmark-Gap")  || "0");
    const passesBenchmark = response.headers.get("X-Passes-Benchmark") === "true";
    const overallScore    = parseFloat(response.headers.get("X-Overall-Score")  || "0");
    const validPixels     = response.headers.get("X-Valid-Pixels");
    const vegPixels       = response.headers.get("X-Vegetated-Pixels");
    const cellSizeM       = parseInt(response.headers.get("X-Cell-Size-M") || "0");

    const geojsonData = await response.json();

    // Store for grid tab and CSV download
    lastVegResult     = geojsonData;
    lastResultBlob    = geojsonData;
    lastResultService = "vegetation";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

    if (inputLayer) map.removeLayer(inputLayer);
    clearMap();

    // Render result cells coloured red→green by vegetation %
    resultLayer = L.geoJSON(geojsonData, {
      style: function(feature) {
        const pct = feature.properties.vegetation_pct ?? 0;
        return {
          fillColor:   vegPctColor(pct),
          fillOpacity: 0.65,
          color:       "rgba(0,0,0,0.2)",
          weight:      0.8,
        };
      },
      onEachFeature: function(feature, layer) {
        const p   = feature.properties;
        const pct = p.vegetation_pct !== null ? p.vegetation_pct.toFixed(1) + "%" : "—";
        const tag = p.passes_30pct ? "✓ Passes 30% standard" : "✗ Below 30% standard";
        layer.bindPopup(
          `<strong>Vegetation:</strong> ${pct}<br>` +
          `<strong>QoL Score:</strong> ${p.qol_score ?? "—"}/100<br>` +
          `<span style="font-size:11px;">${tag}</span>`
        );
      },
    }).addTo(map);

    try {
      const b = resultLayer.getBounds();
      if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
    } catch(e) {}

    renderVegetationResults({
      vegetation_pct:   vegetationPct,
      benchmark_gap:    benchmarkGap,
      passes_benchmark: passesBenchmark,
      overall_score:    overallScore,
      valid_pixels:     validPixels,
      veg_pixels:       vegPixels,
      cell_size_m:      cellSizeM,
    }, inputs);

  } catch (error) {
    console.error("Vegetation analysis error:", error);
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate vegetation density: ${error.message}</p>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('vegetation')">
          ← Back to inputs
        </button>
      </div>`;
  }
}


/* ---------- vegetation % → red-to-green fill colour ---------- */
function vegPctColor(pct) {
  // 0% = red, 30% = yellow (benchmark), 60%+ = green
  const p = Math.max(0, Math.min(100, pct));
  if (p >= 50) {
    const t = (p - 50) / 50;
    return `rgba(${Math.round((1-t)*80+t*30)},${Math.round((1-t)*180+t*160)},50,0.85)`;
  }
  if (p >= 30) {
    const t = (p - 30) / 20;
    return `rgba(${Math.round((1-t)*230+t*80)},${Math.round((1-t)*200+t*180)},0,0.85)`;
  }
  // 0-30: red to orange-yellow
  const t = p / 30;
  return `rgba(${Math.round((1-t)*200+t*230)},${Math.round((1-t)*40+t*160)},0,0.85)`;
}


/* ---------- Render Vegetation Results ---------- */
function renderVegetationResults(stats, inputs) {
  const gap       = parseFloat(stats.benchmark_gap);
  const aboveBelow = gap >= 0
    ? `<span style="color:var(--success)">▲ ${gap.toFixed(1)}% above</span>`
    : `<span style="color:var(--danger)">▼ ${Math.abs(gap).toFixed(1)}% below</span>`;
  const benchmarkMsg = gap >= 0
    ? `You exceed the 30% urban greenery standard by ${gap.toFixed(1)}%.`
    : `You are ${Math.abs(gap).toFixed(1)}% below the healthy urban greenery standard. Consider adding green infrastructure.`;

  const scoreColor = qolScoreTextColor(stats.overall_score);
  const cat = perfCategory(stats.overall_score);
  const vegPct  = stats.vegetation_pct;
  const barePct = (100 - vegPct).toFixed(1);

  const chartHtml = miniBarChart(
    [vegPct.toFixed(1), barePct],
    2,
    [vegPctColor(75), "#c0392b"],
    ["Vegetated", "Bare/Urban"]
  );

  const ineq = inequalityLabel(calcStdDev([vegPct, 100 - vegPct]));
  const keyInsight = vegPct >= 30
    ? `Vegetation coverage meets the urban greenery standard. Green space is healthy across the area.`
    : `Coverage is ${vegPct.toFixed(1)}% — ${Math.abs(gap).toFixed(1)}% below the 30% benchmark. Underserved zones need green infrastructure.`;

  const validPixels = parseInt(stats.valid_pixels);
  const vegPixels   = parseInt(stats.veg_pixels);

  const inputsHtml = `
    <div class="insight-card">
      <div class="label">Raster file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.fileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Total Pixels (Features)</div>
      <div class="value">${validPixels.toLocaleString()}</div>
    </div>
    <div class="insight-card">
      <div class="label">Area of interest</div>
      <div class="value">${inputs.aoiDesc}</div>
    </div>
    <div class="insight-card">
      <div class="label">NDVI threshold</div>
      <div class="value">≥ ${inputs.threshold}</div>
    </div>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Vegetation Density — Results</h3>
      <p class="panel-desc">Vegetation coverage = % of pixels with NDVI ≥ ${inputs.threshold}. Green = vegetated · Red = bare/urban.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- RAW tab -->
      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <!-- FULL AREA tab -->
      <div class="tab-content active" id="tab-full">
        <div class="insight-card" style="border-left:3px solid ${stats.passes_benchmark ? 'var(--success)' : 'var(--danger)'};">
          <div class="label">vs. 30% Greenery Standard</div>
          <div class="value">${aboveBelow}</div>
        </div>
        <div class="insight-card">
          <div class="label">Vegetation Coverage</div>
          <div class="value">${vegPct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Overall QoL Score</div>
          <div class="value" style="color:${scoreColor}">${stats.overall_score.toFixed(1)} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>
        <div class="insight-card">
          <div class="label">Status</div>
          <div class="value" style="color:${stats.passes_benchmark ? 'var(--success)' : 'var(--danger)'}">
            ${stats.passes_benchmark ? "✓ Passes standard" : "✗ Below standard"}
          </div>
        </div>
        <div class="insight-card">
          <div class="label">Coverage Balance</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>
        ${chartHtml}
        <div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>
        <div class="insight-card" style="margin-top:8px;">
          <div class="label">Vegetated Pixels</div>
          <div class="value" style="font-size:14px;">${vegPixels.toLocaleString()} <span style="font-size:11px;color:var(--text-muted);">of ${validPixels.toLocaleString()}</span></div>
        </div>
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <!-- GRID tab -->
      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to score cells…</p>
      </div>

      <div style="display:flex;gap:6px;margin-top:12px;">
        <button class="btn btn-ghost btn-block"
                onclick="downloadVegCSV()"
                style="flex:1;font-size:12px;">⬇ Download CSV</button>
        <button class="btn btn-ghost btn-block"
                onclick="renderServicePanel('vegetation')"
                style="flex:1;font-size:12px;">← Back</button>
      </div>
    </div>`;

  wireTabSwitching();
}


/* ---------- CSV export for vegetation cells ---------- */
function downloadVegCSV() {
  if (!lastVegResult || !lastVegResult.features) {
    alert("Run the analysis first.");
    return;
  }
  const rows = [["lat","lon","vegetation_pct","qol_score","passes_30pct","status"]];
  lastVegResult.features.forEach(f => {
    const p = f.properties;
    const [geoLon, geoLat] = featureCentroid(f);
    rows.push([
      p.cell_cy ?? geoLat ?? "",
      p.cell_cx ?? geoLon ?? "",
      p.vegetation_pct ?? "",
      p.qol_score ?? "",
      p.passes_30pct ? "true" : "false",
      p.passes_30pct ? "PASS" : "FAIL",
    ]);
  });
  const csv  = rows.map(r => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = "vegetation_density_report.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}


/* ============================================================
   TRAFFIC ANALYSIS — analysis and results
   ============================================================ */

/* ---------- Road hierarchy → line colour ---------- */
function hierarchyColor(h) {
  if (h === "primary")   return "#e74c3c";   // red   — main corridors
  if (h === "secondary") return "#f39c12";   // amber — connectors
  return "#3498db";                           // blue  — local roads
}

/* ---------- Congestion level → fill colour ---------- */
function congestionColor(level) {
  if (level === "high")   return "#e74c3c";
  if (level === "medium") return "#f39c12";
  return "#2ecc71";
}

/* ---------- Traffic Analysis — calls backend API ---------- */
async function runTrafficAnalysis() {
  const roadsInput   = document.getElementById("roadsInput");
  const aoiInput     = document.getElementById("aoiInput");
  const populationEl = document.getElementById("populationInput");

  if (!roadsInput || !roadsInput.files[0]) {
    alert("Please upload a GeoJSON file with road network data.");
    return;
  }
  if (!aoiInput || !aoiInput.files[0]) {
    alert("Please upload a GeoJSON file for the area of interest.");
    return;
  }

  const roadsFile  = roadsInput.files[0];
  const aoiFile    = aoiInput.files[0];
  const population = populationEl && populationEl.value.trim()
    ? parseFloat(populationEl.value)
    : null;

  const inputs = {
    roadsFileName: roadsFile.name,
    aoiFileName:   aoiFile.name,
    population:    population,
  };

  const formData = new FormData();
  formData.append("roads_geojson", roadsFile);
  formData.append("aoi_geojson",   aoiFile);

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Traffic Analysis — Processing</h3>
      <p class="panel-desc">Classifying road hierarchy and computing connectivity…</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading…</span>
        </div>
      </div>
    </div>
  `;

  try {
    // let url = "http://localhost:8000/calculate-traffic";
    
    let url = `${API_BASE_URL}/calculate-traffic`;
    if (population !== null) url += `?population=${population}`;

    const response = await fetch(url, { method: "POST", body: formData });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    // ── Summary headers ──────────────────────────────────────────────────────
    const roadLengthKm       = response.headers.get("X-Road-Length-Km");
    const aoiAreaKm2         = response.headers.get("X-AOI-Area-Km2");
    const roadDensity        = response.headers.get("X-Road-Density");
    const densityClass       = response.headers.get("X-Density-Class");
    const trafficPressure    = response.headers.get("X-Traffic-Pressure");
    const highCongestionPct  = response.headers.get("X-High-Congestion-Pct");
    const cellSizeM          = response.headers.get("X-Cell-Size-M");
    // Network structural headers
    const segmentCount       = response.headers.get("X-Segment-Count");
    const avgSegmentLenM     = response.headers.get("X-Avg-Segment-Len-M");
    const intersectionDensity= response.headers.get("X-Intersection-Density");
    const connectivityIndex  = response.headers.get("X-Connectivity-Index");
    const primaryPct         = response.headers.get("X-Primary-Pct");
    const secondaryPct       = response.headers.get("X-Secondary-Pct");
    const localPct           = response.headers.get("X-Local-Pct");
    const primaryLenKm       = response.headers.get("X-Primary-Length-Km");
    const secondaryLenKm     = response.headers.get("X-Secondary-Length-Km");
    const localLenKm         = response.headers.get("X-Local-Length-Km");
    const fragmentedZonePct  = response.headers.get("X-Fragmented-Zone-Pct");

    const geojsonData = await response.json();

    lastResultBlob    = geojsonData;
    lastResultService = "traffic";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }
    if (inputLayer) map.removeLayer(inputLayer);
    clearMap();

    // ── Full-area tab: render road hierarchy lines ───────────────────────────
    const networkFeatures = {
      type: "FeatureCollection",
      features: geojsonData.features.filter(f => f.properties.service === "traffic-network"),
    };

    resultLayer = L.geoJSON(networkFeatures, {
      style: function(feature) {
        const h = feature.properties.hierarchy || "local";
        return {
          color:   hierarchyColor(h),
          weight:  h === "primary" ? 3.5 : h === "secondary" ? 2 : 1,
          opacity: h === "primary" ? 0.95 : h === "secondary" ? 0.80 : 0.55,
        };
      },
      onEachFeature: function(feature, layer) {
        const p = feature.properties;
        const deg = p.max_degree || "—";
        layer.bindPopup(
          `<strong>${(p.hierarchy || "local").charAt(0).toUpperCase() + (p.hierarchy||"local").slice(1)} road</strong><br>` +
          `Length: ${p.length_m != null ? (p.length_m / 1000).toFixed(2) + " km" : "—"}<br>` +
          `Intersections: ${deg} connections`
        );
      },
    }).addTo(map);

    try {
      const b = resultLayer.getBounds();
      if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
    } catch(e) {}

    renderTrafficResults({
      road_length_km:       roadLengthKm,
      aoi_area_km2:         aoiAreaKm2,
      road_density:         roadDensity,
      density_class:        densityClass,
      traffic_pressure:     trafficPressure,
      high_congestion_pct:  highCongestionPct,
      cell_size_m:          cellSizeM,
      segment_count:        segmentCount,
      avg_segment_len_m:    avgSegmentLenM,
      intersection_density: intersectionDensity,
      connectivity_index:   connectivityIndex,
      primary_pct:          primaryPct,
      secondary_pct:        secondaryPct,
      local_pct:            localPct,
      primary_len_km:       primaryLenKm,
      secondary_len_km:     secondaryLenKm,
      local_len_km:         localLenKm,
      fragmented_zone_pct:  fragmentedZonePct,
    }, inputs);

  } catch (error) {
    console.error("Traffic analysis error:", error);
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate traffic analysis: ${error.message}</p>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('traffic')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}


/* ---------- Render Traffic Results ---------- */
function renderTrafficResults(stats, inputs) {
  const aoiKm2       = parseFloat(stats.aoi_area_km2) || 0;
  const roadLenKm    = parseFloat(stats.road_length_km) || 0;
  const roadDensity  = parseFloat(stats.road_density) || 0;
  const densityClass = stats.density_class || "—";
  const highCongPct  = parseFloat(stats.high_congestion_pct) || 0;

  // Network metrics
  const segCount     = parseInt(stats.segment_count)        || 0;
  const avgSegM      = parseFloat(stats.avg_segment_len_m)  || 0;
  const intDensity   = parseFloat(stats.intersection_density)|| 0;
  const connIdx      = parseFloat(stats.connectivity_index)  || 0;
  const primPct      = parseFloat(stats.primary_pct)         || 0;
  const secPct       = parseFloat(stats.secondary_pct)       || 0;
  const locPct       = parseFloat(stats.local_pct)           || 0;
  const primKm       = parseFloat(stats.primary_len_km)      || 0;
  const secKm        = parseFloat(stats.secondary_len_km)    || 0;
  const locKm        = parseFloat(stats.local_len_km)        || 0;
  const fragPct      = parseFloat(stats.fragmented_zone_pct) || 0;

  // Connectivity quality label
  const connLabel = connIdx >= 3.5
    ? { text: "Well-connected",   color: "var(--success)" }
    : connIdx >= 2.5
    ? { text: "Moderately connected", color: "var(--warning)" }
    : { text: "Poorly connected", color: "var(--danger)" };

  // Density badge
  const densityBadge = densityClass === "optimal"
    ? `<span style="color:var(--success)">Optimal (2–10 km/km²)</span>`
    : densityClass === "low"
      ? `<span style="color:var(--danger)">Low — underdeveloped (&lt; 2 km/km²)</span>`
      : `<span style="color:var(--warning)">High — overbuilt (&gt; 10 km/km²)</span>`;

  // Hierarchy stacked bar
  const hierarchyBar = `
    <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Road Hierarchy Distribution</div>
    <div style="display:flex;height:10px;border-radius:5px;overflow:hidden;margin-bottom:6px;">
      <div style="width:${primPct}%;background:#e74c3c;" title="Primary ${primPct.toFixed(1)}%"></div>
      <div style="width:${secPct}%;background:#f39c12;"  title="Secondary ${secPct.toFixed(1)}%"></div>
      <div style="width:${locPct}%;background:#3498db;"  title="Local ${locPct.toFixed(1)}%"></div>
    </div>
    <div style="display:flex;gap:10px;font-size:10px;color:var(--text-muted);">
      <span><span style="color:#e74c3c;">■</span> Primary ${primPct.toFixed(1)}%</span>
      <span><span style="color:#f39c12;">■</span> Secondary ${secPct.toFixed(1)}%</span>
      <span><span style="color:#3498db;">■</span> Local ${locPct.toFixed(1)}%</span>
    </div>`;

  // Fragmentation insight
  const fragInsight = fragPct > 40
    ? `⚠ ${fragPct.toFixed(0)}% of the AOI has only local roads with no structural connections — highly fragmented zones.`
    : fragPct > 15
    ? `Moderate fragmentation: ${fragPct.toFixed(0)}% of the area lacks primary or secondary road access.`
    : `Road network is well-structured with minimal isolated local areas (${fragPct.toFixed(0)}%).`;

  const pressureRow = stats.traffic_pressure ? `
    <div class="insight-card">
      <div class="label">Traffic Pressure</div>
      <div class="value">${parseFloat(stats.traffic_pressure).toFixed(0)} pop / road-km</div>
    </div>` : "";

  const inputsHtml = `
    <div class="insight-card">
      <div class="label">Road network file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.roadsFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Area of interest</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.aoiFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">AOI Area</div>
      <div class="value">${aoiKm2.toFixed(2)} km²</div>
    </div>
    ${inputs.population != null ? `
    <div class="insight-card">
      <div class="label">Population (input)</div>
      <div class="value">${inputs.population.toLocaleString()}</div>
    </div>` : ""}`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Traffic Analysis — Results</h3>
      <p class="panel-desc">Road hierarchy map · Red = primary corridors · Amber = connectors · Blue = local</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- RAW tab -->
      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <!-- FULL AREA tab — structural network analysis -->
      <div class="tab-content active" id="tab-full">

        <div style="margin:0 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Network overview</div>
        <div class="insight-card">
          <div class="label">Total Road Length</div>
          <div class="value">${roadLenKm.toFixed(2)} km</div>
        </div>
        <div class="insight-card">
          <div class="label">Road Segments</div>
          <div class="value">${segCount.toLocaleString()}</div>
        </div>
        <div class="insight-card">
          <div class="label">Avg Segment Length</div>
          <div class="value">${avgSegM >= 1000 ? (avgSegM/1000).toFixed(2) + " km" : avgSegM.toFixed(0) + " m"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Road Density</div>
          <div class="value">${roadDensity.toFixed(2)} km / km²  —  ${densityBadge}</div>
        </div>
        ${pressureRow}

        <div style="margin:12px 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Connectivity &amp; intersections</div>
        <div class="insight-card">
          <div class="label">Connectivity Index</div>
          <div class="value" style="color:${connLabel.color}">${connIdx.toFixed(2)} avg connections — ${connLabel.text}</div>
        </div>
        <div class="insight-card">
          <div class="label">Intersection Density</div>
          <div class="value">${intDensity.toFixed(2)} intersections / km²</div>
        </div>
        <div class="insight-card">
          <div class="label">Fragmented Zones</div>
          <div class="value" style="color:${fragPct > 30 ? "var(--danger)" : fragPct > 15 ? "var(--warning)" : "var(--success)"}">${fragPct.toFixed(1)}% local-only coverage</div>
        </div>

        <div style="margin:12px 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Road hierarchy</div>
        ${hierarchyBar}
        <div class="insight-card" style="margin-top:8px;">
          <div class="label" style="color:#e74c3c;">Primary corridors</div>
          <div class="value">${primKm.toFixed(2)} km &nbsp;·&nbsp; ${primPct.toFixed(1)}% of network</div>
        </div>
        <div class="insight-card">
          <div class="label" style="color:#f39c12;">Secondary connectors</div>
          <div class="value">${secKm.toFixed(2)} km &nbsp;·&nbsp; ${secPct.toFixed(1)}% of network</div>
        </div>
        <div class="insight-card">
          <div class="label" style="color:#3498db;">Local roads</div>
          <div class="value">${locKm.toFixed(2)} km &nbsp;·&nbsp; ${locPct.toFixed(1)}% of network</div>
        </div>

        <div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:10px;font-size:12px;color:var(--text-primary);">
          💡 ${fragInsight}
        </div>

        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <!-- GRID tab — congestion scoring -->
      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the congestion cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('traffic')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ============================================================
   INFORMAL SETTLEMENT PATTERN ANALYSIS — analysis and results
   ============================================================ */

let lastISPAResult = null;

/* ---------- Irregularity score → fill colour ---------- */
function irregularityColor(score) {
  // 0 (planned/good) = green, 33 = yellow, 67+ = red
  if (score === null || score === undefined) return "rgba(150,150,150,0.3)";
  const s = Math.max(0, Math.min(100, score));
  if (s <= 33) {
    const t = s / 33;
    return `rgba(${Math.round((1-t)*46+t*240)},${Math.round((1-t)*180+t*200)},${Math.round((1-t)*50+t*0)},0.72)`;
  }
  if (s <= 66) {
    const t = (s - 33) / 33;
    return `rgba(${Math.round((1-t)*240+t*220)},${Math.round((1-t)*200+t*60)},0,0.72)`;
  }
  const t = (s - 66) / 34;
  return `rgba(${Math.round((1-t)*220+t*180)},${Math.round((1-t)*60+t*20)},0,0.72)`;
}

/* ---------- Informal Settlement Analysis — calls backend API ---------- */
async function runInformalSettlementAnalysis() {
  const tiffInput = document.getElementById("tiffInput");

  if (!tiffInput || !tiffInput.files[0]) {
    alert("Please upload a satellite/aerial GeoTIFF file.");
    return;
  }

  const tiffFile = tiffInput.files[0];
  const inputs   = { fileName: tiffFile.name };

  const formData = new FormData();
  formData.append("geotiff", tiffFile);

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Informal Settlement — Processing</h3>
      <p class="panel-desc">Computing texture irregularity, edge density, and built-up crowding…</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading…</span>
        </div>
      </div>
    </div>`;

  try {
  const response = await fetch(
    `${API_BASE_URL}/calculate-informal-settlement`,
    // "http://localhost:8000/calculate-informal-settlement",
    { method: "POST", body: formData }
  );

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    const avgIrregularity  = parseFloat(response.headers.get("X-Avg-Irregularity") || "0");
    const highPct          = parseFloat(response.headers.get("X-High-Pct")          || "0");
    const mediumPct        = parseFloat(response.headers.get("X-Medium-Pct")        || "0");
    const lowPct           = parseFloat(response.headers.get("X-Low-Pct")           || "0");
    const overallQoL       = parseFloat(response.headers.get("X-Overall-QoL-Score") || "0");
    const cellSizeM        = parseInt(response.headers.get("X-Cell-Size-M")         || "0");
    const highZoneCount    = parseInt(response.headers.get("X-High-Zone-Count")     || "0");

    const geojsonData = await response.json();

    lastISPAResult    = geojsonData;
    lastResultBlob    = geojsonData;
    lastResultService = "informal-settlement";

    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }
    if (inputLayer) map.removeLayer(inputLayer);
    clearMap();

    // Render: cells coloured by irregularity score, high-zone outlines on top
    resultLayer = L.geoJSON(geojsonData, {
      style: function(feature) {
        const p = feature.properties;
        if (p.type === "high_irregularity_zone") {
          return {
            fillColor:   "transparent",
            fillOpacity: 0,
            color:       "#e74c3c",
            weight:      2.5,
            dashArray:   "5,4",
          };
        }
        return {
          fillColor:   irregularityColor(p.irregularity_score),
          fillOpacity: 0.7,
          color:       "rgba(0,0,0,0.18)",
          weight:      0.7,
        };
      },
      onEachFeature: function(feature, layer) {
        const p = feature.properties;
        if (p.type === "high_irregularity_zone") {
          layer.bindPopup("<strong>High Irregularity Zone</strong><br>Potential informal settlement area");
          return;
        }
        const cls   = p.classification || "—";
        const score = p.irregularity_score !== null ? p.irregularity_score : "—";
        const qol   = p.qol_score !== null ? p.qol_score + "/100" : "—";
        layer.bindPopup(
          `<strong>Irregularity Score:</strong> ${score}/100<br>` +
          `<strong>Classification:</strong> ${cls}<br>` +
          `<strong>QoL Score:</strong> ${qol}<br>` +
          `<strong>Built-up Ratio:</strong> ${(p.buildup_ratio * 100).toFixed(1)}%`
        );
      },
    }).addTo(map);

    try {
      const b = resultLayer.getBounds();
      if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
    } catch(e) {}

    renderInformalSettlementResults({
      avg_irregularity: avgIrregularity,
      high_pct:         highPct,
      medium_pct:       mediumPct,
      low_pct:          lowPct,
      overall_qol:      overallQoL,
      cell_size_m:      cellSizeM,
      high_zone_count:  highZoneCount,
    }, inputs);

  } catch (error) {
    console.error("Informal settlement analysis error:", error);
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to analyse informal settlement patterns: ${error.message}</p>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('informal-settlement')">
          ← Back to inputs
        </button>
      </div>`;
  }
}


/* ---------- Render Informal Settlement Results ---------- */
function renderInformalSettlementResults(stats, inputs) {
  const scoreColor = qolScoreTextColor(stats.overall_qol);
  const cat = perfCategory(stats.overall_qol);

  const highColor   = stats.high_pct > 30 ? "var(--danger)" : stats.high_pct > 10 ? "var(--warning)" : "var(--success)";
  const lowColor    = stats.low_pct  > 50 ? "var(--success)" : "var(--text-muted)";

  const classLabel = stats.avg_irregularity <= 33
    ? `<span style="color:var(--success)">Low — Mostly Planned</span>`
    : stats.avg_irregularity <= 66
      ? `<span style="color:var(--warning)">Medium — Mixed Patterns</span>`
      : `<span style="color:var(--danger)">High — Informal Patterns Detected</span>`;

  const chartHtml = miniBarChart(
    [stats.low_pct.toFixed(1), stats.medium_pct.toFixed(1), stats.high_pct.toFixed(1)],
    3,
    [irregularityColor(10), irregularityColor(50), irregularityColor(85)],
    ["Planned", "Mixed", "Informal"]
  );

  const ineq = inequalityLabel(calcStdDev([stats.low_pct, stats.medium_pct, stats.high_pct]));

  const keyInsight = stats.high_pct > 30
    ? `${stats.high_pct.toFixed(1)}% of the area shows high informality patterns — these zones need priority urban planning intervention.`
    : stats.high_pct > 10
    ? `Informality is present in ${stats.high_pct.toFixed(1)}% of the area. Most zones are planned but some require attention.`
    : `The area is mostly planned and regular — only ${stats.high_pct.toFixed(1)}% shows informal settlement patterns.`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Informal Settlement — Results</h3>
      <p class="panel-desc">Irregularity score 0–33 = Planned · 34–66 = Mixed · 67–100 = Informal. Green = regular · Red = irregular.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- RAW tab -->
      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        <div class="insight-card">
          <div class="label">Imagery file</div>
          <div class="value" style="font-size:11px;word-break:break-all;">${inputs.fileName}</div>
        </div>
        <div class="insight-card">
          <div class="label">Metrics computed</div>
          <div class="value" style="font-size:11px;">Texture irregularity · Edge density · Built-up crowding</div>
        </div>
        <div class="insight-card">
          <div class="label">Cell size (approx.)</div>
          <div class="value">${stats.cell_size_m >= 1000 ? (stats.cell_size_m/1000).toFixed(1)+" km" : stats.cell_size_m+" m"} × ${stats.cell_size_m >= 1000 ? (stats.cell_size_m/1000).toFixed(1)+" km" : stats.cell_size_m+" m"}</div>
        </div>
      </div>

      <!-- FULL AREA tab -->
      <div class="tab-content active" id="tab-full">
        <div class="insight-card" style="border-left:3px solid ${stats.avg_irregularity > 66 ? 'var(--danger)' : stats.avg_irregularity > 33 ? 'var(--warning)' : 'var(--success)'};">
          <div class="label">Overall Classification</div>
          <div class="value">${classLabel}</div>
        </div>
        <div class="insight-card">
          <div class="label">Avg Irregularity Score</div>
          <div class="value">${stats.avg_irregularity.toFixed(1)} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Overall QoL Score</div>
          <div class="value" style="color:${scoreColor}">${stats.overall_qol} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>
        <div class="insight-card">
          <div class="label">High-Irregularity Cells</div>
          <div class="value" style="color:${highColor}">${stats.high_pct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Medium-Irregularity Cells</div>
          <div class="value" style="color:var(--warning)">${stats.medium_pct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Low-Irregularity Cells</div>
          <div class="value" style="color:${lowColor}">${stats.low_pct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Merged High-Irregularity Zones</div>
          <div class="value">${stats.high_zone_count}</div>
        </div>
        <div class="insight-card">
          <div class="label">Distribution Balance</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>
        ${chartHtml}
        <div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <!-- GRID tab -->
      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to score cells…</p>
      </div>

      <div style="display:flex;gap:6px;margin-top:12px;">
        <button class="btn btn-ghost btn-block"
                onclick="downloadISPACSV()"
                style="flex:1;font-size:12px;">⬇ Download CSV</button>
        <button class="btn btn-ghost btn-block"
                onclick="renderServicePanel('informal-settlement')"
                style="flex:1;font-size:12px;">← Back</button>
      </div>
    </div>`;

  wireTabSwitching();
}


/* ---------- CSV export for informal settlement cells ---------- */
function downloadISPACSV() {
  if (!lastISPAResult || !lastISPAResult.features) {
    alert("Run the analysis first.");
    return;
  }
  const rows = [["lat","lon","irregularity_score","classification","qol_score","texture_val","edge_val","buildup_ratio"]];
  lastISPAResult.features.forEach(f => {
    const p = f.properties;
    if (p.type === "high_irregularity_zone") return;
    const [geoLon, geoLat] = featureCentroid(f);
    rows.push([
      p.cell_cy ?? geoLat ?? "",
      p.cell_cx ?? geoLon ?? "",
      p.irregularity_score ?? "",
      p.classification ?? "",
      p.qol_score ?? "",
      p.texture_val ?? "",
      p.edge_val ?? "",
      p.buildup_ratio ?? "",
    ]);
  });
  const csv  = rows.map(r => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = "informal_settlement_report.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}


/* ---------- Extract centroid [lon, lat] from a GeoJSON feature ---------- */
function featureCentroid(feature) {
  try {
    const coords = feature.geometry?.coordinates;
    const type   = feature.geometry?.type;
    if (!coords) return [null, null];
    if (type === "Point") return [coords[0], coords[1]];
    // Polygon: average the outer ring
    const ring = type === "MultiPolygon" ? coords[0][0] : coords[0];
    const n = ring.length;
    const lon = ring.reduce((s, c) => s + c[0], 0) / n;
    const lat = ring.reduce((s, c) => s + c[1], 0) / n;
    return [lon, lat];
  } catch { return [null, null]; }
}

/* ---------- Universal grid CSV export (all services) ---------- */
function downloadGridCSV(geojson, service) {
  if (!geojson || !geojson.features) { alert("No grid data to export."); return; }

  // Property keys to exclude from CSV (Simplestyle visual props only)
  const excludeKeys = new Set(["fill", "fill-opacity", "stroke", "stroke-width", "stroke-opacity", "type", "fill_color", "fill_opacity", "stroke_width"]);
  const allKeys = new Set();
  geojson.features.forEach(f => {
    if (f.properties?.type === "high_irregularity_zone") return;
    Object.keys(f.properties || {}).forEach(k => { if (!excludeKeys.has(k)) allKeys.add(k); });
  });

  // Preferred column order — lat/lon always first
  const preferred = ["lat","lon","qol_score","value","classification","congestion",
    "vegetation_pct","passes_30pct","irregularity_score","local_density","local_pressure",
    "density","texture_val","edge_val","buildup_ratio"];

  // Map internal cell_cy/cell_cx → lat/lon; drop the originals
  const skipInternals = new Set(["cell_cy","cell_cx"]);
  const dataKeys = [...allKeys].filter(k => !skipInternals.has(k));
  const orderedKeys = [
    "lat", "lon",
    ...preferred.filter(k => k !== "lat" && k !== "lon" && dataKeys.includes(k)),
    ...dataKeys.filter(k => !preferred.includes(k)),
  ];

  const rows = [orderedKeys];
  geojson.features.forEach(f => {
    if (f.properties?.type === "high_irregularity_zone") return;
    const p = f.properties || {};
    // Derive lat/lon: prefer stored cell centroid, fall back to geometry centroid
    const [geoLon, geoLat] = featureCentroid(f);
    const lat = p.cell_cy ?? geoLat ?? "";
    const lon = p.cell_cx ?? geoLon ?? "";
    rows.push(orderedKeys.map(k => {
      if (k === "lat") return lat;
      if (k === "lon") return lon;
      const v = p[k];
      if (v === null || v === undefined) return "";
      if (typeof v === "number") return isNaN(v) ? "" : v;
      return String(v).includes(",") ? `"${v}"` : v;
    }));
  });

  const csv  = rows.map(r => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `${service}_grid.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}


/* ---------- Render Crime Results with stats ---------- */
function renderCrimeResults(stats, inputs, geojsonData) {
  const avgDen = parseFloat(stats.avg_density) || 0;
  const maxDen = parseFloat(stats.max_density) || 0;
  const crimeCount = parseInt(stats.crime_count) || 0;

  // Invert: higher crime = lower score
  const safetyScore = maxDen > 0 ? Math.max(0, Math.round(100 - Math.min(100, (avgDen / maxDen) * 100))) : 50;
  const cat = perfCategory(safetyScore);
  const scoreColor = qolScoreTextColor(safetyScore);

  const hotRatio  = maxDen > 0 ? Math.min(100, (avgDen / maxDen) * 100) : 0;
  const safeRatio = 100 - hotRatio;
  const chartHtml = miniBarChart(
    [safeRatio.toFixed(1), hotRatio.toFixed(1)],
    2,
    ["#2ecc71", "#e74c3c"],
    ["Safe", "Hotspot"]
  );

  const keyInsight = maxDen > 0
    ? maxDen / Math.max(avgDen, 0.01) > 5
      ? `Crime is heavily concentrated in a few hotspot zones — the rest of the area is relatively safe.`
      : `Crime incidents are spread more evenly across the area with no dominant single hotspot.`
    : "";

  // ---- Per-capita comparison ----
  const totalPop = inputs && inputs.totalPopulation ? parseInt(inputs.totalPopulation) : null;
  let perCapitaHtml = "";
  if (totalPop && totalPop > 0 && crimeCount > 0) {
    const per1000 = (crimeCount / totalPop) * 1000;
    const benchmark = 1; // incidents per 1,000 residents (WHO / urban safety standard)
    const ratio = per1000 / benchmark;
    let ratingLabel, ratingColor, ratingDesc;
    if (per1000 <= 1)       { ratingLabel = "Safe";     ratingColor = "#2ecc71"; ratingDesc = "At or below the safe urban benchmark (< 1 / 1,000)."; }
    else if (per1000 <= 3)  { ratingLabel = "Moderate"; ratingColor = "#f39c12"; ratingDesc = `${ratio.toFixed(1)}× above the safe benchmark.`; }
    else if (per1000 <= 7)  { ratingLabel = "High";     ratingColor = "#e67e22"; ratingDesc = `${ratio.toFixed(1)}× above the safe benchmark.`; }
    else                    { ratingLabel = "Critical";  ratingColor = "#e74c3c"; ratingDesc = `${ratio.toFixed(1)}× above the safe benchmark — urgent intervention needed.`; }

    perCapitaHtml = `<div class="insight-card">
      <div class="label">Per-Capita Crime Rate</div>
      <div class="value" style="color:${ratingColor};">${per1000.toFixed(2)} per 1,000 residents</div>
      <div style="margin-top:6px;font-size:11px;color:var(--text-muted);">
        Based on ${crimeCount.toLocaleString()} incidents · population ${totalPop.toLocaleString()}
      </div>
      <div style="margin-top:4px;display:flex;align-items:center;gap:6px;">
        <span style="font-size:11px;font-weight:600;color:${ratingColor};">${ratingLabel}</span>
        <span style="font-size:11px;color:var(--text-muted);">${ratingDesc}</span>
      </div>
      <div style="margin-top:6px;background:rgba(255,255,255,0.08);border-radius:3px;height:6px;overflow:hidden;">
        <div style="width:${Math.min(100, (per1000 / 10) * 100).toFixed(1)}%;height:100%;background:${ratingColor};border-radius:3px;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);margin-top:2px;">
        <span>0</span><span>▲ benchmark (1)</span><span>10+ /1,000</span>
      </div>
    </div>`;
  }

  // ---- Top safe / unsafe areas from geojson features ----
  let topUnsafeHtml = "", topSafeHtml = "";
  if (geojsonData && geojsonData.features && geojsonData.features.length) {
    const nameKey = ["NBHD_NAME","name","NAME","district","area_name","neighborhood"]
      .find(k => geojsonData.features[0]?.properties?.[k] !== undefined);
    const featuresWithName = geojsonData.features
      .filter(f => f.properties && f.properties.crime_density !== undefined)
      .map(f => ({
        name: nameKey ? f.properties[nameKey] : null,
        density: parseFloat(f.properties.crime_density) || 0,
      }))
      .filter(f => f.name);

    if (featuresWithName.length) {
      const sorted = [...featuresWithName].sort((a, b) => b.density - a.density);
      const top3Unsafe = sorted.slice(0, 3);
      const top3Safe   = sorted.slice(-3).reverse();
      topUnsafeHtml = `<div class="insight-card">
        <div class="label" style="color:var(--danger);">Top Unsafe Areas</div>
        <div style="display:flex;flex-direction:column;gap:3px;margin-top:4px;">
          ${top3Unsafe.map((f, i) => `
            <div style="display:flex;justify-content:space-between;font-size:12px;">
              <span>${i + 1}. ${f.name}</span>
              <span style="color:var(--danger);font-weight:600;">${f.density.toFixed(2)}/km²</span>
            </div>`).join("")}
        </div>
      </div>`;
      topSafeHtml = `<div class="insight-card">
        <div class="label" style="color:#2ecc71;">Top Safe Areas</div>
        <div style="display:flex;flex-direction:column;gap:3px;margin-top:4px;">
          ${top3Safe.map((f, i) => `
            <div style="display:flex;justify-content:space-between;font-size:12px;">
              <span>${i + 1}. ${f.name}</span>
              <span style="color:#2ecc71;font-weight:600;">${f.density.toFixed(2)}/km²</span>
            </div>`).join("")}
        </div>
      </div>`;
    }
  }

  // ---- Crime type breakdown from the uploaded CSV (available via lastCrimeCSVHeaders) ----
  let crimeTypeHtml = "";
  if (window._crimeTypeCounts && Object.keys(window._crimeTypeCounts).length) {
    const entries = Object.entries(window._crimeTypeCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const total = entries.reduce((s, [, v]) => s + v, 0);
    crimeTypeHtml = `
      <div class="insight-card">
        <div class="label">Crime Type Breakdown</div>
        <div style="display:flex;flex-direction:column;gap:4px;margin-top:6px;">
          ${entries.map(([type, count]) => {
            const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
            return `<div style="font-size:11px;">
              <div style="display:flex;justify-content:space-between;margin-bottom:2px;">
                <span style="color:var(--text-primary);">${type}</span>
                <span style="color:var(--text-muted);">${count} (${pct}%)</span>
              </div>
              <div style="background:rgba(255,255,255,0.08);border-radius:3px;height:5px;overflow:hidden;">
                <div style="width:${pct}%;height:100%;background:#e74c3c;border-radius:3px;"></div>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>`;
  }

  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">Crime data (CSV)</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.csvFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Total Incidents</div>
      <div class="value">${crimeCount.toLocaleString()}</div>
    </div>
    <div class="insight-card">
      <div class="label">Areas Analyzed</div>
      <div class="value">${stats.area_count || "N/A"}</div>
    </div>
    <div class="insight-card">
      <div class="label">Boundary data (GeoJSON)</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.geoJsonFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Latitude field</div>
      <div class="value">${inputs.latField}</div>
    </div>
    <div class="insight-card">
      <div class="label">Longitude field</div>
      <div class="value">${inputs.lonField}</div>
    </div>
    ${crimeTypeHtml}
    ${perCapitaHtml}
  ` : `<p class="text-muted">No input info available.</p>`;

  // ---- Color scale for full area tab ----
  const colorScaleHtml = `
    <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Crime density color scale</div>
    <div style="display:flex;flex-direction:column;gap:4px;">
      ${[
        ["#2ecc71", "0 – 5",   "Safe"],
        ["#f1c40f", "5 – 10",  "Low risk"],
        ["#e67e22", "10 – 15", "Moderate"],
        ["#e74c3c", "15 – 20", "High risk"],
        ["#891508", "20 +",    "Hotspot"],
      ].map(([color, range, label]) => `
        <div style="display:flex;align-items:center;gap:8px;font-size:11px;">
          <div style="width:12px;height:12px;background:${color};border-radius:2px;flex-shrink:0;"></div>
          <span><strong>${label}</strong> — ${range} crimes/km²</span>
        </div>`).join("")}
    </div>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Crime Density — Results</h3>
      <p class="panel-desc">Crime density = incidents per km². Higher values = more crime.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        ${chartHtml}
        ${colorScaleHtml}
        <div class="insight-card">
          <div class="label">Overall Safety Score</div>
          <div class="value" style="color:${scoreColor}">${safetyScore} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>
        <div class="insight-card">
          <div class="label">Avg Density</div>
          <div class="value">${stats.avg_density || "N/A"} crimes/km²</div>
        </div>
        <div class="insight-card">
          <div class="label">Peak Hotspot Density</div>
          <div class="value" style="color:var(--danger)">${stats.max_density || "N/A"} crimes/km²</div>
        </div>
        ${topUnsafeHtml}
        ${topSafeHtml}
        ${keyInsight ? `<div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>` : ""}
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the 200 m cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('crime')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Render Urban Density Results with stats ---------- */
function renderUrbanDensityResults(stats, inputs, geojsonData, nameKey) {
  const avgDen    = parseFloat(stats.avg_density) || 0;
  const maxDen    = parseFloat(stats.max_density) || 0;
  const areaCount = parseInt(stats.area_count) || 0;
  const totalArea = parseFloat(stats.total_area) || 0;

  // Average density classification based on 5,000 pop/km² standard
  function avgDensityClass(d) {
    if (d <= 0)     return { label: "No Data",  color: "var(--text-muted)" };
    if (d < 1000)   return { label: "Low",      color: "#4cc2ff" };
    if (d <= 5000)  return { label: "Medium",   color: "#f39c12" };
    return               { label: "High",      color: "var(--danger)" };
  }
  const avgClass = avgDensityClass(avgDen);

  // Per-feature data for hotspot / lowest-zone cards (requires nameKey)
  let hotspotHtml = "";
  let lowzoneHtml = "";
  if (nameKey && geojsonData && geojsonData.features) {
    const areas = geojsonData.features
      .map(f => ({ name: f.properties[nameKey], density: f.properties.urban_density || 0 }))
      .filter(a => a.name);
    if (areas.length) {
      const sorted = [...areas].sort((a, b) => b.density - a.density);
      const top    = sorted.slice(0, 3);
      const bottom = sorted.slice(-3).reverse();
      hotspotHtml = `
        <div class="insight-card">
          <div class="label">High-Density Clusters (Hotspots)</div>
          <div class="value" style="font-size:12px;line-height:1.8;">
            ${top.map((a, i) => `<span style="color:var(--danger);">${i + 1}. ${a.name}</span> <span style="color:var(--text-muted);font-size:11px;">${Math.round(a.density).toLocaleString()} pop/km²</span>`).join("<br>")}
          </div>
        </div>`;
      lowzoneHtml = `
        <div class="insight-card">
          <div class="label">Lowest-Density Zones (Underutilized Land)</div>
          <div class="value" style="font-size:12px;line-height:1.8;">
            ${bottom.map((a, i) => `<span style="color:#4cc2ff;">${i + 1}. ${a.name}</span> <span style="color:var(--text-muted);font-size:11px;">${Math.round(a.density).toLocaleString()} pop/km²</span>`).join("<br>")}
          </div>
        </div>`;
    }
  }

  // Store per-feature data for the grid tab histogram
  lastUrbanDensityFeatures = geojsonData && geojsonData.features
    ? geojsonData.features.map(f => ({
        name:    nameKey ? f.properties[nameKey] : null,
        density: f.properties.urban_density || 0,
      }))
    : null;

  const ineq = maxDen > 0 ? inequalityLabel(calcStdDev([avgDen, maxDen])) : null;

  const keyInsight = maxDen > 0
    ? (maxDen / Math.max(avgDen, 0.01)) > 3
      ? `Density is concentrated in a few zones — most of the area is much less populated than the peak.`
      : `Population is relatively balanced across the area with no extreme density hotspots.`
    : "";

  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">Boundary data (GeoJSON)</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.geoJsonFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Total Features (Areas)</div>
      <div class="value">${areaCount.toLocaleString()}</div>
    </div>
    <div class="insight-card">
      <div class="label">Data Coverage Area</div>
      <div class="value">${totalArea ? totalArea.toFixed(2) + " km²" : "N/A"}</div>
    </div>
    <div class="insight-card">
      <div class="label">Population field</div>
      <div class="value">${inputs.populationField}</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Urban Density — Results</h3>
      <p class="panel-desc">Urban density = population per km². Blue gradient: darker = more densely populated.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        <div class="insight-card">
          <div class="label">Total Population</div>
          <div class="value">${stats.total_population ? parseInt(stats.total_population).toLocaleString() : "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Total Area</div>
          <div class="value">${totalArea ? totalArea.toFixed(2) + " km²" : "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Areas Analyzed</div>
          <div class="value">${areaCount.toLocaleString()}</div>
        </div>
        <div class="insight-card">
          <div class="label">Avg Density</div>
          <div class="value">${stats.avg_density || "N/A"} pop/km²</div>
        </div>
        <div class="insight-card">
          <div class="label">Avg Density Classification</div>
          <div class="value" style="color:${avgClass.color};font-size:15px;">${avgClass.label}
            <span style="font-size:10px;color:var(--text-muted);font-weight:normal;"> (standard: 5,000 pop/km²)</span>
          </div>
        </div>
        <div class="insight-card">
          <div class="label">Peak Density Zone</div>
          <div class="value" style="color:var(--warning)">${stats.max_density || "N/A"} pop/km²</div>
        </div>
        ${ineq ? `<div class="insight-card">
          <div class="label">Distribution Balance</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>` : ""}
        ${hotspotHtml}
        ${lowzoneHtml}
        ${keyInsight ? `<div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>` : ""}
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the 200 m cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('urban-density')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Render NDVI Results with stats ---------- */
function renderNDVIResults(stats, inputs) {
  const meanNDVI = parseFloat(stats.mean)   || 0;
  const minNDVI  = parseFloat(stats.min)    || 0;
  const maxNDVI  = parseFloat(stats.max)    || 0;
  const stdNDVI  = parseFloat(stats.stddev) || 0;
  const validPx  = parseInt(stats.valid_pixels) || 0;

  // Score: mean NDVI mapped to 0–100
  const ndviScore  = Math.max(0, Math.min(100, Math.round(((meanNDVI + 0.2) / 0.8) * 100)));
  const scoreColor = qolScoreTextColor(ndviScore);

  // Vegetation health classification from mean NDVI
  const vegHealthClass = meanNDVI >= 0.5
    ? { label: "Dense / Healthy Vegetation",  color: "#27ae60" }
    : meanNDVI >= 0.2
    ? { label: "Moderate Vegetation",          color: "#f39c12" }
    : meanNDVI >= 0.0
    ? { label: "Sparse / Stressed Vegetation", color: "#e67e22" }
    : { label: "Bare Soil / Built-up Surface", color: "#e74c3c" };

  // Histogram: 10 equal bins across the data range
  const binCount = 10;
  const range = maxNDVI - minNDVI || 1;
  const bins  = new Array(binCount).fill(0);
  // We only have summary stats — approximate a normal distribution histogram
  // using a Gaussian curve seeded by mean and stddev
  const histMax = Math.max(...Array.from({length: binCount}, (_, i) => {
    const binMid = minNDVI + (i + 0.5) * (range / binCount);
    return Math.exp(-0.5 * Math.pow((binMid - meanNDVI) / (stdNDVI || 0.01), 2));
  }), 0.001);
  const histBars = Array.from({length: binCount}, (_, i) => {
    const binMid   = minNDVI + (i + 0.5) * (range / binCount);
    const binLabel = (minNDVI + i * (range / binCount)).toFixed(2);
    const height   = Math.exp(-0.5 * Math.pow((binMid - meanNDVI) / (stdNDVI || 0.01), 2));
    const hPct     = Math.round((height / histMax) * 44);
    const t        = (binMid - minNDVI) / range;
    const r = t < 0.5 ? Math.round(200 - t/0.5*20) : Math.round(180 - (t-0.5)/0.5*180);
    const g = t < 0.5 ? Math.round(20  + t/0.5*180) : Math.round(200 - (t-0.5)/0.5*50);
    return `<div title="${binLabel}" style="flex:1;height:${Math.max(2,hPct)}px;background:rgb(${r},${g},0);border-radius:2px 2px 0 0;"></div>`;
  });
  const histogramHtml = `
    <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Value Distribution</div>
    <div style="display:flex;align-items:flex-end;gap:2px;height:48px;">${histBars.join("")}</div>
    <div style="display:flex;justify-content:space-between;font-size:9px;color:var(--text-muted);margin-top:2px;">
      <span>${minNDVI.toFixed(2)}</span><span>${meanNDVI.toFixed(2)} (mean)</span><span>${maxNDVI.toFixed(2)}</span>
    </div>`;

  const keyInsight = meanNDVI >= 0.4
    ? `Mean NDVI of ${meanNDVI.toFixed(2)} indicates healthy and abundant vegetation across the area.`
    : meanNDVI >= 0.2
    ? `Moderate vegetation detected (mean NDVI ${meanNDVI.toFixed(2)}). Some zones may need greening.`
    : `Low mean NDVI (${meanNDVI.toFixed(2)}) — the area is mostly bare or built-up with limited vegetation.`;

  const pxSizeX = parseFloat(stats.pixel_size_x);
  const pxSizeY = parseFloat(stats.pixel_size_y);
  const pxUnit  = stats.pixel_unit || "";
  const pixelSizeStr = (!isNaN(pxSizeX) && !isNaN(pxSizeY))
    ? `${pxSizeX.toFixed(4)} × ${pxSizeY.toFixed(4)}${pxUnit ? " " + pxUnit : ""}`
    : "—";

  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">GeoTIFF file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.fileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Dimensions</div>
      <div class="value">${stats.img_width || "—"} × ${stats.img_height || "—"} px</div>
    </div>
    <div class="insight-card">
      <div class="label">Pixel Size</div>
      <div class="value">${pixelSizeStr}</div>
    </div>
    <div class="insight-card">
      <div class="label">Satellite</div>
      <div class="value">${stats.satellite || "Unknown"}</div>
    </div>
    <div class="insight-card">
      <div class="label">Red band</div>
      <div class="value">${stats.red_band || "—"} → Red</div>
    </div>
    <div class="insight-card">
      <div class="label">NIR band</div>
      <div class="value">${stats.nir_band || "—"} → NIR</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">NDVI — Results</h3>
      <p class="panel-desc">NDVI ranges −1 to 1. Values &gt; 0.2 = healthy vegetation. Map: green = high NDVI · red = low NDVI.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        <div style="margin-bottom:12px;">
          <div style="height:16px;width:100%;border-radius:4px;background:linear-gradient(to right,rgb(200,20,0),rgb(200,200,0),rgb(0,150,0));border:1px solid rgba(255,255,255,0.15);"></div>
          <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-top:3px;">
            <span>${minNDVI.toFixed(2)} (low)</span>
            <span>NDVI Scale</span>
            <span>(high) ${maxNDVI.toFixed(2)}</span>
          </div>
        </div>
        <div class="insight-card">
          <div class="label">Overall Score</div>
          <div class="value" style="color:${scoreColor}">${ndviScore} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Vegetation Health</div>
          <div class="value" style="color:${vegHealthClass.color};font-size:13px;">${vegHealthClass.label}</div>
        </div>
        <div class="insight-card">
          <div class="label">Mean NDVI</div>
          <div class="value">${meanNDVI.toFixed(4)}</div>
        </div>
        <div class="insight-card">
          <div class="label">Min NDVI</div>
          <div class="value">${minNDVI.toFixed(4)}</div>
        </div>
        <div class="insight-card">
          <div class="label">Max NDVI</div>
          <div class="value">${maxNDVI.toFixed(4)}</div>
        </div>
        <div class="insight-card">
          <div class="label">Std. Deviation</div>
          <div class="value">${stdNDVI.toFixed(4)}</div>
        </div>
        <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Vegetation Coverage</div>
        <div class="insight-card">
          <div class="label" style="color:#e74c3c;">No Vegetation (&lt; 0)</div>
          <div class="value">${stats.pct_no_veg ?? "—"}%</div>
        </div>
        <div class="insight-card">
          <div class="label" style="color:#e67e22;">Bare Soil (0.0 – 0.2)</div>
          <div class="value">${stats.pct_bare_soil ?? "—"}%</div>
        </div>
        <div class="insight-card">
          <div class="label" style="color:#f39c12;">Moderate Vegetation (0.2 – 0.6)</div>
          <div class="value">${stats.pct_moderate ?? "—"}%</div>
        </div>
        <div class="insight-card">
          <div class="label" style="color:#27ae60;">Dense Vegetation (0.6 – 1.0)</div>
          <div class="value">${stats.pct_dense ?? "—"}%</div>
        </div>
        ${histogramHtml}
        <div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/pulsar-line/48/FFFFFF/tif.png" alt="tif"/>
          Download GeoTIFF
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the 200 m cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('ndvi')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Render Heat Index Results with stats ---------- */
function renderHeatIndexResults(stats, inputs) {
  const meanTemp = parseFloat(stats.mean) || 0;
  const minTemp  = parseFloat(stats.min)  || 0;
  const maxTemp  = parseFloat(stats.max)  || 0;
  const validPx  = parseInt(stats.valid_pixels) || 0;

  // Score: cooler = better. < 27 = 100, 38+ = 0
  const heatScore = Math.max(0, Math.min(100, Math.round(((38 - meanTemp) / 11) * 100)));
  const cat = perfCategory(heatScore);
  const scoreColor = qolScoreTextColor(heatScore);

  const heatClass = meanTemp < 27 ? "Comfortable"
    : meanTemp < 32 ? "Caution"
    : meanTemp < 38 ? "Extreme Caution"
    : "Danger";
  const heatClassColor = meanTemp < 27 ? "var(--success)"
    : meanTemp < 32 ? "#8bc34a"
    : meanTemp < 38 ? "var(--warning)"
    : "var(--danger)";

  const tempRange = Math.max(0.1, maxTemp - minTemp);
  const cool = Math.max(0, ((27 - minTemp) / tempRange * 100)).toFixed(1);
  const caution = Math.max(0, (Math.min(32, maxTemp) - Math.max(27, minTemp)) / tempRange * 100).toFixed(1);
  const hot = Math.max(0, ((maxTemp - Math.max(32, minTemp)) / tempRange * 100)).toFixed(1);
  const chartHtml = miniBarChart(
    [cool, caution, hot],
    3,
    ["#4cc2ff", "#f39c12", "#e74c3c"],
    ["Cool", "Caution", "Hot"]
  );

  const ineq = inequalityLabel(calcStdDev([minTemp, meanTemp, maxTemp]));

  const keyInsight = meanTemp >= 38
    ? `Dangerous heat levels detected — mean temperature is ${meanTemp.toFixed(1)}°C. Urgent cooling interventions needed.`
    : meanTemp >= 32
    ? `High heat stress across the area (avg ${meanTemp.toFixed(1)}°C). Green spaces or cool corridors could help.`
    : meanTemp >= 27
    ? `Moderate heat (avg ${meanTemp.toFixed(1)}°C). Some zones may need shade or cooling infrastructure.`
    : `Thermal comfort is good — mean temperature is ${meanTemp.toFixed(1)}°C, below the caution threshold.`;

  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">GeoTIFF file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.fileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Total Pixels (Features)</div>
      <div class="value">${validPx.toLocaleString()}</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Heat Index — Results</h3>
      <p class="panel-desc">Surface temperature in °C. &lt;27 = Comfortable · 27–32 = Caution · 32–38 = Extreme · ≥38 = Danger.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        <div class="insight-card">
          <div class="label">Overall Score</div>
          <div class="value" style="color:${scoreColor}">${heatScore} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>
        <div class="insight-card">
          <div class="label">Thermal Class</div>
          <div class="value" style="color:${heatClassColor}">${heatClass}</div>
        </div>
        <div class="insight-card">
          <div class="label">Mean Temp (°C)</div>
          <div class="value">${stats.mean || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Min Temp (°C)</div>
          <div class="value">${stats.min || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Max Temp (°C)</div>
          <div class="value" style="color:${maxTemp >= 38 ? "var(--danger)" : "inherit"}">${stats.max || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Valid Pixels</div>
          <div class="value">${validPx.toLocaleString()}</div>
        </div>
        <div class="insight-card">
          <div class="label">Temperature Spread</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>
        ${chartHtml}
        <div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/pulsar-line/48/tif.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoTIFF
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the 200 m cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('heat-index')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Air Quality Analysis - calls backend API ---------- */
async function runAirQualityAnalysis() {
  const tiffInput = document.getElementById("tiffInput");

  if (!tiffInput || !tiffInput.files[0]) {
    alert("Please upload a GeoTIFF file first.");
    return;
  }

  const file = tiffInput.files[0];
  const inputs = { fileName: file.name };

  const formData = new FormData();
  formData.append("geotiff", file);

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Air Quality Index — Processing</h3>
      <p class="panel-desc">Classifying AQI from uploaded raster...</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
      </div>
    </div>
  `;

 try {
  const response = await fetch(`${API_BASE_URL}/calculate-air-quality`, {
    method: "POST",
    body: formData,
  });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }

    const pollutant       = response.headers.get("X-Pollutant");
    const validPixels     = response.headers.get("X-Valid-Pixels");
    const goodPct         = response.headers.get("X-Good-Pct");
    const moderatePct     = response.headers.get("X-Moderate-Pct");
    const sensitivePct    = response.headers.get("X-Sensitive-Pct");
    const unhealthyPct    = response.headers.get("X-Unhealthy-Pct");
    const veryUnhealthyPct= response.headers.get("X-Very-Unhealthy-Pct");
    const hazardousPct    = response.headers.get("X-Hazardous-Pct");

    const arrayBuffer = await response.arrayBuffer();
    lastResultBlob    = arrayBuffer.slice(0);
    lastResultService = "air-quality";
    if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

    resultLayer = await renderGeoRasterFromArrayBuffer(arrayBuffer, {
      opacity: 0.9,
      resolution: 256,
    });

    renderAirQualityResults({
      pollutant,
      valid_pixels:      validPixels,
      good_pct:          goodPct,
      moderate_pct:      moderatePct,
      sensitive_pct:     sensitivePct,
      unhealthy_pct:     unhealthyPct,
      very_unhealthy_pct: veryUnhealthyPct,
      hazardous_pct:     hazardousPct,
    }, inputs);

  } catch (error) {
    console.error("Air quality calculation error:", error);
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate AQI: ${error.message}</p>
        <div class="alert alert-warning mt-2">
          <strong>Note:</strong> Upload a single-band GeoTIFF. Pollutant type is
          auto-detected from the filename (include "pm25", "pm10", "no2", or "aqi").
        </div>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('air-quality')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}


/* ---------- Render Air Quality Results ---------- */
function renderAirQualityResults(stats, inputs) {
  const goodPct    = parseFloat(stats.good_pct)          || 0;
  const modPct     = parseFloat(stats.moderate_pct)      || 0;
  const sensPct    = parseFloat(stats.sensitive_pct)     || 0;
  const unhPct     = parseFloat(stats.unhealthy_pct)     || 0;
  const vUnhPct    = parseFloat(stats.very_unhealthy_pct)|| 0;
  const hazPct     = parseFloat(stats.hazardous_pct)     || 0;
  const validPx    = parseInt(stats.valid_pixels)        || 0;

  // Score: weighted sum — good=100, hazardous=0
  const aqiScore = Math.round(
    (goodPct * 100 + modPct * 75 + sensPct * 55 + unhPct * 35 + vUnhPct * 15 + hazPct * 0) / 100
  );
  const cat = perfCategory(aqiScore);
  const scoreColor = qolScoreTextColor(aqiScore);

  const cleanPct  = (goodPct + modPct).toFixed(1);
  const riskyPct  = (unhPct + vUnhPct + hazPct).toFixed(1);

  const chartHtml = miniBarChart(
    [goodPct.toFixed(1), modPct.toFixed(1), sensPct.toFixed(1), unhPct.toFixed(1), vUnhPct.toFixed(1), hazPct.toFixed(1)],
    6,
    ["#2ecc71", "#8bc34a", "#f39c12", "#e67e22", "#c0392b", "#8e0e0e"],
    ["Good", "Mod", "Sens", "Unhl", "V.Unhl", "Haz"]
  );

  const ineq = inequalityLabel(calcStdDev([goodPct, modPct, sensPct, unhPct, vUnhPct, hazPct]));

  const keyInsight = parseFloat(riskyPct) > 30
    ? `${riskyPct}% of the area has unhealthy or worse air quality — this zone requires urgent attention.`
    : parseFloat(cleanPct) > 70
    ? `Air quality is mostly good — ${cleanPct}% of the area meets acceptable standards.`
    : `Mixed air quality: ${cleanPct}% is acceptable while ${riskyPct}% poses health risks.`;

  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">GeoTIFF file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.fileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Total Pixels (Features)</div>
      <div class="value">${validPx.toLocaleString()}</div>
    </div>
    <div class="insight-card">
      <div class="label">Pollutant detected</div>
      <div class="value">${stats.pollutant || "N/A"}</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Air Quality Index — Results</h3>
      <p class="panel-desc">AQI: ≤50 Good · 51–100 Moderate · 101–150 Sensitive · 151–200 Unhealthy · 201–300 Very Unhealthy · &gt;300 Hazardous.</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        <div class="insight-card">
          <div class="label">Overall Score</div>
          <div class="value" style="color:${scoreColor}">${aqiScore} / 100</div>
        </div>
        <div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>
        <div class="insight-card">
          <div class="label">Valid Pixels</div>
          <div class="value">${validPx.toLocaleString()}</div>
        </div>
        <div class="insight-card">
          <div class="label">Good (AQI ≤ 50)</div>
          <div class="value" style="color:var(--success)">${goodPct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Moderate (51–100)</div>
          <div class="value">${modPct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Sensitive Groups (101–150)</div>
          <div class="value" style="color:var(--warning)">${sensPct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Unhealthy (151–200)</div>
          <div class="value" style="color:var(--danger)">${unhPct.toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Very Unhealthy / Hazardous</div>
          <div class="value" style="color:var(--danger)">${(vUnhPct + hazPct).toFixed(1)}%</div>
        </div>
        <div class="insight-card">
          <div class="label">Distribution Balance</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>
        ${chartHtml}
        <div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/pulsar-line/48/FFFFFF/tif.png" alt="tif"/>
          Download GeoTIFF
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('air-quality')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Render Facility Accessibility Results ---------- */
function renderFacilityAccessibilityResults(stats, inputs, geojsonData) {
  const pct5  = stats.pct_5min  !== null ? parseFloat(stats.pct_5min)  : null;
  const pct10 = stats.pct_10min !== null ? parseFloat(stats.pct_10min) : null;
  const pct15 = stats.pct_15min !== null ? parseFloat(stats.pct_15min) : null;

  const totalFacilities     = parseInt(stats.total_facilities)     || "N/A";
  const facilitiesProcessed = parseInt(stats.facilities_processed) || "N/A";

  // Weighted overall score (5-min access weighted highest)
  const overallScore = (pct5 !== null || pct10 !== null || pct15 !== null)
    ? Math.round(
        (pct5  ?? 0) * 0.5 +
        (pct10 ?? 0) * 0.3 +
        (pct15 ?? 0) * 0.2
      )
    : null;
  const cat        = overallScore !== null ? perfCategory(overallScore) : null;
  const scoreColor = overallScore !== null ? qolScoreTextColor(overallScore) : "#888";

  const chartHtml = (pct5 !== null || pct15 !== null) ? miniBarChart(
    [
      (pct5  ?? 0).toFixed(1),
      ((pct10 ?? 0) - (pct5 ?? 0)).toFixed(1),
      ((pct15 ?? 0) - (pct10 ?? 0)).toFixed(1),
    ],
    3,
    ["#198754", "#ffc107", "#dc3545"],
    ["≤ 5 min", "5–10 min", "10–15 min"]
  ) : "";

  const ineq = pct5 !== null && pct15 !== null
    ? inequalityLabel(calcStdDev([pct5, pct10 ?? 0, pct15]))
    : null;

  const keyInsight = pct5 !== null
    ? pct5 > 50
      ? `More than half the service area is within a 5-minute walk — excellent accessibility.`
      : pct15 > 70
      ? `${pct15.toFixed(1)}% of the service area is reachable within 15 minutes, but 5-minute access is limited to ${pct5.toFixed(1)}%.`
      : `Facility coverage is limited — only ${(pct15 ?? 0).toFixed(1)}% of the service area is within a 15-minute walk.`
    : null;

  // Raw Data tab: input summary
  const inputsHtml = `
    <p class="text-muted" style="font-size:11px;">Input data summary. Facility points are shown on the map.</p>
    <div class="insight-card">
      <div class="label">Facilities file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.facilitiesFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Total features</div>
      <div class="value">${totalFacilities}</div>
    </div>
    <div class="insight-card">
      <div class="label">Facilities processed</div>
      <div class="value">${facilitiesProcessed}</div>
    </div>
    <div class="insight-card">
      <div class="label">Walking speed</div>
      <div class="value">${inputs.walkingSpeed} km/h</div>
    </div>
    <div class="insight-card">
      <div class="label">Network download radius</div>
      <div class="value">${parseInt(inputs.networkDist).toLocaleString()} m</div>
    </div>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Facility Accessibility — Results</h3>
      <p class="panel-desc">Walkable service areas: Green = 5 min · Yellow = 10 min · Red = 15 min</p>

      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <div class="tab-content" id="tab-raw">
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        ${overallScore !== null ? `<div class="insight-card">
          <div class="label">Overall Score</div>
          <div class="value" style="color:${scoreColor}">${overallScore} / 100</div>
        </div>` : ""}
        ${cat ? `<div class="insight-card">
          <div class="label">Performance</div>
          <div class="value" style="color:${cat.color};font-size:15px;">${cat.label}</div>
        </div>` : ""}
        <div class="insight-card">
          <div class="label">Facilities analyzed</div>
          <div class="value">${facilitiesProcessed}</div>
        </div>
        <div class="insight-card">
          <div class="label">Walking speed</div>
          <div class="value">${inputs.walkingSpeed} km/h</div>
        </div>
        ${pct5  !== null ? `<div class="insight-card">
          <div class="label">Within 5-min walk</div>
          <div class="value" style="color:#198754">${pct5.toFixed(1)}%</div>
        </div>` : ""}
        ${pct10 !== null ? `<div class="insight-card">
          <div class="label">Within 10-min walk</div>
          <div class="value" style="color:#ffc107">${pct10.toFixed(1)}%</div>
        </div>` : ""}
        ${pct15 !== null ? `<div class="insight-card">
          <div class="label">Within 15-min walk</div>
          <div class="value" style="color:#dc3545">${pct15.toFixed(1)}%</div>
        </div>` : ""}
        ${ineq ? `<div class="insight-card">
          <div class="label">Coverage Balance</div>
          <div class="value" style="color:${ineq.color};font-size:13px;">${ineq.text}</div>
        </div>` : ""}
        ${chartHtml}
        ${keyInsight ? `<div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-top:8px;font-size:12px;color:var(--text-primary);">
          💡 ${keyInsight}
        </div>` : ""}
        <button class="btn btn-ghost btn-block" style="margin-top:12px;font-size:12px;" data-full-dl="true">
          <img width="18" height="18" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="download" style="vertical-align:middle;margin-right:4px;"/>
          Download GeoJSON
        </button>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('facility_Accessibility_index')">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Render the tabbed Results panel ---------- */
function renderResults(service) {
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">${service.title} — Results</h3>
      <p class="panel-desc">Analysis complete. Explore tabs below.</p>

      <!-- Tab headers -->
      <div class="tabs">
        <div class="tab"        data-tab="raw">Raw Data</div>
        <div class="tab active" data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- Tab contents -->
      <div class="tab-content" id="tab-raw">
        <p class="text-muted">Uploaded input data.</p>
        <div class="insight-card">
          <div class="label">Files submitted</div>
          <div class="value">1</div>
        </div>
      </div>

      <div class="tab-content active" id="tab-full">
        <p class="text-muted" style="font-size:12px;">Results will appear here once the backend returns analysis data.</p>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Click this tab to generate the 200 m cell grid…</p>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel(getActiveServiceKey())">
        ← Back to inputs
      </button>
    </div>
  `;

  wireTabSwitching();
}


/* ---------- Helper: which service is currently selected? ---------- */
function getActiveServiceKey() {
  const active = serviceList.querySelector("li.active");
  return active ? active.getAttribute("data-service") : null;
}


/* ---------- Helper: wire up tab switching + map layer toggle ---------- */
function wireTabSwitching() {
  analysisPanel.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", async function () {
      const target = tab.getAttribute("data-tab");
      analysisPanel.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      analysisPanel.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      analysisPanel.querySelector("#tab-" + target).classList.add("active");

      if (target === "raw") {
        if (gridLayer && map.hasLayer(gridLayer)) map.removeLayer(gridLayer);
        // For crime: show both the boundary result layer and the crime point input layer
        if (lastResultService === "crime") {
          if (resultLayer && !map.hasLayer(resultLayer)) {
            try { resultLayer.addTo(map); } catch (e) {}
          }
          if (inputLayer && !map.hasLayer(inputLayer)) {
            try { inputLayer.addTo(map); } catch (e) {}
          }
          if (resultLayer) {
            try {
              const b = resultLayer.getBounds ? resultLayer.getBounds() : null;
              if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
            } catch (e) {}
          }
        } else {
          if (resultLayer && map.hasLayer(resultLayer)) map.removeLayer(resultLayer);
          if (inputLayer && !map.hasLayer(inputLayer)) {
            try {
              inputLayer.addTo(map);
              const b = inputLayer.getBounds ? inputLayer.getBounds() : null;
              if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
            } catch (e) { console.warn("Could not restore input layer:", e); }
          }
        }

      } else if (target === "full") {
        if (inputLayer && map.hasLayer(inputLayer)) map.removeLayer(inputLayer);
        if (gridLayer  && map.hasLayer(gridLayer))  map.removeLayer(gridLayer);
        if (resultLayer && !map.hasLayer(resultLayer)) {
          try {
            resultLayer.addTo(map);
            const b = resultLayer.getBounds ? resultLayer.getBounds() : null;
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch (e) { console.warn("Could not restore result layer:", e); }
        }
        _wireFullDownloadBtn();

      } else if (target === "grid") {
        if (inputLayer  && map.hasLayer(inputLayer))  map.removeLayer(inputLayer);
        if (resultLayer && map.hasLayer(resultLayer)) map.removeLayer(resultLayer);

        // If grid layer already loaded, just show it
        if (gridLayer) {
          if (!map.hasLayer(gridLayer)) gridLayer.addTo(map);
          try {
            const b = gridLayer.getBounds();
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch(e) {}
          return;
        }

        // Need to fetch — show loading indicator in the tab content
        const gridTabContent = analysisPanel.querySelector("#tab-grid");
        if (gridTabContent) {
          gridTabContent.innerHTML = `
            <div class="text-center my-4">
              <div class="spinner-border text-primary" role="status"></div>
              <p class="text-muted mt-2">Generating cell grid (cell size auto-scaled to area)…</p>
            </div>`;
        }

        if (!lastResultBlob || !lastResultService) {
          if (gridTabContent) gridTabContent.innerHTML = `<p class="text-muted">No analysis result available to grid.</p>`;
          return;
        }

        try {
          const geojson = await fetchAndRenderGrid(lastResultService, lastResultBlob);
          gridLayer.addTo(map);

          // For traffic: overlay hotspot outlines on the congestion grid
          if (lastResultService === "traffic" && lastResultBlob) {
            const hotspotFeats = lastResultBlob.features.filter(f => f.properties.type === "hotspot");
            if (hotspotFeats.length > 0) {
              L.geoJSON({ type: "FeatureCollection", features: hotspotFeats }, {
                style: { color: "#c0392b", weight: 2.5, fill: false, dashArray: "6,3" },
              }).addTo(map);
            }
          }

          try {
            const b = gridLayer.getBounds();
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch(e) {}

          // Compute summary stats from geojson
          const scores = geojson.features
            .map(f => f.properties.qol_score)
            .filter(s => s !== null && s !== undefined);
          const avg      = scores.length ? Math.round(scores.reduce((a,b) => a+b, 0) / scores.length) : null;
          const best     = scores.length ? Math.max(...scores) : null;
          const worst    = scores.length ? Math.min(...scores) : null;
          const cellCount = geojson.features.length;
          const cellSizeM = geojson.cell_size_m || "?";
          const cellLabel = cellSizeM >= 1000
            ? `${(cellSizeM / 1000).toFixed(1)} km`
            : `${cellSizeM} m`;

          if (gridTabContent) {
            const isNDVIGrid    = lastResultService === "ndvi";
            const isVegGrid     = lastResultService === "vegetation";
            const isTrafficGrid = lastResultService === "traffic";
            const isISPAGrid    = lastResultService === "informal-settlement";

            // ---- NDVI vegetation health counts ----
            let ndviHealthy = 0, ndviUnhealthy = 0, ndviValues = [];
            if (isNDVIGrid) {
              geojson.features.forEach(f => {
                const v = f.properties.value;
                if (v !== null && v !== undefined) {
                  ndviValues.push(v);
                  if (v >= 0.2) ndviHealthy++; else ndviUnhealthy++;
                }
              });
            }
            const ndviUnhealthyPct = ndviValues.length
              ? ((ndviUnhealthy / ndviValues.length) * 100).toFixed(1) : null;
            const ndviHealthyPct = ndviValues.length
              ? ((ndviHealthy / ndviValues.length) * 100).toFixed(1) : null;

            // ---- Vegetation counts ----
            let vegPassCount = 0, vegFailCount = 0, vegPctValues = [];
            if (isVegGrid) {
              geojson.features.forEach(f => {
                const p = f.properties;
                if (p.passes_30pct) vegPassCount++; else vegFailCount++;
                if (p.value !== null && p.value !== undefined) vegPctValues.push(p.value);
              });
            }
            const vegAvgPct = vegPctValues.length
              ? (vegPctValues.reduce((a,b) => a+b, 0) / vegPctValues.length).toFixed(1) : null;

            // ---- Traffic counts ----
            let trafficLow = 0, trafficMed = 0, trafficHigh = 0;
            if (isTrafficGrid) {
              geojson.features.forEach(f => {
                const c = f.properties.congestion;
                if (c === "high") trafficHigh++; else if (c === "medium") trafficMed++; else trafficLow++;
              });
            }

            // ---- ISPA counts ----
            let ispaLow = 0, ispaMed = 0, ispaHigh = 0, ispaIrrValues = [];
            if (isISPAGrid) {
              geojson.features.forEach(f => {
                const cls = f.properties.classification;
                if (cls === "high") ispaHigh++; else if (cls === "medium") ispaMed++; else ispaLow++;
                if (f.properties.value !== null && f.properties.value !== undefined)
                  ispaIrrValues.push(f.properties.value);
              });
            }
            const ispaAvgIrr = ispaIrrValues.length
              ? (ispaIrrValues.reduce((a,b) => a+b, 0) / ispaIrrValues.length).toFixed(1) : null;

            // ---- Generic QoL tier counts ----
            let tierExcellent = 0, tierGood = 0, tierPoor = 0, tierBad = 0;
            if (!isVegGrid && !isTrafficGrid && !isISPAGrid) {
              scores.forEach(s => {
                if (s >= 75) tierExcellent++;
                else if (s >= 50) tierGood++;
                else if (s >= 25) tierPoor++;
                else tierBad++;
              });
            }

            // ---- Best / Worst cell (score + raw value) ----
            let bestFeature = null, worstFeature = null;
            if (scores.length) {
              bestFeature  = geojson.features.reduce((a, b) => (b.properties.qol_score || 0) > (a?.properties.qol_score || 0) ? b : a, geojson.features[0]);
              worstFeature = geojson.features.reduce((a, b) => (b.properties.qol_score || 0) < (a?.properties.qol_score || 999) ? b : a, geojson.features[0]);
            }
            const bestVal  = bestFeature  ? (bestFeature.properties.value  ?? bestFeature.properties.vegetation_pct  ?? bestFeature.properties.irregularity_score ?? "—") : "—";
            const worstVal = worstFeature ? (worstFeature.properties.value ?? worstFeature.properties.vegetation_pct ?? worstFeature.properties.irregularity_score ?? "—") : "—";

            // ---- Spatial clustering ----
            const clusterInfo = scores.length >= 4 ? clusteringLabel(scores) : null;

            // ---- Distribution bar chart ----
            let gridChartHtml = "";
            if (isVegGrid) {
              gridChartHtml = miniBarChart(
                [vegPassCount, vegFailCount],
                2, [vegPctColor(75), "#c0392b"], ["≥30%", "<30%"]
              );
            } else if (isTrafficGrid) {
              gridChartHtml = miniBarChart(
                [trafficLow, trafficMed, trafficHigh],
                3, ["#2ecc71", "#f39c12", "#e74c3c"], ["Low", "Med", "High"]
              );
            } else if (isISPAGrid) {
              gridChartHtml = miniBarChart(
                [ispaLow, ispaMed, ispaHigh],
                3, [irregularityColor(10), irregularityColor(50), irregularityColor(85)], ["Planned", "Mixed", "Informal"]
              );
            } else if (isNDVIGrid) {
              gridChartHtml = miniBarChart(
                [ndviHealthy, ndviUnhealthy],
                2, ["#27ae60", "#e74c3c"], ["Healthy (≥0.2)", "Unhealthy (<0.2)"]
              );
            } else if (scores.length) {
              gridChartHtml = miniBarChart(
                [tierExcellent, tierGood, tierPoor, tierBad],
                4, [qolScoreColor(88), qolScoreColor(62), qolScoreColor(37), qolScoreColor(12)],
                ["Exc.", "Good", "Poor", "Bad"]
              );
            }

            // ---- Tier legend ----
            const tiersHtml = isVegGrid ? `
              <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Vegetation tiers</div>
              <div style="display:flex;flex-direction:column;gap:4px;">
                ${[["Excellent","≥ 50%",75],["Good","30–50%",38],["Poor","15–30%",20],["Bad","0–15%",5]].map(([l,r,v])=>`
                <div style="display:flex;align-items:center;gap:8px;font-size:11px;">
                  <div style="width:12px;height:12px;background:${vegPctColor(v)};border-radius:2px;flex-shrink:0;"></div>
                  <span><strong>${l}</strong> ${r}</span>
                </div>`).join("")}
              </div>` : isTrafficGrid ? `
              <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Congestion levels</div>
              <div style="display:flex;flex-direction:column;gap:4px;">
                ${[["Low","optimal","#2ecc71"],["Medium","partial risk","#f39c12"],["High","hotspot","#e74c3c"]].map(([l,r,c])=>`
                <div style="display:flex;align-items:center;gap:8px;font-size:11px;">
                  <div style="width:12px;height:12px;background:${c};border-radius:2px;flex-shrink:0;"></div>
                  <span><strong>${l}</strong> ${r}</span>
                </div>`).join("")}
              </div>` : isISPAGrid ? `
              <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Irregularity tiers</div>
              <div style="display:flex;flex-direction:column;gap:4px;">
                ${[["Low (Planned)","0–33",10],["Medium","34–66",50],["High (Informal)","67–100",85]].map(([l,r,v])=>`
                <div style="display:flex;align-items:center;gap:8px;font-size:11px;">
                  <div style="width:12px;height:12px;background:${irregularityColor(v)};border-radius:2px;flex-shrink:0;"></div>
                  <span><strong>${l}</strong> ${r}</span>
                </div>`).join("")}
              </div>` : lastResultService === "urban-density" ? `
              <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Score tiers (target: 5,000 pop/km²)</div>
              <div style="display:flex;flex-direction:column;gap:4px;">
                ${[[88,"Excellent","near 5,000 pop/km²"],[62,"Good","2,500–10,000 pop/km²"],[37,"Fair","500–2,500 or 10,000–20,000"],[12,"Poor","< 500 or > 20,000 pop/km²"]].map(([v,l,r])=>`
                <div style="display:flex;align-items:center;gap:8px;font-size:11px;">
                  <div style="width:12px;height:12px;background:${qolScoreColor(v)};border-radius:2px;flex-shrink:0;"></div>
                  <span><strong>${l}</strong> ${r}</span>
                </div>`).join("")}
              </div>` : `
              <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Score tiers</div>
              <div style="display:flex;flex-direction:column;gap:4px;">
                ${[[88,"Excellent","75–100"],[62,"Good","50–74"],[37,"Fair","25–49"],[12,"Poor","0–24"]].map(([v,l,r])=>`
                <div style="display:flex;align-items:center;gap:8px;font-size:11px;">
                  <div style="width:12px;height:12px;background:${qolScoreColor(v)};border-radius:2px;flex-shrink:0;"></div>
                  <span><strong>${l}</strong> ${r}</span>
                </div>`).join("")}
              </div>`;

            const isUrbanDensityGrid = lastResultService === "urban-density";

            // ---- Urban density histogram (pop/km² bins) ----
            let densityHistogramHtml = "";
            if (isUrbanDensityGrid && lastUrbanDensityFeatures && lastUrbanDensityFeatures.length) {
              const denBins  = [0, 0, 0, 0, 0];  // <500, 500–2500, 2500–5000, 5000–10000, >10000
              const denLabels = ["<500", "500–2.5k", "2.5k–5k", "5k–10k", ">10k"];
              const denColors = ["#4cc2ff", "#7ecbff", "#f39c12", "#e67e22", "#e74c3c"];
              lastUrbanDensityFeatures.forEach(({ density: d }) => {
                if (d < 500)        denBins[0]++;
                else if (d < 2500)  denBins[1]++;
                else if (d < 5000)  denBins[2]++;
                else if (d < 10000) denBins[3]++;
                else                denBins[4]++;
              });
              const maxBin = Math.max(...denBins, 1);
              densityHistogramHtml = `
                <div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Density Histogram (pop/km²)</div>
                <div style="display:flex;align-items:flex-end;gap:3px;height:48px;margin-bottom:4px;">
                  ${denBins.map((v, i) => {
                    const h = Math.max(3, Math.round((v / maxBin) * 46));
                    const isOptimal = i === 2;
                    return `<div title="${denLabels[i]}: ${v} area(s)" style="flex:1;height:${h}px;background:${denColors[i]};border-radius:2px 2px 0 0;position:relative;">
                      ${isOptimal ? `<div style="position:absolute;top:-14px;left:50%;transform:translateX(-50%);font-size:9px;color:var(--accent);white-space:nowrap;">★ target</div>` : ""}
                    </div>`;
                  }).join("")}
                </div>
                <div style="display:flex;gap:3px;">
                  ${denLabels.map(l => `<div style="flex:1;font-size:9px;color:var(--text-muted);text-align:center;overflow:hidden;white-space:nowrap;">${l}</div>`).join("")}
                </div>
                <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">★ 2,500–5,000 band is closest to the 5,000 pop/km² healthy target</div>`;
            }

            gridTabContent.innerHTML = `
              <p style="font-size:11px;color:var(--text-muted);margin:0 0 8px;">Cell size: <strong>${cellLabel} × ${cellLabel}</strong> · Click any cell on the map for details.</p>
              ${isUrbanDensityGrid ? `<div style="background:rgba(76,194,255,0.08);border-left:3px solid var(--accent);border-radius:4px;padding:8px 10px;margin-bottom:8px;font-size:12px;color:var(--text-primary);">
                💡 Scores are based on the healthy recommended population density of <strong>5,000 pop/km²</strong>. Cells closer to this target score higher — both under- and over-populated areas score lower.
              </div>` : ""}
              <div class="insight-card">
                <div class="label">Total Cells</div>
                <div class="value">${cellCount}</div>
              </div>
              ${avg !== null ? `
              <div class="insight-card">
                <div class="label">Average Score</div>
                <div class="value" style="color:${qolScoreTextColor(avg)}">${avg} / 100</div>
              </div>` : ""}
              ${isNDVIGrid && ndviUnhealthyPct !== null ? `
              <div class="insight-card">
                <div class="label">Unhealthy Vegetation Cells</div>
                <div class="value" style="color:#e74c3c;">${ndviUnhealthyPct}% <span style="font-size:11px;color:var(--text-muted);">(NDVI &lt; 0.2)</span></div>
              </div>
              <div class="insight-card">
                <div class="label">Healthy Vegetation Cells</div>
                <div class="value" style="color:#27ae60;">${ndviHealthyPct}% <span style="font-size:11px;color:var(--text-muted);">(NDVI ≥ 0.2)</span></div>
              </div>` : ""}
              ${isVegGrid ? `
              <div class="insight-card">
                <div class="label">Cells meeting 30% benchmark</div>
                <div class="value"><span style="color:var(--success)">${vegPassCount} pass</span> &nbsp;/&nbsp; <span style="color:var(--danger)">${vegFailCount} fail</span></div>
              </div>
              <div class="insight-card">
                <div class="label">% Pass / % Fail</div>
                <div class="value">${cellCount ? ((vegPassCount/cellCount)*100).toFixed(1) : 0}% / ${cellCount ? ((vegFailCount/cellCount)*100).toFixed(1) : 0}%</div>
              </div>` : isTrafficGrid ? `
              <div class="insight-card">
                <div class="label">Cell breakdown</div>
                <div class="value" style="font-size:13px;"><span style="color:var(--success)">${cellCount ? ((trafficLow/cellCount)*100).toFixed(0) : 0}% Low</span> · <span style="color:var(--warning)">${cellCount ? ((trafficMed/cellCount)*100).toFixed(0) : 0}% Med</span> · <span style="color:var(--danger)">${cellCount ? ((trafficHigh/cellCount)*100).toFixed(0) : 0}% High</span></div>
              </div>` : isISPAGrid ? `
              <div class="insight-card">
                <div class="label">Cell breakdown</div>
                <div class="value" style="font-size:13px;"><span style="color:var(--success)">${cellCount ? ((ispaLow/cellCount)*100).toFixed(0) : 0}% Planned</span> · <span style="color:var(--warning)">${cellCount ? ((ispaMed/cellCount)*100).toFixed(0) : 0}% Mixed</span> · <span style="color:var(--danger)">${cellCount ? ((ispaHigh/cellCount)*100).toFixed(0) : 0}% Informal</span></div>
              </div>` : `
              <div class="insight-card">
                <div class="label">Cell breakdown</div>
                <div class="value" style="font-size:13px;"><span style="color:${qolScoreColor(88)}">${cellCount ? ((tierExcellent/cellCount)*100).toFixed(0) : 0}% Exc</span> · <span style="color:${qolScoreColor(62)}">${cellCount ? ((tierGood/cellCount)*100).toFixed(0) : 0}% Good</span> · <span style="color:${qolScoreColor(37)}">${cellCount ? ((tierPoor/cellCount)*100).toFixed(0) : 0}% Fair</span> · <span style="color:${qolScoreColor(12)}">${cellCount ? ((tierBad/cellCount)*100).toFixed(0) : 0}% Poor</span></div>
              </div>`}
              ${best !== null ? `
              <div class="insight-card">
                <div class="label">Best Cell</div>
                <div class="value" style="color:${qolScoreTextColor(best)}">${best}/100 <span style="font-size:11px;color:var(--text-muted);">(value: ${typeof bestVal === "number" ? bestVal.toFixed ? bestVal.toFixed(2) : bestVal : bestVal})</span></div>
              </div>
              <div class="insight-card">
                <div class="label">Worst Cell</div>
                <div class="value" style="color:${qolScoreTextColor(worst)}">${worst}/100 <span style="font-size:11px;color:var(--text-muted);">(value: ${typeof worstVal === "number" ? worstVal.toFixed ? worstVal.toFixed(2) : worstVal : worstVal})</span></div>
              </div>` : ""}
              ${clusterInfo && lastResultService !== "public-transport" && lastResultService !== "crime" ? `<div class="insight-card">
                <div class="label">Spatial Clustering</div>
                <div class="value" style="color:${clusterInfo.color};font-size:13px;">${clusterInfo.text}</div>
              </div>` : ""}
              ${lastResultService === "crime" && scores.length >= 2 ? (() => {
                const scoreMin = Math.min(...scores);
                const scoreMax = Math.max(...scores);
                const scoreRange = scoreMax - scoreMin;
                const scoreAvg = scores.reduce((a, b) => a + b, 0) / scores.length;
                const cv = scoreAvg > 0 ? (Math.sqrt(scores.reduce((s, v) => s + Math.pow(v - scoreAvg, 2), 0) / scores.length) / scoreAvg * 100) : 0;
                let ineqLabel, ineqColor;
                if (cv < 15)       { ineqLabel = "Low inequality — safety is fairly uniform"; ineqColor = "#2ecc71"; }
                else if (cv < 35)  { ineqLabel = "Moderate inequality — some unsafe pockets"; ineqColor = "#f39c12"; }
                else               { ineqLabel = "High inequality — large safety disparities"; ineqColor = "#e74c3c"; }
                return `<div class="insight-card">
                  <div class="label">Safety Inequality</div>
                  <div class="value" style="color:${ineqColor};font-size:13px;">${ineqLabel}</div>
                  <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Score range: ${scoreMin}–${scoreMax} · CV: ${cv.toFixed(1)}%</div>
                </div>`;
              })() : ""}
              ${densityHistogramHtml}
              ${gridChartHtml}
              ${tiersHtml}
              <div style="display:flex;gap:6px;margin-top:12px;">
                <button class="btn btn-ghost btn-block" style="flex:1;font-size:12px;" data-csv-dl="true">
                 <img width="24" height="24" src="https://img.icons8.com/material-outlined/24/FFFFFF/export-csv.png" alt="export-csv"/>
                 Download CSV
                 </button>

                <button class="btn btn-ghost btn-block" style="flex:1;font-size:12px;" data-geojson-dl="true">
                <img width="24" height="24" src="https://img.icons8.com/material-rounded/24/FFFFFF/json-download.png" alt="json-download"/>
                Download GeoJSON
                </button>
              </div>`;

            // Wire CSV download — universal for all services
            const csvBtn = gridTabContent.querySelector("[data-csv-dl]");
            if (csvBtn) csvBtn.onclick = () => downloadGridCSV(geojson, lastResultService);

            // Wire GeoJSON download with colored fill_color already injected
            const gjBtn = gridTabContent.querySelector("[data-geojson-dl]");
            if (gjBtn) gjBtn.onclick = () => downloadGeoJSON(geojson, `${lastResultService}_grid.geojson`);
          }

        } catch (err) {
          console.error("Grid fetch error:", err);
          if (gridTabContent) {
            gridTabContent.innerHTML = `<p class="text-danger">Failed to generate grid: ${err.message}</p>`;
          }
        }
      }
    });
  });

  // Wire the download button for the initially-active full tab
  _wireFullDownloadBtn();
  // Inject the PDF export button into the raw data tab
  _injectPdfBtn();
}

function _wireFullDownloadBtn() {
  const fullTab = analysisPanel.querySelector("#tab-full");
  if (!fullTab) return;
  const btn = fullTab.querySelector("[data-full-dl]");
  if (btn) btn.onclick = downloadFullAnalysisResult;
}

function _injectPdfBtn() {
  const rawTab = analysisPanel.querySelector("#tab-raw");
  if (!rawTab || rawTab.querySelector("[data-pdf-dl]")) return;
  const btn = document.createElement("button");
  btn.className = "btn btn-ghost btn-block";
  btn.setAttribute("data-pdf-dl", "true");
  btn.style.cssText = "margin-top:14px;font-size:12px;display:flex;align-items:center;justify-content:center;gap:6px;";
  btn.innerHTML = `<img width="20" height="20" src="https://img.icons8.com/pulsar-line/48/FFFFFF/export-pdf.png" alt="export-pdf" style="flex-shrink:0;"/> Download PDF Report`;
  btn.onclick = downloadAnalysisPDF;
  rawTab.appendChild(btn);
}


/* ============================================================
   4. AI CHATBOT (placeholder)
   ============================================================ */
function toggleChatbot() {
  document.getElementById("chatbot").classList.toggle("open");
}

function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const text  = input.value.trim();
  if (!text) return;

  const messages = document.getElementById("chatMessages");

  // Append user message
  const userMsg = document.createElement("div");
  userMsg.className = "chat-msg user";
  userMsg.textContent = text;
  messages.appendChild(userMsg);

  input.value = "";

  // TODO: connect to AI backend
  // Example:
  //   fetch("http://localhost:8000/api/chat", {
  //     method: "POST",
  //     headers: { "Content-Type": "application/json" },
  //     body: JSON.stringify({ message: text })
  //   })
  //     .then(r => r.json())
  //     .then(data => addBotMessage(data.reply));

  // Fake bot reply for now
  setTimeout(function () {
    const botMsg = document.createElement("div");
    botMsg.className = "chat-msg bot";
    botMsg.textContent = "🤖 (placeholder) I'll answer once the AI backend is connected.";
    messages.appendChild(botMsg);
    messages.scrollTop = messages.scrollHeight;
  }, 400);

  messages.scrollTop = messages.scrollHeight;
}

// Send chat with Enter key
const chatInputEl = document.getElementById("chatInput");
if (chatInputEl) {
  chatInputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") sendChatMessage();
  });
}


/* ============================================================
   5. LEAFLET MAP (placeholder)
   ------------------------------------------------------------
   The container <div id="map"> is already in dashboard.html.
   Uncomment the lines below once you're ready to use a real
   tile provider.
   ============================================================ */
   
let map;
let currentBasemap;

function initMap() {
  console.log("Initializing map...");
  map = L.map("map").setView([31.2136, 29.8753], 12);

  currentBasemap = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    { attribution: "© CARTO © OpenStreetMap" }
  ).addTo(map);

  document.getElementById("mapPlaceholder").style.display = "none";

  initMapHud();

  fetch("https://ipapi.co/json/")
    .then((res) => res.json())
    .then((data) => {
      if (data.latitude && data.longitude) {
        map.setView([data.latitude, data.longitude], 12);
      }
    })
    .catch(() => {}); // silently keep the default view on failure
}

window.addEventListener("load", initMap);

/* ============================================================
   MAP HUD — coordinates display + scale bar
   ============================================================ */

let _ndviGeoRaster = null;  // raw georaster object for pixel sampling

function enableNdviProbe(layer) {
  // georaster-layer-for-leaflet stores the parsed georaster on the layer object
  _ndviGeoRaster = layer.georaster || null;
  const probeEl = document.getElementById('ndvi-probe');
  if (probeEl) probeEl.style.display = '';
}

function disableNdviProbe() {
  _ndviGeoRaster = null;
  const probeEl = document.getElementById('ndvi-probe');
  if (probeEl) probeEl.style.display = 'none';
}

function sampleNdviAtLatLng(lat, lng) {
  const gr = _ndviGeoRaster;
  if (!gr || !gr.values) return null;

  const { xmin, xmax, ymin, ymax, width, height } = gr;
  // Bounds check
  if (lng < xmin || lng > xmax || lat < ymin || lat > ymax) return null;

  const col = Math.floor((lng - xmin) / (xmax - xmin) * width);
  const row = Math.floor((ymax - lat) / (ymax - ymin) * height);

  if (col < 0 || col >= width || row < 0 || row >= height) return null;

  const band = gr.values[0];
  if (!band || !band[row]) return null;
  const v = band[row][col];
  return (v === undefined || v === null || v <= -9999 || isNaN(v)) ? null : v;
}

function initMapHud() {
  // ── Coordinates ───────────────────────────────────────────
  const coordsEl = document.getElementById('mapCoords');
  const probeEl  = document.getElementById('ndvi-probe');

  map.on('mousemove', function(e) {
    const lat = e.latlng.lat.toFixed(5);
    const lng = e.latlng.lng.toFixed(5);
    coordsEl.textContent = lat + ', ' + lng;

    // NDVI pixel probe
    if (_ndviGeoRaster && probeEl && probeEl.style.display !== 'none') {
      const v = sampleNdviAtLatLng(e.latlng.lat, e.latlng.lng);
      probeEl.textContent = v !== null ? `NDVI: ${v.toFixed(4)}` : 'NDVI: —';
    }
  });

  map.on('mouseout', function() {
    coordsEl.textContent = '— , —';
    if (probeEl) probeEl.textContent = 'NDVI: —';
  });

  // ── Scale bar ─────────────────────────────────────────────
  // Target a bar ~80px wide; snap to a "nice" real-world distance.
  const lineEl  = document.getElementById('mapScaleLine');
  const labelEl = document.getElementById('mapScaleLabel');
  const TARGET_PX = 80;

  const NICE_DISTANCES = [
    1, 2, 5, 10, 20, 50, 100, 200, 500,
    1000, 2000, 5000, 10000, 20000, 50000,
    100000, 200000, 500000, 1000000
  ];

  function updateScale() {
    const center    = map.getCenter();
    const zoom      = map.getZoom();
    // metres per pixel at the current latitude and zoom level
    const mPerPx    = (156543.03392 * Math.cos(center.lat * Math.PI / 180)) / Math.pow(2, zoom);
    const targetM   = mPerPx * TARGET_PX;

    // pick the closest "nice" distance
    let best = NICE_DISTANCES[0];
    for (const d of NICE_DISTANCES) {
      if (Math.abs(d - targetM) < Math.abs(best - targetM)) best = d;
    }

    const barPx = best / mPerPx;
    lineEl.style.width  = barPx + 'px';
    labelEl.textContent = best >= 1000 ? (best / 1000) + ' km' : best + ' m';
  }

  map.on('zoomend moveend', updateScale);
  updateScale();
}

/* ============================================================
   MEASURE TOOL
   ============================================================ */
const measureState = {
  active: false,
  sessionPoints: [], // points in the CURRENT active session only — resets on each activation
  totalDistance: 0,  // accumulated metres across ALL past sessions — never reset except by Clear
  markers: [],       // [L.CircleMarker, ...]
  lines: [],         // [L.Polyline, ...]
  labels: [],        // [L.Marker with divIcon, ...]
  previewLine: null  // ghosted line following cursor
};

function haversineMeters(a, b) {
  const R = 6371000;
  const φ1 = a.lat * Math.PI / 180, φ2 = b.lat * Math.PI / 180;
  const Δφ = (b.lat - a.lat) * Math.PI / 180;
  const Δλ = (b.lng - a.lng) * Math.PI / 180;
  const s = Math.sin(Δφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

function formatDist(m) {
  return m >= 1000 ? (m / 1000).toFixed(2) + ' km' : Math.round(m) + ' m';
}

function measureMidpoint(a, b) {
  return L.latLng((a.lat + b.lat) / 2, (a.lng + b.lng) / 2);
}

function measureDistLabel(mid, text) {
  return L.marker(mid, {
    icon: L.divIcon({
      className: '',
      html: `<div class="measure-label">${text}</div>`,
      iconAnchor: [0, 0]
    }),
    interactive: false,
    zIndexOffset: 500
  }).addTo(map);
}

function measureDrawSegment(a, b) {
  const line = L.polyline([a, b], {
    color: '#4cc2ff',
    weight: 2,
    dashArray: '6 5',
    opacity: 0.7,
    interactive: false
  }).addTo(map);
  const dist = haversineMeters(a, b);
  const label = measureDistLabel(measureMidpoint(a, b), formatDist(dist));
  measureState.lines.push(line);
  measureState.labels.push(label);
  return dist;
}

// Transparent div that sits over the entire map during measure mode,
// capturing all pointer events so vector layers can't swallow clicks.
let _measureOverlay = null;

function measureGetOverlay() {
  if (_measureOverlay) return _measureOverlay;
  _measureOverlay = document.createElement('div');
  _measureOverlay.style.cssText = 'position:absolute;inset:0;z-index:650;cursor:crosshair;display:none;';
  map.getContainer().appendChild(_measureOverlay);
  return _measureOverlay;
}

// dblclick fires a click first; ignore that extra click.
let _measureIgnoreNextClick = false;

function measureOnOverlayClick(e) {
  if (_measureIgnoreNextClick) { _measureIgnoreNextClick = false; return; }
  const latlng = map.containerPointToLatLng(
    L.point(e.clientX - map.getContainer().getBoundingClientRect().left,
            e.clientY - map.getContainer().getBoundingClientRect().top)
  );
  const pts = measureState.sessionPoints;
  const marker = L.circleMarker(latlng, {
    radius: 5,
    color: '#4cc2ff',
    fillColor: '#ffffff',
    fillOpacity: 1,
    weight: 2,
    interactive: false
  }).addTo(map);
  measureState.markers.push(marker);
  if (pts.length > 0) {
    const segDist = measureDrawSegment(pts[pts.length - 1], latlng);
    measureState.totalDistance += segDist;
  }
  pts.push(latlng);
  measureUpdateTotal();
}

function measureOnOverlayDblClick(e) {
  _measureIgnoreNextClick = true;
  measureDeactivate();
}

function measureOnOverlayMouseMove(e) {
  if (measureState.sessionPoints.length === 0) return;
  const rect = map.getContainer().getBoundingClientRect();
  const latlng = map.containerPointToLatLng(L.point(e.clientX - rect.left, e.clientY - rect.top));
  const last = measureState.sessionPoints[measureState.sessionPoints.length - 1];
  if (measureState.previewLine) measureState.previewLine.setLatLngs([last, latlng]);
  else {
    measureState.previewLine = L.polyline([last, latlng], {
      color: '#4cc2ff',
      weight: 1.5,
      dashArray: '4 6',
      opacity: 0.45,
      interactive: false
    }).addTo(map);
  }
}

function measureClearAll() {
  measureState.markers.forEach(m => map.removeLayer(m));
  measureState.lines.forEach(l => map.removeLayer(l));
  measureState.labels.forEach(l => map.removeLayer(l));
  if (measureState.previewLine) map.removeLayer(measureState.previewLine);
  Object.assign(measureState, { sessionPoints: [], totalDistance: 0, markers: [], lines: [], labels: [], previewLine: null });
  const el = document.getElementById('measureTotal');
  el.style.display = 'none';
  el.innerHTML = '';
}

function measureUpdateTotal() {
  const el = document.getElementById('measureTotal');
  if (measureState.totalDistance === 0 && measureState.sessionPoints.length < 2) { el.style.display = 'none'; return; }
  el.innerHTML = 'Total: ' + formatDist(measureState.totalDistance);
  el.style.display = 'flex';
}

function measureDeactivate() {
  measureState.active = false;
  measureState.sessionPoints = []; // reset session; drawn visuals and totalDistance persist
  const btn = document.getElementById('measureBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/material/24/FFFFFF/ruler--v1.png" alt="ruler--v1"/>Measure';
  btn.classList.remove('btn-active');

  const overlay = measureGetOverlay();
  overlay.style.display = 'none';
  overlay.removeEventListener('click', measureOnOverlayClick);
  overlay.removeEventListener('dblclick', measureOnOverlayDblClick);
  overlay.removeEventListener('mousemove', measureOnOverlayMouseMove);

  if (measureState.previewLine) { map.removeLayer(measureState.previewLine); measureState.previewLine = null; }

  if (measureState.totalDistance > 0) {
    const el = document.getElementById('measureTotal');
    el.innerHTML = `Total: ${formatDist(measureState.totalDistance)} <button class="measure-clear-btn" onclick="measureClearAll()">Clear</button>`;
    el.style.display = 'flex';
  }
}

function toggleMeasure() {
  if (measureState.active) {
    measureDeactivate();
    return;
  }
  measureState.sessionPoints = []; // fresh session, no link to previous lines
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

/* =====================  ANNOTATE  ===================== */

const annotateState = {
  active: false,
  drawing: false,
  color: '#e74c3c',
  eraser: false,
  brushSize: 4,
  eraserSize: 18
};

let _annotateCanvas = null;
let _annotateCtx = null;
let _annotateOverlay = null;

function annotateGetCanvas() {
  if (_annotateCanvas) return _annotateCanvas;
  const container = map.getContainer();
  _annotateCanvas = document.createElement('canvas');
  _annotateCanvas.style.cssText = 'position:absolute;inset:0;z-index:640;pointer-events:none;';
  _annotateCanvas.width = container.offsetWidth;
  _annotateCanvas.height = container.offsetHeight;
  container.appendChild(_annotateCanvas);
  _annotateCtx = _annotateCanvas.getContext('2d');

  // keep canvas sized to map container
  new ResizeObserver(() => {
    const imgData = _annotateCtx.getImageData(0, 0, _annotateCanvas.width, _annotateCanvas.height);
    _annotateCanvas.width = container.offsetWidth;
    _annotateCanvas.height = container.offsetHeight;
    _annotateCtx.putImageData(imgData, 0, 0);
  }).observe(container);

  return _annotateCanvas;
}

function annotateGetOverlay() {
  if (_annotateOverlay) return _annotateOverlay;
  _annotateOverlay = document.createElement('div');
  _annotateOverlay.style.cssText = 'position:absolute;inset:0;z-index:645;cursor:crosshair;display:none;';
  map.getContainer().appendChild(_annotateOverlay);
  return _annotateOverlay;
}

function annotatePos(e) {
  const rect = map.getContainer().getBoundingClientRect();
  const src = e.touches ? e.touches[0] : e;
  return { x: src.clientX - rect.left, y: src.clientY - rect.top };
}

function annotateOnPointerDown(e) {
  annotateState.drawing = true;
  const ctx = _annotateCtx;
  const { x, y } = annotatePos(e);
  ctx.beginPath();
  ctx.moveTo(x, y);
  if (annotateState.eraser) {
    ctx.globalCompositeOperation = 'destination-out';
    ctx.lineWidth = annotateState.eraserSize;
  } else {
    ctx.globalCompositeOperation = 'source-over';
    ctx.strokeStyle = annotateState.color;
    ctx.lineWidth = annotateState.brushSize;
  }
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
}

function annotateOnPointerMove(e) {
  if (!annotateState.drawing) return;
  const { x, y } = annotatePos(e);
  _annotateCtx.lineTo(x, y);
  _annotateCtx.stroke();
}

function annotateOnPointerUp() {
  if (!annotateState.drawing) return;
  annotateState.drawing = false;
  _annotateCtx.closePath();
}

function annotateClearAll() {
  if (_annotateCtx && _annotateCanvas) {
    _annotateCtx.clearRect(0, 0, _annotateCanvas.width, _annotateCanvas.height);
  }
}

function annotateSelectTool(type, color, btnEl) {
  // deselect all color buttons and eraser
  document.querySelectorAll('.annotate-color-btn').forEach(b => b.classList.remove('selected'));
  document.getElementById('annotateEraserBtn').classList.remove('selected');

  if (type === 'eraser') {
    annotateState.eraser = true;
    btnEl.classList.add('selected');
  } else {
    annotateState.eraser = false;
    annotateState.color = color;
    btnEl.classList.add('selected');
  }
}

function annotateDeactivate() {
  annotateState.active = false;
  annotateState.drawing = false;

  const btn = document.getElementById('annotateBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/windows/32/FFFFFF/sign-up.png" alt="sign-up"/>Annotate';
  btn.classList.remove('btn-active');

  document.getElementById('annotateToolbar').classList.remove('visible');

  map.dragging.enable();
  map.doubleClickZoom.enable();

  const overlay = annotateGetOverlay();
  overlay.style.display = 'none';
  overlay.removeEventListener('mousedown', annotateOnPointerDown);
  overlay.removeEventListener('mousemove', annotateOnPointerMove);
  overlay.removeEventListener('mouseup', annotateOnPointerUp);
  overlay.removeEventListener('mouseleave', annotateOnPointerUp);

  if (_annotateCanvas) _annotateCanvas.style.pointerEvents = 'none';
}

function toggleAnnotate() {
  if (annotateState.active) {
    annotateDeactivate();
    return;
  }

  annotateState.active = true;
  annotateGetCanvas(); // ensure canvas exists

  const btn = document.getElementById('annotateBtn');
  btn.innerHTML = '<img width="20" height="20" src="https://img.icons8.com/windows/32/FFFFFF/sign-up.png" alt="sign-up"/>Cancel';
  btn.classList.add('btn-active');

  document.getElementById('annotateToolbar').classList.add('visible');

  map.dragging.disable();
  map.doubleClickZoom.disable();

  const overlay = annotateGetOverlay();
  overlay.style.display = 'block';
  overlay.addEventListener('mousedown', annotateOnPointerDown);
  overlay.addEventListener('mousemove', annotateOnPointerMove);
  overlay.addEventListener('mouseup', annotateOnPointerUp);
  overlay.addEventListener('mouseleave', annotateOnPointerUp);
}

/* changning basemap*/

function changeBasemap(new_basemap) { // value passed directly
  if (currentBasemap) {
    map.removeLayer(currentBasemap);
  }

  if (new_basemap === "dark") {
    currentBasemap = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      { attribution: "© CARTO © OpenStreetMap" }
    );
  } else if (new_basemap === "voyager") {
    currentBasemap = L.tileLayer(
      "https://tiledbasemaps.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { attribution: "© Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community, © OpenStreetMap contributors © CARTO" }
    );
  } else {
    currentBasemap = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager_labels_under/{z}/{x}/{y}{r}.png",
      { attribution: "© CARTO © OpenStreetMap" }
    );
  }

  currentBasemap.addTo(map);

  currentBasemap.setZIndex(0);

  // Close the dropdown after selection
  document.getElementById("basemapMenu").classList.remove("open");
}


function toggleBasemapMenu() {
  document.getElementById("basemapMenu").classList.toggle("open");
}

// Close when clicking outside (same as user menu)
document.addEventListener("click", function(e) {
  const menu = document.getElementById("basemapMenu");
  if (menu && !menu.contains(e.target)) {
    menu.classList.remove("open");
  }
});

// Renders a GeoRaster (e.g. from a GeoTIFF) onto the map using georaster-layer-for-leaflet
async function renderGeoRasterFromArrayBuffer(arrayBuffer, options = {}) {
  if (inputLayer) {
    console.log("Removing previous layer from map...");
    map.removeLayer(inputLayer);
  }

  clearMap()
  let georaster;
  try {
    georaster = await parseGeoraster(arrayBuffer);
  } catch (parseError) {
    console.error("Failed to parse GeoRaster:", parseError);
    throw new Error("Could not parse the GeoTIFF file. Make sure it's a valid GeoTIFF.");
  }

  console.log("GeoRaster loaded:", georaster);
  console.log("CRS:", georaster.crs);
  console.log("Projection:", georaster.projection);

  // Add common CRS definitions if not present
  if (typeof proj4 !== "undefined") {
    // WGS84 (EPSG:4326)
    proj4.defs("EPSG:4326", "+proj=longlat +datum=WGS84 +no_defs");
    // Web Mercator (EPSG:3857)
    proj4.defs("EPSG:3857", "+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +nadgrids=@null +wktext +no_defs");
    // UTM zones commonly used in Egypt
    proj4.defs("EPSG:32636", "+proj=utm +zone=36 +datum=WGS84 +units=m +no_defs");
    proj4.defs("EPSG:32637", "+proj=utm +zone=37 +datum=WGS84 +units=m +no_defs");
    proj4.defs("EPSG:32638", "+proj=utm +zone=38 +datum=WGS84 +units=m +no_defs");

    // 32767 = "user-defined" in the GeoTIFF spec — georaster can't reproject it.
    // If the pixel coordinates are already in lat/lng, alias it to WGS84
    // so the library skips reprojection and places pixels directly on the map.
    const { xmin, xmax, ymin, ymax } = georaster;
    const pixelsAreLatLng = xmin >= -180 && xmax <= 180 && ymin >= -90 && ymax <= 90;
    if (pixelsAreLatLng) {
      console.log("Pixel extents suggest lat/lng coordinates. Aliasing projection 32767 to EPSG:4326.");
      proj4.defs("32767", "+proj=longlat +datum=WGS84 +no_defs");
      console.warn("Projection 32767 detected — coordinates are lat/lng, aliased to WGS84.");
    }
  }

  // Check if georaster has bounds and CRS
  const hasBounds = georaster.bounds && georaster.bounds.length === 4;
  const hasCrs = georaster.crs || georaster.projection;
  
  console.log("Has bounds:", hasBounds, "Has CRS:", hasCrs);

  let layerOptions = {
    georaster: georaster,
    opacity: options.opacity || 0.9,
    resolution: options.resolution || 256,
  };

  // Only add color function if we have CRS (to avoid projection issues)
  if (hasCrs && options.colorFn) {
    layerOptions.pixelValuesToColorFn = options.colorFn;
  }

  // 32767 = unknown projection — georaster-layer-for-leaflet crashes hard on it.
  // If the pixel extents are valid lat/lng, override the georaster's projection
  // field directly so the library treats it as already-projected WGS84.
  if (georaster.projection === 32767) {
    const { xmin, xmax, ymin, ymax } = georaster;
    if (xmin >= -180 && xmax <= 180 && ymin >= -90 && ymax <= 90) {
      georaster.projection = 4326;
      console.warn("Overrode projection 32767 → 4326 (pixel extents confirm lat/lng).");
    }
  }

  try {
    const layer = new GeoRasterLayer(layerOptions);

    layer.addTo(map);
    
    // Fit bounds with padding
    try {
      const bounds = layer.getBounds();
      if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    } catch (boundsError) {
      console.warn("Could not fit bounds:", boundsError);
    }

    return layer;
  } catch (layerError) {
    console.error("GeoRasterLayer error:", layerError);
    throw new Error("Could not render the raster on the map. The file may have coordinate system issues.");
  }
}

let inputLayer  = null;  // pre-analysis layer — shown when Raw Data tab is active
let resultLayer = null;  // analysis result layer — shown when Full Area tab is active
let gridLayer   = null;  // 200 m cell QoL layer — shown when Grid/Cell tab is active

// Holds the last analysis result so the grid endpoint can re-use it
let lastResultBlob    = null;  // ArrayBuffer (rasters) or object (geojson)
let lastResultService = null;  // e.g. "ndvi", "heat-index", "crime", "urban-density"

// Holds per-feature urban density data so the grid tab can build a histogram
let lastUrbanDensityFeatures = null;  // array of {name, density} from the full-area result

/* ---------- QoL score → colour (4-tier: green / yellow-green / orange / red) ---------- */
function _qolRGB(score) {
  // Returns [r, g, b] — shared by map fill and text helpers
  // Tier boundaries match scoring functions: 75–100 green, 50–74 yellow-green, 25–49 orange, 0–24 red
  if (score === null || score === undefined) return [150, 150, 150];
  const s = Math.max(0, Math.min(100, score));
  let r, g, b;
  if (s >= 75) {
    // Excellent: deep green → bright green  (100 → 75)
    const t = (s - 75) / 25;          // 1 at 100, 0 at 75
    r = Math.round((1 - t) * 80  + t * 30);
    g = Math.round((1 - t) * 200 + t * 160);
    b = Math.round((1 - t) * 60  + t * 40);
  } else if (s >= 50) {
    // Good: yellow-green → lime  (74 → 50)
    const t = (s - 50) / 25;
    r = Math.round((1 - t) * 230 + t * 100);
    g = Math.round((1 - t) * 210 + t * 200);
    b = 0;
  } else if (s >= 25) {
    // Poor: orange → amber  (49 → 25)
    const t = (s - 25) / 25;
    r = Math.round((1 - t) * 220 + t * 240);
    g = Math.round((1 - t) * 100 + t * 170);
    b = 0;
  } else {
    // Bad: dark red → red  (24 → 0)
    const t = s / 25;
    r = Math.round((1 - t) * 160 + t * 220);
    g = Math.round((1 - t) * 20  + t * 60);
    b = 0;
  }
  return [r, g, b];
}
// Semi-transparent fill for map cells
function qolScoreColor(score) {
  if (score === null || score === undefined) return "rgba(150,150,150,0.25)";
  const [r, g, b] = _qolRGB(score);
  return `rgba(${r},${g},${b},0.72)`;
}
// Solid colour for sidebar text
function qolScoreTextColor(score) {
  if (score === null || score === undefined) return "#888";
  const [r, g, b] = _qolRGB(score);
  return `rgb(${r},${g},${b})`;
}

/* ============================================================
   SHARED INSIGHT HELPERS
   ============================================================ */

function perfCategory(score) {
  if (score >= 75) return { label: "Excellent", color: "var(--success)" };
  if (score >= 50) return { label: "Good",      color: "#8bc34a" };
  if (score >= 25) return { label: "Fair",       color: "var(--warning)" };
  return               { label: "Poor",      color: "var(--danger)" };
}

function inequalityLabel(stdDev) {
  if (stdDev < 10)  return { text: "Evenly distributed",  color: "var(--success)" };
  if (stdDev < 25)  return { text: "Moderate variation",  color: "var(--warning)" };
  return                   { text: "Highly uneven",        color: "var(--danger)"  };
}

function miniBarChart(values, bins, colors, labels) {
  const max = Math.max(...values, 1);
  return `<div style="margin:10px 0 4px;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted);">Distribution</div>
    <div style="display:flex;align-items:flex-end;gap:3px;height:40px;margin-bottom:4px;">
      ${values.map((v, i) => {
        const h = Math.max(3, Math.round((v / max) * 38));
        return `<div title="${labels[i]}: ${v}%" style="flex:1;height:${h}px;background:${colors[i]};border-radius:2px 2px 0 0;"></div>`;
      }).join("")}
    </div>
    <div style="display:flex;gap:3px;">
      ${labels.map((l, i) => `<div style="flex:1;font-size:9px;color:var(--text-muted);text-align:center;overflow:hidden;white-space:nowrap;">${l}</div>`).join("")}
    </div>`;
}

function calcStdDev(arr) {
  if (!arr.length) return 0;
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  return Math.sqrt(arr.reduce((s, v) => s + (v - mean) ** 2, 0) / arr.length);
}

function boundingExtentHtml(features) {
  let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity;
  features.forEach(f => {
    const coords = f.geometry?.coordinates;
    if (!coords) return;
    const flat = f.geometry.type === "Point" ? [coords]
      : f.geometry.type === "LineString" ? coords
      : f.geometry.type === "Polygon" ? coords[0]
      : f.geometry.type === "MultiPolygon" ? coords.flat(2)
      : [];
    flat.forEach(([lng, lat]) => {
      if (lng < minLng) minLng = lng; if (lng > maxLng) maxLng = lng;
      if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
    });
  });
  if (!isFinite(minLng)) return "";
  const dLng = (maxLng - minLng).toFixed(4), dLat = (maxLat - minLat).toFixed(4);
  return `<div class="insight-card">
    <div class="label">Bounding Extent</div>
    <div class="value" style="font-size:12px;">${parseFloat(minLat).toFixed(4)}°N – ${parseFloat(maxLat).toFixed(4)}°N<br>${parseFloat(minLng).toFixed(4)}°E – ${parseFloat(maxLng).toFixed(4)}°E</div>
    <div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${dLng}° wide × ${dLat}° tall</div>
  </div>`;
}

function coverageAreaHtml(features) {
  let total = 0;
  features.forEach(f => {
    const a = f.properties?.area_km2 || f.properties?.aoi_area_km2;
    if (a) total += parseFloat(a);
  });
  if (!total) return "";
  return `<div class="insight-card">
    <div class="label">Data Coverage Area</div>
    <div class="value">${total.toFixed(2)} km²</div>
  </div>`;
}

function clusteringLabel(scores) {
  if (scores.length < 4) return null;
  const sorted = [...scores].sort((a, b) => a - b);
  const n = sorted.length;
  const topQuartile   = sorted.slice(Math.floor(n * 0.75));
  const botQuartile   = sorted.slice(0, Math.floor(n * 0.25));
  const topMean = topQuartile.reduce((a, b) => a + b, 0) / topQuartile.length;
  const botMean = botQuartile.reduce((a, b) => a + b, 0) / botQuartile.length;
  const spread = topMean - botMean;
  if (spread > 50) return { text: "High/low zones are clustered apart", color: "var(--warning)" };
  if (spread > 25) return { text: "Moderate spatial grouping", color: "#8bc34a" };
  return { text: "Well-mixed — scores spread evenly", color: "var(--success)" };
}

/* ---------- Convert rgba/rgb CSS string → "#rrggbb" hex ---------- */
function cssColorToHex(css) {
  const m = css.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (!m) return css; // already hex or unknown — pass through
  const r = parseInt(m[1]).toString(16).padStart(2, "0");
  const g = parseInt(m[2]).toString(16).padStart(2, "0");
  const b = parseInt(m[3]).toString(16).padStart(2, "0");
  return `#${r}${g}${b}`;
}

/* ---------- Derive hex fill colour for a grid feature ---------- */
function featureFillHex(feature, service) {
  const p = feature.properties;
  const isVeg     = service === "vegetation";
  const isTraffic = service === "traffic";
  const isISPA    = service === "informal-settlement";
  let rgba;
  if (isVeg)     rgba = vegPctColor(p.value ?? 0);
  else if (isTraffic) rgba = congestionColor(p.congestion || "low");
  else if (isISPA)    rgba = irregularityColor(p.value ?? 0);
  else                rgba = qolScoreColor(p.qol_score ?? 0);
  return cssColorToHex(rgba);
}

function downloadGeoJSON(geojson, filename) {
  const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function _fullAnalysisFillHex(feature, service) {
  const p = feature.properties;
  switch (service) {
    case "crime": {
      const d = p.crime_density || 0;
      if (d > 20) return "#891508";
      if (d > 15) return "#e74c3c";
      if (d > 10) return "#e67e22";
      if (d > 5)  return "#f1c40f";
      return "#2ecc71";
    }
    case "urban-density": {
      const d = p.urban_density || 0;
      if (d > 2000) return "#000080";
      if (d > 1000) return "#4169e1";
      if (d > 500)  return "#4682b4";
      if (d > 100)  return "#87ceeb";
      return "#add8e6";
    }
    case "public-transport": {
      const layer = p.layer;
      if (layer === "boundary" || layer === "station") return null;
      return p.type === "covered" ? "#4cc2ff" : "#e74c3c";
    }
    case "facility-accessibility": {
      const t = p.time_min;
      if (t === 5)  return "#198754";
      if (t === 10) return "#ffc107";
      return "#dc3545";
    }
    case "vegetation":
      return cssColorToHex(vegPctColor(p.vegetation_pct ?? 0));
    case "traffic":
      return p.type === "hotspot" ? null : cssColorToHex(congestionColor(p.congestion || "low"));
    case "informal-settlement":
      return p.type === "high_irregularity_zone" ? null : cssColorToHex(irregularityColor(p.irregularity_score));
    default:
      return "#888888";
  }
}

function _fullAnalysisFillOpacity(feature, service) {
  const p = feature.properties;
  if (service === "public-transport") {
    if (p.layer === "boundary" || p.layer === "station") return 0;
    return p.type === "covered" ? 0.45 : 0.25;
  }
  if (service === "facility-accessibility") {
    const t = p.time_min;
    if (t === 5) return 0.40; if (t === 10) return 0.32; return 0.24;
  }
  if (service === "traffic" && p.type === "hotspot") return 0;
  if (service === "informal-settlement" && p.type === "high_irregularity_zone") return 0;
  return 0.6;
}

function downloadFullAnalysisResult() {
  if (!lastResultBlob || !lastResultService) {
    alert("No analysis result available.");
    return;
  }
  const rasterServices = ["ndvi", "heat-index", "air-quality"];
  const isRaster = rasterServices.includes(lastResultService);
  if (isRaster) {
    const blob = new Blob([lastResultBlob], { type: "image/tiff" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = `${lastResultService}_result.tif`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } else {
    // Deep-copy the GeoJSON and inject simplestyle fill properties
    const geojson = JSON.parse(JSON.stringify(lastResultBlob));
    geojson.features.forEach(f => {
      const fill = _fullAnalysisFillHex(f, lastResultService);
      const fillOpacity = _fullAnalysisFillOpacity(f, lastResultService);
      const p = f.properties;
      p["fill"]          = fill || "transparent";
      p["fill-opacity"]  = fillOpacity;
      p["stroke"]        = fill || "#333333";
      p["stroke-width"]  = 1;
      p["stroke-opacity"] = fill ? 0.6 : 0;
    });
    downloadGeoJSON(geojson, `${lastResultService}_result.geojson`);
  }
}

/* ---------- Fetch grid from backend and render on map ---------- */
async function fetchAndRenderGrid(service, blob) {
  if (gridLayer) { map.removeLayer(gridLayer); gridLayer = null; }

  let geojson;

  if (service === "traffic") {
    // Traffic: the full analysis response already contains the correctly clipped,
    // correctly scored grid cells. Re-sending to the backend would re-score from
    // scratch and can produce different results. Filter out hotspot features and
    // use the blob directly so the grid tab is identical to the full area tab.
    geojson = {
      type:        "FeatureCollection",
      features:    blob.features.filter(f => f.properties.service === "traffic"),
      cell_size_m: blob.cell_size_m,
    };
  } else {
    // All other services: send to the appropriate grid endpoint
    const formData = new FormData();
    let endpoint;

    if (service === "ndvi" || service === "heat-index" || service === "air-quality") {
      const file = new File([blob], "result.tif", { type: "image/tiff" });
      formData.append("geotiff", file);
      // endpoint = service === "ndvi"
      //   ? "http://localhost:8000/calculate-grid/ndvi"
      //   : service === "heat-index"
      //     ? "http://localhost:8000/calculate-grid/heat-index"
      //     : "http://localhost:8000/calculate-grid/air-quality";
      
      endpoint = service === "ndvi"
  ? `${API_BASE_URL}/calculate-grid/ndvi`
  : service === "heat-index"
    ? `${API_BASE_URL}/calculate-grid/heat-index`
    : `${API_BASE_URL}/calculate-grid/air-quality`;

    } else {
      const file = new File(
        [JSON.stringify(blob)],
        "result.geojson",
        { type: "application/json" }
      );
    //   formData.append("geojson", file);
    //   endpoint = service === "crime"
    //     ? "http://localhost:8000/calculate-grid/crime"
    //     : service === "urban-density"
    //       ? "http://localhost:8000/calculate-grid/urban-density"
    //       : service === "public-transport"
    //         ? "http://localhost:8000/calculate-grid/public-transport"
    //         : service === "vegetation"
    //           ? "http://localhost:8000/calculate-grid/vegetation"
    //           : service === "informal-settlement"
    //             ? "http://localhost:8000/calculate-grid/informal-settlement"
    //             : "http://localhost:8000/calculate-grid/facility-accessibility";
    
    // }
    formData.append("geojson", file);

endpoint = service === "crime"
  ? `${API_BASE_URL}/calculate-grid/crime`
  : service === "urban-density"
    ? `${API_BASE_URL}/calculate-grid/urban-density`
    : service === "public-transport"
      ? `${API_BASE_URL}/calculate-grid/public-transport`
      : service === "vegetation"
        ? `${API_BASE_URL}/calculate-grid/vegetation`
        : service === "informal-settlement"
          ? `${API_BASE_URL}/calculate-grid/informal-settlement`
          : `${API_BASE_URL}/calculate-grid/facility-accessibility`;



    formData.append("geojson", file);

endpoint = service === "crime"
  ? `${API_BASE_URL}/calculate-grid/crime`
  : service === "urban-density"
    ? `${API_BASE_URL}/calculate-grid/urban-density`
    : service === "public-transport"
      ? `${API_BASE_URL}/calculate-grid/public-transport`
      : service === "vegetation"
        ? `${API_BASE_URL}/calculate-grid/vegetation`
        : service === "informal-settlement"
          ? `${API_BASE_URL}/calculate-grid/informal-settlement`
          : `${API_BASE_URL}/calculate-grid/facility-accessibility`;

    const response = await fetch(endpoint, { method: "POST", body: formData });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Grid request failed: ${response.status}`);
    }
    geojson = await response.json();
  }

  const isVeg   = service === "vegetation";
  const isTraffic = service === "traffic";
  const isISPA  = service === "informal-settlement";

  gridLayer = L.geoJSON(geojson, {
    style: function(feature) {
      const p     = feature.properties;
      const score = p.qol_score;
      let fillColor;
      if (isVeg) {
        fillColor = vegPctColor(p.value ?? 0);
      } else if (isTraffic) {
        fillColor = congestionColor(p.congestion || "low");
      } else if (isISPA) {
        fillColor = irregularityColor(p.value ?? 0);
      } else {
        fillColor = qolScoreColor(score);
      }
      return {
        fillColor,
        fillOpacity: 0.75,
        color:       "rgba(0,0,0,0.15)",
        weight:      0.5,
      };
    },
    onEachFeature: function(feature, layer) {
      const p = feature.properties;
      if (isVeg) {
        const pct  = p.value !== null ? p.value.toFixed(1) + "%" : "—";
        const tag  = p.passes_30pct ? "✓ Passes 30%" : "✗ Below 30%";
        layer.bindPopup(
          `<strong>Vegetation:</strong> ${pct}<br>` +
          `<strong>QoL Score:</strong> ${p.qol_score ?? "—"}/100<br>` +
          `<span style="font-size:11px">${tag}</span>`
        );
      } else if (isTraffic) {
        const pressure = p.local_pressure != null
          ? `<br><strong>Traffic Pressure:</strong> ${p.local_pressure.toFixed(0)} pop/km`
          : "";
        layer.bindPopup(
          `<strong>Congestion:</strong> ${p.congestion}<br>` +
          `<strong>Road Density:</strong> ${(p.value ?? 0).toFixed(2)} km/km²` +
          `<br><strong>QoL Score:</strong> ${p.qol_score ?? "—"}/100` +
          pressure
        );
      } else if (isISPA) {
        const cls = p.classification || "—";
        layer.bindPopup(
          `<strong>Irregularity Score:</strong> ${p.value ?? "—"}/100<br>` +
          `<strong>Classification:</strong> ${cls}<br>` +
          `<strong>QoL Score:</strong> ${p.qol_score ?? "—"}/100`
        );
      } else if (service === "urban-density") {
        const density   = p.value !== null && p.value !== undefined ? Math.round(p.value) : "—";
        const scoreText = p.qol_score !== null ? `${p.qol_score}/100` : "No data";
        layer.bindPopup(
          `<strong>Density:</strong> ${density} pop/km²<br>` +
          `<strong>Score:</strong> ${scoreText}<br>` +
          `<span style="font-size:11px;color:#aaa;">Score is based on proximity to the healthy recommended density of 5,000 pop/km²</span>`
        );
      } else {
        const scoreText = p.qol_score !== null ? `${p.qol_score}/100` : "No data";
        const valText   = p.value     !== null ? p.value : "—";
        layer.bindPopup(
          `<strong>QoL Score:</strong> ${scoreText}<br>` +
          `<strong>Value:</strong> ${valText}`
        );
      }
    },
  });

  // Inject Simplestyle-spec properties so any GeoJSON viewer renders the same colors as the map
  geojson.features.forEach(f => {
    const p = f.properties;
    p["fill"]           = featureFillHex(f, service);
    p["fill-opacity"]   = 0.75;
    p["stroke"]         = "#000000";
    p["stroke-width"]   = 0.5;
    p["stroke-opacity"] = 0.15;
  });

  return geojson;
}

/* ---------- Attach file input listeners after DOM is updated ---------- */
function attachFileInputListeners() {
  // GeoTIFF file input handler
  const tiffInput = document.getElementById("tiffInput");
  if (tiffInput) {
    tiffInput.addEventListener("change", async function (e) {
      const file = e.target.files[0];
      if (!file) return;

      const arrayBuffer = await file.arrayBuffer();

      inputLayer = await renderGeoRasterFromArrayBuffer(arrayBuffer);
    })
  }

  // GeoJSON file input handler
  const fileInput = document.getElementById("geoJsonInput");
  if (fileInput) {
    fileInput.addEventListener("change", function (e) {
      const file = e.target.files[0];

      if (!file) return;

      const reader = new FileReader();

      reader.onload = function (event) {
        const geojsonData = JSON.parse(event.target.result);

        console.log("Uploaded GeoJSON:", geojsonData);

        // Auto-detect population field for urban density service
        const popFieldInput = document.getElementById("populationField");
        if (popFieldInput && !popFieldInput.value) {
          const firstFeature = geojsonData.features && geojsonData.features[0];
          if (firstFeature && firstFeature.properties) {
            const popKey = Object.keys(firstFeature.properties)
              .find(k => k.toLowerCase().includes("pop"));
            if (popKey) {
              popFieldInput.value = popKey;
              const hint = document.getElementById("populationFieldHint");
              if (hint) hint.style.display = "inline";
              popFieldInput.addEventListener("input", function onEdit() {
                if (hint) hint.style.display = "none";
                popFieldInput.removeEventListener("input", onEdit);
              });
            }
          }
        }

        // ADD TO MAP (track as inputLayer so tab switching can restore it)
        if (inputLayer) map.removeLayer(inputLayer);
        inputLayer = L.geoJSON(geojsonData).addTo(map);

        // FIT BOUNDS
        try {
          const bounds = inputLayer.getBounds();
          if (bounds && bounds.isValid()) {
            map.fitBounds(bounds, { padding: [50, 50] });
          }
        } catch (boundsError) {
          console.warn("Could not fit bounds:", boundsError);
        }
      }

        reader.readAsText(file);
    });
  }

  // Transit stations file input — previews points on map
  const stationsInput = document.getElementById("stationsInput");
  if (stationsInput) {
    stationsInput.addEventListener("change", function(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(event) {
        try {
          const geojsonData = JSON.parse(event.target.result);
          if (inputLayer) map.removeLayer(inputLayer);
          inputLayer = L.geoJSON(geojsonData, {
            pointToLayer: function(feature, latlng) {
              return L.circleMarker(latlng, {
                radius: 5, fillColor: "#4cc2ff", color: "#1a8fc1",
                weight: 1.5, opacity: 1, fillOpacity: 0.9,
              });
            }
          }).addTo(map);
          try {
            const b = inputLayer.getBounds();
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch(e) {}
        } catch(err) { console.warn("Could not parse stations GeoJSON:", err); }
      };
      reader.readAsText(file);
    });
  }

  // AOI file input — previews boundary on map (layered on top of stations)
  const aoiInput = document.getElementById("aoiInput");
  if (aoiInput) {
    aoiInput.addEventListener("change", function(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(event) {
        try {
          const geojsonData = JSON.parse(event.target.result);
          // Add as a separate overlay — don't overwrite the stations inputLayer
          const aoiLayer = L.geoJSON(geojsonData, {
            style: { color: "#f39c12", weight: 2.5, fill: false },
          }).addTo(map);
          try {
            const b = aoiLayer.getBounds();
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch(e) {}
        } catch(err) { console.warn("Could not parse AOI GeoJSON:", err); }
      };
      reader.readAsText(file);
    });
  }

  // Facilities file input — previews facility points on map
  const facilitiesGeojsonInput = document.getElementById("facilitiesGeojsonInput");
  if (facilitiesGeojsonInput) {
    facilitiesGeojsonInput.addEventListener("change", function(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(event) {
        try {
          const geojsonData = JSON.parse(event.target.result);
          if (inputLayer) map.removeLayer(inputLayer);
          inputLayer = L.geoJSON(geojsonData, {
            pointToLayer: function(feature, latlng) {
              return L.circleMarker(latlng, {
                radius: 6, fillColor: "#198754", color: "#145a32",
                weight: 1.5, opacity: 1, fillOpacity: 0.9,
              });
            },
            onEachFeature: function(feature, layer) {
              const p = feature.properties || {};
              const nameKey = Object.keys(p).find(k => /^name$/i.test(k) || /^title$/i.test(k));
              layer.bindPopup(`<strong>${nameKey ? p[nameKey] : "Facility"}</strong>`);
            }
          }).addTo(map);
          try {
            const b = inputLayer.getBounds();
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch(e) {}
        } catch(err) { console.warn("Could not parse facilities GeoJSON:", err); }
      };
      reader.readAsText(file);
    });
  }

  // Roads file input — previews road lines on map
  const roadsInput = document.getElementById("roadsInput");
  if (roadsInput) {
    roadsInput.addEventListener("change", function(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function(event) {
        try {
          const geojsonData = JSON.parse(event.target.result);
          if (inputLayer) map.removeLayer(inputLayer);
          inputLayer = L.geoJSON(geojsonData, {
            style: { color: "#e67e22", weight: 2, opacity: 0.8 },
          }).addTo(map);
          try {
            const b = inputLayer.getBounds();
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch(e) {}
        } catch(err) { console.warn("Could not parse roads GeoJSON:", err); }
      };
      reader.readAsText(file);
    });
  }

  // CSV file input handler
  const csvInput = document.getElementById("csvInput");
  if (csvInput) {
    csvInput.addEventListener("change", function (e) {
      const file = e.target.files[0];
      if (!file) return;

      const reader = new FileReader();

      reader.onload = function (event) {
        const csvText = event.target.result;
        console.log("Uploaded CSV:", csvText.substring(0, 500) + "...");

        // Parse CSV to get column names
        const lines = csvText.trim().split('\n');
        if (lines.length < 1) {
          alert("CSV file is empty");
          return;
        }

        // Parse header row to get column names
        const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
        console.log("CSV Headers:", headers);

        const colsLower = {};
        headers.forEach(h => { colsLower[h.toLowerCase()] = h; });

        function detectCoordField(candidates, prefixes) {
          for (const name of candidates) {
            if (colsLower[name]) return colsLower[name];
          }
          for (const [lower, orig] of Object.entries(colsLower)) {
            for (const prefix of prefixes) {
              if (lower.startsWith(prefix)) return orig;
            }
          }
          return null;
        }

        // Check if the user already typed values in the input fields
        const latInputEl = document.getElementById("latField");
        const lonInputEl = document.getElementById("lonField");
        const userLat = latInputEl ? latInputEl.value.trim() : "";
        const userLon = lonInputEl ? lonInputEl.value.trim() : "";

        let latHeader = userLat
          ? headers.find(h => h.toLowerCase() === userLat.toLowerCase())
          : detectCoordField(["latitude", "lat", "y"], ["lat"]);

        let lonHeader = userLon
          ? headers.find(h => h.toLowerCase() === userLon.toLowerCase())
          : detectCoordField(["longitude", "lon", "long", "x"], ["lon", "long"]);

        // Auto-populate the text fields and show hints
        if (latInputEl && latHeader && !userLat) {
          latInputEl.value = latHeader;
          const hint = document.getElementById("latFieldHint");
          if (hint) hint.style.display = "inline";
          latInputEl.addEventListener("input", function onEdit() {
            if (hint) hint.style.display = "none";
            latInputEl.removeEventListener("input", onEdit);
          });
        }
        if (lonInputEl && lonHeader && !userLon) {
          lonInputEl.value = lonHeader;
          const hint = document.getElementById("lonFieldHint");
          if (hint) hint.style.display = "inline";
          lonInputEl.addEventListener("input", function onEdit() {
            if (hint) hint.style.display = "none";
            lonInputEl.removeEventListener("input", onEdit);
          });
        }

        // Detect a crime type column for breakdown (runs regardless of coord detection)
        const _typeRoots = ["offense","crime","incident","violation","charge","category","classification","nature","description","ucr","primary_type","event_type","call_type","report_type"];
        const typeCol = headers.find(h => _typeRoots.some(root => h.toLowerCase().replace(/\s+/g, "_").includes(root)));
        const typeIndex = typeCol != null ? headers.indexOf(typeCol) : -1;
        window._crimeTypeCounts = {};

        if (!lonHeader || !latHeader) {
          console.warn("Could not detect lat/lon columns from CSV headers:", headers);
          // Still count types from all rows even without coordinates
          if (typeIndex >= 0) {
            for (let i = 1; i < lines.length; i++) {
              const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
              if (values[typeIndex]) {
                const t = values[typeIndex];
                window._crimeTypeCounts[t] = (window._crimeTypeCounts[t] || 0) + 1;
              }
            }
          }
          return;
        }

        const lonIndex = headers.indexOf(lonHeader);
        const latIndex = headers.indexOf(latHeader);

        console.log(`Using columns: ${lonHeader} (index ${lonIndex}) and ${latHeader} (index ${latIndex})`);

        // Parse data rows and create GeoJSON points
        const features = [];
        for (let i = 1; i < lines.length; i++) {
          const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
          if (values.length > Math.max(lonIndex, latIndex)) {
            const lon = parseFloat(values[lonIndex]);
            const lat = parseFloat(values[latIndex]);
            if (!isNaN(lon) && !isNaN(lat)) {
              const crimeLabel = typeIndex >= 0 && values[typeIndex] ? values[typeIndex] : null;
              features.push({
                type: "Feature",
                geometry: { type: "Point", coordinates: [lon, lat] },
                properties: { row: i, crime: crimeLabel }
              });
              if (crimeLabel) {
                window._crimeTypeCounts[crimeLabel] = (window._crimeTypeCounts[crimeLabel] || 0) + 1;
              }
            }
          }
        }

        if (features.length === 0) {
          alert("No valid coordinate points found in the CSV.");
          return;
        }

        const geojsonData = {
          type: "FeatureCollection",
          features: features
        };

        console.log("Converted GeoJSON:", geojsonData);

        // ADD TO MAP
        let csvLayer = L.geoJSON(geojsonData, {
          pointToLayer: function (feature, latlng) {
            return L.circleMarker(latlng, {
              radius: 6,
              fillColor: "#ff7800",
              color: "#000",
              weight: 1,
              opacity: 1,
              fillOpacity: 0.8
            });
          },
          onEachFeature: function (feature, layer) {
            if (feature.properties.crime) {
              layer.bindPopup(`<strong>${feature.properties.crime}</strong>`, { maxWidth: 200 });
            }
          }
        }).addTo(map);

        // Store reference to remove later
        inputLayer = csvLayer;

        // FIT BOUNDS
        try {
          const bounds = csvLayer.getBounds();
          if (bounds && bounds.isValid()) {
            map.fitBounds(bounds, { padding: [50, 50] });
          }
        } catch (boundsError) {
          console.warn("Could not fit bounds:", boundsError);
        }

        console.log(`Added ${features.length} crime points from CSV to the map.`);
      };

      reader.readAsText(file);
    });
  }
}
// ============================================================


// 
// ============================================================
// mapExport.js
// Full map export — captures basemap + GeoTIFF raster layers
// + GeoJSON polygons + CSV-converted layers all in one image.
//
// Strategy:
//   1. Collect every canvas in the map container (tile layers,
//      georaster WebGL canvases, etc.)
//   2. Manually redraw all Leaflet SVG/Canvas vector layers
//      (GeoJSON polygons, polylines, points) on top
//   3. Flatten everything into one export canvas
//   4. Download in the chosen format (PNG / JPG / JPEG / TIFF)
//
// Dependencies (add to your HTML before this script):
//   <script src="https://unpkg.com/leaflet-image@0.4.0/leaflet-image.js"></script>
//
// Usage (HTML):
//   <div class="user-menu" id="exportMenu">
//     <button class="btn" id="export-btn" onclick="toggleExportMenu()">
//       💾 Export ▾
//     </button>
//     <div class="dropdown">
//       <a href="#" onclick="exportMap('png');  toggleExportMenu(); return false;">🖼️ PNG</a>
//       <a href="#" onclick="exportMap('jpg');  toggleExportMenu(); return false;">📷 JPG</a>
//       <a href="#" onclick="exportMap('jpeg'); toggleExportMenu(); return false;">📷 JPEG</a>
//       <a href="#" onclick="exportMap('tiff'); toggleExportMenu(); return false;">🗺️ TIFF</a>
//     </div>
//   </div>
// ============================================================


// ── STEP 1: Master export entry point ────────────────────────────────────────

/**
 * exportMap(format)
 * Main export function. Call from your Export dropdown buttons.
 *
 * @param {string} format — 'png' | 'jpg' | 'jpeg' | 'tiff'
 */
function exportMap(format) {

  // Guard: map must be initialized
  // 'map' is the global Leaflet map variable from your dashboard.js
  if (typeof map === 'undefined' || !map) {
    showToast('Map is not initialized yet.', 'warning');
    return;
  }

  format = format.toLowerCase();

  const supported = ['png', 'jpg', 'jpeg', 'tiff'];
  if (!supported.includes(format)) {
    showToast(`Unsupported format: ${format}`, 'warning');
    return;
  }

  // Disable export button and show loading state
  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.disabled     = true;
    exportBtn.innerHTML    = '⏳ Exporting...';
  }

  showToast(`Preparing ${format.toUpperCase()} export — please wait...`, 'info');

  // Give Leaflet a frame to finish rendering any pending redraws
  // before we start reading canvases
  setTimeout(() => {
    try {
      buildCompositeCanvas(function(compositeCanvas) {

        // Re-enable button
        if (exportBtn) {
          exportBtn.disabled  = false;
          exportBtn.innerHTML = '💾 Export ▾';
        }

        if (!compositeCanvas) {
          showToast('Export failed — could not read map canvas.', 'warning');
          return;
        }

        // Hand off to format-specific encoder
        encodeAndDownload(compositeCanvas, format);
      });

    } catch (err) {
      console.error('[exportMap] Unexpected error:', err);
      showToast('Export failed — see console.', 'warning');
      if (exportBtn) {
        exportBtn.disabled  = false;
        exportBtn.innerHTML = '💾 Export ▾';
      }
    }
  }, 250); // 250 ms is enough for georaster tiles to finish painting
}


// ── STEP 2: Build composite canvas ───────────────────────────────────────────

/**
 * getElementOffsetInContainer(el, containerRect)
 * Returns {x, y} of el's top-left corner relative to containerRect,
 * accounting for any CSS transform: translate() on the element itself.
 */
function getElementOffsetInContainer(el, containerRect) {
  const rect = el.getBoundingClientRect();
  let x = rect.left - containerRect.left;
  let y = rect.top  - containerRect.top;

  const transform = window.getComputedStyle(el).transform;
  if (transform && transform !== 'none') {
    const m = transform.match(/matrix\(([^)]+)\)/);
    if (m) {
      const parts = m[1].split(',');
      x += parseFloat(parts[4]) || 0;
      y += parseFloat(parts[5]) || 0;
    }
  }
  return { x, y };
}

/**
 * drawTilesOntoCanvas(mapContainer, containerRect, ctx, done)
 * Reloads every tile <img> in .leaflet-tile-pane with crossOrigin='anonymous'
 * and composites them onto ctx at the correct map-relative position.
 * Falls back gracefully for tiles that block CORS (e.g. Esri satellite).
 */
function drawTilesOntoCanvas(mapContainer, containerRect, ctx, done) {
  const tileImgs = Array.from(
    mapContainer.querySelectorAll('.leaflet-tile-pane img.leaflet-tile')
  ).filter(img => !img.classList.contains('leaflet-tile-loaded') === false || img.complete);

  if (tileImgs.length === 0) { done(false); return; }

  let pending  = tileImgs.length;
  let anyDrawn = false;

  tileImgs.forEach(function(srcImg) {
    // Compute where this tile sits inside the map container.
    // Tile positions come from inline style (left/top) on the <img>,
    // but the containing pane (.leaflet-map-pane) itself is also translated.
    const tileRect = srcImg.getBoundingClientRect();
    const dx = tileRect.left - containerRect.left;
    const dy = tileRect.top  - containerRect.top;
    const dw = tileRect.width  || 256;
    const dh = tileRect.height || 256;

    const img = new Image();
    img.crossOrigin = 'anonymous';

    img.onload = function() {
      try {
        ctx.drawImage(img, dx, dy, dw, dh);
        anyDrawn = true;
      } catch (e) {
        console.warn('[drawTiles] Could not draw tile:', e.message);
      }
      if (--pending === 0) done(anyDrawn);
    };
    img.onerror = function() {
      // CORS blocked or network error — try drawing the already-loaded img directly
      try {
        ctx.drawImage(srcImg, dx, dy, dw, dh);
        anyDrawn = true;
      } catch (e) {
        console.warn('[drawTiles] Tile CORS blocked, skipping:', srcImg.src.slice(0, 80));
      }
      if (--pending === 0) done(anyDrawn);
    };

    // Append a cache-bust only for Esri (which ignores crossOrigin anyway)
    img.src = srcImg.src;
  });
}

/**
 * buildCompositeCanvas(callback)
 * Collects ALL rendered layers from the Leaflet map container and
 * flattens them into a single HTMLCanvasElement matching the current
 * visible map extent exactly.
 *
 * Layer order (bottom → top):
 *   [1] Basemap tile <img> elements (.leaflet-tile-pane)
 *   [2] All <canvas> elements (georaster WebGL canvases, etc.)
 *   [3] SVG vector layers (GeoJSON polygons / polylines)
 *   [4] Marker icons
 *
 * @param {function} callback — called with the finished canvas (or null on error)
 */
function buildCompositeCanvas(callback) {

  const mapContainer = document.querySelector('.leaflet-container');
  if (!mapContainer) {
    console.error('[buildCompositeCanvas] .leaflet-container not found in DOM');
    callback(null);
    return;
  }

  // Use the map container's visible pixel size — this is the exact export extent.
  const mapWidth  = mapContainer.offsetWidth;
  const mapHeight = mapContainer.offsetHeight;

  const exportCanvas = document.createElement('canvas');
  exportCanvas.width  = mapWidth;
  exportCanvas.height = mapHeight;
  const ctx = exportCanvas.getContext('2d');

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, mapWidth, mapHeight);

  // Clip all drawing to the map container bounds so panned-out tiles don't bleed
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, mapWidth, mapHeight);
  ctx.clip();

  const containerRect = mapContainer.getBoundingClientRect();

  // ── Layer 1: Basemap tiles ──────────────────────────────────────────────
  drawTilesOntoCanvas(mapContainer, containerRect, ctx, function(tilesDrawn) {
    if (!tilesDrawn) {
      ctx.fillStyle = 'rgba(200,200,200,0.4)';
      ctx.fillRect(0, 0, mapWidth, mapHeight);
      ctx.font      = '12px sans-serif';
      ctx.fillStyle = '#666';
      ctx.fillText('⚠ Basemap blocked by CORS — layers still exported', 10, 20);
    }

    // ── Layer 2: Canvas elements (georaster / WebGL raster layers) ────────
    // Skip the annotation canvas here — it is painted last (topmost layer).
    mapContainer.querySelectorAll('canvas').forEach(function(sourceCanvas) {
      if (sourceCanvas === _annotateCanvas) return;
      if (sourceCanvas.width === 0 || sourceCanvas.height === 0) return;
      try {
        const off = getElementOffsetInContainer(sourceCanvas, containerRect);
        ctx.drawImage(sourceCanvas, off.x, off.y);
      } catch (e) {
        console.warn('[buildCompositeCanvas] Canvas tainted:', e.message);
      }
    });

    // ── Layer 3: SVG vector layers ─────────────────────────────────────────
    const svgElement = mapContainer.querySelector('.leaflet-overlay-pane svg');

    function drawAnnotationCanvas() {
      // ── Layer 5: Annotation (must be topmost) ──────────────────────────
      if (_annotateCanvas && _annotateCanvas.width > 0 && _annotateCanvas.height > 0) {
        try {
          const off = getElementOffsetInContainer(_annotateCanvas, containerRect);
          ctx.drawImage(_annotateCanvas, off.x, off.y);
        } catch (e) {
          console.warn('[buildCompositeCanvas] Annotation canvas tainted:', e.message);
        }
      }
      ctx.restore();
      callback(exportCanvas);
    }

    if (svgElement) {
      drawSvgOntoCanvas(svgElement, mapContainer, ctx, mapWidth, mapHeight, function() {
        // ── Layer 4: Marker icons ───────────────────────────────────────────
        drawMarkersOntoCanvas(mapContainer, ctx, drawAnnotationCanvas);
      });
    } else {
      drawMarkersOntoCanvas(mapContainer, ctx, drawAnnotationCanvas);
    }
  });
}


// ── STEP 3: SVG drawing helper ────────────────────────────────────────────────

/**
 * drawSvgOntoCanvas(svgEl, mapContainer, ctx, w, h, done)
 * Serialize a Leaflet SVG overlay to a data URL and paint it onto ctx.
 *
 * Key fix for missing polygons:
 *   Leaflet SVG paths often have fill-opacity:0 in their inline style
 *   when first created. We temporarily set them to visible before
 *   serializing, then restore the original values.
 *
 * @param {SVGElement}  svgEl        — The SVG element from Leaflet
 * @param {HTMLElement} mapContainer — The .leaflet-container div
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} w  — Canvas width
 * @param {number} h  — Canvas height
 * @param {function} done — Callback when finished
 */
function drawSvgOntoCanvas(svgEl, mapContainer, ctx, w, h, done) {

  // ── Fix invisible polygons ─────────────────────────────────────────────────
  // Leaflet polygon paths default fill-opacity to 0.2 but sometimes
  // the computed style comes through as 0. We force them visible here.
  const allPaths     = svgEl.querySelectorAll('path, polygon, rect, circle, ellipse');
  const savedStyles  = [];

  allPaths.forEach(function(path) {
    const computed = window.getComputedStyle(path);
    savedStyles.push({
      el:              path,
      fillOpacity:     path.style.fillOpacity,
      strokeOpacity:   path.style.strokeOpacity,
    });

    // Only override if currently invisible
    // Don't override intentionally transparent layers (opacity < 0.01)
    const fo = parseFloat(computed.fillOpacity);
    const so = parseFloat(computed.strokeOpacity);

    if (fo === 0 && path.getAttribute('fill') !== 'none') {
      path.style.fillOpacity = '0.5'; // reasonable default for polygons
    }
    if (so === 0) {
      path.style.strokeOpacity = '1';
    }
  });

  // ── Serialize SVG to string ────────────────────────────────────────────────
  // We need to clone the SVG and set explicit width/height on it,
  // because the Leaflet SVG uses viewBox but no explicit dimensions.
  const svgClone = svgEl.cloneNode(true);

  // Position the SVG at the correct offset within the map
  const svgRect       = svgEl.getBoundingClientRect();
  const containerRect = mapContainer.getBoundingClientRect();
  const svgOffsetX    = svgRect.left - containerRect.left;
  const svgOffsetY    = svgRect.top  - containerRect.top;

  // Set explicit dimensions so the browser can render it
  svgClone.setAttribute('width',  svgRect.width  || w);
  svgClone.setAttribute('height', svgRect.height || h);

  // Inline all computed styles on paths so they survive serialization
  // (SVG serialized to <img> loses external stylesheet styles)
  const clonedPaths = svgClone.querySelectorAll('path, polygon, circle, ellipse, polyline');
  const livePaths   = svgEl.querySelectorAll('path, polygon, circle, ellipse, polyline');

  livePaths.forEach(function(livePath, i) {
    if (!clonedPaths[i]) return;
    const computed = window.getComputedStyle(livePath);

    // Copy the visual properties that matter for export
    const props = [
      'fill', 'fill-opacity', 'stroke', 'stroke-width',
      'stroke-opacity', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin'
    ];
    props.forEach(function(prop) {
      const val = computed.getPropertyValue(prop);
      if (val) clonedPaths[i].style.setProperty(prop, val);
    });
  });

  // Serialize to XML string
  const serializer = new XMLSerializer();
  const svgString  = serializer.serializeToString(svgClone);
  const svgBlob    = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
  const svgUrl     = URL.createObjectURL(svgBlob);

  // Restore original opacity values on live paths
  savedStyles.forEach(function(s) {
    s.el.style.fillOpacity   = s.fillOpacity;
    s.el.style.strokeOpacity = s.strokeOpacity;
  });

  // Draw SVG image onto our export canvas at the correct offset
  const svgImg  = new Image();
  svgImg.onload = function() {
    ctx.drawImage(svgImg, svgOffsetX, svgOffsetY);
    URL.revokeObjectURL(svgUrl);
    done();
  };
  svgImg.onerror = function(e) {
    console.warn('[drawSvgOntoCanvas] SVG render failed:', e);
    URL.revokeObjectURL(svgUrl);
    done(); // Continue anyway — don't block the export
  };
  svgImg.src = svgUrl;
}


// ── STEP 4: Marker drawing helper ────────────────────────────────────────────

/**
 * drawMarkersOntoCanvas(mapContainer, ctx, done)
 * Draws all Leaflet marker icons (standard pin markers and DivIcons)
 * onto the export canvas.
 *
 * Standard markers are <img> elements in .leaflet-marker-pane.
 * DivIcons are <div> elements — we draw a fallback dot for those.
 *
 * @param {HTMLElement} mapContainer
 * @param {CanvasRenderingContext2D} ctx
 * @param {function} done
 */
function drawMarkersOntoCanvas(mapContainer, ctx, done) {

  const markerPane    = mapContainer.querySelector('.leaflet-marker-pane');
  if (!markerPane) { done(); return; }

  const containerRect = mapContainer.getBoundingClientRect();
  const markerImgs    = markerPane.querySelectorAll('img.leaflet-marker-icon');

  // If no img markers, check for DivIcon markers
  if (markerImgs.length === 0) {
    // DivIcons: draw a circle dot at each marker's position
    const divMarkers = markerPane.querySelectorAll('.leaflet-marker-icon');
    divMarkers.forEach(function(div) {
      const rect = div.getBoundingClientRect();
      const cx   = rect.left - containerRect.left + rect.width  / 2;
      const cy   = rect.top  - containerRect.top  + rect.height / 2;
      ctx.beginPath();
      ctx.arc(cx, cy, 7, 0, Math.PI * 2);
      ctx.fillStyle   = '#3388ff';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth   = 1.5;
      ctx.stroke();
    });
    done();
    return;
  }

  // Load and draw each marker image
  let loaded = 0;
  markerImgs.forEach(function(imgEl) {
    const rect    = imgEl.getBoundingClientRect();
    const offsetX = rect.left - containerRect.left;
    const offsetY = rect.top  - containerRect.top;

    const img   = new Image();
    img.crossOrigin = 'anonymous';
    img.onload  = function() {
      ctx.drawImage(img, offsetX, offsetY, rect.width, rect.height);
      loaded++;
      if (loaded === markerImgs.length) done();
    };
    img.onerror = function() {
      // Draw a fallback dot if the marker image fails to load
      ctx.beginPath();
      ctx.arc(offsetX + rect.width / 2, offsetY + rect.height / 2, 7, 0, Math.PI * 2);
      ctx.fillStyle = '#3388ff';
      ctx.fill();
      loaded++;
      if (loaded === markerImgs.length) done();
    };
    img.src = imgEl.src;
  });
}


// ── STEP 5: Format encoding and download ─────────────────────────────────────

/**
 * encodeAndDownload(canvas, format)
 * Encodes the final composite canvas in the requested format and
 * triggers a browser download.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {string} format — 'png' | 'jpg' | 'jpeg' | 'tiff'
 */
function encodeAndDownload(canvas, format) {

  const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  const filename  = `map_export_${timestamp}.${format}`;

  if (format === 'png') {
    triggerDownload(canvas.toDataURL('image/png'), filename);
    showToast('Map exported as PNG!', 'success');
    return;
  }

  if (format === 'jpg' || format === 'jpeg') {
    // JPG has no alpha channel — composite onto white background first
    const jpgCanvas        = document.createElement('canvas');
    jpgCanvas.width        = canvas.width;
    jpgCanvas.height       = canvas.height;
    const jpgCtx           = jpgCanvas.getContext('2d');
    jpgCtx.fillStyle       = '#ffffff';
    jpgCtx.fillRect(0, 0, jpgCanvas.width, jpgCanvas.height);
    jpgCtx.drawImage(canvas, 0, 0);
    triggerDownload(jpgCanvas.toDataURL('image/jpeg', 0.95), filename);
    showToast('Map exported as JPG!', 'success');
    return;
  }

  if (format === 'tiff') {
    try {
      const tiffBlob = canvasToTiff(canvas);
      const url      = URL.createObjectURL(tiffBlob);
      triggerDownload(url, filename);
      setTimeout(() => URL.revokeObjectURL(url), 8000);
      showToast('Map exported as TIFF!', 'success');
    } catch (err) {
      console.error('[encodeAndDownload] TIFF encode failed:', err);
      // Fallback to PNG
      showToast('TIFF encode failed — falling back to PNG.', 'warning');
      triggerDownload(canvas.toDataURL('image/png'), filename.replace('.tiff', '.png'));
    }
    return;
  }
}


// ── TIFF encoder ──────────────────────────────────────────────────────────────

/**
 * canvasToTiff(canvas)
 * Encodes an HTMLCanvasElement as an uncompressed 24-bit RGB TIFF blob.
 *
 * Structure written:
 *   [8 bytes]  TIFF header  (little-endian magic + IFD offset)
 *   [2 bytes]  IFD entry count
 *   [132 bytes] 11 × IFD entries (12 bytes each)
 *   [4 bytes]  Next IFD pointer (0)
 *   [6 bytes]  BitsPerSample values [8, 8, 8]
 *   [N bytes]  Raw RGB pixel rows (no compression)
 *
 * NOTE: This is a visual TIFF only — it does NOT embed georeferencing.
 * For a proper GeoTIFF with coordinates, send this image + map bounds
 * to your Python backend and use rasterio to write the GeoTIFF there.
 *
 * @param  {HTMLCanvasElement} canvas
 * @returns {Blob}
 */
function canvasToTiff(canvas) {

  const ctx    = canvas.getContext('2d');
  const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data; // RGBA
  const width  = canvas.width;
  const height = canvas.height;

  // Convert RGBA → RGB (drop alpha channel)
  const rgbData = new Uint8Array(width * height * 3);
  for (let i = 0, j = 0; i < pixels.length; i += 4, j += 3) {
    rgbData[j]     = pixels[i];       // R
    rgbData[j + 1] = pixels[i + 1];   // G
    rgbData[j + 2] = pixels[i + 2];   // B
  }

  // ── File layout ────────────────────────────────────────────────────────────
  const NUM_TAGS     = 11;
  const headerSize   = 8;
  const ifdOffset    = headerSize;
  const ifdSize      = 2 + NUM_TAGS * 12 + 4;  // count + entries + next-pointer
  const bpsOffset    = ifdOffset + ifdSize;      // where BitsPerSample [8,8,8] lives
  const dataOffset   = bpsOffset + 6;            // where pixel bytes start
  const dataSize     = rgbData.byteLength;
  const totalSize    = dataOffset + dataSize;

  const buf  = new ArrayBuffer(totalSize);
  const view = new DataView(buf);
  let   p    = 0; // write cursor

  const w8  = (v) => { view.setUint8(p,  v);           p += 1; };
  const w16 = (v) => { view.setUint16(p, v, true);     p += 2; }; // LE
  const w32 = (v) => { view.setUint32(p, v, true);     p += 4; };

  /**
   * writeTag(tag, type, count, value)
   * Write one 12-byte IFD entry.
   *   type 3 = SHORT (uint16), type 4 = LONG (uint32)
   * For SHORT count=1 the value is packed into the 4-byte value field (padded).
   * For everything else the value field holds an offset to the actual data.
   */
  function writeTag(tag, type, count, value) {
    w16(tag);
    w16(type);
    w32(count);
    if (type === 3 && count === 1) {
      w16(value);
      w16(0); // padding to fill 4 bytes
    } else {
      w32(value);
    }
  }

  // ── TIFF Header ────────────────────────────────────────────────────────────
  w8(0x49); w8(0x49); // 'II' = Intel byte order (little-endian)
  w16(42);            // TIFF magic number
  w32(ifdOffset);     // Offset to first IFD (immediately after header = 8)

  // ── IFD ───────────────────────────────────────────────────────────────────
  // Tags MUST be in ascending numeric order per the TIFF spec.
  w16(NUM_TAGS); // number of entries

  writeTag(256, 4, 1, width);          // ImageWidth
  writeTag(257, 4, 1, height);         // ImageLength (height)
  writeTag(258, 3, 3, bpsOffset);      // BitsPerSample → [8,8,8] at bpsOffset
  writeTag(259, 3, 1, 1);              // Compression: 1 = none
  writeTag(262, 3, 1, 2);              // PhotometricInterpretation: 2 = RGB
  writeTag(273, 4, 1, dataOffset);     // StripOffsets: pixel data starts here
  writeTag(277, 3, 1, 3);              // SamplesPerPixel: 3
  writeTag(278, 4, 1, height);         // RowsPerStrip: all rows in one strip
  writeTag(279, 4, 1, dataSize);       // StripByteCounts: total bytes of pixel data
  writeTag(282, 4, 1, bpsOffset);      // XResolution (rational placeholder)
  writeTag(283, 4, 1, bpsOffset);      // YResolution (rational placeholder)

  w32(0); // NextIFD = 0 (no more IFDs)

  // ── BitsPerSample values ──────────────────────────────────────────────────
  w16(8); // Red channel:   8 bits
  w16(8); // Green channel: 8 bits
  w16(8); // Blue channel:  8 bits

  // ── Pixel data ─────────────────────────────────────────────────────────────
  new Uint8Array(buf, p).set(rgbData);

  return new Blob([buf], { type: 'image/tiff' });
}


// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * triggerDownload(url, filename)
 * Creates an invisible <a> and clicks it to download a file.
 * Works for both data: URLs and blob: URLs.
 */
function triggerDownload(url, filename) {
  const a      = document.createElement('a');
  a.href       = url;
  a.download   = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}


/**
 * toggleExportMenu()
 * Opens / closes the export format picker dropdown.
 * Closes automatically when the user clicks outside.
 */
function toggleExportMenu() {
  const menu = document.getElementById('exportMenu');
  if (!menu) return;

  const isOpen = menu.classList.toggle('open');

  if (isOpen) {
    // Attach a one-time outside-click listener
    const closeHandler = function(e) {
      if (!menu.contains(e.target)) {
        menu.classList.remove('open');
        document.removeEventListener('click', closeHandler);
      }
    };
    // Delay so the current click doesn't immediately close the menu
    setTimeout(() => document.addEventListener('click', closeHandler), 10);
  }
}


/**
 * showToast(message, type)
 * Displays a temporary notification toast in the lower-right corner.
 * Reuses an existing #toastContainer if present (from app.js),
 * otherwise creates one.
 *
 * @param {string} message
 * @param {string} type — 'info' | 'success' | 'warning' | 'danger'
 */
function showToast(message, type = 'info') {

  // Reuse app.js container if it exists
  let container = document.getElementById('toastContainer')
                || document.getElementById('toast-container');

  if (!container) {
    container    = document.createElement('div');
    container.id = 'toastContainer';
    Object.assign(container.style, {
      position:       'fixed',
      bottom:         '80px',
      right:          '20px',
      zIndex:         '9999',
      display:        'flex',
      flexDirection:  'column',
      gap:            '8px',
      pointerEvents:  'none',
    });
    document.body.appendChild(container);
  }

  const colors = { info:'#0d6efd', success:'#198754', warning:'#ffc107', danger:'#dc3545' };

  const toast = document.createElement('div');
  toast.textContent = message;
  Object.assign(toast.style, {
    minWidth:        '220px',
    padding:         '10px 14px',
    borderRadius:    '8px',
    color:           '#fff',
    fontSize:        '13px',
    backgroundColor: colors[type] || colors.info,
    boxShadow:       '0 4px 14px rgba(0,0,0,0.25)',
    opacity:         '1',
    transition:      'opacity 0.3s ease, transform 0.3s ease',
    transform:       'translateY(0)',
    pointerEvents:   'auto',
  });

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity   = '0';
    toast.style.transform = 'translateY(8px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}


/* ============================================================
   PDF REPORT EXPORT
   ============================================================ */
async function downloadAnalysisPDF() {
  const { jsPDF } = window.jspdf;
  if (!jsPDF) { alert("PDF library not loaded. Try refreshing the page."); return; }

  const panel = document.getElementById("analysisPanel");
  if (!panel) return;

  const titleEl = panel.querySelector(".panel-title");
  const title   = titleEl ? titleEl.textContent.trim() : "Urban QoL Analysis";
  const service = lastResultService || "analysis";

  // ── Extract insight-cards from a tab element ──────────────
  function extractCards(tabEl) {
    if (!tabEl) return [];
    const cards = [];
    tabEl.querySelectorAll(".insight-card").forEach(card => {
      const label = card.querySelector(".label")?.textContent.trim() || "";
      const value = card.querySelector(".value")?.textContent.trim().replace(/\s+/g, " ") || "";
      if (label) cards.push({ label, value });
    });
    return cards;
  }

  // ── Extract insight paragraphs (💡 boxes) ────────────────
  function extractInsights(tabEl) {
    if (!tabEl) return [];
    const texts = [];
    tabEl.querySelectorAll("div[style*='border-left']").forEach(el => {
      const t = el.textContent.trim().replace(/\s+/g, " ");
      if (t.length > 4) texts.push(t.replace(/^💡\s*/, ""));
    });
    return texts;
  }

  // ── Compute visual data from live GeoJSON ─────────────────
  function computeFullVisuals() {
    if (!lastResultBlob || !lastResultBlob.features) return null;
    const feats = lastResultBlob.features;
    switch (service) {
      case "crime": {
        const bins  = [0,0,0,0,0];
        feats.forEach(f => {
          const d = f.properties.crime_density || 0;
          if (d <= 5)  bins[0]++;
          else if (d <= 10) bins[1]++;
          else if (d <= 15) bins[2]++;
          else if (d <= 20) bins[3]++;
          else bins[4]++;
        });
        return { type:"bar", title:"Crime Density Distribution",
          labels:["0–5","5–10","10–15","15–20",">20"], values:bins,
          colors:["#2ecc71","#f1c40f","#e67e22","#e74c3c","#891508"], unit:"/km²" };
      }
      case "urban-density": {
        const bins  = [0,0,0,0,0];
        feats.forEach(f => {
          const d = f.properties.urban_density || 0;
          if (d < 500)        bins[0]++;
          else if (d < 2000)  bins[1]++;
          else if (d < 5000)  bins[2]++;
          else if (d < 10000) bins[3]++;
          else bins[4]++;
        });
        return { type:"bar", title:"Population Density Distribution",
          labels:["<500","500–2k","2k–5k","5k–10k",">10k"], values:bins,
          colors:["#add8e6","#87ceeb","#4682b4","#4169e1","#000080"], unit:"pop/km²" };
      }
      case "public-transport": {
        const covered   = feats.filter(f => f.properties.type === "covered").length;
        const uncovered = feats.filter(f => f.properties.type === "uncovered").length;
        if (!covered && !uncovered) return null;
        return { type:"bar", title:"Coverage Breakdown",
          labels:["Covered","Uncovered"], values:[covered, uncovered],
          colors:["#4cc2ff","#e74c3c"], unit:"zones" };
      }
      case "facility-accessibility": {
        const t5 = feats.filter(f => f.properties.time_min === 5).length;
        const t10= feats.filter(f => f.properties.time_min === 10).length;
        const t15= feats.filter(f => f.properties.time_min === 15).length;
        if (!t5 && !t10 && !t15) return null;
        return { type:"bar", title:"Accessibility Walk-Time Zones",
          labels:["≤5 min","≤10 min","≤15 min"], values:[t5,t10,t15],
          colors:["#198754","#ffc107","#dc3545"], unit:"zones" };
      }
      case "vegetation": {
        const bins = [0,0,0,0];
        feats.forEach(f => {
          const p = f.properties.vegetation_pct ?? 0;
          if (p >= 50)      bins[0]++;
          else if (p >= 30) bins[1]++;
          else if (p >= 15) bins[2]++;
          else              bins[3]++;
        });
        return { type:"bar", title:"Vegetation Coverage Distribution",
          labels:["≥50%","30–50%","15–30%","<15%"], values:bins,
          colors:["#27ae60","#8bc34a","#f39c12","#c0392b"], unit:"cells" };
      }
      case "traffic": {
        const gridFeats = feats.filter(f => f.properties.type !== "hotspot");
        const bins = [0,0,0];
        gridFeats.forEach(f => {
          const c = f.properties.congestion;
          if (c === "high")   bins[2]++;
          else if (c==="medium") bins[1]++;
          else bins[0]++;
        });
        return { type:"bar", title:"Congestion Level Distribution",
          labels:["Low","Medium","High"], values:bins,
          colors:["#2ecc71","#f39c12","#e74c3c"], unit:"cells" };
      }
      case "informal-settlement": {
        const gridFeats = feats.filter(f => f.properties.type !== "high_irregularity_zone");
        const bins = [0,0,0];
        gridFeats.forEach(f => {
          const s = f.properties.irregularity_score ?? 0;
          if (s <= 33)      bins[0]++;
          else if (s <= 66) bins[1]++;
          else              bins[2]++;
        });
        return { type:"bar", title:"Irregularity Classification",
          labels:["Planned (0–33)","Mixed (34–66)","Informal (67–100)"], values:bins,
          colors:["#2ecc71","#f39c12","#e74c3c"], unit:"cells" };
      }
      default:
        return null;
    }
  }

  // ── Compute QoL score gauge value from full cards ─────────
  function extractOverallScore(cards) {
    for (const c of cards) {
      const m = c.value.match(/^(\d+(?:\.\d+)?)\s*\/\s*100/);
      if (m && (c.label.toLowerCase().includes("score") || c.label.toLowerCase().includes("overall")))
        return parseFloat(m[1]);
    }
    return null;
  }

  // ── Compute grid cell tier distribution ───────────────────
  function computeGridVisuals() {
    if (!gridLayer) return null;
    const feats = [];
    gridLayer.eachLayer(l => { if (l.feature) feats.push(l.feature); });
    if (!feats.length) return null;

    const isVeg     = service === "vegetation";
    const isTraffic = service === "traffic";
    const isISPA    = service === "informal-settlement";
    const isNDVI    = service === "ndvi";

    if (isVeg) {
      const pass = feats.filter(f => f.properties.passes_30pct).length;
      const fail = feats.length - pass;
      return { type:"bar", title:"Grid: Greenery Standard",
        labels:["≥30% (Pass)","<30% (Fail)"], values:[pass,fail],
        colors:["#27ae60","#c0392b"], unit:"cells" };
    }
    if (isTraffic) {
      const lo = feats.filter(f=>f.properties.congestion==="low").length;
      const me = feats.filter(f=>f.properties.congestion==="medium").length;
      const hi = feats.filter(f=>f.properties.congestion==="high").length;
      return { type:"bar", title:"Grid: Congestion Levels",
        labels:["Low","Medium","High"], values:[lo,me,hi],
        colors:["#2ecc71","#f39c12","#e74c3c"], unit:"cells" };
    }
    if (isISPA) {
      const lo = feats.filter(f=>(f.properties.value??0)<=33).length;
      const me = feats.filter(f=>{const v=f.properties.value??0;return v>33&&v<=66;}).length;
      const hi = feats.filter(f=>(f.properties.value??0)>66).length;
      return { type:"bar", title:"Grid: Irregularity Tiers",
        labels:["Planned","Mixed","Informal"], values:[lo,me,hi],
        colors:["#2ecc71","#f39c12","#e74c3c"], unit:"cells" };
    }
    if (isNDVI) {
      const healthy   = feats.filter(f=>(f.properties.value??-1)>=0.2).length;
      const unhealthy = feats.length - healthy;
      return { type:"bar", title:"Grid: Vegetation Health",
        labels:["Healthy (≥0.2)","Unhealthy (<0.2)"], values:[healthy,unhealthy],
        colors:["#27ae60","#e74c3c"], unit:"cells" };
    }
    // Generic QoL tiers
    const exc = feats.filter(f=>(f.properties.qol_score??0)>=75).length;
    const goo = feats.filter(f=>{const s=f.properties.qol_score??0;return s>=50&&s<75;}).length;
    const fai = feats.filter(f=>{const s=f.properties.qol_score??0;return s>=25&&s<50;}).length;
    const poo = feats.filter(f=>(f.properties.qol_score??0)<25).length;
    return { type:"bar", title:"Grid: QoL Score Tiers",
      labels:["Excellent (75–100)","Good (50–74)","Fair (25–49)","Poor (0–24)"],
      values:[exc,goo,fai,poo],
      colors:["#2ecc71","#8bc34a","#f39c12","#e74c3c"], unit:"cells" };
  }

  // ── Capture map ───────────────────────────────────────────
  let mapDataUrl = null;
  try {
    const mapCanvas = document.querySelector("#map canvas");
    if (mapCanvas) mapDataUrl = mapCanvas.toDataURL("image/jpeg", 0.85);
  } catch(e) {}

  // ── PDF setup ─────────────────────────────────────────────
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const PW  = 210, PH = 297, ML = 14, MR = 14;
  const CW  = PW - ML - MR;
  let   y   = 0;

  const C = {
    bg:        [15,  17,  26],
    panel:     [22,  26,  40],
    card:      [28,  33,  50],
    accent:    [76, 194, 255],
    accentDim: [40, 100, 140],
    textMain:  [220, 225, 240],
    textMuted: [130, 140, 165],
    border:    [45,  52,  75],
    white:     [255, 255, 255],
  };

  function setFill(rgb)  { doc.setFillColor(rgb[0], rgb[1], rgb[2]); }
  function setDraw(rgb)  { doc.setDrawColor(rgb[0], rgb[1], rgb[2]); }
  function setTextC(rgb) { doc.setTextColor(rgb[0], rgb[1], rgb[2]); }
  function rect(x, yw, w, h, style="F") { doc.rect(x, yw, w, h, style); }

  function hexToRgb(hex) {
    const r = parseInt(hex.slice(1,3),16);
    const g = parseInt(hex.slice(3,5),16);
    const b = parseInt(hex.slice(5,7),16);
    return [r,g,b];
  }

  function ensurePage(needed) {
    if (y + needed > PH - 12) {
      doc.addPage();
      setFill(C.bg); rect(0, 0, PW, PH);
      y = 14;
    }
  }

  function wrapText(text, maxWidth, fontSize) {
    doc.setFontSize(fontSize);
    return doc.splitTextToSize(text, maxWidth);
  }

  // ── Section header ────────────────────────────────────────
  function sectionHeader(text) {
    ensurePage(12);
    setFill(C.panel); rect(ML, y, CW, 9);
    setFill(C.accent); rect(ML, y, 3, 9);
    setTextC(C.white); doc.setFontSize(9); doc.setFont("helvetica", "bold");
    doc.text(text, ML + 5, y + 6);
    y += 12;
  }

  // ── Insight callout box ───────────────────────────────────
  function insightBox(text) {
    if (!text) return;
    const lines = wrapText(text, CW - 10, 8);
    const bh = lines.length * 4.5 + 5;
    ensurePage(bh + 3);
    setFill(C.panel); rect(ML, y, CW, bh);
    setFill(C.accentDim); rect(ML, y, 2.5, bh);
    setTextC(C.textMain); doc.setFont("helvetica", "italic"); doc.setFontSize(8);
    lines.forEach((line, i) => doc.text(line, ML + 5, y + 4.5 + i * 4.5));
    y += bh + 3;
  }

  // ── Two-column card grid ──────────────────────────────────
  function cardGrid(cards) {
    if (!cards.length) return;
    const colW = (CW - 2) / 2, cardH = 10, gap = 1.5;
    let rowY = y;
    cards.forEach((card, i) => {
      if (i % 2 === 0) { ensurePage(cardH + gap); rowY = y; }
      const col = i % 2;
      const cx  = ML + col * (colW + 2);
      setFill(C.card); rect(cx, rowY, colW, cardH);
      setDraw(C.border); doc.setLineWidth(0.15); rect(cx, rowY, colW, cardH, "S");
      doc.setFont("helvetica","normal"); doc.setFontSize(7); setTextC(C.textMuted);
      doc.text(card.label, cx + 3, rowY + 3.5);
      doc.setFont("helvetica","bold"); doc.setFontSize(8); setTextC(C.textMain);
      const vl = doc.splitTextToSize(card.value, colW - 6);
      doc.text(vl[0] || card.value, cx + 3, rowY + 7.5);
      if (col === 1 || i === cards.length - 1) y = rowY + cardH + gap;
    });
  }

  // ── Score gauge bar ───────────────────────────────────────
  // Draws a full-width horizontal bar: track + filled portion + score label
  function scoreGauge(score) {
    if (score === null || score === undefined) return;
    ensurePage(22);
    const bx = ML, bw = CW, bh = 12, by = y + 4;
    // background panel
    setFill(C.panel); rect(ML, y, CW, 20);
    // label
    setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(7);
    doc.text("Overall QoL Score", ML + 2, y + 3.5);
    // track
    setFill(C.card); rect(bx, by, bw, bh);
    setDraw(C.border); doc.setLineWidth(0.2); rect(bx, by, bw, bh, "S");
    // filled portion — colour based on score
    const fillW = Math.max(2, (score / 100) * bw);
    let fillColor;
    if      (score >= 75) fillColor = [46, 204, 113];
    else if (score >= 50) fillColor = [139, 195,  74];
    else if (score >= 25) fillColor = [243, 156,  18];
    else                  fillColor = [231,  76,  60];
    setFill(fillColor); rect(bx, by, fillW, bh);
    // tick marks every 25
    setDraw(C.border); doc.setLineWidth(0.3);
    [25,50,75].forEach(v => {
      const tx = bx + (v / 100) * bw;
      doc.line(tx, by, tx, by + bh);
    });
    // score text centred on fill
    setTextC(C.white); doc.setFont("helvetica","bold"); doc.setFontSize(8);
    doc.text(`${Math.round(score)} / 100`, bx + fillW / 2, by + bh / 2 + 2.5, { align:"center" });
    // tier labels below track
    setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(6.5);
    ["Poor","Fair","Good","Excellent"].forEach((lbl, i) => {
      doc.text(lbl, bx + (i * 25 + 12.5) / 100 * bw, by + bh + 3.5, { align:"center" });
    });
    y += 24;
  }

  // ── Vertical bar chart ────────────────────────────────────
  // data = { title, labels[], values[], colors[], unit }
  function barChart(data) {
    if (!data) return;
    const { title: chartTitle, labels, values, colors, unit } = data;
    const n      = labels.length;
    const maxVal = Math.max(...values, 1);
    const chartH = 38;   // height of bar area
    const totalH = chartH + 22;  // + title + labels
    ensurePage(totalH + 4);

    // panel bg
    setFill(C.panel); rect(ML, y, CW, totalH + 2);

    // chart title
    setTextC(C.textMuted); doc.setFont("helvetica","bold"); doc.setFontSize(7.5);
    doc.text(chartTitle, ML + CW / 2, y + 5, { align:"center" });

    const chartTop = y + 8;
    const barAreaW = CW - 16;
    const barAreaX = ML + 8;

    // horizontal gridlines at 0%, 50%, 100%
    setDraw(C.border); doc.setLineWidth(0.15);
    [0, 0.5, 1].forEach(frac => {
      const lineY = chartTop + chartH * (1 - frac);
      doc.line(barAreaX, lineY, barAreaX + barAreaW, lineY);
      if (frac > 0) {
        setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(6);
        doc.text(`${Math.round(maxVal * frac)}`, barAreaX - 1, lineY + 1, { align:"right" });
      }
    });

    // bars
    const slotW = barAreaW / n;
    const barW  = Math.min(slotW * 0.62, 18);
    values.forEach((val, i) => {
      const barH   = Math.max(1, (val / maxVal) * chartH);
      const bx     = barAreaX + i * slotW + (slotW - barW) / 2;
      const by     = chartTop + chartH - barH;
      const rgb    = hexToRgb(colors[i] || "#4cc2ff");
      // bar shadow / glow
      setFill([rgb[0]*0.4, rgb[1]*0.4, rgb[2]*0.4]);
      rect(bx + 0.5, by + 0.5, barW, barH);
      // bar
      setFill(rgb); rect(bx, by, barW, barH);
      // value label above bar
      setTextC(C.textMain); doc.setFont("helvetica","bold"); doc.setFontSize(6.5);
      doc.text(`${val}`, bx + barW / 2, by - 1.2, { align:"center" });
      // axis label below
      setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(6);
      const lbl = doc.splitTextToSize(labels[i], slotW - 1);
      lbl.forEach((ln, li) => doc.text(ln, bx + barW / 2, chartTop + chartH + 4 + li * 3.5, { align:"center" }));
    });

    // unit label bottom-right
    setTextC(C.textMuted); doc.setFont("helvetica","italic"); doc.setFontSize(6);
    doc.text(`(${unit})`, barAreaX + barAreaW, chartTop + chartH + 4, { align:"right" });

    y += totalH + 5;
  }

  // ── Score heatmap strip ───────────────────────────────────
  // Renders a row of small coloured squares — one per grid cell, sorted by score
  function scoreHeatmapStrip() {
    if (!gridLayer) return;
    const scores = [];
    gridLayer.eachLayer(l => {
      const s = l.feature?.properties?.qol_score;
      if (s !== null && s !== undefined) scores.push(s);
    });
    if (!scores.length) return;
    scores.sort((a,b) => a - b);

    ensurePage(28);
    setFill(C.panel); rect(ML, y, CW, 26);
    setTextC(C.textMuted); doc.setFont("helvetica","bold"); doc.setFontSize(7.5);
    doc.text("Grid Cell Score Distribution (sorted low → high)", ML + CW/2, y + 5, { align:"center" });

    const stripY = y + 8;
    const stripH = 10;
    const n      = scores.length;
    const cellW  = Math.max(0.3, CW / n);
    scores.forEach((s, i) => {
      let r, g, b;
      if (s >= 75)      { r=46;  g=204; b=113; }
      else if (s >= 50) { r=139; g=195; b=74;  }
      else if (s >= 25) { r=243; g=156; b=18;  }
      else              { r=231; g=76;  b=60;  }
      doc.setFillColor(r, g, b);
      doc.rect(ML + i * cellW, stripY, cellW + 0.1, stripH, "F");
    });

    // legend under strip
    const legItems = [
      { label:"Excellent (75–100)", r:46,  g:204, b:113 },
      { label:"Good (50–74)",       r:139, g:195, b:74  },
      { label:"Fair (25–49)",       r:243, g:156, b:18  },
      { label:"Poor (0–24)",        r:231, g:76,  b:60  },
    ];
    const legW = CW / legItems.length;
    legItems.forEach((item, i) => {
      const lx = ML + i * legW;
      doc.setFillColor(item.r, item.g, item.b);
      doc.rect(lx, stripY + stripH + 2, 4, 3, "F");
      setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(6);
      doc.text(item.label, lx + 5.5, stripY + stripH + 4.5);
    });

    y += 30;
  }

  // ═══════════════════════════════════════════════════════
  // Gather all data before drawing
  // ═══════════════════════════════════════════════════════
  const tabRaw  = panel.querySelector("#tab-raw");
  const tabFull = panel.querySelector("#tab-full");
  const tabGrid = panel.querySelector("#tab-grid");

  const rawCards     = extractCards(tabRaw);
  const fullCards    = extractCards(tabFull);
  const gridCards    = extractCards(tabGrid);
  const fullInsights = extractInsights(tabFull);
  const gridInsights = extractInsights(tabGrid);
  const overallScore = extractOverallScore(fullCards);
  const fullVisData  = computeFullVisuals();
  const gridVisData  = computeGridVisuals();

  // ═══════════════════════════════════════════════════════
  // PAGE 1 — Cover
  // ═══════════════════════════════════════════════════════
  setFill(C.bg); rect(0, 0, PW, PH);
  setFill(C.panel); rect(0, 0, PW, 38);
  setFill(C.accent); rect(0, 35.5, PW, 2.5);

  setTextC(C.accent); doc.setFont("helvetica","bold"); doc.setFontSize(9);
  doc.text("MALAZ", ML, 12);
  setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(7);
  doc.text("Urban Quality of Life Platform", ML, 17);

  setTextC(C.white); doc.setFont("helvetica","bold"); doc.setFontSize(16);
  doc.splitTextToSize(title, CW - 20).forEach((line, i) => doc.text(line, ML, 27 + i * 7));

  setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(7.5);
  const dateStr = new Date().toLocaleDateString("en-US", { year:"numeric", month:"long", day:"numeric" });
  doc.text(`Generated: ${dateStr}`, PW - MR, 12, { align:"right" });
  doc.text(`Service: ${service}`,   PW - MR, 17, { align:"right" });

  y = 44;

  // Map image
  if (mapDataUrl) {
    const mapH = 68;
    ensurePage(mapH + 8);
    setFill(C.panel); rect(ML, y, CW, mapH + 4);
    try { doc.addImage(mapDataUrl, "JPEG", ML + 1, y + 1, CW - 2, mapH + 2); } catch(e) {}
    setTextC(C.textMuted); doc.setFont("helvetica","italic"); doc.setFontSize(7);
    doc.text("Map — Full Area view at time of export", ML + 2, y + mapH + 5);
    y += mapH + 9;
  }

  // ═══════════════════════════════════════════════════════
  // SECTION 1 — Raw Data
  // ═══════════════════════════════════════════════════════
  if (rawCards.length) {
    sectionHeader("RAW DATA  /  INPUT SUMMARY");
    cardGrid(rawCards);
    y += 3;
  }

  // ═══════════════════════════════════════════════════════
  // SECTION 1b — Crime-specific: Type Breakdown + Area Rankings
  // (data sourced directly from globals, not DOM scraping)
  // ═══════════════════════════════════════════════════════
  if (service === "crime") {
    // ── Crime Type Breakdown ──────────────────────────────
    const typeCounts = window._crimeTypeCounts || {};
    const typeEntries = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    if (typeEntries.length) {
      const typeTotal = typeEntries.reduce((s, [, v]) => s + v, 0);
      sectionHeader("CRIME TYPE BREAKDOWN");
      typeEntries.forEach(([type, count]) => {
        const pct = typeTotal > 0 ? (count / typeTotal) * 100 : 0;
        const rowH = 7;
        ensurePage(rowH + 2);
        // row bg
        setFill(C.card); rect(ML, y, CW, rowH);
        // label
        doc.setFont("helvetica","normal"); doc.setFontSize(7.5); setTextC(C.textMain);
        doc.text(type, ML + 3, y + 4.5);
        // count + pct right-aligned
        doc.setFont("helvetica","bold"); doc.setFontSize(7); setTextC(C.textMuted);
        doc.text(`${count}  (${pct.toFixed(1)}%)`, ML + CW - 3, y + 4.5, { align:"right" });
        // bar track
        const barX = ML + 3, barY = y + 5.5, barH = 1.2;
        const barMaxW = CW - 6;
        setFill(C.border); rect(barX, barY, barMaxW, barH);
        setFill(hexToRgb("#e74c3c")); rect(barX, barY, (pct / 100) * barMaxW, barH);
        y += rowH + 1;
      });
      y += 4;
    }

    // ── Top Unsafe / Safe Areas ───────────────────────────
    if (lastResultBlob && lastResultBlob.features && lastResultBlob.features.length) {
      const nameKey = ["NBHD_NAME","name","NAME","district","area_name","neighborhood"]
        .find(k => lastResultBlob.features[0]?.properties?.[k] !== undefined);
      const areaList = lastResultBlob.features
        .filter(f => f.properties && f.properties.crime_density !== undefined && nameKey && f.properties[nameKey])
        .map(f => ({ name: f.properties[nameKey], density: parseFloat(f.properties.crime_density) || 0 }))
        .sort((a, b) => b.density - a.density);

      if (areaList.length) {
        sectionHeader("AREA SAFETY RANKINGS");

        // helper: draw a ranked list
        function areaRankList(items, headerText, barColor) {
          const maxDen = items[0]?.density || 1;
          ensurePage(8 + items.length * 8);
          // sub-label
          doc.setFont("helvetica","bold"); doc.setFontSize(7.5); setTextC(C.textMuted);
          doc.text(headerText, ML, y + 4); y += 6;
          items.forEach((item, i) => {
            const rowH = 7;
            ensurePage(rowH + 1);
            setFill(C.card); rect(ML, y, CW, rowH);
            // rank badge
            setFill(barColor); rect(ML, y, 6, rowH);
            doc.setFont("helvetica","bold"); doc.setFontSize(7); setTextC(C.white);
            doc.text(`${i + 1}`, ML + 3, y + 4.5, { align:"center" });
            // name
            doc.setFont("helvetica","normal"); doc.setFontSize(7.5); setTextC(C.textMain);
            doc.text(item.name, ML + 9, y + 4.5);
            // density value
            doc.setFont("helvetica","bold"); doc.setFontSize(7); setTextC(C.textMuted);
            doc.text(`${item.density.toFixed(2)} /km²`, ML + CW - 3, y + 4.5, { align:"right" });
            // density bar
            const barX = ML + 9, barY = y + 5.5, barH = 1.2, barMaxW = CW - 12 - 22;
            setFill(C.border); rect(barX, barY, barMaxW, barH);
            setFill(barColor); rect(barX, barY, (item.density / maxDen) * barMaxW, barH);
            y += rowH + 1;
          });
          y += 3;
        }

        const top5Unsafe = areaList.slice(0, 5);
        const top5Safe   = areaList.slice(-5).reverse();
        areaRankList(top5Unsafe, "Most Unsafe Areas (highest crime density)", hexToRgb("#e74c3c"));
        areaRankList(top5Safe,   "Safest Areas (lowest crime density)",        hexToRgb("#2ecc71"));
      }
    }
  }

  // ═══════════════════════════════════════════════════════
  // SECTION 2 — Full Area Analysis
  // ═══════════════════════════════════════════════════════
  if (fullCards.length || fullInsights.length) {
    sectionHeader("FULL AREA ANALYSIS");
    cardGrid(fullCards);
    // ── visuals ──
    if (overallScore !== null) { y += 3; scoreGauge(overallScore); }
    if (fullVisData)           { y += 2; barChart(fullVisData);    }
    if (fullInsights.length)   { y += 2; fullInsights.forEach(t => insightBox(t)); }
    y += 3;
  }

  // ═══════════════════════════════════════════════════════
  // SECTION 3 — Grid / Cell Analysis
  // ═══════════════════════════════════════════════════════
  sectionHeader("GRID / CELL ANALYSIS");
  if (gridCards.length || gridVisData) {
    cardGrid(gridCards);
    if (gridVisData)         { y += 3; barChart(gridVisData);     }
    if (gridLayer)           { y += 2; scoreHeatmapStrip();       }
    if (gridInsights.length) { y += 2; gridInsights.forEach(t => insightBox(t)); }
    y += 3;
  } else {
    ensurePage(16);
    setFill(C.panel); rect(ML, y, CW, 13);
    setTextC(C.textMuted); doc.setFont("helvetica","italic"); doc.setFontSize(8);
    doc.text("Grid analysis not yet generated. Open the Grid / Cell tab to compute cell scores first.", ML + 4, y + 7);
    y += 16;
  }

  // ═══════════════════════════════════════════════════════
  // Footer on every page
  // ═══════════════════════════════════════════════════════
  const pageCount = doc.getNumberOfPages();
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p);
    setFill(C.panel); rect(0, PH - 10, PW, 10);
    setFill(C.accentDim); rect(0, PH - 10, PW, 0.5);
    setTextC(C.textMuted); doc.setFont("helvetica","normal"); doc.setFontSize(7);
    doc.text("Malaz · Urban Quality of Life Platform", ML, PH - 4);
    doc.text(`Page ${p} of ${pageCount}`, PW - MR, PH - 4, { align:"right" });
  }

  doc.save(`${service}_analysis_report.pdf`);
}
}