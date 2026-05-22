<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const apiBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'
const configData = ref({})
const loading = ref(true)

const fetchConfig = async () => {
  try {
    const res = await axios.get(`${apiBase}/config/`)
    if (res.data.status === 'success') {
      configData.value = res.data.data
    }
  } catch (err) {
    console.error('Error fetching config', err)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchConfig()
})

const updateSetting = async (section, key, value) => {
  try {
    // If it looks like a number, parse it
    let parsedValue = value
    if (!isNaN(value) && value.toString().trim() !== '') {
      parsedValue = Number(value)
    } else if (value === 'true' || value === true) {
      parsedValue = true
    } else if (value === 'false' || value === false) {
      parsedValue = false
    }

    await axios.post(`${apiBase}/config/`, {
      section,
      key,
      value: parsedValue
    })
    
    // Show a small success indicator (could use a toast library in a real app)
    const el = document.getElementById(`input-${section}-${key}`)
    if (el) {
      el.classList.add('success-flash')
      setTimeout(() => el.classList.remove('success-flash'), 1000)
    }
  } catch (err) {
    alert(`Failed to update ${key}`)
  }
}
</script>

<template>
  <div class="settings">
    <h2>System Configuration</h2>
    <p class="text-muted mb-4">Changes made here are applied directly to settings.toml and updated in real-time.</p>
    
    <div v-if="loading" class="text-muted">Loading configuration...</div>
    
    <div v-else class="config-sections">
      <div v-for="(keys, section) in configData" :key="section" class="glass-panel section-card">
        <h3>[{{ section }}]</h3>
        
        <div class="config-grid">
          <div v-for="(val, key) in keys" :key="key" class="config-item">
            <label :for="`input-${section}-${key}`">{{ key }}</label>
            <input 
              :id="`input-${section}-${key}`"
              type="text" 
              :value="val" 
              @change="e => updateSetting(section, key, e.target.value)"
              class="glass-input"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mb-4 {
  margin-bottom: 24px;
}

.config-sections {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.section-card h3 {
  color: var(--accent-cyan);
  margin-bottom: 16px;
  font-family: 'Fira Code', monospace;
  font-size: 1.1rem;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-item label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.glass-input {
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--glass-border);
  color: var(--text-primary);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 0.95rem;
  transition: all 0.2s;
}

.glass-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 2px rgba(43, 222, 195, 0.2);
}

.success-flash {
  animation: flashGreen 1s ease;
}

@keyframes flashGreen {
  0% { background: rgba(63, 185, 80, 0.3); }
  100% { background: rgba(0, 0, 0, 0.2); }
}
</style>
