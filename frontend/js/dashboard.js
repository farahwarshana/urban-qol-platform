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
      { type: "file", id: "geoJsonInput", label: "Upload boundary data (GeoJSON)" },
      { type: "text", id: "populationField", label: "Population field name", placeholder: "e.g. population, pop" }
    ],
  },
  "public-transport": {
    title: "Public Transport Coverage",
    desc: "Analyze coverage of public transport stations.",
    inputs: [
      { type: "file", id: "geoJsonInput", label: "Upload raster (GeoTIFF)" },
    ],
  },
  "facility_Accessibility_index": {
    title: "Service Area Analysis",
    desc: "Compute walkable service areas around facilities.",
  inputs: [
      {
      type: "file",
      id: "facilitiesGeojsonInput",
      label: "Upload facilities layer (GeoJSON)"
      }
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
  const inputs = {
    fileName: file.name,
    satelliteLabel: satelliteSelect ? satelliteSelect.options[satelliteSelect.selectedIndex].text : satelliteType,
  };

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
    resultLayer = await renderGeoRasterFromArrayBuffer(arrayBuffer, {
      opacity: 0.9,
      resolution: 256,
    });
    
    
    // Render results panel with NDVI stats
    renderNDVIResults({
      min: ndviMin,
      max: ndviMax,
      mean: ndviMean,
      valid_pixels: validPixels,
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

  if (!latFieldValue || !lonFieldValue) {
    alert("Please enter the latitude and longitude column names.");
    return;
  }

  const csvFile = csvInput.files[0];
  const geoJsonFile = geoJsonInput.files[0];
  const inputs = {
    csvFileName: csvFile.name,
    geoJsonFileName: geoJsonFile.name,
    latField: latFieldValue,
    lonField: lonFieldValue,
  };

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
    }, inputs);

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
    const url = `http://localhost:8000/calculate-urban-density?population_field=${encodeURIComponent(populationFieldValue)}`;
    
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

    // Render the urban density result on the map as GeoJSON
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
        const info = `
          <strong>Area:</strong> ${props.NBHD_NAME || props.name || 'Unknown'}<br>
          <strong>Population:</strong> ${props[populationFieldValue] || 0}<br>
          <strong>Area:</strong> ${props.area_km2?.toFixed(2) || 0} km²<br>
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
    }, inputs);

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
  const input = document.getElementById("facilitiesGeojsonInput");

  if (!input || !input.files[0]) {
    alert("Please upload facilities GeoJSON first.");
    return;
  }

  const formData = new FormData();
  formData.append("facilities_geojson", input.files[0]);

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Facility Accessibility — Processing</h3>
      <p class="panel-desc">Calculating 5, 10, and 15 minute walking service areas...</p>
      <div class="text-center my-4">
        <div class="spinner-border text-primary"></div>
      </div>
    </div>
  `;

  try {
    const response = await fetch("http://localhost:8000/calculate-facility-accessibility", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Facility Accessibility failed");
    }

    const geojson = await response.json();

    if (resultLayer) {
      map.removeLayer(resultLayer);
    }

    resultLayer = L.geoJSON(geojson, {
      style: function (feature) {
        const time = feature.properties.time_min;

        if (time === 5) {
          return {
            color: "#198754",
            weight: 2,
            fillColor: "#198754",
            fillOpacity: 0.35
          };
        }

        if (time === 10) {
          return {
            color: "#ffc107",
            weight: 2,
            fillColor: "#ffc107",
            fillOpacity: 0.28
          };
        }

        return {
          color: "#dc3545",
          weight: 2,
          fillColor: "#dc3545",
          fillOpacity: 0.22
        };
      },

      onEachFeature: function (feature, layer) {
        const props = feature.properties || {};

        layer.bindPopup(`
          <div style="min-width:180px">
            <b>Facility Accessibility</b><br>
            <hr style="margin:6px 0">
            <b>Facility ID:</b> ${props.facility_id ?? "N/A"}<br>
            <b>Walking Time:</b> ${props.time_min ?? "N/A"} min<br>
            <b>Distance:</b> ${props.distance_m ?? "N/A"} m
          </div>
        `);
      }
    }).addTo(map);

    if (resultLayer.getBounds && resultLayer.getBounds().isValid()) {
      map.fitBounds(resultLayer.getBounds());
    }

    renderResults({
      title: "Facility Accessibility",
      desc: "Walkable service areas calculated successfully."
    });

  } catch (error) {
    console.error(error);

    analysisPanel.innerHTML = `
      <div class="fade-in">
        <h3 class="panel-title">Error</h3>
        <p class="text-danger">${error.message}</p>
        <button class="btn btn-ghost"
                onclick="renderServicePanel('facility_Accessibility_index')">
          ← Back
        </button>
      </div>
    `;
  }
}
/* ---------- Render Crime Results with stats ---------- */
function renderCrimeResults(stats, inputs) {
  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">Crime data (CSV)</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.csvFileName}</div>
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
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Crime Density — Results</h3>
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
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
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

  wireTabSwitching();
}


/* ---------- Render Urban Density Results with stats ---------- */
function renderUrbanDensityResults(stats, inputs) {
  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">Boundary data (GeoJSON)</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.geoJsonFileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Population field</div>
      <div class="value">${inputs.populationField}</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">Urban Density — Results</h3>
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
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
        <div class="insight-card">
          <div class="label">Total Population</div>
          <div class="value">${stats.total_population || "N/A"}</div>
        </div>
        <div class="insight-card">
          <div class="label">Total Area</div>
          <div class="value">${stats.total_area || "N/A"} km²</div>
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
          <li>Urban density = population per km²</li>
          <li>Areas are automatically calculated from polygon geometries</li>
          <li>Higher values indicate more densely populated areas</li>
          <li>Layer displayed with blue color gradient on map</li>
        </ul>
      </div>

      <div class="tab-content" id="tab-grid">
        <p class="text-muted">Grid analysis of urban density values.</p>
        <div class="insight-card">
          <div class="label">High density areas</div>
          <div class="value">${((parseFloat(stats.max_density) || 0) > 1000 ? "Yes" : "Limited")}</div>
        </div>
        <div class="insight-card">
          <div class="label">Urbanization level</div>
          <div class="value">${(parseFloat(stats.avg_density) || 0) < 100 ? "Low" : (parseFloat(stats.avg_density) || 0) < 500 ? "Medium" : "High"}</div>
        </div>
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
  const inputsHtml = inputs ? `
    <div class="insight-card">
      <div class="label">GeoTIFF file</div>
      <div class="value" style="font-size:11px;word-break:break-all;">${inputs.fileName}</div>
    </div>
    <div class="insight-card">
      <div class="label">Satellite type</div>
      <div class="value">${inputs.satelliteLabel}</div>
    </div>
  ` : `<p class="text-muted">No input info available.</p>`;

  analysisPanel.innerHTML = `
    <div class="fade-in">
      <h3 class="panel-title">NDVI — Results</h3>
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
        ${inputsHtml}
      </div>

      <div class="tab-content active" id="tab-full">
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
    tab.addEventListener("click", function () {
      const target = tab.getAttribute("data-tab");
      analysisPanel.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      analysisPanel.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      tab.classList.add("active");
      analysisPanel.querySelector("#tab-" + target).classList.add("active");

      if (target === "raw") {
        if (resultLayer && map.hasLayer(resultLayer)) map.removeLayer(resultLayer);
        if (inputLayer && !map.hasLayer(inputLayer)) {
          try {
            inputLayer.addTo(map);
            const b = inputLayer.getBounds ? inputLayer.getBounds() : null;
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch (e) { console.warn("Could not restore input layer:", e); }
        }
      } else if (target === "full") {
        if (inputLayer && map.hasLayer(inputLayer)) map.removeLayer(inputLayer);
        if (resultLayer && !map.hasLayer(resultLayer)) {
          try {
            resultLayer.addTo(map);
            const b = resultLayer.getBounds ? resultLayer.getBounds() : null;
            if (b && b.isValid()) map.fitBounds(b, { padding: [50, 50] });
          } catch (e) { console.warn("Could not restore result layer:", e); }
        }
      }
    });
  });
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

let inputLayer = null;  // pre-analysis layer — shown when Raw Data tab is active
let resultLayer = null; // analysis result layer — shown when Full Area tab is active

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
    mapContainer.querySelectorAll('canvas').forEach(function(sourceCanvas) {
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
    if (svgElement) {
      drawSvgOntoCanvas(svgElement, mapContainer, ctx, mapWidth, mapHeight, function() {
        // ── Layer 4: Marker icons ───────────────────────────────────────────
        drawMarkersOntoCanvas(mapContainer, ctx, function() {
          ctx.restore();
          callback(exportCanvas);
        });
      });
    } else {
      drawMarkersOntoCanvas(mapContainer, ctx, function() {
        ctx.restore();
        callback(exportCanvas);
      });
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