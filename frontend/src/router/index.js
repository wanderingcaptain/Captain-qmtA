import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Portfolio from '../views/Portfolio.vue'
import Watchlist from '../views/Watchlist.vue'
import Settings from '../views/Settings.vue'

const routes = [
  { path: '/', component: Dashboard, name: 'Dashboard' },
  { path: '/portfolio', component: Portfolio, name: 'Portfolio' },
  { path: '/watchlist', component: Watchlist, name: 'Watchlist' },
  { path: '/settings', component: Settings, name: 'Settings' }
]

const router = createRouter({
  // Use hash history for easy static file serving from FastAPI
  history: createWebHashHistory(),
  routes
})

export default router
