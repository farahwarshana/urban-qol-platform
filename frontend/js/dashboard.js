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
const SERVICES = {
  "urban-density": {
    title: "Urban Density",
    desc: "Estimate population density across an area.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "public-transport": {
    title: "Public Transport Coverage",
    desc: "Analyze coverage of public transport stations.",
    inputs: [
      { type: "file", id: "geoJsonInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "service-area": {
    title: "Service Area Analysis",
    desc: "Compute walkable service areas around facilities.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
      { type: "number", id: "walkingTime", label: "Walking time (minutes)", value: 10 },
    ],
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
    desc: "Compute vegetation cover from satellite imagery.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "ndvi": {
    title: "NDVI",
    desc: "Normalized Difference Vegetation Index from raster.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
      { type: "select", id: "satelliteType", label: "Satellite type", options: [
        { value: "landsat", label: "Landsat 8/9 (Band 4 Red, Band 5 NIR)", selected: true },
        { value: "sentinel2", label: "Sentinel-2 (Band 4 Red, Band 8 NIR)" },
      ]},
    ],
  },
  "crime": {
    title: "Safety / Crime Density",
    desc: "Hotspot analysis from incident points.",
    inputs: [
      { type: "file", id: "csvInput", label: "Upload crime data (CSV)" },
      { type: "file", id: "geoJsonInput", label: "Upload boundary data (GeoJSON)" },
      { type: "text", id: "latField", label: "Latitude column name", placeholder: "e.g. latitude, lat" },
      { type: "text", id: "lonField", label: "Longitude column name", placeholder: "e.g. longitude, lon" }
    ],
  },
  "traffic": {
    title: "Traffic Analysis",
    desc: "Analyze traffic flow and congestion.",
    inputs: [
      { type: "file", id: "tiffInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "air-quality": {
    title: "Air Quality Index",
    desc: "Compute AQI for the selected area.",
    inputs: [
      { type: "text", id: "areaName", label: "Area name (e.g. Downtown)" },
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
      return `
        <div class="form-group">
          <label for="${field.id}">${field.label}</label>
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
    // default: text
    return `
      <div class="form-group">
        <label for="${field.id}">${field.label}</label>
        <input type="text" id="${field.id}" />
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
function runAnalysis(key) {
  const service = SERVICES[key];

  if (key === "ndvi") {
    runNDVIAnalysis();
    return;
  }

  if (key === "crime") {
    runCrimeAnalysis();
    return;
  }

  renderResults(service);
}


/* ---------- NDVI Analysis - calls backend API ---------- */
async function runNDVIAnalysis() {
  const tiffInput = document.getElementById("tiffInput");
  const satelliteSelect = document.getElementById("satelliteType");
  
  if (!tiffInput || !tiffInput.files[0]) {
    alert("Please upload a GeoTIFF file first.");
    return;
  }

  const file = tiffInput.files[0];
  const satelliteType = satelliteSelect ? satelliteSelect.value : "landsat";
  
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
    // Build URL with query parameter
    const url = `http://localhost:8000/calculate-ndvi?satellite_type=${satelliteType}`;
    
    const response = await fetch(url, {
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

    // Convert response to array buffer
    const arrayBuffer = await response.arrayBuffer();

    // Render the NDVI result on the map (without custom color function to avoid projection issues)
    let resultLayer = await renderGeoRasterFromArrayBuffer(arrayBuffer, {
      opacity: 0.9,
      resolution: 256,
    });
    
    
    // Render results panel with NDVI stats
    renderNDVIResults({
      min: ndviMin,
      max: ndviMax,
      mean: ndviMean,
      valid_pixels: validPixels,
    });

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

  if (!latFieldValue || !lonFieldValue) {
    alert("Please enter the latitude and longitude column names.");
    return;
  }

  const csvFile = csvInput.files[0];
  const geoJsonFile = geoJsonInput.files[0];
  
  const formData = new FormData();
  formData.append("csv", csvFile);
  formData.append("geojson", geoJsonFile);
  formData.append("lat_field", latFieldValue);
  formData.append("lon_field", lonFieldValue);

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
    const url = `http://localhost:8000/calculate-crime-density?lat_field=${encodeURIComponent(latFieldValue)}&lon_field=${encodeURIComponent(lonFieldValue)}`;
    
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

    // Render the crime density result on the map as GeoJSON
    if (inputLayer) {
      map.removeLayer(inputLayer);
    }
    clearMap();

    inputLayer = L.geoJSON(geojsonData, {
      style: function(feature) {
        const density = feature.properties.crime_density || 0;
        // Color gradient from green (low crime) to red (high crime)
        let color = '#2ecc71'; // green
        if (density > 10) color = '#f1c40f'; // yellow
        if (density > 30) color = '#e67e22'; // orange
        if (density > 50) color = '#e74c3c'; // red
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
      const bounds = inputLayer.getBounds();
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
    });

  } catch (error) {
    console.error("Crime density calculation error:", error);
    
    // Try to get error details from response
    let errorMessage = error.message;
    
    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">Failed to calculate crime density: ${errorMessage}</p>
        <div class="alert alert-warning mt-2">
          <strong>Note:</strong> Make sure your CSV has columns for latitude and longitude.
          <br>• Latitude column: ${latFieldValue}
          <br>• Longitude column: ${lonFieldValue}
        </div>
        <button class="btn btn-ghost btn-block mt-3"
                onclick="renderServicePanel('crime')">
          ← Back to inputs
        </button>
      </div>
    `;
  }
}


/* ---------- Render Crime Results with stats ---------- */
function renderCrimeResults(stats) {
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Crime Density — Results</h3>
      <p class="panel-desc">Analysis complete. Explore tabs below.</p>

      <!-- Tab headers -->
      <div class="tabs">
        <div class="tab active" data-tab="raw">Raw Data</div>
        <div class="tab"        data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- Tab contents -->
      <div class="tab-content active" id="tab-raw">
        <p class="text-muted">Crime density layer rendered on map.</p>
        <div class="insight-card">
          <div class="label">Layers loaded</div>
          <div class="value">1</div>
        </div>
      </div>

      <div class="tab-content" id="tab-full">
        <div class="insight-card">
          <div class="label">Total Crimes</div>
          <div class="value">${stats.crime_count || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Areas Analyzed</div>
          <div class="value">${stats.area_count || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Avg Density</div>
          <div class="value">${stats.avg_density || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Max Density</div>
          <div class="value">${stats.max_density || "N/A"}</div>
        </div>
        <ul class="bullet-list">
          <li>Crime density = crimes per km²</li>
          <li>Higher values indicate more crime incidents</li>
          <li>Layer displayed with color gradient on map</li>
        </ul>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Grid analysis of crime density values.</p>
        <div class="insight-card">
          <div class="label">High crime areas</div>
          <div class="value">${((parseFloat(stats.max_density) || 0) > 50 ? "Yes" : "Limited")}</div>
        </div>
        <div class="insight-card">
          <div class="label">Safety rating</div>
          <div class="value">${(parseFloat(stats.avg_density) || 0) < 10 ? "Good" : (parseFloat(stats.avg_density) || 0) < 30 ? "Moderate" : "Poor"}</div>
        </div>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('crime')">
        ← Back to inputs
      </button>
    </div>
  `;

  // Wire up tab switching
  analysisPanel.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", function () {
      const target = tab.getAttribute("data-tab");
      analysisPanel.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      analysisPanel.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      analysisPanel.querySelector("#tab-" + target).classList.add("active");
    });
  });
}


/* ---------- Render NDVI Results with stats ---------- */
function renderNDVIResults(stats) {
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">NDVI — Results</h3>
      <p class="panel-desc">Analysis complete. Explore tabs below.</p>

      <!-- Tab headers -->
      <div class="tabs">
        <div class="tab active" data-tab="raw">Raw Data</div>
        <div class="tab"        data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- Tab contents -->
      <div class="tab-content active" id="tab-raw">
        <p class="text-muted">NDVI layer rendered on map.</p>
        <div class="insight-card">
          <div class="label">Layers loaded</div>
          <div class="value">1</div>
        </div>
      </div>

      <div class="tab-content" id="tab-full">
        <div class="insight-card">
          <div class="label">Min NDVI</div>
          <div class="value">${stats.min || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Max NDVI</div>
          <div class="value">${stats.max || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Mean NDVI</div>
          <div class="value">${stats.mean || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Valid Pixels</div>
          <div class="value">${stats.valid_pixels || "N/A"}</div>
        </div>
        <ul class="bullet-list">
          <li>NDVI range: -1 to 1</li>
          <li>Values > 0.2 indicate healthy vegetation</li>
          <li>Layer displayed with color gradient on map</li>
        </ul>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Grid analysis of NDVI values.</p>
        <div class="insight-card">
          <div class="label">High vegetation areas</div>
          <div class="value">${((parseFloat(stats.mean) || 0) > 0.4 ? "Yes" : "Limited")}</div>
        </div>
        <div class="insight-card">
          <div class="label">Vegetation health</div>
          <div class="value">${(parseFloat(stats.mean) || 0) > 0.6 ? "Excellent" : (parseFloat(stats.mean) || 0) > 0.4 ? "Good" : "Moderate"}</div>
        </div>
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel('ndvi')">
        ← Back to inputs
      </button>
    </div>
  `;

  // Wire up tab switching
  analysisPanel.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", function () {
      const target = tab.getAttribute("data-tab");
      analysisPanel.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      analysisPanel.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      analysisPanel.querySelector("#tab-" + target).classList.add("active");
    });
  });
}


/* ---------- Render the tabbed Results panel ---------- */
function renderResults(service) {
  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">${service.title} — Results</h3>
      <p class="panel-desc">Analysis complete. Explore tabs below.</p>

      <!-- Tab headers -->
      <div class="tabs">
        <div class="tab active" data-tab="raw">Raw Data</div>
        <div class="tab"        data-tab="full">Full Area</div>
        <div class="tab"        data-tab="grid">Grid / Cell</div>
      </div>

      <!-- Tab contents -->
      <div class="tab-content active" id="tab-raw">
        <p class="text-muted">Uploaded layers preview.</p>
        <div class="insight-card">
          <div class="label">Layers loaded</div>
          <div class="value">2</div>
        </div>
        <!-- TODO: populate with real raw data from backend -->
      </div>

      <div class="tab-content" id="tab-full">
        <div class="insight-card">
          <div class="label">Mean value</div>
          <div class="value">72.4</div>
        </div>
        <div class="insight-card">
          <div class="label">Coverage</div>
          <div class="value">86%</div>
        </div>
        <ul class="bullet-list">
          <li>Area shows above-average performance.</li>
          <li>3 hotspots detected.</li>
          <li>Recommended follow-up: detailed grid review.</li>
        </ul>
        <!-- TODO: populate with backend analysis results -->
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">AOI divided into cells.</p>
        <div class="insight-card">
          <div class="label">Cells analyzed</div>
          <div class="value">256</div>
        </div>
        <div class="insight-card">
          <div class="label">Best cell score</div>
          <div class="value">0.91</div>
        </div>
        <!-- TODO: render grid cell table or heatmap from backend -->
      </div>

      <button class="btn btn-ghost btn-block mt-3"
              onclick="renderServicePanel(getActiveServiceKey())">
        ← Back to inputs
      </button>
    </div>
  `;

  // Wire up tab switching
  analysisPanel.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", function () {
      const target = tab.getAttribute("data-tab");
      analysisPanel.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      analysisPanel.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      analysisPanel.querySelector("#tab-" + target).classList.add("active");
    });
  });
}


/* ---------- Helper: which service is currently selected? ---------- */
function getActiveServiceKey() {
  const active = serviceList.querySelector("li.active");
  return active ? active.getAttribute("data-service") : null;
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
  map = L.map("map").setView([31.2136, 29.8753], 11); // no const/let — assigns to outer variable

  currentBasemap = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    { attribution: "© CARTO © OpenStreetMap" }
  ).addTo(map);

  document.getElementById("mapPlaceholder").style.display = "none";
}

window.addEventListener("load", initMap);

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

let inputLayer = null; // Store reference to the currently displayed input layer so we can remove it when loading a new one

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

        // ADD TO MAP
        let geojsonLayer = L.geoJSON(geojsonData).addTo(map);

        // FIT BOUNDS
        try {
          const bounds = geojsonLayer.getBounds();
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

         // Find matching column names (case-insensitive)
        let lonHeader = headers.find(h => h.toLowerCase() === "lon");
        let latHeader = headers.find(h => h.toLowerCase() === "lat");

        if(!lonHeader) {
          let lonCol = prompt(`Enter the longitude column name from: ${headers.join(', ')}`);
          if (!lonCol) return;
          lonHeader = headers.find(h => h.toLowerCase() === lonCol.toLowerCase());
        }

        if(!latHeader) {
          let latCol = prompt(`Enter the latitude column name from: ${headers.join(', ')}`);
          if (!latCol) return;
          latHeader = headers.find(h => h.toLowerCase() === latCol.toLowerCase());
        }

        if (!lonHeader || !latHeader) {
          alert("Could not find the specified column names. Please check and try again.");
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
              features.push({
                type: "Feature",
                geometry: {
                  type: "Point",
                  coordinates: [lon, lat]
                },
                properties: {
                  row: i
                }
              });
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

        alert(`Successfully added ${features.length} points from CSV to the map.`);
      };

      reader.readAsText(file);
    });
  }
}