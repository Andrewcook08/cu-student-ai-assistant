import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/cu-classes.css'
import './assets/index.css'
import { useAuthStore } from './stores/authStore'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia).use(router)

// Restore JWT auth state from localStorage before mounting
useAuthStore().initFromStorage()

app.mount('#app')
