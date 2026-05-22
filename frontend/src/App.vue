<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const currentRouteName = computed(() => route.name)
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar glass-panel">
      <div class="logo">
        <span class="text-cyan">⚡</span> Captain
      </div>
      <nav class="nav-menu">
        <router-link to="/" class="nav-item" :class="{ active: currentRouteName === 'Dashboard' }">Dashboard</router-link>
        <router-link to="/portfolio" class="nav-item" :class="{ active: currentRouteName === 'Portfolio' }">Portfolio</router-link>
        <router-link to="/watchlist" class="nav-item" :class="{ active: currentRouteName === 'Watchlist' }">Watchlist</router-link>
        <router-link to="/settings" class="nav-item" :class="{ active: currentRouteName === 'Settings' }">Settings</router-link>
      </nav>
    </aside>
    
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 240px;
  margin: 16px;
  display: flex;
  flex-direction: column;
  position: fixed;
  height: calc(100vh - 32px);
  z-index: 10;
}

.logo {
  font-size: 1.5rem;
  font-weight: 800;
  padding: 12px 16px;
  margin-bottom: 24px;
  letter-spacing: -1px;
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-item {
  text-decoration: none;
  color: var(--text-secondary);
  padding: 12px 16px;
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.2s;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(43, 222, 195, 0.1);
  color: var(--accent-cyan);
  border-left: 3px solid var(--accent-cyan);
}

.main-content {
  flex: 1;
  margin-left: 280px; /* sidebar width + margins */
  padding: 16px 24px 16px 0;
  max-width: calc(100% - 280px);
}

/* Page transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
