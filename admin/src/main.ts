import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import './extra.css'
import {router} from './router'
createApp(App).use(router).mount('#app')
