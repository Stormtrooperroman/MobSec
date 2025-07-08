<template>
  <div class="chains-container">
    <div class="header">
      <h2 class="page-title">Analysis Chains</h2>
      <button @click="openCreateModal" class="create-button">
        <span class="button-icon">+</span>
        Create Chain
      </button>
    </div>

    <div class="chains-grid">
      <div v-for="chain in chains" :key="chain.name" class="chain-card">
        <div class="chain-header">
          <h3 class="chain-title">{{ chain.name }}</h3>
          <div class="modules-count">{{ chain.modules.length }} modules</div>
        </div>

        <p class="chain-description">{{ chain.description }}</p>

        <div class="modules-list">
          <div v-for="module in chain.modules" :key="module.module.name" class="module-item">
            <span class="module-order">#{{ module.order }}</span>
            <span class="module-name">{{ module.module.name }}</span>
          </div>
        </div>

        <div class="button-container">
          <button @click="exportChain(chain)" class="card-button export-button" title="Export chain configuration">
            <span class="button-icon">📤</span>
            Export
          </button>
          <button @click="editChain(chain)" class="card-button edit-button" title="Edit chain configuration">
            <span class="button-icon">✏️</span>
            Edit
          </button>
          <button @click="confirmDelete(chain)" class="card-button delete-button" title="Delete chain">
            <span class="button-icon">🗑️</span>
            Delete
          </button>
        </div>
      </div>
    </div>

    <CreateChainModal
      :is-open="isModalOpen"
      :edit-chain="selectedChain"
      @close="closeModal"
      @chain-created="handleChainCreated"
      @chain-updated="handleChainUpdated"
    />

    <div v-if="showDeleteConfirm" class="delete-modal">
      <div class="delete-modal-content">
        <h3>Delete Chain</h3>
        <p>Are you sure you want to delete "{{ chainToDelete?.name }}"?</p>
        <div class="delete-modal-buttons">
          <button @click="deleteChain" class="confirm-delete-button">Delete</button>
          <button @click="cancelDelete" class="cancel-button">Cancel</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import CreateChainModal from './CreateChainModal.vue';

export default {
  name: 'ChainView',
  components: {
    CreateChainModal,
  },
  data() {
    return {
      chains: [],
      isModalOpen: false,
      selectedChain: null,
      showDeleteConfirm: false,
      chainToDelete: null,
    };
  },
  methods: {
    async fetchChains() {
      try {
        const response = await fetch('/api/v1/chains');
        const data = await response.json();
        this.chains = data;
      } catch (error) {
        console.error('Error fetching chains:', error);
      }
    },
    editChain(chain) {
      this.selectedChain = JSON.parse(JSON.stringify(chain));
      this.isModalOpen = true;
    },
    openCreateModal() {
      this.selectedChain = null;
      this.isModalOpen = true;
    },
    closeModal() {
      this.isModalOpen = false;
      this.selectedChain = null;
    },
    handleChainCreated() {
      this.fetchChains();
      this.closeModal();
    },
    handleChainUpdated() {
      this.fetchChains();
      this.closeModal();
    },
    confirmDelete(chain) {
      this.chainToDelete = chain;
      this.showDeleteConfirm = true;
    },
    cancelDelete() {
      this.showDeleteConfirm = false;
      this.chainToDelete = null;
    },
    async deleteChain() {
      try {
        const response = await fetch(`/api/v1/chains/${this.chainToDelete.name}`, {
          method: 'DELETE',
        });

        if (response.ok) {
          await this.fetchChains();
          this.showDeleteConfirm = false;
          this.chainToDelete = null;
        } else {
          console.error('Error deleting chain');
        }
      } catch (error) {
        console.error('Error deleting chain:', error);
      }
    },
    async exportChain(chain) {
      try {
        const response = await fetch(`/api/v1/chains/${chain.name}/export`);
        if (!response.ok) throw new Error('Export failed');

        const blob = await response.blob();

        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${chain.name}.yaml`;

        document.body.appendChild(a);
        a.click();

        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } catch (error) {
        console.error('Error exporting chain:', error);
      }
    },
  },
  mounted() {
    this.fetchChains();
  },
};
</script>

<style scoped>
.chains-container {
  padding: 24px;
  max-width: 1280px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: #111827;
  margin: 0;
}

.create-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
}

.create-button:hover {
  background-color: #1d4ed8;
}

.button-icon {
  font-size: 16px;
}

.chains-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 24px;
}

.chain-card {
  background-color: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 20px;
  transition: box-shadow 0.2s;
}

.chain-card:hover {
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.chain-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.chain-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #111827;
}

.modules-count {
  font-size: 14px;
  color: #6b7280;
  padding: 4px 8px;
  background-color: #f3f4f6;
  border-radius: 12px;
}

.chain-description {
  color: #4b5563;
  margin: 0 0 16px;
  font-size: 14px;
  line-height: 1.5;
}

.modules-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
  padding: 12px;
  background-color: #f9fafb;
  border-radius: 6px;
}

.module-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background-color: white;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  font-size: 14px;
}

.module-order {
  color: #6b7280;
  font-size: 12px;
  font-weight: 500;
}

.module-name {
  color: #374151;
  font-weight: 500;
}

.button-container {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.card-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.export-button {
  color: #047857;
  background-color: #ecfdf5;
}

.export-button:hover {
  background-color: #d1fae5;
}

.edit-button {
  color: #4b5563;
  background-color: #f3f4f6;
}

.edit-button:hover {
  background-color: #e5e7eb;
}

.delete-button {
  color: #dc2626;
  background-color: #fee2e2;
}

.delete-button:hover {
  background-color: #fecaca;
}

.delete-modal {
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

.delete-modal-content {
  background-color: white;
  padding: 24px;
  border-radius: 8px;
  max-width: 400px;
  width: 90%;
}

.delete-modal-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 24px;
}

.confirm-delete-button {
  padding: 8px 16px;
  background-color: #dc2626;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.confirm-delete-button:hover {
  background-color: #b91c1c;
}

.cancel-button {
  padding: 8px 16px;
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  color: #4b5563;
  font-size: 14px;
  cursor: pointer;
}

.cancel-button:hover {
  background-color: #e5e7eb;
}

@media (max-width: 768px) {
  .chains-container {
    padding: 16px;
  }

  .chains-grid {
    grid-template-columns: 1fr;
  }

  .button-container {
    flex-direction: column;
  }

  .card-button {
    width: 100%;
    justify-content: center;
  }
}
</style>
