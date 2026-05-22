<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const apiBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'
const positions = ref([])
let pollInterval = null

const fetchPositions = async () => {
  try {
    const res = await axios.get(`${apiBase}/portfolio/positions`)
    if (res.data.status === 'success') {
      positions.value = res.data.data
    }
  } catch (err) {
    console.error('Error fetching positions', err)
  }
}

onMounted(() => {
  fetchPositions()
  pollInterval = setInterval(fetchPositions, 3000)
})

onUnmounted(() => {
  clearInterval(pollInterval)
})

const formatCurrency = (val) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(val)
const formatPct = (val) => `${val > 0 ? '+' : ''}${val.toFixed(2)}%`
</script>

<template>
  <div class="portfolio">
    <h2>Current Positions</h2>
    
    <div class="glass-panel">
      <table class="glass-table">
        <thead>
          <tr>
            <th>Code</th>
            <th>Reason</th>
            <th>Qty</th>
            <th>Entry Price</th>
            <th>Current Price</th>
            <th>Unrealized PnL</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="pos in positions" :key="pos.code">
            <td>
              <strong>{{ pos.code }}</strong>
            </td>
            <td><span class="badge">{{ pos.buy_reason }}</span></td>
            <td>{{ pos.remaining_quantity }} / {{ pos.quantity }}</td>
            <td>{{ formatCurrency(pos.entry_price) }}</td>
            <td>{{ formatCurrency(pos.current_price) }}</td>
            <td :class="pos.unrealized_pnl >= 0 ? 'text-red' : 'text-green'">
              <strong>{{ formatCurrency(pos.unrealized_pnl) }}</strong>
              <small> ({{ formatPct(pos.unrealized_pct) }})</small>
            </td>
            <td>
              <div class="status-flags">
                <span class="dot" :class="{ active: pos.take_profit_1_done }" title="TP1 Done"></span>
                <span class="dot" :class="{ active: pos.take_profit_2_done }" title="TP2 Done"></span>
                <span v-if="pos.resistance_counter > 0" class="badge red">R: {{ pos.resistance_counter }}</span>
              </div>
            </td>
          </tr>
          <tr v-if="positions.length === 0">
            <td colspan="7" style="text-align: center; padding: 32px;" class="text-muted">
              No open positions.
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.portfolio {
  width: 100%;
}

h2 {
  margin-bottom: 24px;
}

.status-flags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
}

.dot.active {
  background: var(--accent-cyan);
  box-shadow: 0 0 8px rgba(43, 222, 195, 0.6);
}

.text-red { color: var(--accent-red); }
.text-green { color: var(--accent-green); }
</style>
