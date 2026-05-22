<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const apiBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'
const watchlist = ref([])
let pollInterval = null

const fetchWatchlist = async () => {
  try {
    const res = await axios.get(`${apiBase}/market/watchlist`)
    if (res.data.status === 'success') {
      watchlist.value = res.data.data
    }
  } catch (err) {
    console.error('Error fetching watchlist', err)
  }
}

onMounted(() => {
  fetchWatchlist()
  // Watchlist doesn't need to be polled as aggressively as portfolio
  pollInterval = setInterval(fetchWatchlist, 10000)
})

onUnmounted(() => {
  clearInterval(pollInterval)
})

const formatCurrency = (val) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(val)
const formatPct = (val) => `${val > 0 ? '+' : ''}${val.toFixed(2)}%`
</script>

<template>
  <div class="watchlist-view">
    <h2>Nightly Watchlist</h2>
    
    <div class="glass-panel">
      <div class="header-actions">
        <p class="text-muted">Currently tracking {{ watchlist.length }} stocks for intraday signals.</p>
      </div>

      <div class="grid-container">
        <div v-for="stock in watchlist" :key="stock.code" class="stock-card glass-panel">
          <div class="stock-header">
            <h4>{{ stock.name }}</h4>
            <span class="code">{{ stock.code }}</span>
          </div>
          <div class="stock-price" :class="stock.pct_chg >= 0 ? 'text-red' : 'text-green'">
            <span class="price">{{ formatCurrency(stock.price) }}</span>
            <span class="pct">{{ formatPct(stock.pct_chg) }}</span>
          </div>
        </div>
      </div>
      
      <div v-if="watchlist.length === 0" class="empty-state">
        <p class="text-muted">No stocks in watchlist. Run the Nightly Screener to populate.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.header-actions {
  margin-bottom: 24px;
}

.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.stock-card {
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  transition: transform 0.2s;
}

.stock-card:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(43, 222, 195, 0.3);
}

.stock-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.stock-header h4 {
  margin: 0;
  font-size: 1.1rem;
}

.code {
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.2);
  padding: 2px 6px;
  border-radius: 4px;
}

.stock-price {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.price {
  font-size: 1.25rem;
  font-weight: 700;
}

.pct {
  font-size: 0.9rem;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 40px;
}
</style>
