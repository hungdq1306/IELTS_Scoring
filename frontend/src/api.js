import {runtimeConfig} from './pilot-auth';
import {pilotApi} from './pilot-api';
export async function api(path, options = {}) {
  const config=await runtimeConfig();
  return config.mode==='clerk'?pilotApi(path,options):legacyApi(path,options);
}
async function legacyApi(path, options = {}) {
  let response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("The grading backend is unreachable. Start FastAPI on port 8000.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok || body === null) {
    const detail = body?.detail;
    const message = Array.isArray(detail) ? detail.map(item => item.msg).join(" ") :
      detail?.message || (typeof detail === "string" ? detail : "The grading backend returned an unexpected response.");
    throw new Error(message);
  }
  return body;
}
