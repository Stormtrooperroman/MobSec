<template>
  <header :class="{ 'nav-hidden': isHidden }" ref="header">
    <nav class="nav-container">
      <div class="nav-content">
        <div class="logo-section">
          <div class="logo-container">
            <i class="fas fa-bars menu-icon"></i>
            <span class="app-title">Mobile Scanner</span>
          </div>
        </div>
        <div class="navigation-buttons">
          <router-link 
            v-for="route in routes" 
            :key="route.path"
            :to="route.path"
            custom
            v-slot="{ isActive, navigate }"
          >
            <button
              @click="navigate"
              :class="['nav-button', isActive && route.path === $route.path ? 'active' : '']"
            >
              {{ route.name }}
            </button>
          </router-link>
        </div>
      </div>
    </nav>
  </header>
</template>

<script>
export default {
  name: 'NavigationBar',
  data() {
    return {
      routes: [
        { path: '/', name: 'Upload App', exact: true },
        { path: '/apps', name: 'Stored Apps' },
        { path: '/modules', name: 'Modules' },
        { path: '/chains', name: 'Chains' },
        { path: '/settings', name: 'Settings' }
      ],
      lastScrollPosition: 0,
      isHidden: false,
      scrollThreshold: 60 // minimum scroll before hiding
    }
  },
  mounted() {
    window.addEventListener('scroll', this.onScroll)
  },
  beforeUnmount() {
    window.removeEventListener('scroll', this.onScroll)
  },
  methods: {
    onScroll() {
      const currentScrollPosition = window.scrollY
      
      // Don't do anything if not enough scroll
      if (Math.abs(currentScrollPosition - this.lastScrollPosition) < this.scrollThreshold) {
        return
      }

      this.isHidden = currentScrollPosition > this.lastScrollPosition 
                      && currentScrollPosition > this.$refs.header.offsetHeight
      
      this.lastScrollPosition = currentScrollPosition
    }
  }
}
</script>

<style>
.app-container {
  min-height: 100vh;
  background-color: #f9fafb;
  padding-top: 64px; /* Height of the navbar */
}

header {
  background-color: white;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  transition: transform 0.3s ease;
}

header.nav-hidden {
  transform: translateY(-100%);
}

.nav-container {
  margin: 0 auto;
  padding: 0 16px;
}

@media (min-width: 640px) {
  .nav-container {
    padding: 0 24px;
  }
}

@media (min-width: 1024px) {
  .nav-container {
    padding: 0 32px;
  }
}

.nav-content {
  height: 64px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo-section {
  display: flex;
}

.logo-container {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.menu-icon {
  height: 24px;
  width: 24px;
}

.app-title {
  margin-left: 8px;
  font-size: 20px;
  font-weight: 600;
}

.navigation-buttons {
  display: flex;
  gap: 16px;
}

.nav-button {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
  background: none;
  border: none;
  cursor: pointer;
}

.nav-button:hover:not(.active) {
  background-color: #f3f4f6;
}

.nav-button.active {
  background-color: #111827;
  color: white;
}

.main-content {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 16px;
}

@media (min-width: 640px) {
  .main-content {
    padding: 24px;
  }
}

@media (min-width: 1024px) {
  .main-content {
    padding: 24px 32px;
  }
}
</style>