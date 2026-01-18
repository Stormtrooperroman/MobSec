<template>
  <div class="call-graph-report">
    <div v-if="!hasResults" class="module-empty">
      <div class="empty-icon">📊</div>
      <h3>Call Graph Analysis</h3>
      <p>No call graph data available for this APK.</p>
    </div>

    <div v-else class="call-graph-results">
      <div class="module-header">
        <div class="header-section">
          <h3 class="module-title">Call Graph Analysis</h3>
        </div>
        
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-header">
              <h4>Total Methods</h4>
              <div class="badge badge-info">{{ stats.total_methods }}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <h4>Entry Points</h4>
              <div class="badge badge-warning">{{ stats.entry_points }}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <h4>Main Activities</h4>
              <div class="badge badge-success">{{ stats.main_activities_found || 0 }}</div>
            </div>
            <div v-if="stats.main_activity_names && stats.main_activity_names.length > 0" class="stat-details">
              <small>{{ stats.main_activity_names.join(', ') }}</small>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-header">
              <h4>External Calls</h4>
              <div class="badge badge-primary">{{ stats.external_calls }}</div>
            </div>
          </div>
        </div>

        <!-- Graph container -->
        <div class="graph-wrapper">
          <div class="graph-container" 
             ref="graphContainer"
             @mousedown="startPan"
             @mousemove="onDrag"
             @mouseup="endDrag"
             @mouseleave="endDrag">
          <svg width="100%" height="600">
            <!-- Add transform to the graph group with zoom and pan -->
            <g class="graph" :transform="`translate(${panX},${panY}) scale(${zoom})`">
              <!-- Draw edges -->
              <g class="edges">
                <line v-for="(edge, index) in processedEdges" 
                      :key="'edge-' + index"
                      :x1="edge.source.x"
                      :y1="edge.source.y"
                      :x2="edge.target.x"
                      :y2="edge.target.y"
                      stroke="#999"
                      stroke-width="1"
                      marker-end="url(#arrowhead)" />
              </g>
              
              <!-- Draw nodes -->
              <g class="nodes">
                <g v-for="node in processedNodes" 
                   :key="node.id" 
                   :transform="`translate(${node.x},${node.y})`"
                   @mousedown="startDrag(node, $event)"
                   class="node">
                  <circle 
                    :r="getNodeRadius(node)"
                    :fill="getNodeColor(node)"
                    :stroke="getNodeStroke(node)"
                    :stroke-width="getNodeStrokeWidth(node)" />
                  <title>{{ node.class }}->{{ node.method }}{{ node.descriptor }}</title>
                  <text 
                    dx="12" 
                    dy="4" 
                    font-size="10"
                    fill="#333">{{ formatMethodName(node.method) }}</text>
                  <text 
                    dx="12" 
                    dy="16" 
                    font-size="8"
                    fill="#666">{{ formatClassName(node.class) }}</text>
                </g>
              </g>
            </g>
            
            <!-- Arrow marker definition -->
            <defs>
              <marker id="arrowhead" 
                     viewBox="-0 -5 10 10" 
                     refX="8" 
                     refY="0" 
                     orient="auto" 
                     markerWidth="6" 
                     markerHeight="6">
                <path d="M 0,-5 L 10,0 L 0,5" fill="#999"/>
              </marker>
            </defs>
          </svg>
        </div>
        </div>

        <!-- Update the graph-controls section -->
        <div class="graph-controls">
          <div class="zoom-controls">
            <button @click="zoomIn" class="control-btn" title="Zoom In">
              <span class="zoom-icon">🔍+</span>
            </button>
            <button @click="zoomOut" class="control-btn" title="Zoom Out">
              <span class="zoom-icon">🔍-</span>
            </button>
            <button @click="resetZoom" class="control-btn" title="Reset View">
              <span class="zoom-icon">↺</span>
            </button>
          </div>
          
          <!-- Legend is already implemented but let's make it more visible -->
          <div class="graph-legend">
            <div class="legend-item">
              <span class="legend-color" style="background: #ff5722"></span>
              <span class="legend-label">Main Activity</span>
            </div>
            <div class="legend-item">
              <span class="legend-color" style="background: #ffc107"></span>
              <span class="legend-label">Entry Points</span>
            </div>
            <div class="legend-item">
              <span class="legend-color" style="background: #2196f3"></span>
              <span class="legend-label">External Methods</span>
            </div>
            <div class="legend-item">
              <span class="legend-color" style="background: #9c27b0"></span>
              <span class="legend-label">Native Methods</span>
            </div>
            <div class="legend-item">
              <span class="legend-color" style="background: #4caf50"></span>
              <span class="legend-label">Regular Methods</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'CallGraphReport',
  props: {
    moduleData: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      processedNodes: [],
      processedEdges: [],
      dragging: null,
      width: 800,
      height: 600,
      zoom: 1,
      panX: 0,
      panY: 0,
      isPanning: false,
      lastX: 0,
      lastY: 0
    }
  },
  computed: {
    hasResults() {
      return this.moduleData?.results !== undefined;
    },
    nodes() {
      return this.moduleData?.results?.nodes || [];
    },
    edges() {
      return this.moduleData?.results?.edges || [];
    },
    stats() {
      const baseStats = this.moduleData?.results?.stats || {
        total_methods: 0,
        entry_points: 0,
        external_calls: 0
      };
      
      // Add MainActivity info
      const mainActivities = this.findMainActivity();
      return {
        ...baseStats,
        main_activities_found: mainActivities.length,
        main_activity_names: mainActivities.map(node => this.formatClassName(node.class))
      };
    }
  },
  mounted() {
    if (this.hasResults) {
      this.initGraph();
      this.$refs.graphContainer?.addEventListener('wheel', this.handleWheel);
    }
  },
  beforeUnmount() {
    this.$refs.graphContainer?.removeEventListener('wheel', this.handleWheel);
  },
  methods: {
    initGraph() {
      const container = this.$refs.graphContainer;
      if (!container) return;

      this.width = container.clientWidth;
      this.height = container.clientHeight;

      // Create tree layout
      this.processedNodes = this.createTreeLayout();

      this.updateEdges();
    },
    createTreeLayout() {
      // Build adjacency list
      const adjacencyList = {};
      const nodeMap = {};
      
      // Create node map for quick lookup
      this.nodes.forEach(node => {
        nodeMap[node.id_hash] = node;
        adjacencyList[node.id_hash] = [];
      });
      
      // Build adjacency list from edges
      this.edges.forEach(edge => {
        if (adjacencyList[edge.from_hash]) {
          adjacencyList[edge.from_hash].push(edge.to_hash);
        }
      });
      
      // Find MainActivity or similar main entry points
      let entryPoints = this.findMainActivity();
      
      // If no MainActivity found, use other entry points
      if (entryPoints.length === 0) {
        entryPoints = this.nodes.filter(node => 
          node.is_entry_point || node.depth === 0
        );
      }
      
      // If still no entry points found, use first few nodes
      if (entryPoints.length === 0) {
        entryPoints.push(...this.nodes.slice(0, Math.min(5, this.nodes.length)));
      }
      
      // Layout parameters
      const levelHeight = 120;
      const nodeSpacing = 200;
      const startY = 50;
      const centerX = this.width / 2;
      
      // Track visited nodes and their positions
      const visited = new Set();
      const positionedNodes = [];
      
      // Position entry points at the top, centered
      const entryPointCount = entryPoints.length;
      const startX = centerX - ((entryPointCount - 1) * nodeSpacing) / 2;
      
      entryPoints.forEach((entryPoint, index) => {
        if (!visited.has(entryPoint.id_hash)) {
          const node = {
            ...entryPoint,
            x: startX + index * nodeSpacing,
            y: startY
          };
          positionedNodes.push(node);
          visited.add(entryPoint.id_hash);
        }
      });
      
      // BFS to position remaining nodes
      const queue = [...entryPoints];
      let level = 1;
      let nodesInCurrentLevel = entryPoints.length;
      let nodesInNextLevel = 0;
      const levelNodes = [];
      
      while (queue.length > 0) {
        const currentNode = queue.shift();
        nodesInCurrentLevel--;
        
        const children = adjacencyList[currentNode.id_hash] || [];
        children.forEach(childId => {
          if (!visited.has(childId)) {
            const childNode = nodeMap[childId];
            if (childNode) {
              levelNodes.push(childNode);
              visited.add(childId);
              queue.push(childNode);
              nodesInNextLevel++;
            }
          }
        });
        
        if (nodesInCurrentLevel === 0) {
          // Position all nodes in current level
          if (levelNodes.length > 0) {
            const levelStartX = centerX - ((levelNodes.length - 1) * nodeSpacing) / 2;
            levelNodes.forEach((node, index) => {
              const positionedNode = {
                ...node,
                x: levelStartX + index * nodeSpacing,
                y: startY + level * levelHeight
              };
              positionedNodes.push(positionedNode);
            });
            levelNodes.length = 0; // Clear array
          }
          
          level++;
          nodesInCurrentLevel = nodesInNextLevel;
          nodesInNextLevel = 0;
        }
      }
      
      // Position any remaining unvisited nodes
      const remainingNodes = this.nodes.filter(node => !visited.has(node.id_hash));
      if (remainingNodes.length > 0) {
        const remainingStartX = centerX - ((remainingNodes.length - 1) * nodeSpacing) / 2;
        remainingNodes.forEach((node, index) => {
          const positionedNode = {
            ...node,
            x: remainingStartX + index * nodeSpacing,
            y: startY + level * levelHeight
          };
          positionedNodes.push(positionedNode);
        });
      }
      
      return positionedNodes;
    },
    findMainActivity() {
      // Look for MainActivity or similar main entry points
      const mainActivityPatterns = [
        /MainActivity/i,
        /Main/i,
        /Launcher/i,
        /SplashActivity/i,
        /StartActivity/i,
        /HomeActivity/i
      ];
      
      const candidates = [];
      
      // First, look for exact MainActivity matches
      this.nodes.forEach(node => {
        const className = this.formatClassName(node.class);
        const fullClassName = node.class.replace(/^L/, '').replace(/;$/, '').replace(/\//g, '.');
        
        // Check for MainActivity patterns
        for (const pattern of mainActivityPatterns) {
          if (pattern.test(className) || pattern.test(fullClassName)) {
            candidates.push({
              node,
              priority: pattern.source === 'MainActivity' ? 1 : 2,
              match: pattern.source
            });
            break;
          }
        }
      });
      
      // Sort by priority (MainActivity first) and return the best matches
      candidates.sort((a, b) => a.priority - b.priority);
      
      // Return top candidates (up to 3)
      return candidates.slice(0, 3).map(c => c.node);
    },
    updateEdges() {
      // Create edges using node positions
      this.processedEdges = this.edges.map(edge => {
        const source = this.processedNodes.find(n => n.id_hash === edge.from_hash);
        const target = this.processedNodes.find(n => n.id_hash === edge.to_hash);
        return { source, target };
      });
    },
    startDrag(node, event) {
      this.dragging = {
        node,
        offsetX: node.x - (event.clientX - this.panX) / this.zoom,
        offsetY: node.y - (event.clientY - this.panY) / this.zoom
      };
    },
    startPan(event) {
      if (event.target.classList.contains('graph-container') || 
          event.target.tagName === 'svg' ||
          event.target.classList.contains('graph')) {
        this.isPanning = true;
        this.lastX = event.clientX;
        this.lastY = event.clientY;
      }
    },
    onDrag(event) {
      if (this.dragging) {
        this.dragging.node.x = (event.clientX - this.panX) / this.zoom + this.dragging.offsetX;
        this.dragging.node.y = (event.clientY - this.panY) / this.zoom + this.dragging.offsetY;
        this.updateEdges();
      } else if (this.isPanning) {
        const dx = event.clientX - this.lastX;
        const dy = event.clientY - this.lastY;
        this.panX += dx;
        this.panY += dy;
        this.lastX = event.clientX;
        this.lastY = event.clientY;
      }
    },
    endDrag() {
      this.dragging = null;
      this.isPanning = false;
    },
    formatMethodName(name) {
      return name.length > 20 ? name.substring(0, 17) + '...' : name;
    },
    formatClassName(className) {
      // Remove 'L' prefix and ';' suffix, replace '/' with '.'
      let formatted = className.replace(/^L/, '').replace(/;$/, '').replace(/\//g, '.');
      // Get last part of package name
      const parts = formatted.split('.');
      return parts[parts.length - 1] || formatted;
    },
    getNodeColor(node) {
      if (this.isMainActivity(node)) return '#ff5722'; // Orange for MainActivity
      if (node.is_entry_point) return '#ffc107';
      if (node.is_external) return '#2196f3';
      if (node.is_native) return '#9c27b0';
      return '#4caf50';
    },
    getNodeRadius(node) {
      if (this.isMainActivity(node)) return 12; // Larger for MainActivity
      if (node.is_entry_point) return 8;
      return 5;
    },
    getNodeStroke(node) {
      if (this.isMainActivity(node)) return '#d84315'; // Darker orange border
      return '#666';
    },
    getNodeStrokeWidth(node) {
      if (this.isMainActivity(node)) return 2; // Thicker border for MainActivity
      return 1;
    },
    isMainActivity(node) {
      const mainActivityPatterns = [
        /MainActivity/i,
        /Main/i,
        /Launcher/i,
        /SplashActivity/i,
        /StartActivity/i,
        /HomeActivity/i
      ];
      
      const className = this.formatClassName(node.class);
      const fullClassName = node.class.replace(/^L/, '').replace(/;$/, '').replace(/\//g, '.');
      
      return mainActivityPatterns.some(pattern => 
        pattern.test(className) || pattern.test(fullClassName)
      );
    },
    zoomIn() {
      const oldZoom = this.zoom;
      this.zoom = Math.min(4, this.zoom * 1.2);
      
      const container = this.$refs.graphContainer;
      if (container) {
        const rect = container.getBoundingClientRect();
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        
        this.panX = centerX - (centerX - this.panX) * (this.zoom / oldZoom);
        this.panY = centerY - (centerY - this.panY) * (this.zoom / oldZoom);
      }
    },
    zoomOut() {
      const oldZoom = this.zoom;
      this.zoom = Math.max(0.2, this.zoom / 1.2);
      
      // Adjust pan to keep the center point fixed
      const container = this.$refs.graphContainer;
      if (container) {
        const rect = container.getBoundingClientRect();
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        
        this.panX = centerX - (centerX - this.panX) * (this.zoom / oldZoom);
        this.panY = centerY - (centerY - this.panY) * (this.zoom / oldZoom);
      }
    },
    resetZoom() {
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;
    },
    handleWheel(event) {
      if (!event.ctrlKey && !event.metaKey) return;
      
      event.preventDefault();
      
      // Get mouse position relative to container
      const container = this.$refs.graphContainer;
      const rect = container.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;
      
      // Store old zoom for calculations
      const oldZoom = this.zoom;
      
      // Zoom based on wheel direction
      if (event.deltaY > 0) {
        this.zoom = Math.max(0.2, this.zoom / 1.2);
      } else {
        this.zoom = Math.min(4, this.zoom * 1.2);
      }
      
      // Adjust pan to keep the mouse point fixed
      this.panX = mouseX - (mouseX - this.panX) * (this.zoom / oldZoom);
      this.panY = mouseY - (mouseY - this.panY) * (this.zoom / oldZoom);
    }
  }
};
</script>

<style scoped>
.call-graph-report {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: #333;
}

.call-graph-results {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.module-header {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.header-section {
  margin-bottom: 8px;
}

.module-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.5px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-top: 8px;
}

.stat-card {
  padding: 20px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.12);
}

.stat-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #666;
}

.graph-wrapper {
  width: 100%;
  margin-top: 8px;
}

.graph-container {
  width: 100%;
  height: 600px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #f8f9fa;
  overflow: hidden;
  cursor: grab;
  position: relative;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.graph-container:active {
  cursor: grabbing;
}

.node {
  cursor: move;
}

.node:hover {
  cursor: move;
}

.node:active {
  cursor: grabbing;
}

.node text {
  user-select: none;
}

.graph {
  transition: transform 0.05s linear;
}

.graph-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  flex-wrap: wrap;
  gap: 20px;
}

.zoom-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.control-btn {
  padding: 10px 14px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
}

.control-btn:hover {
  background: #f5f5f5;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
  border-color: #ccc;
}

.control-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.zoom-icon {
  font-size: 14px;
  font-weight: bold;
}

.graph-legend {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
  flex: 1;
  justify-content: flex-end;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  background: #f8f9fa;
  transition: background 0.2s ease;
}

.legend-item:hover {
  background: #f0f0f0;
}

.legend-color {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px #ddd;
}

.legend-label {
  font-size: 13px;
  color: #333;
  font-weight: 500;
}

.stat-details {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #eee;
}

.stat-details small {
  color: #666;
  font-size: 11px;
  line-height: 1.5;
  display: block;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .graph-controls {
    flex-direction: column;
    align-items: stretch;
  }
  
  .zoom-controls {
    justify-content: center;
  }
  
  .graph-legend {
    justify-content: center;
  }
}
</style>
