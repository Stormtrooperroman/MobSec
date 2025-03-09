<template>
    <div class="permission-report">
      <div v-if="!hasResults" class="module-empty">
        <div class="empty-icon">🔒</div>
        <h3>Permissions Analysis</h3>
        <p>No permission data available for this APK.</p>
      </div>
  
      <div v-else class="permission-results">
        <div class="module-header">
          <h3 class="module-title">Android Permissions Analysis</h3>
          
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-header">
                <h4>Total Permissions</h4>
                <div class="badge badge-info">{{ metrics.total_permissions }}</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-header">
                <h4>Dangerous Permissions</h4>
                <div :class="['badge', dangerousPermissionsBadgeClass]">
                  {{ metrics.dangerous_permissions }}
                </div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-header">
                <h4>Custom Permissions</h4>
                <div class="badge badge-primary">{{ metrics.custom_permissions }}</div>
              </div>
            </div>
          </div>
  
          <div class="analysis-grid">
            <div class="analysis-card">
              <div class="card-header">
                <h5>Dangerous Permissions</h5>
                <div :class="['badge', dangerousPermissionsBadgeClass]">
                  {{ dangerousPermissions.length }} Found
                </div>
              </div>
              <div class="card-content">
                <div v-if="dangerousPermissions.length" class="permission-list">
                  <div v-for="perm in dangerousPermissions" 
                       :key="perm" 
                       class="permission-item dangerous">
                    <div class="permission-name">{{ formatPermissionName(perm) }}</div>
                    <div class="permission-description">{{ getPermissionDescription(perm) }}</div>
                  </div>
                </div>
                <p v-else class="no-items">No dangerous permissions detected</p>
              </div>
            </div>
  
            <div class="analysis-card">
              <div class="card-header">
                <h5>Custom Permissions</h5>
                <div class="badge badge-primary">{{ customPermissions.length }} Found</div>
              </div>
              <div class="card-content">
                <div v-if="customPermissions.length" class="permission-list">
                  <div v-for="perm in customPermissions" 
                       :key="perm" 
                       class="permission-item custom">
                    {{ perm }}
                  </div>
                </div>
                <p v-else class="no-items">No custom permissions defined</p>
              </div>
            </div>
  
            <div class="analysis-card">
              <div class="card-header">
                <h5>Other Permissions</h5>
                <div class="badge badge-info">{{ otherPermissions.length }} Found</div>
              </div>
              <div class="card-content">
                <div v-if="otherPermissions.length" class="permission-list">
                  <div v-for="perm in otherPermissions" 
                       :key="perm" 
                       class="permission-item normal">
                    <div class="permission-name">{{ formatPermissionName(perm) }}</div>
                    <div class="permission-description">{{ getPermissionDescription(perm) }}</div>
                  </div>
                </div>
                <p v-else class="no-items">No other permissions found</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'PermissionReport',
    props: {
      moduleData: {
        type: Object,
        required: true
      }
    },
    computed: {
      hasResults() {
        return this.moduleData?.results?.summary !== undefined;
      },
      metrics() {
        return this.moduleData?.results?.summary?.metrics || {
          total_permissions: 0,
          dangerous_permissions: 0,
          custom_permissions: 0
        };
      },
      components() {
        return this.moduleData?.results?.summary?.components || {
          activities: [],
          services: [],
          receivers: [],
          providers: []
        };
      },
      dangerousPermissions() {
        return this.moduleData?.results?.summary?.permissions?.dangerous || [];
      },
      customPermissions() {
        return this.moduleData?.results?.summary?.permissions?.custom || [];
      },
      otherPermissions() {
        const allPerms = this.moduleData?.results?.summary?.permissions?.all || [];
        const dangerousPerms = new Set(this.dangerousPermissions);
        const customPerms = new Set(this.customPermissions);
        
        return allPerms.filter(perm => 
          !dangerousPerms.has(perm) && 
          !customPerms.has(perm) &&
          perm.startsWith('android.permission.')
        );
      },
      dangerousPermissionsBadgeClass() {
        return this.dangerousPermissions.length > 0 ? 'badge-warning' : 'badge-success';
      }
    },
    methods: {
      formatPermissionName(permission) {
        return permission.replace('android.permission.', '').replace(/_/g, ' ');
      },
      formatComponentName(component) {
        const parts = component.split('.');
        return parts[parts.length - 1];
      },
      getPermissionDescription(permission) {
        const descriptions = {
          'android.permission.READ_CONTACTS': 'Allows reading user\'s contacts data',
          'android.permission.CAMERA': 'Allows access to the camera device',
          'android.permission.ACCESS_FINE_LOCATION': 'Allows access to precise location',
          'android.permission.READ_EXTERNAL_STORAGE': 'Allows reading from external storage',
          'android.permission.WRITE_EXTERNAL_STORAGE': 'Allows writing to external storage',
          'android.permission.INTERNET': 'Allows the app to create network sockets and use custom network protocols',
          'android.permission.ACCESS_NETWORK_STATE': 'Allows the app to view information about network connections',
          'android.permission.WAKE_LOCK': 'Allows the app to prevent the phone from going to sleep',
          'android.permission.VIBRATE': 'Allows the app to control the vibrator',
          'android.permission.RECEIVE_BOOT_COMPLETED': 'Allows the app to start at system boot',
          // Add more permission descriptions as needed
        };
        return descriptions[permission] || 'Standard Android permission';
      }
    }
  };
  </script>
  
  <style scoped>
  .permission-report {
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
  
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 20px;
  }
  
  .stat-card {
    background: white;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  }
  
  .stat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .stat-header h4 {
    margin: 0;
    font-size: 1rem;
    color: #495057;
  }
  
  .analysis-grid {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }
  
  .analysis-card {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    width: 100%;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px;
    border-bottom: 1px solid #e9ecef;
  }
  
  .card-header h5 {
    margin: 0;
    font-size: 1.1rem;
    color: #2c3e50;
  }
  
  .card-content {
    padding: 15px;
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
  
  .badge-primary {
    background-color: #007bff;
    color: white;
  }
  
  .permission-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  
  .permission-item {
    padding: 10px;
    border-radius: 6px;
    background-color: #f8f9fa;
  }
  
  .permission-item.dangerous {
    border-left: 4px solid #ffc107;
  }
  
  .permission-item.custom {
    border-left: 4px solid #007bff;
  }
  
  .permission-item.normal {
    border-left: 4px solid #17a2b8;  /* Same color as badge-info */
  }
  
  .permission-name {
    font-weight: 600;
    margin-bottom: 4px;
  }
  
  .permission-description {
    font-size: 0.9rem;
    color: #666;
  }
  
  .components-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 15px;
  }
  
  .component-type h6 {
    margin: 0 0 10px 0;
    color: #495057;
  }
  
  .component-count {
    font-size: 1.5rem;
    font-weight: 600;
    color: #2c3e50;
    margin-bottom: 10px;
  }
  
  .component-list {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  
  .component-item {
    font-size: 0.9rem;
    padding: 5px 10px;
    background-color: #f8f9fa;
    border-radius: 4px;
  }
  
  .more-items {
    font-size: 0.9rem;
    color: #666;
    font-style: italic;
    margin-top: 5px;
  }
  
  .no-items {
    color: #666;
    font-style: italic;
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
    .stats-grid,
    .components-grid {
      grid-template-columns: 1fr;
    }
  }
  </style>