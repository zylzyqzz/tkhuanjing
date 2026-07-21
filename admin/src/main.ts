import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import './extra.css'
import {router} from './router'
import {cssVariables} from './design/tokens'
document.documentElement.style.cssText+=`;${cssVariables}`
createApp(App).use(router).mount('#app')
