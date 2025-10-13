<template>
  <div v-if="isOpen" class="modal-overlay">
    <div class="modal-container">
      <div class="modal-header">
        <h3>{{ editChain ? 'Edit Chain' : 'Create New Chain' }}</h3>
        <button @click="close" class="close-button">&times;</button>
      </div>

      <div class="modal-body">
        <form @submit.prevent="handleSubmit">
          <div class="form-group">
            <label for="chainName">Chain Name</label>
            <input
              id="chainName"
              v-model="formData.name"
              type="text"
              required
              :disabled="!!editChain"
              class="form-input"
            />
          </div>

          <div class="form-group">
            <label for="chainDescription">Description</label>
            <textarea id="chainDescription" v-model="formData.description" class="form-input" rows="3"></textarea>
          </div>

          <div class="form-group">
            <label>Modules</label>
            <draggable
              v-model="formData.modules"
              @end="updateModuleOrders"
              item-key="name"
              tag="div"
              class="modules-list"
              handle=".drag-handle"
            >
              <template #item="{ element, index }">
                <div class="module-item">
                  <span class="drag-handle">⋮⋮</span>
                  <select v-model="element.name" class="form-input" required>
                    <option value="">Select Module</option>
                    <option
                      v-for="availableModule in availableModules"
                      :key="availableModule.name"
                      :value="availableModule.name"
                    >
                      {{ availableModule.name }}
                    </option>
                  </select>
                  <span class="order-display">{{ element.order }}</span>
                  <button type="button" @click="removeModule(index)" class="remove-button">Remove</button>
                </div>
              </template>
            </draggable>
            <button type="button" @click="addModule" class="add-module-button">Add Module</button>
          </div>

          <div class="modal-footer">
            <button type="button" @click="close" class="cancel-button">Cancel</button>
            <button type="submit" class="submit-button">
              {{ editChain ? 'Update Chain' : 'Create Chain' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import draggable from 'vuedraggable';

export default {
  name: 'CreateChainModal',
  components: {
    draggable,
  },
  props: {
    isOpen: {
      type: Boolean,
      required: true,
    },
    editChain: {
      type: Object,
      default: null,
    },
  },
  watch: {
    editChain: {
      handler(newVal) {
        if (newVal) {
          this.formData = {
            name: newVal.name,
            description: newVal.description,
            modules: newVal.modules.map(moduleData => ({
              name: moduleData.module.name,
              order: moduleData.order,
              parameters: moduleData.parameters || {},
            })),
          };
        } else {
          this.formData = {
            name: '',
            description: '',
            modules: [],
          };
        }
      },
      immediate: true,
    },
  },
  data() {
    return {
      formData: {
        name: '',
        description: '',
        modules: [],
      },
      availableModules: [],
    };
  },
  methods: {
    async fetchModules() {
      try {
        const response = await fetch('/api/v1/modules');
        this.availableModules = await response.json();
      } catch (error) {
        console.error('Error fetching modules:', error);
      }
    },
    addModule() {
      this.formData.modules.push({
        name: '',
        order: this.formData.modules.length + 1,
        parameters: {},
      });
    },
    updateModuleOrders() {
      this.formData.modules.forEach((module, index) => {
        module.order = index + 1;
      });
    },
    removeModule(index) {
      this.formData.modules.splice(index, 1);
      this.updateModuleOrders();
    },
    async handleSubmit() {
      try {
        const url = this.editChain ? `/api/v1/chains/${this.editChain.name}` : '/api/v1/chains';

        const response = await fetch(url, {
          method: this.editChain ? 'PUT' : 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(this.formData),
        });

        if (response.ok) {
          this.$emit(this.editChain ? 'chain-updated' : 'chain-created');
          this.close();
        } else {
          throw new Error(`Failed to ${this.editChain ? 'update' : 'create'} chain`);
        }
      } catch (error) {
        console.error('Error:', error);
      }
    },
    close() {
      this.formData = {
        name: '',
        description: '',
        modules: [],
      };
      this.$emit('close');
    },
  },
  mounted() {
    this.fetchModules();
  },
};
</script>

<style scoped>
.drag-handle {
  cursor: move;
  padding: 0 8px;
  user-select: none;
  opacity: 0.6;
}

.module-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.order-display {
  min-width: 30px;
  text-align: center;
  font-weight: 500;
  color: #4b5563;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-container {
  background-color: white;
  border-radius: 8px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  padding: 16px 26px;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.close-button {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #6b7280;
}

.modal-body {
  padding: 16px 26px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}

.modules-list {
  margin-bottom: 16px;
}

.order-input {
  width: 80px;
}

.remove-button {
  padding: 6px 12px;
  background-color: #fee2e2;
  color: #dc2626;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.add-module-button {
  width: 100%;
  padding: 8px;
  background-color: #f3f4f6;
  border: 1px dashed #d1d5db;
  border-radius: 4px;
  color: #4b5563;
  cursor: pointer;
}

.modal-footer {
  padding: 16px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.cancel-button {
  padding: 8px 16px;
  background-color: white;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  color: #4b5563;
  cursor: pointer;
}

.submit-button {
  padding: 8px 16px;
  background-color: #2563eb;
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
}

.submit-button:hover {
  background-color: #1d4ed8;
}
</style>
