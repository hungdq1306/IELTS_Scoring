let runtimePromise, clerkPromise;
export function runtimeConfig() {
  if (!runtimePromise) runtimePromise=fetch('/api/auth/config',{cache:'no-store'}).then(async r=>{
    if(r.status===404)return {mode:'demo'};
    if(!r.ok)throw new Error('Backend configuration is unavailable.');
    return r.json();
  });
  return runtimePromise;
}
export async function clerkClient(){
  const config=await runtimeConfig();
  if(config.mode!=='clerk')return null;
  if(!config.publishable_key||!config.issuer)throw new Error('The administrator must configure Clerk first.');
  if(!clerkPromise)clerkPromise=(async()=>{
    const load=(url,publishableKey)=>new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.async=true;script.crossOrigin='anonymous';
      if(publishableKey)script.dataset.clerkPublishableKey=publishableKey;
      script.src=config.issuer.replace(/\/$/,'')+url;
      script.onload=resolve;script.onerror=()=>reject(new Error('The sign-in service could not be loaded.'));
      document.head.appendChild(script);
    });
    await load('/npm/@clerk/ui@1/dist/ui.browser.js');
    await load('/npm/@clerk/clerk-js@6/dist/clerk.browser.js',config.publishable_key);
    await window.Clerk.load({ui:{ClerkUI:window.__internal_ClerkUICtor}});
    return window.Clerk;
  })();
  return clerkPromise;
}
export async function sessionToken(){const clerk=await clerkClient();return clerk?.session?clerk.session.getToken():null;}
export async function openSignIn(){const clerk=await clerkClient();if(clerk)clerk.openSignIn();}
