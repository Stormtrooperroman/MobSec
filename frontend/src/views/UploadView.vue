<template>
  <div class="upload-container">
    <div class="upload-card">
      <div class="upload-header">
        <h1 class="upload-title">App Analysis</h1>
        <p class="upload-subtitle">Upload your application file for security analysis</p>
      </div>
      
      <div class="upload-area" 
           @dragover.prevent 
           @drop.prevent="handleFileDrop"
           :class="{ 'drag-over': isDragging }">
        <div class="upload-icon">📤</div>
        <p class="upload-instructions">
          <span class="highlight">Click to browse</span> or drag & drop your file here
        </p>
        <p class="file-types">Supported formats: APK, IPA, JAR, ZIP</p>
        <input 
          type="file" 
          ref="fileInput" 
          @change="handleFileUpload" 
          class="file-input" 
          accept=".apk,.ipa,.jar,.zip"
        />
      </div>
      
      <div v-if="file" class="selected-file">
        <div class="file-icon">📄</div>
        <div class="file-details">
          <div class="file-name">{{ file.name }}</div>
          <div class="file-size">{{ formatFileSize(file.size) }}</div>
        </div>
        <button @click="removeFile" class="remove-button">✕</button>
      </div>
      
      <button 
        @click="uploadFile" 
        :disabled="isUploading || !file" 
        class="upload-button"
      >
        <span v-if="isUploading">
          <span class="spinner"></span> Uploading...
        </span>
        <span v-else>
          Start Analysis
        </span>
      </button>
      
      <div v-if="error" class="error-container">
        <div class="error-icon">!</div>
        <div class="error-message">{{ error }}</div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      file: null,
      isUploading: false,
      error: null,
      isDragging: false
    };
  },
  methods: {
    handleFileUpload(event) {
      if (event.target.files.length > 0) {
        this.file = event.target.files[0];
        this.error = null;
      }
    },
    handleFileDrop(event) {
      this.isDragging = false;
      
      if (event.dataTransfer.files.length > 0) {
        this.file = event.dataTransfer.files[0];
        this.error = null;
      }
    },
    removeFile() {
      this.file = null;
      // Reset the file input
      this.$refs.fileInput.value = '';
    },
    formatFileSize(bytes) {
      if (bytes === 0) return '0 Bytes';
      
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    openFileDialog() {
      this.$refs.fileInput.click();
    },
    async uploadFile() {
      if (!this.file) {
        this.error = "Please select a file first";
        return;
      }

      const allowedTypes = ['.apk', '.ipa', '.jar', '.zip'];
      const fileExt = '.' + this.file.name.split('.').pop().toLowerCase();
      
      if (!allowedTypes.includes(fileExt)) {
        this.error = "Invalid file type. Please upload APK, IPA, JAR, or ZIP files.";
        return;
      }

      this.isUploading = true;
      this.error = null;
      const formData = new FormData();
      formData.append("file", this.file);

      try {
        const response = await fetch("/api/v1/apps/upload", {
          method: "POST",
          body: formData,
          timeout: 300000
        });

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        await response.json();
        // Redirect to the apps page after successful upload
        this.$router.push({ name: 'apps' });
      } catch (error) {
        console.error("Error when uploading file:", error);
        this.error = "Failed to upload file. Please try again.";
      } finally {
        this.isUploading = false;
      }
    }
  },
  mounted() {
    // Add event listeners for drag and drop
    const uploadArea = document.querySelector('.upload-area');
    
    uploadArea.addEventListener('dragenter', () => {
      this.isDragging = true;
    });
    
    uploadArea.addEventListener('dragleave', () => {
      this.isDragging = false;
    });
    
    // Handle click on the upload area
    uploadArea.addEventListener('click', this.openFileDialog);
  }
};
</script>

<style scoped>
.upload-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 80vh;
  padding: 20px;
}

.upload-card {
  background-color: white;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 32px;
  width: 100%;
  max-width: 600px;
}

.upload-header {
  text-align: center;
  margin-bottom: 28px;
}

.upload-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: #1a202c;
}

.upload-subtitle {
  font-size: 16px;
  color: #6b7280;
  margin: 0;
}

.upload-area {
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 40px 20px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
  margin-bottom: 20px;
}

.upload-area:hover {
  border-color: #4f46e5;
  background-color: #f9fafb;
}

.drag-over {
  border-color: #4f46e5;
  background-color: #eff6ff;
}

.upload-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.upload-instructions {
  font-size: 16px;
  color: #4b5563;
  margin-bottom: 8px;
}

.highlight {
  color: #4f46e5;
  font-weight: 600;
}

.file-types {
  font-size: 14px;
  color: #9ca3af;
  margin: 0;
}

.file-input {
  opacity: 0;
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.selected-file {
  display: flex;
  align-items: center;
  padding: 16px;
  border-radius: 8px;
  background-color: #f3f4f6;
  margin-bottom: 20px;
}

.file-icon {
  margin-right: 12px;
  font-size: 24px;
}

.file-details {
  flex: 1;
}

.file-name {
  font-weight: 500;
  font-size: 14px;
  margin-bottom: 4px;
  word-break: break-all;
}

.file-size {
  font-size: 12px;
  color: #6b7280;
}

.remove-button {
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  font-size: 16px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.remove-button:hover {
  color: #dc2626;
  background-color: #fee2e2;
}

.upload-button {
  width: 100%;
  padding: 12px 24px;
  background-color: #4f46e5;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s;
  display: flex;
  justify-content: center;
  align-items: center;
}

.upload-button:hover:not(:disabled) {
  background-color: #4338ca;
}

.upload-button:disabled {
  background-color: #9ca3af;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 1s ease-in-out infinite;
  margin-right: 8px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-container {
  display: flex;
  align-items: center;
  margin-top: 16px;
  padding: 12px 16px;
  background-color: #fee2e2;
  border-radius: 8px;
  color: #dc2626;
}

.error-icon {
  margin-right: 12px;
  font-weight: bold;
  background-color: #fecaca;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.error-message {
  font-size: 14px;
}

@media (max-width: 640px) {
  .upload-card {
    padding: 24px;
  }
  
  .upload-area {
    padding: 30px 16px;
  }
  
  .upload-title {
    font-size: 24px;
  }
}
</style>