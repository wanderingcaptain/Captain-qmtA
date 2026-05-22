<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import LogConsole from '../components/LogConsole.vue'

const apiBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const systemStatus = ref({})
const marketStatus = ref({ advancing: 0, declining: 0, flat: 0 })
const portfolioSummary = ref({ total_assets: 0, cash: 0, consecutive_loss_days: 0 })

let pollInterval = null

const fetchStatus = async () => {
  try {
    const [sysRes, mktRes, portRes] = await Promise.all([
      axios.get(`${apiBase}/system/status`),
      axios.get(`${apiBase}/market/sentiment`),
      axios.get(`${apiBase}/portfolio/summary`)
    ])
    systemStatus.value = sysRes.data
    if (mktRes.data.status === 'success') marketStatus.value = mktRes.data.data
    if (portRes.data.status === 'success') portfolioSummary.value = portRes.data.data
  } catch (err) {
    console.error('Error fetching status', err)
  }
}

const toggleIntraday = async () => {
  try {
    if (systemStatus.value.intraday_running) {
      await axios.post(`${apiBase}/system/intraday/stop`)
    } else {
      await axios.post(`${apiBase}/system/intraday/start`)
    }
    await fetchStatus()
  } catch (err) {
    alert('Failed to toggle intraday engine')
  }
}

const startScreening = async () => {
  try {
    await axios.post(`${apiBase}/system/screening/start`)
    alert('Screening started in background')
    await fetchStatus()
  } catch (err) {
    alert('Failed to start screening')
  }
}

onMounted(() => {
  fetchStatus()
  pollInterval = setInterval(fetchStatus, 3000)
})

onUnmounted(() => {
  clearInterval(pollInterval)
})

const formatCurrency = (val) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(val)
</script>

<template>
  <div class="dashboard">
    <h2>System Dashboard</h2>
    
    <div class="grid-cards">
      <!-- Engine Status -->
      <div class="glass-panel card">
        <h3>Engine Control</h3>
        <div class="status-item">
          <span>Intraday Monitor</span>
          <span class="badge" :class="systemStatus.intraday_running ? 'green' : 'red'">
            {{ systemStatus.intraday_running ? 'RUNNING' : 'STOPPED' }}
          </span>
        </div>
        <div class="status-item">
          <span>Nightly Screener</span>
          <span class="badge" :class="systemStatus.screening_running ? 'green' : ''">
            {{ systemStatus.screening_running ? 'RUNNING' : 'IDLE' }}
          </span>
        </div>
        
        <div class="actions">
          <button class="btn" :class="systemStatus.intraday_running ? 'danger' : 'primary'" @click="toggleIntraday">
            {{ systemStatus.intraday_running ? 'Stop Intraday' : 'Start Intraday' }}
          </button>
          <button class="btn" :disabled="systemStatus.screening_running" @click="startScreening">
            Run Nightly Screener
          </button>
        </div>
      </div>

      <!-- Market Sentiment -->
      <div class="glass-panel card" :class="{ 'danger-glow': marketStatus.declining >= 4000 }">
        <h3>Market Sentiment</h3>
        <div class="sentiment-stats">
          <div class="stat-box text-red">
            <span class="label">Advancing</span>
            <span class="value">{{ marketStatus.advancing }}</span>
          </div>
          <div class="stat-box text-green">
            <span class="label">Declining</span>
            <span class="value">{{ marketStatus.declining }}</span>
          </div>
          <div class="stat-box text-muted">
            <span class="label">Flat</span>
            <span class="value">{{ marketStatus.flat }}</span>
          </div>
        </div>
        <div class="sentiment-bar">
          <div class="adv" :style="{ width: `${marketStatus.advancing / 5500 * 100}%` }"></div>
          <div class="dec" :style="{ width: `${marketStatus.declining / 5500 * 100}%` }"></div>
        </div>
      </div>

      <!-- Account Summary -->
      <div class="glass-panel card">
        <h3>Account Summary</h3>
        <div class="account-stats">
          <div class="stat-row">
            <span class="label">Total Assets</span>
            <span class="value highlight">{{ formatCurrency(portfolioSummary.total_assets) }}</span>
          </div>
          <div class="stat-row">
            <span class="label">Available Cash</span>
            <span class="value">{{ formatCurrency(portfolioSummary.cash) }}</span>
          </div>
          <div class="stat-row">
            <span class="label">Loss Days</span>
            <span class="value" :class="{ 'text-red': portfolioSummary.consecutive_loss_days > 0 }">
              {{ portfolioSummary.consecutive_loss_days }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Terminal -->
    <div class="terminal-section mt-4">
      <LogConsole />
    </div>
  </div>
</template>

<style scoped>
.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.card {
  display: flex;
  flex-direction: column;
}

.card h3 {
  margin-bottom: 16px;
  color: var(--text-secondary);
  font-size: 1rem;
}

.status-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-weight: 500;
}

.actions {
  margin-top: auto;
  padding-top: 16px;
  display: flex;
  gap: 10px;
}

.sentiment-stats {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}

.stat-box {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-box .label {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-box .value {
  font-size: 1.8rem;
  font-weight: 700;
}

.sentiment-bar {
  height: 8px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  display: flex;
  overflow: hidden;
}

.sentiment-bar .adv { background: var(--accent-red); } /* In China, red is up */
.sentiment-bar .dec { background: var(--accent-green); } /* In China, green is down */

.account-stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 1.1rem;
}

.stat-row .label { color: var(--text-secondary); }
.stat-row .value.highlight {
  color: var(--accent-cyan);
  font-size: 1.5rem;
  font-weight: 700;
}

.danger-glow {
  animation: pulseGlow 2s infinite;
}

.mt-4 {
  margin-top: 24px;
}
</style>
