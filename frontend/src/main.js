import { createApp } from 'vue';
import App from './App.vue';
import router from './router';

import { library } from '@fortawesome/fontawesome-svg-core';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import { 
  faCheckCircle, 
  faTimesCircle, 
  faSpinner, 
  faStop, 
  faPlay, 
  faSync, 
  faRefresh,
  faCircle,
  faDownload,
  faList,
  faFolderOpen,
  faPlus,
  faEdit,
  faTrash,
  faFolder,
  faBug,
  faLevelUpAlt,
  faFolderPlus,
  faUpload,
  faFile,
  faLink,
  faUser,
  faLock,
  faMobile,
  faChevronUp,
  faChevronDown,
  faExclamationCircle,
} from '@fortawesome/free-solid-svg-icons';

import {
  faAndroid
} from "@fortawesome/free-brands-svg-icons";

library.add(
  faCheckCircle, 
  faTimesCircle, 
  faSpinner, 
  faStop, 
  faPlay, 
  faSync, 
  faRefresh,
  faCircle,
  faDownload,
  faList,
  faFolderOpen,
  faPlus,
  faEdit,
  faTrash,
  faFolder,
  faBug,
  faLevelUpAlt,
  faFolderPlus,
  faUpload,
  faFile,
  faLink,
  faUser,
  faLock,
  faMobile,
  faChevronUp,
  faChevronDown,
  faExclamationCircle,
  faAndroid
);

const app = createApp(App);
app.use(router);
app.component('font-awesome-icon', FontAwesomeIcon);
app.mount('#app');
