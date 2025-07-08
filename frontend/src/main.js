import { createApp } from 'vue';
import App from './App.vue';
import router from './router';

import { library } from '@fortawesome/fontawesome-svg-core';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { faCheckCircle, faTimesCircle, faSpinner, faStop, faPlay, faSync } from '@fortawesome/free-solid-svg-icons';

library.add(faCheckCircle, faTimesCircle, faSpinner, faStop, faPlay, faSync);

const app = createApp(App);
app.use(router);
app.component('font-awesome-icon', FontAwesomeIcon);
app.mount('#app');
