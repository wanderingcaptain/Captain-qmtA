<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const logs = ref([])
const terminalRef = ref(null)
let ws = null

const connectWebSocket = () => {
  // Use relative URL to support deployment
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host || 'localhost:8000'
  const wsUrl = `${protocol}//${host}/api/system/ws/logs`
  
  ws = new WebSocket(wsUrl)
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    logs.value.push(data)
    if (logs.value.length > 200) {
      logs.value.shift()
    }
    
    // Auto-scroll to bottom
    nextTick(() => {
      if (terminalRef.value) {
        terminalRef.value.scrollTop = terminalRef.value.scrollHeight
      }
    })
  }
  
  ws.onclose = () => {
    setTimeout(connectWebSocket, 3000) // Reconnect on close
  }
}

onMounted(() => {
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) ws.close()
})

const getLogColor = (level) => {
  switch (level) {
    case 'INFO': return 'var(--text-primary)'
    case 'WARNING': return '#e3b341'
    case 'ERROR': return 'var(--accent-red)'
    case 'CRITICAL': return '#ff0000'
    default: return 'var(--text-secondary)'
  }
}
</script>

<template>
  <div class="log-console glass-panel">
    <div class="console-header">
      <h3>Terminal Output</h3>
      <div class="status-indicator" :class="{ connected: ws && ws.readyState === 1 }"></div>
    </div>
    <div class="terminal-body" ref="terminalRef">
      <div v-for="(log, idx) in logs" :key="idx" class="log-line">
        <span class="log-time">[{{ log.timestamp }}]</span>
        <span class="log-level" :style="{ color: getLogColor(log.level) }">[{{ log.level }}]</span>
        <span class="log-name">[{{ log.name }}]</span>
        <span class="log-msg" :style="{ color: getLogColor(log.level) }">{{ log.message }}</span>
      </div>
      <div v-if="logs.length === 0" class="text-muted">Waiting for logs...</div>
    </div>
  </div>
</template>

<style scoped>
.log-console {
  display: flex;
  flex-direction: column;
  height: 300px;
  padding: 16px;
  background: rgba(10, 14, 20, 0.8); /* Darker for terminal */
}

.console-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 8px;
  margin-bottom: 8px;
}

.console-header h3 {
  margin: 0;
  font-size: 0.9rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent-red);
}

.status-indicator.connected {
  background: var(--accent-green);
  box-shadow: 0 0 8px rgba(63, 185, 80, 0.6);
}

.terminal-body {
  flex: 1;
  overflow-y: auto;
  font-family: 'Fira Code', 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  line-height: 1.5;
}

.log-line {
  margin-bottom: 4px;
  word-break: break-all;
}

.log-time, .log-name {
  color: var(--text-secondary);
  margin-right: 8px;
}

.log-level {
  font-weight: 600;
  margin-right: 8px;
}
</style>
