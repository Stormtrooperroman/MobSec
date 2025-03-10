<template>
    <div class="permission-report">
      <div v-if="!hasResults" class="module-empty">
        <div class="empty-icon">🔒</div>
        <h3>Permissions Analysis</h3>
        <p>{{ getStatusMessage }}</p>
      </div>
  
      <div v-else class="permission-results">
        <div class="module-header">
          <h3 class="module-title">Android Permissions Analysis</h3>
          
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-header">
                <h4>Total Permissions</h4>
                <div class="badge badge-info">{{ totalPermissions }}</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-header">
                <h4>Dangerous Permissions</h4>
                <div :class="['badge', dangerousPermissionsBadgeClass]">
                  {{ dangerousPermissions.length }}
                </div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-header">
                <h4>Custom Permissions</h4>
                <div class="badge badge-primary">{{ customPermissions.length }}</div>
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
                <h5>Requested Permissions</h5>
                <div class="badge badge-info">{{ requestedPermissions.length }} Found</div>
              </div>
              <div class="card-content">
                <div v-if="requestedPermissions.length" class="permission-list">
                  <div v-for="perm in requestedPermissions" 
                       :key="perm" 
                       class="permission-item normal">
                    <div class="permission-name">{{ formatPermissionName(perm) }}</div>
                    <div class="permission-description">{{ getPermissionDescription(perm) }}</div>
                  </div>
                </div>
                <p v-else class="no-items">No requested permissions found</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'PermissionsReport',
    props: {
      moduleData: {
        type: Object,
        required: true
      }
    },
    computed: {
      hasResults() {
        return !!this.moduleData?.results;
      },
      getStatusMessage() {
        if (!this.moduleData) {
          return "Permission analysis not yet started";
        }
        if (!this.moduleData?.results) {
          return "No permission data available for this APK";
        }
        return "";
      },
      permissionResults() {
        return this.moduleData?.results || {};
      },
      totalPermissions() {
        return this.permissionResults?.requested?.length || 0;
      },
      dangerousPermissions() {
        return this.permissionResults?.dangerous || [];
      },
      customPermissions() {
        return this.permissionResults?.custom || [];
      },
      requestedPermissions() {
        return this.permissionResults?.requested || [];
      },
      dangerousPermissionsBadgeClass() {
        return this.dangerousPermissions.length > 0 ? 'badge-warning' : 'badge-success';
      }
    },
    methods: {
      formatPermissionName(permission) {
        return permission.replace('android.permission.', '').replace(/_/g, ' ');
      },
      getPermissionDescription(permission) {
        const descriptions = {
          'android.permission.READ_CALENDAR': 'Allows reading calendar events and details',
          'android.permission.WRITE_CALENDAR': 'Allows adding/modifying calendar events',
          'android.permission.CAMERA': 'Allows access to the camera device',
          'android.permission.READ_CONTACTS': 'Allows reading user\'s contacts data',
          'android.permission.WRITE_CONTACTS': 'Allows modifying user\'s contacts data',
          'android.permission.GET_ACCOUNTS': 'Allows access to the list of accounts',
          'android.permission.ACCESS_FINE_LOCATION': 'Allows access to precise location',
          'android.permission.ACCESS_COARSE_LOCATION': 'Allows access to approximate location',
          'android.permission.RECORD_AUDIO': 'Allows recording audio',
          'android.permission.READ_PHONE_STATE': 'Allows read only access to phone state',
          'android.permission.READ_PHONE_NUMBERS': 'Allows reading phone numbers',
          'android.permission.CALL_PHONE': 'Allows making phone calls',
          'android.permission.ANSWER_PHONE_CALLS': 'Allows answering incoming calls',
          'android.permission.READ_CALL_LOG': 'Allows reading call log',
          'android.permission.WRITE_CALL_LOG': 'Allows writing call log',
          'android.permission.ADD_VOICEMAIL': 'Allows adding voicemails',
          'android.permission.USE_SIP': 'Allows using SIP service',
          'android.permission.BODY_SENSORS': 'Allows access to body sensors',
          'android.permission.SEND_SMS': 'Allows sending SMS messages',
          'android.permission.RECEIVE_SMS': 'Allows receiving SMS messages',
          'android.permission.READ_SMS': 'Allows reading SMS messages',
          'android.permission.RECEIVE_WAP_PUSH': 'Allows receiving WAP push messages',
          'android.permission.RECEIVE_MMS': 'Allows receiving MMS messages',
          'android.permission.READ_EXTERNAL_STORAGE': 'Allows reading from external storage',
          'android.permission.WRITE_EXTERNAL_STORAGE': 'Allows writing to external storage',
          'android.permission.USE_BIOMETRIC': 'Allows using biometric hardware',
          'android.permission.USE_FINGERPRINT': 'Allows using fingerprint hardware',
          'android.permission.NFC': 'Allows using NFC hardware',
          'android.permission.INTERNET': 'Allows internet access',
          'android.permission.ACCESS_NETWORK_STATE': 'Allows checking network connectivity',
          'android.permission.ACCESS_WIFI_STATE': 'Allows checking WiFi status',
          'android.permission.WAKE_LOCK': 'Allows keeping device awake',
          'android.permission.RECEIVE_BOOT_COMPLETED': 'Allows starting at boot',
          'android.permission.FOREGROUND_SERVICE': 'Allows running foreground services',
          'android.permission.POST_NOTIFICATIONS': 'Allows posting notifications',
          'android.permission.VIBRATE': 'Allows using device vibration',
          'android.permission.REQUEST_INSTALL_PACKAGES': 'Allows requesting package installation'
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