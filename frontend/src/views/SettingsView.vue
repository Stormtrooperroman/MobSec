<template>
  <div class="settings-container">
    <h1>Settings</h1>

    <div class="card">
      <h2>Auto-Run Settings</h2>
      <p>Configure which module or chain will automatically run when specific file types are uploaded.</p>

      <form @submit.prevent="saveSettings" class="settings-form">
        <div class="settings-section">
          <h3>APK Files</h3>
          <div class="setting-row">
            <div class="setting-type">
              <label>
                <input type="radio" v-model="formData.apkActionType" value="" @change="updateApkSettings" /> None
              </label>
              <label>
                <input type="radio" v-model="formData.apkActionType" value="module" @change="updateApkSettings" />
                Module
              </label>
              <label>
                <input type="radio" v-model="formData.apkActionType" value="chain" @change="updateApkSettings" /> Chain
              </label>
            </div>

            <div class="setting-action" v-if="formData.apkActionType === 'module'">
              <label>Select Module:</label>
              <select v-model="formData.apkAction">
                <option value="">Select a module</option>
                <option v-for="module in modules" :key="module.id" :value="module.id">
                  {{ module.name }}
                </option>
              </select>
            </div>

            <div class="setting-action" v-if="formData.apkActionType === 'chain'">
              <label>Select Chain:</label>
              <select v-model="formData.apkAction">
                <option :value="null">Select a chain</option>
                <option v-for="chain in chains" :key="chain.id" :value="chain.name">
                  {{ chain.name }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <h3>IPA Files</h3>
          <div class="setting-row">
            <div class="setting-type">
              <label>
                <input type="radio" v-model="formData.ipaActionType" value="" @change="updateIpaSettings" /> None
              </label>
              <label>
                <input type="radio" v-model="formData.ipaActionType" value="module" @change="updateIpaSettings" />
                Module
              </label>
              <label>
                <input type="radio" v-model="formData.ipaActionType" value="chain" @change="updateIpaSettings" /> Chain
              </label>
            </div>

            <div class="setting-action" v-if="formData.ipaActionType === 'module'">
              <label>Select Module:</label>
              <select v-model="formData.ipaAction">
                <option value="">Select a module</option>
                <option v-for="module in modules" :key="module.id" :value="module.id">
                  {{ module.name }}
                </option>
              </select>
            </div>

            <div class="setting-action" v-if="formData.ipaActionType === 'chain'">
              <label>Select Chain:</label>
              <select v-model="formData.ipaAction">
                <option :value="null">Select a chain</option>
                <option v-for="chain in chains" :key="chain.id" :value="chain.name">
                  {{ chain.name }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <div class="settings-section">
          <h3>ZIP Files</h3>
          <div class="setting-row">
            <div class="setting-type">
              <label>
                <input type="radio" v-model="formData.zipActionType" value="" @change="updateZipSettings" /> None
              </label>
              <label>
                <input type="radio" v-model="formData.zipActionType" value="module" @change="updateZipSettings" />
                Module
              </label>
              <label>
                <input type="radio" v-model="formData.zipActionType" value="chain" @change="updateZipSettings" /> Chain
              </label>
            </div>

            <div class="setting-action" v-if="formData.zipActionType === 'module'">
              <label>Select Module:</label>
              <select v-model="formData.zipAction">
                <option value="">Select a module</option>
                <option v-for="module in modules" :key="module.id" :value="module.id">
                  {{ module.name }}
                </option>
              </select>
            </div>

            <div class="setting-action" v-if="formData.zipActionType === 'chain'">
              <label>Select Chain:</label>
              <select v-model="formData.zipAction">
                <option :value="null">Select a chain</option>
                <option v-for="chain in chains" :key="chain.id" :value="chain.name">
                  {{ chain.name }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <div class="save-section">
          <button type="submit" class="save-btn" :disabled="saving">
            {{ saving ? 'Saving...' : 'Save Settings' }}
          </button>
          <div class="status-message" v-if="statusMessage">
            <span :class="{ success: !isError, error: isError }">
              {{ statusMessage }}
            </span>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'SettingsView',
  data() {
    return {
      modules: [],
      chains: [],
      saving: false,
      statusMessage: '',
      isError: false,

      formData: {
        apkAction: null,
        apkActionType: '',
        ipaAction: null,
        ipaActionType: '',
        zipAction: null,
        zipActionType: '',
      },
    };
  },
  created() {
    this.fetchModules();
    this.fetchChains();
    this.fetchSettings();
  },
  methods: {
    async fetchModules() {
      try {
        const response = await axios.get('/api/v1/modules/');
        this.modules = response.data;
      } catch (error) {
        this.showError('Error fetching modules');
      }
    },
    async fetchChains() {
      try {
        const response = await axios.get('/api/v1/chains/');
        this.chains = response.data;
      } catch (error) {
        this.showError('Error fetching chains');
      }
    },
    async fetchSettings() {
      try {
        const response = await axios.get('/api/v1/settings/auto-run');

        this.formData = {
          apkAction: response.data.apk_action || null,
          apkActionType: response.data.apk_action_type || '',
          ipaAction: response.data.ipa_action || null,
          ipaActionType: response.data.ipa_action_type || '',
          zipAction: response.data.zip_action || null,
          zipActionType: response.data.zip_action_type || '',
        };
      } catch (error) {
        this.showError('Error fetching settings');
      }
    },
    validateSettings() {
      const errors = [];

      if (this.formData.apkActionType && !this.formData.apkAction) {
        errors.push('Please select an APK action');
      }

      if (this.formData.ipaActionType && !this.formData.ipaAction) {
        errors.push('Please select an IPA action');
      }

      if (this.formData.zipActionType && !this.formData.zipAction) {
        errors.push('Please select a ZIP action');
      }

      return errors;
    },
    prepareSettingsData() {
      return {
        zip_action: this.formData.zipActionType && this.formData.zipAction ? this.formData.zipAction : null,
        zip_action_type: this.formData.zipActionType && this.formData.zipAction ? this.formData.zipActionType : null,

        apk_action: this.formData.apkActionType && this.formData.apkAction ? this.formData.apkAction : null,
        apk_action_type: this.formData.apkActionType && this.formData.apkAction ? this.formData.apkActionType : null,

        ipa_action: this.formData.ipaActionType && this.formData.ipaAction ? this.formData.ipaAction : null,
        ipa_action_type: this.formData.ipaActionType && this.formData.ipaAction ? this.formData.ipaActionType : null,
      };
    },
    updateApkSettings() {
      if (this.formData.apkActionType === '') {
        this.formData.apkAction = null;
      } else {
        this.formData.apkAction = null;
      }
    },
    updateIpaSettings() {
      if (this.formData.ipaActionType === '') {
        this.formData.ipaAction = null;
      } else {
        this.formData.ipaAction = null;
      }
    },
    updateZipSettings() {
      if (this.formData.zipActionType === '') {
        this.formData.zipAction = null;
      } else {
        this.formData.zipAction = null;
      }
    },
    showSuccess(message) {
      this.statusMessage = message;
      this.isError = false;
      setTimeout(() => {
        this.statusMessage = '';
      }, 3000);
    },
    showError(message) {
      this.statusMessage = message;
      this.isError = true;
      setTimeout(() => {
        this.statusMessage = '';
      }, 5000);
    },
    async saveSettings() {
      if (this.saving) return;

      const errors = this.validateSettings();
      if (errors.length > 0) {
        this.showError(errors.join(', '));
        return;
      }

      this.saving = true;
      try {
        const settings = this.prepareSettingsData();
        await axios.post('/api/v1/settings/auto-run', settings);
        this.showSuccess('Settings saved successfully!');
      } catch (error) {
        this.showError('Error saving settings. Please try again.');
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<style scoped>
.settings-container {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.settings-section {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid #eee;
  border-radius: 4px;
}

.setting-row {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.setting-type {
  display: flex;
  gap: 16px;
}

.setting-action {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

select {
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #ddd;
  width: 100%;
  max-width: 300px;
}

.save-section {
  margin-top: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.save-btn {
  padding: 8px 16px;
  background-color: #4caf50;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.save-btn:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.status-message {
  font-weight: 500;
}

.success {
  color: #4caf50;
}

.error {
  color: #f44336;
}
</style>
