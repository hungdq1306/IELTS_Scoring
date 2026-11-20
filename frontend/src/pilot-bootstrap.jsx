import {createRoot} from 'react-dom/client';
import {PilotAccount} from './components/PilotAccount';
import {runtimeConfig} from './pilot-auth';
runtimeConfig().then(config=>{if(config.mode==='clerk')document.documentElement.dataset.pilotAuth='clerk';}).catch(()=>{});
const accountRoot=document.createElement('div');
accountRoot.id='pilot-account-root';
document.getElementById('root').before(accountRoot);
createRoot(accountRoot).render(<PilotAccount/>);
