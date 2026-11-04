import Vue from 'vue'
import './compat/composition'
import 'element-ui/lib/theme-chalk/index.css'
import { planningStore } from './store'
import { router } from './router'
import App from './App.vue'
import { installPlanningUi } from './install'
import './styles/tokens.css'
import './style.css'
import './styles/system.css'

installPlanningUi()
Vue.config.productionTip = false
new Vue({ router, store: planningStore, render: h => h(App) }).$mount('#app')

