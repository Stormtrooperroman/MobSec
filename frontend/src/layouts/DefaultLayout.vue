<template>
  <div class="app-container">
    <NavigationBar />
    <main class="main-content">
      <router-view></router-view>
    </main>
  </div>
</template>

<script>
import NavigationBar from '@/components/NavigationBar.vue';

export default {
  name: 'DefaultLayout',
  components: {
    NavigationBar,
  },
};
</script>

<style>
.app-container {
  background-color: #f9fafb;
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
