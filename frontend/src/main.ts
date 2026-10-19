import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { router } from './router'
import App from './App.vue'
import { installManualConfirmEnhancer } from './manualConfirmEnhancer'
import { installTopicDetailClickFix } from './topicDetailClickFix'
import './styles/tokens.css'
import './style.css'
import './styles/system.css'
import './styles/topic-detail-click-fix.css'

createApp(App).use(createPinia()).use(router).mount('#app')
installManualConfirmEnhancer()
installTopicDetailClickFix()

