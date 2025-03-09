<template>
    <div class="apkid-report">
      <div v-if="!hasResults" class="module-empty">
        <div class="empty-icon">🕵️</div>
        <h3>APKiD Analysis</h3>
        <p>No results available for this APK.</p>
      </div>
  
      <div v-else class="apkid-results">
        <div class="module-header">
          <h3 class="module-title">APKiD Packers & Obfuscation Analysis</h3>
          
          <div class="findings-section">
            <h4>Detailed Analysis</h4>
            <div class="analysis-grid">
              <div class="analysis-card">
                <div class="card-header">
                  <h5>Anti-VM Detection</h5>
                  <div :class="['badge', hasAntiVM ? 'badge-warning' : 'badge-success']">
                    {{ hasAntiVM ? 'Detected' : 'Not Detected' }}
                  </div>
                </div>
                <div class="card-content">
                  <div v-if="antiVMTechniques.length > 0">
                    <div v-for="(technique, index) in antiVMTechniques" 
                         :key="index" 
                         class="metric-item">
                      {{ technique.name }}
                      <div class="finding-description">{{ technique.metadata.description }}</div>
                    </div>
                  </div>
                  <p v-else>No anti-VM techniques detected</p>
                </div>
              </div>
  
              <div class="analysis-card">
                <div class="card-header">
                  <h5>Anti-Debug Detection</h5>
                  <div :class="['badge', hasAntiDebug ? 'badge-warning' : 'badge-success']">
                    {{ hasAntiDebug ? 'Detected' : 'Not Detected' }}
                  </div>
                </div>
                <div class="card-content">
                  <div v-if="antiDebugTechniques.length > 0">
                    <div v-for="(technique, index) in antiDebugTechniques" 
                         :key="index" 
                         class="metric-item">
                      {{ technique.name }}
                      <div class="finding-description">{{ technique.metadata.description }}</div>
                    </div>
                  </div>
                  <p v-else>No anti-debug techniques detected</p>
                </div>
              </div>
  
              <div class="analysis-card">
                <div class="card-header">
                  <h5>Obfuscation & Packing</h5>
                  <div :class="['badge', hasObfuscation ? 'badge-warning' : 'badge-success']">
                    {{ hasObfuscation ? 'Detected' : 'Not Detected' }}
                  </div>
                </div>
                <div class="card-content">
                  <div v-if="obfuscationTechniques.length > 0">
                    <div v-for="(technique, index) in obfuscationTechniques" 
                         :key="index" 
                         class="metric-item">
                      {{ technique.name }}
                      <div class="finding-description">{{ technique.metadata.description }}</div>
                    </div>
                  </div>
                  <p v-else>No obfuscation techniques detected</p>
                </div>
              </div>
  
              <div class="analysis-card">
                <div class="card-header">
                  <h5>Compiler Information</h5>
                  <div class="badge badge-info">Info</div>
                </div>
                <div class="card-content">
                  <div v-if="compilerFindings.length > 0">
                    <div v-for="(finding, index) in compilerFindings" 
                         :key="index" 
                         class="metric-item">
                      {{ finding.name }}
                      <div class="finding-description">{{ finding.metadata.description }}</div>
                    </div>
                  </div>
                  <p v-else>No compiler information available</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'ApkidReport',
    props: {
      moduleData: {
        type: Object,
        required: true
      }
    },
    computed: {
      hasResults() {
        return this.moduleData?.results?.findings?.length > 0;
      },
      antiVMTechniques() {
        return this.moduleData?.results?.findings?.filter(f => f.rule_id === 'anti_vm') || [];
      },
      hasAntiVM() {
        return this.antiVMTechniques.length > 0;
      },
      antiDebugTechniques() {
        return this.moduleData?.results?.findings?.filter(f => f.rule_id === 'anti_debug') || [];
      },
      hasAntiDebug() {
        return this.antiDebugTechniques.length > 0;
      },
      obfuscationTechniques() {
        return this.moduleData?.results?.findings?.filter(f => 
          f.rule_id === 'obfuscator' || f.rule_id === 'packer' || f.rule_id === 'protector'
        ) || [];
      },
      hasObfuscation() {
        return this.obfuscationTechniques.length > 0;
      },
      compilerFindings() {
        return this.moduleData?.results?.findings?.filter(f => f.rule_id === 'compiler') || [];
      }
    }
  }
  </script>
  
  <style scoped>
  .apkid-report {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #333;
  }
  
  .module-header {
    background-color: #f4f6f9;
    padding: 20px;
    border-radius: 8px;
  }
  
  .module-title {
    font-size: 1.5rem;
    margin-bottom: 20px;
    color: #2c3e50;
  }
  
  .analysis-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 20px;
    margin-top: 15px;
  }
  
  .analysis-card {
    background-color: white;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 15px;
    background-color: #f8f9fa;
    border-bottom: 1px solid #e9ecef;
  }
  
  .card-header h5 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }
  
  .badge {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
  }
  
  .badge-warning {
    background-color: #ffc107;
    color: #212529;
  }
  
  .badge-success {
    background-color: #28a745;
    color: white;
  }
  
  .badge-info {
    background-color: #17a2b8;
    color: white;
  }
  
  .card-content {
    padding: 15px;
  }
  
  .metric-item {
    margin-bottom: 15px;
    padding: 10px;
    background-color: #f8f9fa;
    border-radius: 6px;
    font-weight: 500;
  }
  
  .finding-description {
    margin-top: 5px;
    font-size: 0.9rem;
    color: #666;
    font-weight: normal;
  }
  
  .module-empty {
    text-align: center;
    padding: 40px;
    color: #6c757d;
  }
  
  .empty-icon {
    font-size: 48px;
    margin-bottom: 16px;
  }
  
  @media (max-width: 768px) {
    .analysis-grid {
      grid-template-columns: 1fr;
    }
  }
  </style>